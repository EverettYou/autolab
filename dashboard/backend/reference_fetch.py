"""Restore missing reference PDFs and repository clones through fetch-reference.

The dashboard does not invent download logic: ``fetch_reference.py`` is the only writer
(``refetch`` for PDFs with sha256 checks; ``repo`` for clones from recorded provenance).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .repo import BadRequest, NotFound, text_value, valid_id

_REPO = Path(__file__).resolve().parents[2]
_FETCH = _REPO / "skills" / "fetch-reference" / "scripts" / "fetch_reference.py"


def _load_provenance(app, rid: str) -> tuple[Path, dict]:
    rid = valid_id(rid, "reference id")
    if not _FETCH.is_file():
        raise BadRequest("the fetch-reference script is missing")
    folder = app.repo.path(f"references/{rid}")
    prov_path = folder / "provenance.json"
    if not prov_path.is_file():
        raise NotFound(f"no reference {rid}")
    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BadRequest(f"provenance.json is unreadable: {error}") from error
    if not isinstance(prov, dict):
        raise BadRequest("provenance.json must be an object")
    return folder, prov


def _run_fetch(app, args: list[str], *, fail: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(_FETCH), "--root", str(app.root), *args],
        cwd=app.root, capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or fail).strip()
        raise BadRequest(detail.splitlines()[-1][:500] if detail else fail)


def refetch_pdf(app, rid: str) -> dict:
    """Run ``fetch_reference.py refetch <id>`` and return the PDF route once the file exists."""
    folder, prov = _load_provenance(app, rid)
    rid = valid_id(rid, "reference id")

    pdf_name = text_value(prov.get("pdf")) or "paper.pdf"
    if "/" in pdf_name or pdf_name.startswith(".") or not pdf_name.lower().endswith(".pdf"):
        raise BadRequest("this reference has no PDF recorded")

    dest = folder / pdf_name
    if dest.is_file():
        return {"route": f"/references/{rid}/paper.pdf", "size": dest.stat().st_size}

    if not (text_value(prov.get("pdf_url")) or text_value(prov.get("arxiv_id"))):
        raise BadRequest("no pdf_url or arxiv_id recorded; cannot restore the PDF")

    _run_fetch(app, ["refetch", rid], fail="could not restore the PDF")
    if not dest.is_file():
        raise BadRequest("could not restore the PDF")
    return {"route": f"/references/{rid}/paper.pdf", "size": dest.stat().st_size}


def refetch_repo(app, rid: str, name: str) -> dict:
    """Clone a missing ``repos/<name>/`` via ``fetch_reference.py repo`` and return its files route."""
    folder, prov = _load_provenance(app, rid)
    rid = valid_id(rid, "reference id")
    name = valid_id(name, "repository name")

    repos = prov.get("repos") if isinstance(prov.get("repos"), list) else []
    record = next(
        (item for item in repos if isinstance(item, dict) and text_value(item.get("name")) == name),
        None,
    )
    if record is None:
        raise NotFound(f"no repository {name} on reference {rid}")

    url = text_value(record.get("url"))
    rel = text_value(record.get("path")) or f"repos/{name}"
    if "/" in Path(rel).name or rel.startswith(".") or ".." in Path(rel).parts:
        raise BadRequest("recorded repository path is invalid")
    dest = folder / rel
    inner = rel if rel.startswith("repos/") else f"repos/{name}"
    view_route = f"/references/{rid}?file={inner}#files"

    if dest.is_dir():
        return {"route": view_route, "name": name, "path": f"references/{rid}/{rel}"}

    if not url:
        raise BadRequest("no clone URL recorded; cannot restore the repository")

    args = ["repo", "--id", rid, "--url", url, "--name", name]
    commit = text_value(record.get("commit"))
    if commit:
        args.extend(["--commit", commit])
    title = text_value(prov.get("title"))
    if title:
        args.extend(["--title", title])

    _run_fetch(app, args, fail="could not restore the repository")
    if not dest.is_dir():
        raise BadRequest("could not restore the repository")
    return {"route": view_route, "name": name, "path": f"references/{rid}/{rel}"}
