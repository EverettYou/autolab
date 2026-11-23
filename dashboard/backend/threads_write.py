"""Record a researcher's words in `.auto-research/threads/<id>.json` from the dashboard.

The browser always writes as ``author=user``. Opening, replying, closing and reopening go through
``skills/research-threads/scripts/research_threads.py``, so the dashboard follows the same schema,
lock and append-only rules as the command line. A close from the page is the researcher's
resolution; an agent still closes with ``close`` and the default author.
"""

from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path

from .repo import BadRequest, NotFound
from .sections import THREADS_SCRIPT, thread_detail

MAX_CONTENT = 20_000


def _load_threads_module(root: Path):
    path = (root / THREADS_SCRIPT).resolve()
    if not path.is_file() or not path.is_relative_to(root.resolve()):
        raise NotFound("the research-threads Threads script is not in this checkout")
    spec = importlib.util.spec_from_file_location("lab_dashboard_threads", path)
    if spec is None or spec.loader is None:
        raise NotFound("the research-threads Threads script cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not all(hasattr(module, name) for name in ("cmd_open", "cmd_reply", "cmd_close", "cmd_reopen", "ThreadsError")):
        raise NotFound("research_threads.py in this checkout cannot record messages")
    return module


def _object(body: object) -> dict:
    if not isinstance(body, dict):
        raise BadRequest("body must be a JSON object")
    return body


def _text(body: dict, key: str, *, limit: int) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BadRequest(f"{key} must be non-empty text")
    if len(value) > limit:
        raise BadRequest(f"{key} is longer than {limit} characters")
    return value


def _choice(body: dict, key: str, allowed: tuple[str, ...], default: str | None) -> str | None:
    if key not in body or body[key] in (None, ""):
        return default
    value = body[key]
    if value not in allowed:
        raise BadRequest(f"{key} must be one of {', '.join(allowed)}")
    return value


def _labs(body: dict) -> list[str]:
    value = body.get("labs", [])
    if value in (None, ""):
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BadRequest("labs must be a list of lab ids")
    return [item for item in value if item.strip()]


def _call(module, command, root: Path, args: Namespace) -> dict:
    try:
        return command(root, args)
    except module.ThreadsError as exc:
        message = str(exc).strip()
        if len(message) > 500:
            message = message[:500] + "…"
        raise BadRequest(message) from exc


def open_thread(app, body: object) -> dict:
    """Open a thread with the researcher's instruction. Returns the new thread."""
    data = _object(body)
    module = _load_threads_module(app.root)
    summary = _call(module, module.cmd_open, app.root, Namespace(
        type="instruction", author="user", content_file=None,
        title=_text(data, "title", limit=module.MAX_TITLE),
        content=_text(data, "content", limit=MAX_CONTENT),
        category=_choice(data, "category", module.CATEGORIES, None),
        priority=_choice(data, "priority", module.PRIORITIES, "normal"),
        lab=_labs(data)))
    return thread_detail(app, summary["id"])


def reply_thread(app, thread_id: str, body: object) -> dict:
    """Append the researcher's reply, decision or further instruction."""
    data = _object(body)
    module = _load_threads_module(app.root)
    _call(module, module.cmd_reply, app.root, Namespace(
        thread_id=thread_id, author="user", content_file=None,
        type=_choice(data, "type", ("reply", "decision", "instruction"), "reply"),
        content=_text(data, "content", limit=MAX_CONTENT),
        lab=_labs(data),
        # Mailbox hygiene flag for agent follow-ups; researcher posts never use it.
        continue_thread=False))
    return thread_detail(app, thread_id)


def close_thread(app, thread_id: str, body: object) -> dict:
    """Close an open thread with the researcher's resolution."""
    data = _object(body)
    module = _load_threads_module(app.root)
    _call(module, module.cmd_close, app.root, Namespace(
        thread_id=thread_id, author="user", content_file=None,
        content=_text(data, "content", limit=MAX_CONTENT)))
    return thread_detail(app, thread_id)


def reopen_thread(app, thread_id: str, body: object) -> dict:
    """Reopen a closed thread, recording why in the researcher's words."""
    data = _object(body)
    module = _load_threads_module(app.root)
    _call(module, module.cmd_reopen, app.root, Namespace(
        thread_id=thread_id, author="user", content_file=None,
        type=_choice(data, "type", ("reply", "decision", "instruction"), "instruction"),
        content=_text(data, "content", limit=MAX_CONTENT)))
    return thread_detail(app, thread_id)
