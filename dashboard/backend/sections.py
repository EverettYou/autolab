"""JSON payloads of the dashboard sections, built from the repository files at request time.

Every builder tolerates missing and partially written files: it returns an empty section together
with ``warnings`` (human-readable strings the page shows) instead of raising. Only a request for a
specific item that does not exist raises :class:`~dashboard.backend.repo.NotFound`.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .links import link_map
from .markup import display_frontmatter, first_heading, parse_frontmatter, title_from_name
from .repo import (HIDDEN_NAMES, ID_PATTERN, LAB_STAGES, LANGUAGES, LISTING_LIMIT,
                   TEXT_PREVIEW_LIMIT, BadRequest, Conflict, DashboardError, Forbidden, NotFound, iso_time,
                   kind_for_name,
                   normalize_rel, records, string_list, text_value, valid_id)
from .repo import public_parts

REFERENCE_STATUSES = ("reproduced", "partial", "attempted", "failed", "fetched", "pending")
REFERENCE_KINDS = ("paper", "repository", "dataset")
THREAD_STATUSES = ("open", "closed")
LAB_REPORTS = ("REPORT.md", "report.md")
LAB_PLAN = "PLAN.md"
TEMPLATE_MARKER = "<!-- fill:"
REPRODUCE_DOCS = ("README.md", "ARCHITECTURE.md")
THREADS_SCRIPT = "skills/thread-interaction/scripts/thread_interaction.py"
THREADS_SKILL = "skills/thread-interaction/SKILL.md"
REPRODUCE_FILE_LIMIT = 500
SKIP_WALK = frozenset({"__pycache__", "node_modules", "site-packages"})


def _add(warnings: list[str], warning: str | None) -> None:
    if warning and warning not in warnings:
        warnings.append(warning)


def _text(value: Any) -> str:
    return text_value(value) or ""


def _count(value: Any) -> int:
    if isinstance(value, (list, dict)):
        return len(value)
    return 1 if isinstance(value, str) and value else 0


def _dict_items(value: Any) -> list[tuple[int, dict]]:
    """``(position, item)`` for the dict entries of a list field; anything else yields nothing."""
    if not isinstance(value, list):
        return []
    return [(position, item) for position, item in enumerate(value) if isinstance(item, dict)]


def _extras(data: dict, known) -> list[list[str]]:
    """Remaining scalar and list fields of a record, for a compact key/value table."""
    out = []
    for key, value in data.items():
        if key in known or value in (None, "", [], {}):
            continue
        if isinstance(value, list) and all(isinstance(item, (str, int, float)) for item in value):
            out.append([key, ", ".join(str(item) for item in value)])
        elif isinstance(value, dict):
            out.append([key, json.dumps(value, ensure_ascii=False)[:400]])
        else:
            out.append([key, _text(value)])
    return out


def _mtime(path: Path) -> str | None:
    try:
        return iso_time(path.stat().st_mtime)
    except OSError:
        return None


def _read_capped(path: Path) -> tuple[str, bool]:
    with path.open("rb") as handle:
        data = handle.read(TEXT_PREVIEW_LIMIT + 1)
    truncated = len(data) > TEXT_PREVIEW_LIMIT
    return data[:TEXT_PREVIEW_LIMIT].decode("utf-8", errors="replace"), truncated


def markdown_doc(app, rel: str, path: Path) -> dict:
    """A Markdown file as ``{path, title, frontmatter, markdown, links, ...}``."""
    try:
        if path.stat().st_size <= TEXT_PREVIEW_LIMIT:
            text, truncated = app.repo.read_text(path), False
        else:
            text, truncated = _read_capped(path)
    except OSError as exc:
        return {"path": rel, "name": posixpath.basename(rel), "error": f"cannot be read ({exc.strerror})",
                "markdown": "", "frontmatter": [], "links": {}}
    meta, body = parse_frontmatter(text)
    title = meta.get("title") if isinstance(meta.get("title"), str) and meta.get("title") else None
    resolver = app.resolver()
    links = resolver.link_map(body, rel)
    for value in meta.values():
        for item in (value if isinstance(value, list) else [value]):
            if isinstance(item, str) and "/" in item and item not in links["code"]:
                info = resolver.code_span(item, rel)
                if info:
                    links["code"][item] = info
    return {
        "path": rel, "name": posixpath.basename(rel),
        "title": title or first_heading(body) or title_from_name(posixpath.basename(rel)),
        "frontmatter": display_frontmatter(meta), "markdown": body, "truncated": truncated,
        "modified": _mtime(path), "links": links,
    }


# -- directory listings -----------------------------------------------------------------------


def _entry(app, parent_rel: str, entry: os.DirEntry) -> dict | None:
    name = entry.name
    if name.startswith(".") or name in HIDDEN_NAMES:
        return None
    rel = f"{parent_rel}/{name}" if parent_rel else name
    if not public_parts(Path(rel).parts):
        return None
    item: dict[str, Any] = {"name": name, "path": rel}
    try:
        if entry.is_symlink():
            target = Path(entry.path).resolve(strict=False)
            if not target.exists():
                item["type"] = "broken-link"
                return item
            if not app.repo.inside(target):
                item["type"] = "outside-link"
                return item
        if entry.is_dir():
            item["type"] = "dir"
        else:
            st = entry.stat()
            item.update(type="file", size=st.st_size, modified=iso_time(st.st_mtime),
                        kind=kind_for_name(name) or "file")
    except OSError:
        item["type"] = "broken-link"
    return item


def list_dir(app, rel: str, resolved: Path, limit: int = LISTING_LIMIT) -> dict:
    try:
        with os.scandir(resolved) as handle:
            raw = sorted(handle, key=lambda e: e.name.casefold())
    except OSError as exc:
        raise BadRequest(f"{rel or '.'} cannot be listed ({exc.strerror})") from exc
    entries = []
    for entry in raw:
        item = _entry(app, rel, entry)
        if item is not None:
            entries.append(item)
    entries.sort(key=lambda item: (item["type"] != "dir", item["name"].casefold()))
    return {"path": rel, "entries": entries[:limit], "total": len(entries),
            "truncated": len(entries) > limit}


def fs_listing(app, raw: str | None) -> dict:
    rel, resolved = app.repo.resolve(raw or "")
    if not resolved.is_dir():
        raise BadRequest(f"{rel} is not a folder")
    return list_dir(app, rel, resolved)


def walk_files(app, rel: str, limit: int) -> dict:
    """Files under a folder (recursively, hidden and cache folders skipped), capped at ``limit``."""
    base = app.repo.path(rel)
    files, total = [], 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if public_parts((d,)) and d not in SKIP_WALK
                             and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg")))
        for name in sorted(filenames):
            if not public_parts((name,)):
                continue
            total += 1
            if len(files) >= limit:
                continue
            path = Path(dirpath) / name
            try:
                st = path.stat()
            except OSError:
                files.append({"path": app.repo.rel(path), "name": name, "type": "broken-link"})
                continue
            if path.is_symlink() and not app.repo.inside(path.resolve()):
                files.append({"path": app.repo.rel(path), "name": name, "type": "outside-link"})
                continue
            files.append({"path": app.repo.rel(path), "name": name, "type": "file", "size": st.st_size,
                          "kind": kind_for_name(name) or "file"})
        if total > limit * 20:
            break
    return {"path": rel, "files": files, "total": total, "truncated": total > len(files)}


# -- file viewer --------------------------------------------------------------------------------


def file_view(app, raw: str | None) -> dict:
    rel, resolved = app.repo.resolve(raw or "")
    route = app.resolver().route_for_path(rel)
    root_name = app.root.name
    if resolved.is_dir():
        listing = list_dir(app, rel, resolved)
        return {"type": "dir", "route": route, "root_name": root_name, **listing}
    try:
        st = resolved.stat()
    except OSError as exc:
        raise NotFound(f"{rel} cannot be read") from exc
    name = posixpath.basename(rel)
    kind = app.repo.classify(resolved, name)
    out: dict[str, Any] = {"type": "file", "path": rel, "name": name, "kind": kind, "size": st.st_size,
                           "modified": iso_time(st.st_mtime), "route": route, "root_name": root_name,
                           "language": LANGUAGES.get(os.path.splitext(name)[1].lower())}
    if kind in ("image", "pdf"):
        out["raw"] = f"/raw/{_quote(rel)}"
        return out
    if kind == "binary":
        return out
    out["raw"] = f"/raw/{_quote(rel)}"
    if kind == "markdown":
        out.update(markdown_doc(app, rel, resolved))
        return out
    try:
        text, truncated = _read_capped(resolved)
    except OSError as exc:
        out["error"] = f"cannot be read ({exc.strerror})"
        return out
    out.update(content=text, truncated=truncated)
    if kind == "json" and not truncated:
        try:
            out["content"] = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            out["language"] = "json"
        except (json.JSONDecodeError, RecursionError):
            out["warning"] = "invalid JSON; shown as text"
    return out


def save_text_file(app, body: dict) -> dict:
    """Replace one source or plain-text file from the full-screen editor."""
    raw = body.get("path")
    content = body.get("content")
    if not isinstance(raw, str) or not raw:
        raise BadRequest("path is required")
    if not isinstance(content, str):
        raise BadRequest("content must be text")
    rel, resolved = app.repo.resolve(raw)
    if not resolved.is_file():
        raise BadRequest("only a text file can be saved")
    name = posixpath.basename(rel)
    if app.repo.classify(resolved, name) != "text":
        raise Forbidden("only plain text and source files can be saved from the editor")
    try:
        st = resolved.stat()
    except OSError as exc:
        raise NotFound(f"{rel} cannot be read") from exc
    if st.st_size > TEXT_PREVIEW_LIMIT:
        raise BadRequest("this file is larger than the editor can save")
    base = body.get("modified")
    if isinstance(base, str) and base and base != iso_time(st.st_mtime):
        raise Conflict("this file changed on disk; reload it before saving")
    try:
        app.repo.replace_text(resolved, content)
    except OSError as exc:
        raise BadRequest(f"cannot save {rel} ({exc.strerror})") from exc
    return file_view(app, rel)


def _quote(rel: str) -> str:
    return quote(rel, safe="/")


# -- auto-research ------------------------------------------------------------------------------


def _task_detail(app, value: Any) -> tuple[str | None, bool]:
    if not isinstance(value, str) or not value:
        return None, False
    match = re.match(r"^\.auto-research/tasks/([A-Za-z0-9][A-Za-z0-9._-]*)\.md$", value.strip())
    if not match:
        return None, False
    return match.group(1), app.repo.path(value.strip()).is_file()


def _task_items(app, state: dict) -> list[dict]:
    items = []
    for position, item in _dict_items(state.get("tasks")):
        blocked = item.get("blocked_on")
        slug, has_detail = _task_detail(app, item.get("detail"))
        if slug is None and isinstance(item.get("id"), str):
            candidate = item["id"]
            if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", candidate):
                slug = candidate
                has_detail = app.repo.path(f".auto-research/tasks/{candidate}.md").is_file()
        items.append({
            "position": position + 1, "id": _text(item.get("id")),
            "title": _text(item.get("title")) or _text(item.get("id")) or f"item {position + 1}",
            "question": _text(item.get("question")), "next_step": _text(item.get("next_step")),
            "for": _text(item.get("for")), "gpu": _text(item.get("gpu")), "time": _text(item.get("time")),
            "blocked": bool(blocked), "blocked_on": (", ".join(string_list(blocked)) if isinstance(blocked, list)
                                                    else _text(blocked)) or None,
            "related_labs": string_list(item.get("related_labs")), "added": _text(item.get("added")),
            "detail": slug if has_detail else (_text(item.get("id")) if item.get("report") else None),
        })
    return items


def _thread_brief(threads: dict[str, dict], thread_id: Any) -> dict | None:
    if not isinstance(thread_id, str) or not thread_id:
        return None
    thread = threads.get(thread_id)
    if thread is None:
        return {"id": thread_id, "exists": False}
    return {"id": thread_id, "exists": True, "title": _text(thread.get("title")),
            "status": _text(thread.get("status"))}


def _state(app) -> tuple[dict, list[str], bool]:
    data, warning, exists = app.repo.load_json(".auto-research/state.json")
    warnings: list[str] = []
    _add(warnings, warning)
    if exists and warning is None and not isinstance(data, dict):
        _add(warnings, ".auto-research/state.json: expected a JSON object")
    return (data if isinstance(data, dict) else {}), warnings, exists


def _describe(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, dict):
        for key in ("title", "summary", "name", "id"):
            if isinstance(value.get(key), str) and value[key]:
                return value[key]
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def auto_research(app, threads: dict[str, dict] | None = None) -> dict:
    state, warnings, exists = _state(app)
    if threads is None:
        threads = {t["id"]: t for t in _threads(app)[0]}
    last = state.get("last_action")
    if isinstance(last, dict):
        last_action = {"at": _text(last.get("at")), "summary": _text(last.get("summary"))}
    elif last:
        last_action = {"at": "", "summary": _text(last)}
    else:
        last_action = None
    tasks = _task_items(app, state)
    flag_status = _text(state.get("status")) if exists else None
    out = {
        "exists": exists, "schema": _text(state.get("schema")),
        "flag_status": flag_status,
        "status": flag_status or "missing",
        "liveness": None,
        "scheduler": None,
        "checked_at": None,
        "updated": _text(state.get("updated")), "next_action": _text(state.get("next_action")),
        "active_deliverable": _describe(state.get("active_deliverable")),
        "pending_threads": [
            brief for tid, thread in threads.items()
            if isinstance(thread, dict) and thread.get("status") == "open"
            and (thread.get("messages") or [{}])[-1].get("author") == "agent"
            for brief in [_thread_brief(threads, tid)]
            if brief
        ],
        "last_action": last_action,
        "last_supervisor_at": _text(state.get("last_supervisor_at")) or None,
        "tasks": tasks,
        "counts": {"tasks": len(tasks), "blocked": sum(1 for item in tasks if item["blocked"])},
        "extra": _extras(state, {"schema", "status", "updated", "next_action", "active_deliverable",
                                 "last_action", "last_supervisor_at", "idle", "tasks", "threads"}),
        "warnings": warnings,
    }
    text = "\n\n".join([out["next_action"], out["active_deliverable"] or "",
                        (last_action or {}).get("summary", "")] + [item["title"] for item in tasks])
    out["links"] = link_map(app, text, ".auto-research/state.json")
    return out


def task_item(app, slug: str) -> dict:
    valid_id(slug, "task id")
    rel = f".auto-research/tasks/{slug}.md"
    path = app.repo.path(rel)
    folder = app.repo.path(".auto-research/tasks").resolve()
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise NotFound(f"no task note {slug}") from exc
    if resolved.parent != folder or not resolved.is_file():
        raise NotFound(f"no task note {slug}")
    state, warnings, _ = _state(app)
    item = next((entry for entry in _task_items(app, state) if entry["detail"] == slug or entry["id"] == slug),
                None)
    doc = markdown_doc(app, rel, resolved)
    return {"id": slug, "item": item, "title": (item or {}).get("title") or doc["title"], "doc": doc,
            "warnings": warnings}


# -- references ---------------------------------------------------------------------------------


def _registry(app) -> tuple[dict[str, dict], list[str], bool]:
    data, warning, exists = app.repo.load_json("references/references.json")
    warnings: list[str] = []
    _add(warnings, warning)
    return {item["id"]: item for item in records(data, "references")}, warnings, exists


def _provenance(app, rid: str) -> tuple[dict, str | None]:
    data, warning, _ = app.repo.load_json(f"references/{rid}/provenance.json")
    return (data if isinstance(data, dict) else {}), warning


def _threads(app) -> tuple[list[dict], list[str], bool]:
    data, warning, exists = app.repo.load_json(".auto-research/state.json")
    warnings: list[str] = []
    _add(warnings, warning)
    if not exists or not isinstance(data, dict):
        return [], warnings, exists
    metas = data.get("threads")
    if not isinstance(metas, list):
        return [], warnings, exists
    threads: list[dict] = []
    for meta in metas:
        if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
            continue
        tid = meta["id"]
        thread = dict(meta)
        body, file_warning, file_exists = app.repo.load_json(f".auto-research/threads/{tid}.json")
        _add(warnings, file_warning)
        if file_exists and isinstance(body, dict) and isinstance(body.get("messages"), list):
            thread["messages"] = body["messages"]
        elif file_exists and isinstance(body, list):
            thread["messages"] = body
        elif file_exists and isinstance(body, dict) and "messages" in body:
            thread["messages"] = body.get("messages") or []
        else:
            thread.setdefault("messages", [])
            if not file_exists:
                _add(warnings, f".auto-research/threads/{tid}.json missing")
        threads.append(thread)
    return threads, warnings, exists


def _labs_index(app) -> tuple[dict[str, dict], list[str], bool]:
    data, warning, exists = app.repo.load_json("labs/labs.json")
    warnings: list[str] = []
    _add(warnings, warning)
    return {item["id"]: item for item in records(data, "labs")}, warnings, exists


def _lab_record(app, lab_id: str, index: dict[str, dict]) -> tuple[dict, str | None]:
    detail, warning, _ = app.repo.load_json(f"labs/{lab_id}/lab.json")
    merged = dict(index.get(lab_id) or {})
    if isinstance(detail, dict):
        merged.update({key: value for key, value in detail.items() if value not in (None, "") or key not in merged})
    merged["id"] = lab_id
    return merged, warning


def lab_reference_index(app, labs: dict[str, dict] | None = None) -> dict[str, list[str]]:
    """Reference id -> ids of the labs whose lab.json cites it."""
    labs = labs if labs is not None else _labs_index(app)[0]
    index: dict[str, list[str]] = {}
    for lab_id in sorted(app.repo.lab_ids()):
        record, _ = _lab_record(app, lab_id, labs)
        for rid in string_list(record.get("references")):
            index.setdefault(rid, []).append(lab_id)
    return index


def _status_counts(values, order) -> dict[str, int]:
    counts = Counter(values)
    ordered = {key: counts[key] for key in order if counts.get(key)}
    ordered.update({key: counts[key] for key in sorted(counts, key=str) if key not in ordered})
    return ordered


def _aliases(registry: dict[str, dict]) -> dict[str, str]:
    out = {}
    for rid, entry in registry.items():
        for alias in string_list(entry.get("aliases")):
            out.setdefault(alias, rid)
    return out


def references_list(app) -> dict:
    registry, warnings, exists = _registry(app)
    cited = lab_reference_index(app)
    items = []
    for rid in sorted(app.repo.reference_ids() | set(registry)):
        entry = registry.get(rid, {})
        prov, pwarn = _provenance(app, rid)
        _add(warnings, pwarn)
        folder = app.repo.path(f"references/{rid}")
        pdf_name = _pdf_name(prov, entry)
        authors = string_list(prov.get("authors"))
        arxiv = _text(entry.get("arxiv_id")) or _text(prov.get("arxiv_id"))
        has_pdf = bool(pdf_name and (folder / pdf_name).is_file())
        items.append({
            "id": rid, "title": _text(entry.get("title")) or _text(prov.get("title")) or rid,
            "kind": reference_kinds(prov, entry),
            "status": _text(entry.get("status")) or _text(prov.get("status")) or "unknown",
            "arxiv_id": arxiv,
            "entry_url": _text(prov.get("entry_url")) or (f"https://arxiv.org/abs/{arxiv}" if arxiv else ""),
            "published_url": _text(prov.get("published_url")),
            "authors": authors[:3], "authors_total": len(authors),
            "published": _text(prov.get("published"))[:10],
            "has_pdf": has_pdf,
            "can_fetch_pdf": _can_fetch_pdf(prov, entry, has_pdf=has_pdf),
            "repos": _count(entry.get("repos") or prov.get("repos")),
            "primary_repo": _primary_repo(app, rid, entry, prov),
            "attempts": _count(entry.get("attempts") or prov.get("attempts")),
            "reproduction": bool(entry.get("reproduction") or prov.get("reproduction")),
            "aliases": string_list(entry.get("aliases") or prov.get("aliases")),
            "blurb": (_text(prov.get("abstract")) or "")[:240],
            "cited_by": len(cited.get(rid, [])), "in_registry": rid in registry,
            "folder": folder.is_dir(),
        })
    # Empty search shows publication date first (newest, undated last), then title.
    items.sort(key=lambda item: (item["title"].casefold(), item["id"]))
    items.sort(key=lambda item: item["published"] or "", reverse=True)
    return {"exists": exists, "references": items,
            "counts": _status_counts((item["status"] for item in items), REFERENCE_STATUSES),
            "kinds": _status_counts((kind for item in items for kind in item["kind"]), REFERENCE_KINDS),
            "warnings": warnings}


def reference_kinds(prov: dict, entry: dict | None = None) -> list[str]:
    """Labels for one reference. A paper keeps its code or dataset instead of a second entry."""
    entry = entry or {}
    raw = entry.get("kind") if entry.get("kind") not in (None, "") else prov.get("kind")
    if isinstance(raw, str):
        declared = [raw] if raw else []
    elif isinstance(raw, list):
        declared = [item for item in raw if isinstance(item, str) and item]
    else:
        declared = []
    kinds = list(declared)
    if (prov.get("arxiv_id") or prov.get("pdf")) and "paper" not in kinds:
        kinds.append("paper")
    repos = prov.get("repos") if isinstance(prov.get("repos"), list) else []
    code = any(isinstance(repo, dict) and isinstance(repo.get("url"), str)
               and ("github.com" in repo["url"] or "gitlab.com" in repo["url"]) for repo in repos)
    if code and "repository" not in kinds:
        kinds.append("repository")
    ordered = [kind for kind in REFERENCE_KINDS if kind in kinds]
    ordered += [kind for kind in kinds if kind not in ordered]
    return ordered or ["paper"]


def _pdf_name(prov: dict, entry: dict) -> str | None:
    name = prov.get("pdf") if isinstance(prov.get("pdf"), str) and prov.get("pdf") else "paper.pdf"
    if "/" in name or name.startswith(".") or not name.lower().endswith(".pdf"):
        return None
    return name


def _can_fetch_pdf(prov: dict, entry: dict, *, has_pdf: bool) -> bool:
    """True when the local PDF is missing but provenance still points at a downloadable source."""
    if has_pdf:
        return False
    return bool(
        _text(prov.get("pdf_url"))
        or _text(entry.get("arxiv_id"))
        or _text(prov.get("arxiv_id"))
    )


def reference_pdf(app, rid: str) -> Path:
    valid_id(rid, "reference id")
    registry, _, _ = _registry(app)
    prov, _ = _provenance(app, rid)
    name = _pdf_name(prov, registry.get(rid, {}))
    if name is None:
        raise NotFound("this reference has no PDF")
    _, resolved = app.repo.resolve(f"references/{rid}/{name}")
    if not resolved.is_file():
        raise NotFound("this reference has no PDF")
    return resolved


def _primary_repo(app, rid: str, entry: dict, prov: dict) -> dict | None:
    """First recorded repository, for list-row View Repo actions."""
    repos = _repos(app, rid, entry, prov)
    if not repos:
        return None
    repo = repos[0]
    return {
        "name": repo["name"],
        "exists": repo["exists"],
        "can_fetch": repo["can_fetch"],
        "route": repo["route"],
    }


def _repos(app, rid: str, entry: dict, prov: dict) -> list[dict]:
    out, seen = [], set()
    raw = prov.get("repos") if isinstance(prov.get("repos"), list) else []
    declared = entry.get("repos")
    raw = raw + [name for name in (declared if isinstance(declared, list) else [declared])
                 if isinstance(name, str) and name]
    for item in raw:
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name")) or posixpath.basename(_text(item.get("path")).rstrip("/"))
        if not name or name in seen:
            continue
        seen.add(name)
        path = _text(item.get("path")) or f"repos/{name}"
        rel = posixpath.normpath(f"references/{rid}/{path}")
        url = _text(item.get("url"))
        commit = _text(item.get("commit"))
        browse = None
        if url.startswith("https://github.com/") or url.startswith("https://gitlab.com/"):
            base = url[:-4] if url.endswith(".git") else url
            browse = f"{base}/tree/{commit}" if commit else base
        folder = app.repo.path(rel)
        exists = rel.startswith(f"references/{rid}/") and folder.is_dir()
        can_fetch = (not exists) and bool(url)
        # Stay on the reference page Files browser (not the generic /files bounce).
        inner = path if path.startswith("repos/") else f"repos/{name}"
        view_route = f"/references/{_quote(rid)}?file={quote(inner, safe='/')}#files"
        out.append({"name": name, "path": rel, "exists": exists, "can_fetch": can_fetch,
                    "url": url or None, "commit": commit or None,
                    "retrieved_at": _text(item.get("retrieved_at")) or None,
                    "browse": browse or (url if url.startswith("https://") else None),
                    "route": view_route if exists else None,
                    "summary": _repo_summary(folder) if exists else None})
    return out


def _repo_excerpt(text: str) -> str | None:
    """The first prose paragraph of a repository README or pointer note."""
    text = re.sub(r"<[^>]+>", " ", text)
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    for chunk in re.split(r"\n\s*\n", text):
        lines = []
        for raw in chunk.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(">") or line.startswith("```"):
                continue
            lines.append(line)
        plain = re.sub(r"[*_`>#]", "", " ".join(lines))
        plain = " ".join(plain.split())
        if len(plain) < 24 or plain.lower().startswith("paper:"):
            continue
        return _clip(plain)
    return None


def _repo_summary(folder: Path) -> str | None:
    for name in ("README.md", "readme.md", "README.rst", "POINTER.md"):
        path = folder / name
        if not path.is_file():
            continue
        try:
            text, _ = _read_capped(path)
        except OSError:
            continue
        excerpt = _repo_excerpt(text)
        if excerpt:
            return excerpt
    return None


ATTEMPT_NOTES = ("DISPOSITION.md", "REPRO-PLAN.md", "REPRODUCTION-NOTES.md", "PLAN.md",
                 "NOTES.md", "RESULTS.md", "ARCHITECTURE.md", "README.md")
ATTEMPT_RESULTS = ("result.json", "RESULT.json")
ATTEMPT_SUMMARY_LIMIT = 480


def _mapping_file(path: Path) -> dict:
    """A small JSON or YAML mapping, or ``{}`` when the file is missing or unreadable."""
    if not path.is_file():
        return {}
    try:
        text, _ = _read_capped(path)
    except OSError:
        return {}
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _scalar(data: dict, key: str) -> str | None:
    value = data.get(key) if isinstance(data, dict) else None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = " ".join(str(value).split())
    return text or None


def _clip(text: str, limit: int = ATTEMPT_SUMMARY_LIMIT) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut or text[:limit]}…"


def _markdown_excerpt(text: str) -> str | None:
    body = text
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            body = body[end + 4:]
    paragraph = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            if paragraph:
                break
            continue
        paragraph.append(line)
    if not paragraph:
        return None
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", " ".join(paragraph))
    plain = re.sub(r"[*_`>#]", "", plain)
    plain = " ".join(plain.split())
    return _clip(plain) or None


def _attempt_summary(gate: dict, result: dict, folder: Path) -> str | None:
    for text in (_scalar(gate, "notes"), _scalar(result, "verdict_note"), _scalar(result, "verdict_detail")):
        if text:
            return _clip(text)
    notes = result.get("notes") if isinstance(result, dict) else None
    if isinstance(notes, str) and notes.strip():
        return _clip(notes)
    if isinstance(notes, list):
        lines = [item.strip() for item in notes if isinstance(item, str) and item.strip()]
        if lines:
            return _clip(" ".join(lines[:4]))
    for name in ATTEMPT_NOTES:
        path = folder / name
        if not path.is_file():
            continue
        try:
            text, _ = _read_capped(path)
        except OSError:
            continue
        excerpt = _markdown_excerpt(text)
        if excerpt:
            return excerpt
    return None


def _attempt_claims(gate: dict) -> list[dict]:
    raw = gate.get("claims") if isinstance(gate, dict) else None
    if not isinstance(raw, list):
        return []
    claims = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = _scalar(item, "text")
        if not text:
            continue
        claims.append({"id": _scalar(item, "id"), "status": _scalar(item, "status"), "text": _clip(text, 500)})
        if len(claims) == 12:
            break
    return claims


def _attempts(app, rid: str, entry: dict, prov: dict) -> list[dict]:
    names = string_list(prov.get("attempts")) + string_list(entry.get("attempts"))
    folder = app.repo.path(f"references/{rid}/attempts")
    try:
        names += sorted(e.name for e in os.scandir(folder) if e.is_dir() and not e.name.startswith("."))
    except OSError:
        pass
    out = []
    for name in dict.fromkeys(names):
        if "/" in name or name.startswith("."):
            continue
        rel = f"references/{rid}/attempts/{name}"
        path = app.repo.path(rel)
        docs = []
        gate: dict = {}
        result: dict = {}
        if path.is_dir():
            try:
                docs = sorted(e.name for e in os.scandir(path) if e.is_file() and e.name.lower().endswith(".md"))
            except OSError:
                docs = []
            gate = _mapping_file(path / "gate-state.yaml")
            for result_name in ATTEMPT_RESULTS:
                result = _mapping_file(path / result_name)
                if result:
                    break
        out.append({
            "name": name, "path": rel, "exists": path.is_dir(), "docs": docs,
            "route": f"/files/{_quote(rel)}" if path.is_dir() else None,
            "phase": _scalar(gate, "phase"), "mode": _scalar(gate, "implementation_mode"),
            "verdict": _scalar(gate, "verdict") or _scalar(result, "verdict"),
            "status": _scalar(result, "status"), "rigor": _scalar(gate, "rigor_recommendation"),
            "summary": _attempt_summary(gate, result, path) if path.is_dir() else None,
            "claims": _attempt_claims(gate),
        })
    return out


def _reproduction(app, rid: str, entry: dict, prov: dict, warnings: list[str]) -> dict | None:
    declared = _text(entry.get("reproduction")) or _text(prov.get("reproduction"))
    sub = declared.strip("/")
    if not ID_PATTERN.match(sub) or ".." in sub:
        sub = "reproduce"
    rel = f"references/{rid}/{sub}"
    path = app.repo.path(rel)
    if not path.is_dir():
        return {"path": rel, "exists": False} if declared else None
    docs = []
    for name in REPRODUCE_DOCS:
        doc_path = path / name
        if doc_path.is_file():
            docs.append(markdown_doc(app, f"{rel}/{name}", doc_path))
    others = []
    try:
        others = sorted(e.name for e in os.scandir(path)
                        if e.is_file() and e.name.lower().endswith(".md") and e.name not in REPRODUCE_DOCS)
    except OSError:
        pass
    result = None
    result_path = path / "RESULT.json"
    if result_path.is_file():
        data, warning, _ = app.repo.load_json(f"{rel}/RESULT.json")
        if warning:
            _add(warnings, warning)
            text, _ = _read_capped(result_path)
            result = {"path": f"{rel}/RESULT.json", "text": text, "valid": False}
        else:
            result = {"path": f"{rel}/RESULT.json", "valid": True,
                      "text": json.dumps(data, indent=2, ensure_ascii=False)[:TEXT_PREVIEW_LIMIT]}
    return {"path": rel, "exists": True, "docs": docs, "other_docs": [f"{rel}/{name}" for name in others],
            "result": result, "files": walk_files(app, rel, REPRODUCE_FILE_LIMIT)}


def _related(app, prov: dict, registry: dict, warnings: list[str]) -> list[dict]:
    out = []
    for rid in string_list(prov.get("related")):
        if not ID_PATTERN.match(rid):
            continue
        entry = registry.get(rid, {})
        other, warning = _provenance(app, rid)
        _add(warnings, warning)
        if rid not in registry and not other:
            _add(warnings, f"related reference {rid} is not archived")
            continue
        out.append({
            "id": rid,
            "title": _text(entry.get("title")) or _text(other.get("title")) or rid,
            "kind": reference_kinds(other, entry),
        })
    return out


def reference_detail(app, rid: str) -> dict:
    valid_id(rid, "reference id")
    registry, warnings, _ = _registry(app)
    folder = app.repo.path(f"references/{rid}")
    if rid not in registry and not (folder / "provenance.json").is_file():
        canonical = _aliases(registry).get(rid)
        if canonical:
            return {"redirect": f"/references/{canonical}", "id": canonical}
        raise NotFound(f"no reference {rid}")
    entry = registry.get(rid, {})
    prov, pwarn = _provenance(app, rid)
    _add(warnings, pwarn)
    arxiv = _text(entry.get("arxiv_id")) or _text(prov.get("arxiv_id"))
    pdf_name = _pdf_name(prov, entry)
    pdf_path = folder / pdf_name if pdf_name else None
    pdf = None
    if pdf_path is not None and pdf_path.is_file():
        pdf = {"route": f"/references/{rid}/paper.pdf", "size": pdf_path.stat().st_size,
               "pages": prov.get("pages") if isinstance(prov.get("pages"), int) else None}
    labs_index, lab_warnings, _ = _labs_index(app)
    cited_by = []
    for lab_id in lab_reference_index(app, labs_index).get(rid, []):
        record, _ = _lab_record(app, lab_id, labs_index)
        cited_by.append({"id": lab_id, "title": _text(record.get("title")) or lab_id,
                         "stage": _text(record.get("stage"))})
    wiki = [page.summary() for page in app.wiki.index().mentioning("references", rid)]
    listing = list_dir(app, f"references/{rid}", folder) if folder.is_dir() else None
    abstract = _text(prov.get("abstract")) or _text(entry.get("abstract"))
    out = {
        "id": rid, "in_registry": rid in registry,
        "title": _text(prov.get("title")) or _text(entry.get("title")) or rid,
        "kind": reference_kinds(prov, entry),
        "status": _text(entry.get("status")) or _text(prov.get("status")) or "unknown",
        "arxiv_id": arxiv or None, "authors": string_list(prov.get("authors")), "abstract": abstract,
        "categories": string_list(prov.get("categories")), "published": _text(prov.get("published")),
        "upstream_updated": _text(prov.get("upstream_updated")),
        "entry_url": _text(prov.get("entry_url")) or (f"https://arxiv.org/abs/{arxiv}" if arxiv else ""),
        "pdf_url": _text(prov.get("pdf_url")) or (f"https://arxiv.org/pdf/{arxiv}" if arxiv else ""),
        "published_url": _text(prov.get("published_url")),
        "related": _related(app, prov, registry, warnings),
        "pdf": pdf,
        "can_fetch_pdf": _can_fetch_pdf(prov, entry, has_pdf=pdf is not None),
        "aliases": string_list(entry.get("aliases") or prov.get("aliases")),
        "repos": _repos(app, rid, entry, prov), "attempts": _attempts(app, rid, entry, prov),
        "reproduction": _reproduction(app, rid, entry, prov, warnings),
        "legacy_paths": string_list(prov.get("legacy_paths")),
        "provenance": [[key, _text(prov.get(key))] for key in (
            "fetched_at", "fetch_status", "metadata_source", "title_match_score")
            if _text(prov.get(key))],
        "cited_by": cited_by, "wiki": wiki, "files": listing, "warnings": warnings + lab_warnings,
    }
    out["links"] = link_map(app, abstract, f"references/{rid}/provenance.json")
    return out


# -- labs ---------------------------------------------------------------------------------------


def _lab_item(record: dict) -> dict:
    return {
        "id": record["id"], "title": _text(record.get("title")) or record["id"],
        "stage": (_text(record.get("stage")) or "unknown").lower(),
        "summary": _text(record.get("summary")), "current_focus": _text(record.get("current_focus")),
        "blocked_reason": _text(record.get("blocked_reason")),
        "next_action": _text(record.get("next_action")), "created": _text(record.get("created")),
        "updated": _text(record.get("updated")),
        "references": len(string_list(record.get("references"))),
        "discussion": len(string_list(record.get("discussion"))),
    }


def labs_list(app) -> dict:
    index, warnings, exists = _labs_index(app)
    items = []
    for lab_id in app.repo.lab_ids() | set(index):
        record, warning = _lab_record(app, lab_id, index)
        _add(warnings, warning)
        item = _lab_item(record)
        item["in_index"] = lab_id in index
        items.append(item)
    items.sort(key=lambda item: (item["created"] or item["id"][:10], item["id"]), reverse=True)
    return {"exists": exists, "labs": items,
            "counts": _status_counts((item["stage"] for item in items), LAB_STAGES), "warnings": warnings}


def _lab_docs(app, lab_id: str) -> list[dict]:
    """The lab's REPORT.md and PLAN.md, then its notes: notes/**/*.md and any other top-level
    Markdown file of a lab not yet moved to the standard layout."""
    folder = app.repo.path(f"labs/{lab_id}")
    try:
        top = sorted(e.name for e in os.scandir(folder)
                     if e.name.lower().endswith(".md") and not e.name.startswith(".") and e.is_file())
    except OSError:
        return []
    report = next((name for name in LAB_REPORTS if name in top), None)
    docs = [{"name": report, "path": f"labs/{lab_id}/{report}", "kind": "report"}] if report else []
    if LAB_PLAN in top:
        docs.append({"name": LAB_PLAN, "path": f"labs/{lab_id}/{LAB_PLAN}", "kind": "plan"})
    notes = [name for name in top if name not in (report, LAB_PLAN)]
    notes_dir = folder / "notes"
    if notes_dir.is_dir():
        for path in notes_dir.rglob("*.md"):
            rel = path.relative_to(folder)
            if path.is_file() and not any(part.startswith(".") or part in SKIP_WALK for part in rel.parts):
                notes.append(rel.as_posix())
    notes.sort(key=lambda name: ("/" in name, name.casefold()))
    return docs + [{"name": name, "path": f"labs/{lab_id}/{name}", "kind": "note"} for name in notes]


def _unfinished(app, doc: dict) -> bool:
    """A report still in its template skeleton."""
    try:
        with open(app.repo.path(doc["path"]), encoding="utf-8", errors="replace") as handle:
            return TEMPLATE_MARKER in handle.read(65536)
    except OSError:
        return False


def _default_doc(app, docs: list[dict]) -> dict | None:
    by_kind = {doc["kind"]: doc for doc in reversed(docs)}
    report, plan = by_kind.get("report"), by_kind.get("plan")
    if report and not (plan and _unfinished(app, report)):
        return report
    return plan or report or by_kind.get("note")


def lab_detail(app, lab_id: str, doc: str | None = None) -> dict:
    valid_id(lab_id, "lab id")
    index, warnings, _ = _labs_index(app)
    folder = app.repo.path(f"labs/{lab_id}")
    if lab_id not in index and not (folder / "lab.json").is_file():
        raise NotFound(f"no lab {lab_id}")
    record, warning = _lab_record(app, lab_id, index)
    _add(warnings, warning)
    item = _lab_item(record)
    registry, ref_warnings, _ = _registry(app)
    references = []
    for rid in string_list(record.get("references")):
        entry = registry.get(rid)
        references.append({"id": rid, "exists": entry is not None or app.repo.path(f"references/{rid}").is_dir(),
                           "title": _text((entry or {}).get("title")) or rid,
                           "status": _text((entry or {}).get("status"))})
    threads, thread_warnings, _ = _threads(app)
    by_id = {thread["id"]: thread for thread in threads}
    thread_ids = list(dict.fromkeys(string_list(record.get("discussion")) + [
        thread["id"] for thread in threads if lab_id in string_list(thread.get("related_labs"))]))
    discussion = [_thread_brief(by_id, thread_id) for thread_id in thread_ids]
    state, state_warnings, _ = _state(app)
    tasks = [entry for entry in _task_items(app, state) if lab_id in entry["related_labs"]]
    docs = _lab_docs(app, lab_id)
    match = _default_doc(app, docs) if doc is None else next(
        (item for item in docs if item["name"].casefold() == doc.casefold()), None)
    missing = None
    if doc is not None and match is None:
        if doc.casefold() not in (LAB_REPORTS[0].casefold(), LAB_PLAN.casefold()):
            raise NotFound(f"{doc} is not a document of this lab")
        missing = LAB_REPORTS[0] if doc.casefold() == LAB_REPORTS[0].casefold() else LAB_PLAN
    selected = markdown_doc(app, match["path"], app.repo.path(match["path"])) if match else None
    known = {"id", "title", "stage", "summary", "current_focus", "blocked_reason", "next_action",
             "created", "updated", "references", "discussion", "report", "plan", "readme"}
    out = {
        **item, "extra": _extras(record, known), "docs": docs, "doc": selected,
        "doc_kind": match["kind"] if match else None, "missing_doc": missing,
        "reference_list": references, "threads": discussion, "tasks": tasks,
        "wiki": [page.summary() for page in app.wiki.index().mentioning("labs", lab_id)],
        "files": list_dir(app, f"labs/{lab_id}", folder) if folder.is_dir() else None,
        "warnings": warnings + ref_warnings + thread_warnings + state_warnings,
    }
    text = "\n\n".join([item["summary"], item["current_focus"], item["blocked_reason"], item["next_action"]])
    out["links"] = link_map(app, text, f"labs/{lab_id}/lab.json")
    return out


# -- discussion ---------------------------------------------------------------------------------


def _messages(thread: dict) -> list[dict]:
    out = []
    for position, message in _dict_items(thread.get("messages")):
        out.append({"id": _text(message.get("id")) or f"msg-{position + 1:03d}",
                    "author": _text(message.get("author")) or "unknown",
                    "type": _text(message.get("type")) or "message",
                    "created": _text(message.get("created")),
                    "content": _text(message.get("text")) or _text(message.get("content"))})
    return out


THREAD_REF = re.compile(r"\bthread-\d+\b")


def _thread_blockers(app) -> dict[str, list[str]]:
    """Map each thread id to the task-list items whose `blocked_on` cites it."""
    state, _, _ = _state(app)
    out: dict[str, list[str]] = {}
    for _, task in _dict_items(state.get("tasks")):
        blocked = task.get("blocked_on")
        text = " ".join(string_list(blocked)) if isinstance(blocked, list) else (_text(blocked) or "")
        for thread_id in dict.fromkeys(THREAD_REF.findall(text)):
            out.setdefault(thread_id, []).append(_text(task.get("id")) or "")
    return out


def _thread_item(thread: dict, blockers: dict[str, list[str]]) -> dict:
    messages = _messages(thread)
    last = messages[-1] if messages else None
    status = "closed" if thread.get("status") in {"closed", "resolved"} else "open"
    blocks = blockers.get(thread["id"], []) if status == "open" else []
    return {
        "id": thread["id"], "title": _text(thread.get("title")) or thread["id"],
        "category": _text(thread.get("category")), "priority": _text(thread.get("priority")),
        "status": status, "created": _text(thread.get("created")),
        "updated": _text(thread.get("updated")) or (last or {}).get("created", ""),
        "messages": len(messages), "related_labs": string_list(thread.get("related_labs")),
        "last": {"author": last["author"], "type": last["type"], "created": last["created"]} if last else None,
        "blocks": blocks,
        # Same rule as loop_state status: open thread, last message is an agent question.
        # Progress/status notes do not set the badge even when a task lists the thread.
        "awaiting_human": (
            status == "open" and bool(last)
            and last.get("author") == "agent" and last.get("type") == "question"
        ),
    }


def discussion_list(app, status: str | None = None) -> dict:
    threads, warnings, exists = _threads(app)
    blockers = _thread_blockers(app)
    items = [_thread_item(thread, blockers) for thread in threads]
    counts = _status_counts((item["status"] for item in items), THREAD_STATUSES)
    if status and status != "all":
        items = [item for item in items if item["status"] == status]
    items.sort(key=lambda item: item["updated"], reverse=True)
    items.sort(key=lambda item: item["status"] != "open")
    return {"exists": exists, "threads": items, "counts": counts, "status": status or "all",
            "warnings": warnings}


def reply_hint(app, thread_id: str, status: str) -> dict:
    available = app.repo.path(THREADS_SCRIPT).is_file()
    base = f".venv/bin/python {THREADS_SCRIPT}"
    if status == "open":
        command = f'{base} reply {thread_id} --author user --type decision --content "..."'
        close_command = f'{base} close {thread_id} --author user --content "..."'
    else:
        command = f'{base} reopen {thread_id} --author user --content "..."'
        close_command = None
    return {"available": available, "command": command if available else None,
            "close_command": close_command if available else None,
            "skill": THREADS_SKILL if app.repo.path(THREADS_SKILL).is_file() else None}


def thread_detail(app, thread_id: str) -> dict:
    valid_id(thread_id, "thread id")
    threads, warnings, _ = _threads(app)
    thread = next((item for item in threads if item["id"] == thread_id), None)
    if thread is None:
        raise NotFound(f"no thread {thread_id}")
    item = _thread_item(thread, _thread_blockers(app))
    messages = _messages(thread)
    index, lab_warnings, _ = _labs_index(app)
    lab_ids = list(item["related_labs"])
    for lab_id in sorted(app.repo.lab_ids()):
        record, _ = _lab_record(app, lab_id, index)
        if thread_id in string_list(record.get("discussion")) and lab_id not in lab_ids:
            lab_ids.append(lab_id)
    known = app.repo.lab_ids() | set(index)
    labs = []
    for lab_id in lab_ids:
        if lab_id in known:
            record, _ = _lab_record(app, lab_id, index)
            labs.append({"id": lab_id, "exists": True, "title": _text(record.get("title")) or lab_id,
                         "stage": _text(record.get("stage"))})
        else:
            labs.append({"id": lab_id, "exists": False, "title": lab_id, "stage": ""})
    ids = [entry["id"] for entry in threads]
    position = ids.index(thread_id)
    out = {**item, "messages": messages, "labs": labs, "reply": reply_hint(app, thread_id, item["status"]),
           "previous": ids[position - 1] if position > 0 else None,
           "next": ids[position + 1] if position + 1 < len(ids) else None,
           "warnings": warnings + lab_warnings}
    out["links"] = link_map(app, "\n\n".join(message["content"] for message in messages),
                            ".auto-research/state.json")
    return out


# -- wiki ---------------------------------------------------------------------------------------


def wiki_tree(app) -> dict:
    exists = app.repo.path("wiki").is_dir()
    tree = app.wiki.tree()
    return {"exists": exists, "tree": tree, "count": tree["count"]}


def wiki_page(app, page_id: str) -> dict:
    page_id = (page_id or "").strip().strip("/")
    if page_id.endswith(".md"):
        page_id = page_id[:-3]
    normalize_rel(f"wiki/{page_id or 'index'}.md")
    index = app.wiki.index()
    if not page_id:
        page_id = "index"
    if page_id == "index" and page_id not in index.pages and "README" in index.pages:
        page_id = "README"
    page = index.pages.get(page_id)
    if page is None:
        if f"{page_id}/index" in index.pages:
            return {"redirect": f"/wiki/{page_id}/index", "id": f"{page_id}/index"}
        folder = app.repo.path(f"wiki/{page_id}")
        if folder.is_dir():
            node = _tree_node(app.wiki.tree(), page_id)
            if node is not None:
                return {"folder": node, "id": page_id, "title": title_from_name(page_id.rsplit("/", 1)[-1])}
        found = index.lookup(page_id)
        if found:
            return {"redirect": f"/wiki/{found}", "id": found}
        raise NotFound(f"no wiki page {page_id}")
    path = app.repo.path(page.path)
    doc = markdown_doc(app, page.path, path)
    parts = page_id.split("/")
    crumbs = []
    for depth in range(1, len(parts)):
        folder_id = "/".join(parts[:depth])
        crumbs.append({"name": parts[depth - 1], "id": folder_id,
                       "page": f"{folder_id}/index" if f"{folder_id}/index" in index.pages else None})
    backlinks = [index.pages[other].summary() for other in index.backlinks().get(page_id, [])
                 if other in index.pages]
    return {"id": page_id, **page.summary(), "doc": doc, "breadcrumbs": crumbs, "backlinks": backlinks}


def _tree_node(tree: dict, folder_id: str) -> dict | None:
    node = tree
    for part in folder_id.split("/"):
        node = next((child for child in node["folders"] if child["name"] == part), None)
        if node is None:
            return None
    return node


# -- home ---------------------------------------------------------------------------------------


def home(app) -> dict:
    threads_raw, thread_warnings, _ = _threads(app)
    by_id = {thread["id"]: thread for thread in threads_raw}
    research = auto_research(app, by_id)
    blockers = _thread_blockers(app)
    threads = [_thread_item(thread, blockers) for thread in threads_raw]
    open_threads = sorted((item for item in threads if item["status"] == "open"),
                          key=lambda item: item["updated"], reverse=True)
    labs = labs_list(app)
    recent = sorted(labs["labs"], key=lambda item: (item["updated"] or item["created"], item["id"]), reverse=True)
    active = [item for item in recent if item["stage"] in ("active", "blocked")]
    refs = references_list(app)
    wiki_index = app.wiki.index()
    compiled_pages = [page for page in wiki_index.pages.values() if not page.id.startswith("records/")]
    folder_counts: dict[str, int] = {}
    for page in compiled_pages:
        folder = page.id.split("/", 1)[0] if "/" in page.id else "overview"
        folder_counts[folder] = folder_counts.get(folder, 0) + 1
    recent_pages = sorted(wiki_index.pages.values(), key=lambda page: (page.updated or "", page.mtime),
                          reverse=True)[:6]
    warnings = []
    for source in (research["warnings"], thread_warnings, labs["warnings"], refs["warnings"]):
        for warning in source:
            _add(warnings, warning)
    return {
        "auto_research": {key: research[key] for key in (
            "exists", "status", "flag_status", "liveness", "checked_at", "updated", "next_action",
            "active_deliverable", "pending_threads", "last_action", "counts")} | {
                "tasks": research["tasks"], "links": research["links"]},
        "open_threads": open_threads,
        "thread_counts": _status_counts((item["status"] for item in threads), THREAD_STATUSES),
        "active_labs": active[:12], "recent_labs": recent[:8],
        "lab_counts": labs["counts"], "lab_total": len(labs["labs"]),
        "reference_counts": refs["counts"], "reference_total": len(refs["references"]),
        "reference_kinds": refs["kinds"],
        "wiki": {"pages": len(wiki_index.pages), "compiled": len(compiled_pages),
                 "records": len(wiki_index.pages) - len(compiled_pages),
                 "folders": folder_counts, "recent": [page.summary() for page in recent_pages]},
        "warnings": warnings,
    }
