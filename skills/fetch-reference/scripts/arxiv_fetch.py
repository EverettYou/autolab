"""Download and validate paper PDFs; produce the paper fields of provenance.json.

Library used by fetch_reference.py. Importing it needs only the standard library; pypdf is
loaded when a PDF is validated.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from arxiv_http import (
    RATE_LIMIT_SEC,
    fetch_metadata_abs,
    fetch_metadata_api,
    http_get,
    is_rate_limited,
    log_fallback,
)

TITLE_THRESHOLD = 0.55


class FetchError(RuntimeError):
    """Download or network failure (exit code 1)."""


class PdfValidationError(RuntimeError):
    """The file is not a usable PDF (exit code 2)."""


class TitleMismatchError(RuntimeError):
    """The first page does not match the metadata title (exit code 3)."""


def _require_pypdf():
    try:
        from pypdf import PdfReader
    except ImportError:
        print(
            "error: pypdf is not installed. Install with: "
            ".venv/bin/python -m pip install -r skills/fetch-reference/requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return PdfReader


def normalize_arxiv_id(arxiv_id: str) -> str:
    """Bare arXiv id without URL prefix or version suffix: 2408.07038."""
    raw = arxiv_id.strip()
    raw = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", raw)
    raw = re.sub(r"^arxiv:", "", raw, flags=re.IGNORECASE)
    raw = raw.removesuffix(".pdf")
    return re.sub(r"v\d+$", "", raw)


def arxiv_pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{normalize_arxiv_id(arxiv_id)}.pdf"


def resolve_metadata_pdf_only(arxiv_id: str) -> dict[str, Any]:
    aid = normalize_arxiv_id(arxiv_id)
    return {
        "arxiv_id": aid,
        "title": "",
        "authors": [],
        "abstract": "",
        "categories": [],
        "published": None,
        "updated": None,
        "pdf_url": arxiv_pdf_url(aid),
        "entry_url": f"https://arxiv.org/abs/{aid}",
        "metadata_source": "pdf_only",
    }


def resolve_metadata(arxiv_id: str) -> dict[str, Any]:
    """Tiered metadata: export API, then the abs HTML page, then a PDF-only stub."""
    aid = normalize_arxiv_id(arxiv_id)
    try:
        return fetch_metadata_api(aid)
    except Exception as exc:
        log_fallback("export API", "abs HTML", str(exc))
        try:
            return fetch_metadata_abs(aid)
        except Exception as exc2:
            log_fallback("abs HTML", "PDF-only", str(exc2))
            return resolve_metadata_pdf_only(aid)


def download(url: str, dest: Path, timeout: int = 120) -> None:
    """Download url to dest, retrying once after the rate-limit pause. Requires a %PDF body."""
    try:
        data = http_get(url, timeout=timeout)
    except Exception as exc:
        if not is_rate_limited(exc):
            raise FetchError(f"PDF download failed: {exc}") from exc
        time.sleep(RATE_LIMIT_SEC)
        try:
            data = http_get(url, timeout=timeout)
        except Exception as exc2:
            raise FetchError(f"PDF download failed: {exc2}") from exc2
    if not data.startswith(b"%PDF"):
        preview = data[:200].decode("utf-8", errors="replace")
        raise PdfValidationError(f"downloaded body is not a PDF (starts with: {preview!r})")
    dest.write_bytes(data)


def validate_pdf(pdf_path: Path) -> tuple[int, str]:
    """Return (pages, first-page text); raise PdfValidationError for unusable files."""
    PdfReader = _require_pypdf()
    raw = pdf_path.read_bytes()
    if not raw.startswith(b"%PDF"):
        raise PdfValidationError("missing %PDF magic bytes")
    if b"%%EOF" not in raw[-4096:]:
        raise PdfValidationError("missing %%EOF trailer (truncated download?)")
    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            raise PdfValidationError("PDF is encrypted")
        pages = len(reader.pages)
    except PdfValidationError:
        raise
    except Exception as exc:
        raise PdfValidationError(f"PDF does not parse: {exc}") from exc
    if pages < 1:
        raise PdfValidationError("PDF has zero pages")
    try:
        first_text = (reader.pages[0].extract_text() or "").strip()
    except Exception:
        first_text = ""
    return pages, first_text


def normalize_title(title: str) -> str:
    """Fold a title for comparison between arXiv metadata (ASCII) and PDF text (typeset).

    LaTeX typesets ``ffi``/``fi``/``fl`` as single ligature glyphs (U+FB03/FB01/FB02). Those are
    ``\\w`` characters, so they survive the punctuation filter intact and never match the plain-ASCII
    metadata title; on arXiv:2510.05795 ("Efficient Post-Selection...") that alone drove the score
    to 0.19 and refused a good PDF.

    NFKD decomposes ligatures (and superscripts, en-dashes, etc.), but it also splits accented letters
    into base + combining mark, and a combining mark is not ``\\w``, so it would become a space and
    break the word (``schrödinger`` -> ``schro dinger``). Dropping combining marks after the
    decomposition gives the intended fold (``schrodinger``, ``naive``).
    """
    t = unicodedata.normalize("NFKD", title)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def title_similarity(expected: str, observed: str) -> float:
    a = normalize_title(expected)
    b = normalize_title(observed)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def title_match_score(api_title: str, first_page_text: str) -> float:
    if not first_page_text:
        return 0.0
    norm = normalize_title(api_title)
    window = normalize_title(first_page_text[:2000])
    if norm and norm in window:
        return 1.0
    words = first_page_text.split()
    for size in (20, 15, 10):
        for i in range(0, min(len(words), 80), max(1, size // 2)):
            chunk = " ".join(words[i : i + size])
            score = title_similarity(api_title, chunk)
            if score >= 0.85:
                return score
    return title_similarity(api_title, first_page_text[:500])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def paper_fields(
    *,
    meta: dict[str, Any],
    pdf_path: Path,
    pages: int,
    first_page_text: str,
    allow_title_mismatch: bool = False,
    title_threshold: float = TITLE_THRESHOLD,
) -> dict[str, Any]:
    """Paper fields of provenance.json for a validated PDF and its metadata."""
    source = meta.get("metadata_source", "arxiv_api")
    title = meta.get("title") or ""
    if source == "pdf_only" and not title and first_page_text:
        title = first_page_text.split("\n")[0].strip()[:300]

    fetch_status = "pdf:ok"
    score: float | None = title_match_score(title, first_page_text) if title else None
    if source == "pdf_only":
        fetch_status = "pdf:ok:pdf_only"
        score = 1.0 if title else None
    elif source in ("local", "url"):
        score = None
    elif title and score is not None and score < title_threshold:
        if not allow_title_mismatch:
            raise TitleMismatchError(f"title mismatch (score={score:.2f}): metadata title={title!r}")
        fetch_status = "pdf:ok:title_mismatch"

    arxiv_id = meta.get("arxiv_id")
    return {
        "title": title,
        "arxiv_id": normalize_arxiv_id(arxiv_id) if arxiv_id else None,
        "authors": meta.get("authors") or [],
        "abstract": meta.get("abstract") or "",
        "categories": meta.get("categories") or [],
        "published": meta.get("published"),
        "upstream_updated": meta.get("updated"),
        "entry_url": meta.get("entry_url"),
        "pdf_url": meta.get("pdf_url"),
        "pdf": pdf_path.name,
        "pdf_sha256": sha256_file(pdf_path),
        "pages": pages,
        "fetched_at": utc_now(),
        "fetch_status": fetch_status,
        "metadata_source": source,
        "title_match_score": round(score, 3) if score is not None else None,
    }


def fetch_arxiv(
    arxiv_id: str,
    dest: Path,
    *,
    allow_title_mismatch: bool = False,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Download an arXiv PDF to dest (atomically) and return its provenance fields.

    With expected_sha256, the download is installed only if it matches (used to restore a
    gitignored local copy without silently accepting a different upstream version).
    """
    meta = resolve_metadata(arxiv_id)
    return _fetch_to(meta["pdf_url"], meta, dest, allow_title_mismatch, expected_sha256)


def fetch_url(
    url: str,
    dest: Path,
    *,
    title: str,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Download a non-arXiv PDF URL to dest (atomically) and return its provenance fields."""
    meta = {"title": title, "pdf_url": url, "entry_url": None, "metadata_source": "url"}
    return _fetch_to(url, meta, dest, True, expected_sha256)


def _fetch_to(
    url: str,
    meta: dict[str, Any],
    dest: Path,
    allow_title_mismatch: bool,
    expected_sha256: str | None,
) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        download(url, tmp)
        pages, first_text = validate_pdf(tmp)
        fields = paper_fields(
            meta=meta, pdf_path=tmp, pages=pages, first_page_text=first_text,
            allow_title_mismatch=allow_title_mismatch,
        )
        if expected_sha256 and fields["pdf_sha256"] != expected_sha256:
            raise PdfValidationError(
                f"downloaded sha256 {fields['pdf_sha256'][:12]} differs from recorded "
                f"{expected_sha256[:12]} (upstream changed); not installed"
            )
        fields["pdf"] = dest.name
        os.replace(tmp, dest)
        return fields
    finally:
        tmp.unlink(missing_ok=True)


def ingest_local_pdf(source: Path, dest: Path, *, title: str) -> dict[str, Any]:
    """Copy a local PDF to dest (atomically) after validation and return its provenance fields."""
    if not source.is_file():
        raise FileNotFoundError(f"PDF not found: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        tmp.write_bytes(source.read_bytes())
        pages, first_text = validate_pdf(tmp)
        fields = paper_fields(
            meta={"title": title, "metadata_source": "local"},
            pdf_path=tmp, pages=pages, first_page_text=first_text,
        )
        fields["pdf"] = dest.name
        os.replace(tmp, dest)
        return fields
    finally:
        tmp.unlink(missing_ok=True)


def adopt_local_pdf(pdf: Path) -> dict[str, Any]:
    """Validate a PDF already in place and return checksum fields without touching the file."""
    pages, _ = validate_pdf(pdf)
    return {
        "pdf": pdf.name,
        "pdf_sha256": sha256_file(pdf),
        "pages": pages,
        "fetched_at": utc_now(),
        "fetch_status": "pdf:ok:adopted",
    }


def check_pdf(pdf: Path, expected_sha256: str | None) -> dict[str, Any]:
    """Local status of a recorded PDF: present, valid, checksum match."""
    result: dict[str, Any] = {"exists": pdf.is_file(), "errors": []}
    if not result["exists"]:
        result["errors"].append(f"{pdf.name} missing")
        return result
    try:
        result["pages"], _ = validate_pdf(pdf)
    except PdfValidationError as exc:
        result["errors"].append(f"invalid PDF: {exc}")
    result["sha256"] = sha256_file(pdf)
    if expected_sha256 and result["sha256"] != expected_sha256:
        result["errors"].append("sha256 differs from provenance.json")
    return result
