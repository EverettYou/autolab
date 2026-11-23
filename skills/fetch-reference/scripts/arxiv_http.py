"""Shared arXiv HTTP client with rate limiting (arXiv policy: ~1 req / 3s)."""

from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

USER_AGENT = "lab-fetch-reference/1.0 (research pipeline; contact: research)"
RATE_LIMIT_SEC = 3.0

ATOM_NS = "http://www.w3.org/2005/Atom"
ATOM = f"{{{ATOM_NS}}}"

_last_request_at: float = 0.0


def throttle() -> None:
    """Enforce minimum interval between arXiv requests."""
    global _last_request_at
    now = time.monotonic()
    wait = RATE_LIMIT_SEC - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def is_rate_limited(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in ("429", "503", "timeout", "timed out"))


def http_get(url: str, *, timeout: int = 15) -> bytes:
    throttle()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 429:
                raise RuntimeError(f"HTTP 429 from {url}")
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (429, 503):
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        raise


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_atom_entry(entry: ET.Element) -> dict[str, Any]:
    def _text(tag: str) -> str:
        el = entry.find(f"{ATOM}{tag}")
        if el is None or el.text is None:
            return ""
        return re.sub(r"\s+", " ", el.text).strip()

    authors = []
    for author in entry.findall(f"{ATOM}author"):
        name_el = author.find(f"{ATOM}name")
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    categories = [
        c.attrib["term"]
        for c in entry.findall(f"{ATOM}category")
        if c.attrib.get("term")
    ]

    entry_id = _text("id")
    short_id = entry_id.rstrip("/").split("/abs/")[-1] if entry_id else ""

    pdf_url = f"https://arxiv.org/pdf/{short_id}.pdf"
    for link in entry.findall(f"{ATOM}link"):
        if link.attrib.get("type") == "application/pdf":
            pdf_url = link.attrib.get("href", pdf_url)
            break

    return {
        "arxiv_id": short_id,
        "title": _text("title"),
        "authors": authors,
        "abstract": _text("summary"),
        "categories": categories,
        "published": _text("published") or None,
        "updated": _text("updated") or None,
        "pdf_url": pdf_url,
        "entry_url": f"https://arxiv.org/abs/{short_id}",
        "metadata_source": "arxiv_api",
    }


def fetch_metadata_api(arxiv_id: str, *, timeout: int = 10) -> dict[str, Any]:
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    data = http_get(url, timeout=timeout)
    root = ET.fromstring(data)
    entry = root.find(f"{ATOM}entry")
    if entry is None:
        raise ValueError(f"No arXiv entry found for {arxiv_id}")
    return parse_atom_entry(entry)


def fetch_metadata_abs(arxiv_id: str, *, timeout: int = 15) -> dict[str, Any]:
    url = f"https://arxiv.org/abs/{arxiv_id}"
    html = http_get(url, timeout=timeout).decode("utf-8", errors="replace")

    title = ""
    m = re.search(
        r'<h1 class="title[^"]*">(?:\s*<span class="descriptor">Title:</span>)?\s*(.*?)</h1>',
        html,
        re.S | re.I,
    )
    if m:
        title = strip_html(m.group(1))

    authors: list[str] = []
    m = re.search(r'<div class="authors">(.*?)</div>', html, re.S | re.I)
    if m:
        block = m.group(1)
        for a in re.findall(r'<a[^>]*>([^<]+)</a>', block):
            name = a.strip()
            if name and name not in authors:
                authors.append(name)

    abstract = ""
    m = re.search(
        r'<blockquote class="abstract[^"]*">(?:\s*<span class="descriptor">Abstract:</span>)?\s*(.*?)</blockquote>',
        html,
        re.S | re.I,
    )
    if m:
        abstract = strip_html(m.group(1))

    categories = re.findall(r'class="primary-subject">([^<]+)<', html)
    if not categories:
        categories = re.findall(r"/list/([^/\"']+)", html)
        categories = [c for c in categories if re.match(r"^[a-z-]+(\.[A-Z]{2})?$", c)][:5]

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "categories": categories,
        "published": None,
        "updated": None,
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "entry_url": url,
        "metadata_source": "abs_html",
    }


def search_api(
    query: str,
    *,
    max_results: int = 10,
    timeout: int = 15,
    sort: str = "relevance",
) -> list[dict[str, Any]]:
    """``sort`` is ``"relevance"`` or ``"submittedDate"`` (newest first)."""
    from urllib.parse import quote

    if sort not in ("relevance", "submittedDate"):
        raise ValueError(f"sort must be 'relevance' or 'submittedDate'; got {sort!r}")
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query={quote(query)}&start=0&max_results={max_results}"
        f"&sortBy={sort}&sortOrder=descending"
    )
    data = http_get(url, timeout=timeout)
    root = ET.fromstring(data)
    entries = root.findall(f"{ATOM}entry")
    return [parse_atom_entry(e) for e in entries]


def log_fallback(from_source: str, to_source: str, reason: str) -> None:
    print(
        f"note: metadata via {to_source} ({from_source} unavailable: {reason})",
        file=sys.stderr,
    )
