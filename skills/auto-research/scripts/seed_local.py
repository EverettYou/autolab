"""Ensure `.auto-research/state.json` exists with the auto-research loop schema.

This repository tracks an empty `state.json` as part of the minimum scaffold. This script only creates
one when the file is missing (broken or pre-scaffold checkout). Consumer projects gitignore live
loop data (`state.json`, task bodies, thread files) but keep the README contracts tracked and
OS-synced via ``sync_apply``.

Threads layout:
- ``state.threads`` — ordered meta (id, title, category, priority, status, related_labs,
  created, updated); **no** ``messages``
- ``threads/<id>.json`` — ``{"messages": [...]}`` only

Migrates legacy shapes: embedded full threads, ``thread_ids`` + full files, or ``threads.json``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "auto-research-1"
THREAD_META_KEYS = ("id", "title", "category", "priority", "status", "related_labs",
                    "created", "updated")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state() -> dict:
    return {
        "schema": SCHEMA,
        "status": "paused",
        "updated": _now(),
        "active_deliverable": None,
        "next_action": "Start the loop only on your own branch after the researcher sets an active deliverable.",
        "last_action": None,
        "last_supervisor_at": None,
        "idle": None,
        "tasks": [],
        "threads": [],
    }


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _legacy_threads(legacy: Path) -> list:
    if not legacy.is_file():
        return []
    try:
        payload = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict) and isinstance(payload.get("threads"), list):
        return payload["threads"]
    if isinstance(payload, list):
        return payload
    return []


def _meta_of(thread: dict) -> dict:
    return {key: thread[key] for key in THREAD_META_KEYS if key in thread}


def _split_thread(folder: Path, thread: dict) -> dict:
    """Write messages-only file; return meta row for state.threads."""
    tid = thread["id"]
    messages = thread.get("messages")
    path = folder / f"{tid}.json"
    if isinstance(messages, list):
        _write_json(path, {"messages": messages})
    elif path.is_file():
        # Already a file; if it's a full Thread, peel messages.
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and "messages" in payload and set(payload) != {"messages"}:
            _write_json(path, {"messages": payload["messages"]})
        elif isinstance(payload, list):
            _write_json(path, {"messages": payload})
    return _meta_of(thread)


def _migrate_threads(root: Path, state: dict) -> bool:
    """Normalize to meta-in-state + messages-only files. Returns True if state changed."""
    auto = root / ".auto-research"
    folder = auto / "threads"
    folder.mkdir(parents=True, exist_ok=True)
    changed = False

    if "pending_human_thread_id" in state:
        state.pop("pending_human_thread_id", None)
        changed = True

    if not state.get("schema"):
        state["schema"] = SCHEMA
        changed = True

    # Legacy: thread_ids + full files (or messages files).
    if "thread_ids" in state:
        ids = state.pop("thread_ids")
        changed = True
        metas: list[dict] = []
        if isinstance(ids, list):
            for tid in ids:
                if not isinstance(tid, str):
                    continue
                path = folder / f"{tid}.json"
                if not path.is_file():
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict) and "id" in payload and "messages" in payload:
                    metas.append(_split_thread(folder, payload))
                elif isinstance(payload, dict) and set(payload) == {"messages"}:
                    # Meta must already be elsewhere; synthesize a stub only if needed later.
                    # Prefer existing state.threads if present.
                    pass
                elif isinstance(payload, list):
                    _write_json(path, {"messages": payload})
        # If we also had embedded threads with meta, prefer those below.
        if isinstance(state.get("threads"), list) and state["threads"]:
            pass
        elif metas:
            state["threads"] = metas

    raw = state.get("threads")
    legacy = _legacy_threads(auto / "threads.json")
    sources: list[dict] = []
    if isinstance(raw, list) and raw:
        sources = [t for t in raw if isinstance(t, dict) and isinstance(t.get("id"), str)]
    elif legacy:
        sources = [t for t in legacy if isinstance(t, dict) and isinstance(t.get("id"), str)]
        changed = True

    if not sources and not isinstance(state.get("threads"), list):
        state["threads"] = []
        return True

    if not sources:
        # Ensure messages-only shape for any existing files paired with meta rows.
        for meta in state.get("threads") or []:
            if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
                continue
            if "messages" in meta:
                _split_thread(folder, meta)
                changed = True
            else:
                path = folder / f"{meta['id']}.json"
                if path.is_file():
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(payload, dict) and set(payload) != {"messages"} and "messages" in payload:
                        _write_json(path, {"messages": payload["messages"]})
                        changed = True
                    elif isinstance(payload, list):
                        _write_json(path, {"messages": payload})
                        changed = True
        # Strip messages from meta rows if still present.
        cleaned = []
        for meta in state.get("threads") or []:
            if not isinstance(meta, dict):
                continue
            if "messages" in meta:
                cleaned.append(_meta_of(meta))
                changed = True
            else:
                cleaned.append(meta)
        if cleaned != state.get("threads"):
            state["threads"] = cleaned
            changed = True
        return changed

    # Full split from source threads (embedded or legacy).
    metas = []
    for thread in sources:
        if "messages" in thread or (folder / f"{thread['id']}.json").is_file():
            metas.append(_split_thread(folder, thread))
        else:
            metas.append(_meta_of(thread))
        if "messages" in thread:
            changed = True
    state["threads"] = metas
    legacy_path = auto / "threads.json"
    if legacy_path.is_file():
        legacy_path.unlink()
        changed = True
    return changed


def seed_local_files(root: Path) -> None:
    root = Path(root)
    auto = root / ".auto-research"
    auto.mkdir(parents=True, exist_ok=True)
    (auto / "tasks").mkdir(parents=True, exist_ok=True)
    (auto / "threads").mkdir(parents=True, exist_ok=True)
    path = auto / "state.json"
    legacy = auto / "threads.json"

    if not path.is_file():
        state = default_state()
        threads = _legacy_threads(legacy)
        if threads:
            state["threads"] = threads
        _migrate_threads(root, state)
        _write_json(path, state)
    else:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = None
        if isinstance(state, dict):
            changed = _migrate_threads(root, state)
            if "idle" not in state:
                state["idle"] = None
                changed = True
            elif state.get("status") != "idle":
                if state.get("idle") is not None:
                    state["idle"] = None
                    changed = True
            if "last_supervisor_at" not in state:
                state["last_supervisor_at"] = None
                changed = True
            if changed:
                _write_json(path, state)

    site_defaults = root / "dashboard" / "frontend" / "site.defaults.json"
    site = root / "dashboard" / "frontend" / "site.json"
    if site_defaults.is_file() and not site.exists():
        site.write_text(site_defaults.read_text(encoding="utf-8"), encoding="utf-8")
