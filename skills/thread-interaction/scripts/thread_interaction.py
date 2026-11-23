#!/usr/bin/env python3
"""Threads: meta in ``state.json["threads"]``, messages in ``.auto-research/threads/<id>.json``.

Each ``state.threads`` entry keeps the Thread fields (id, title, category, priority, status,
related_labs, created, updated) — not ``messages``. The companion file stores only
``{"messages": [...]}``. Run from the repository root:

    .venv/bin/python skills/thread-interaction/scripts/thread_interaction.py <command> ...

Commands: list, show, open, reply, close, reopen, validate. Writers only append messages, assign
sequential ids, and replace message files + ``state.json`` under the same lock as ``loop_state.py``.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3]
CATEGORIES = ("direction", "decision", "scope", "checkpoint")
PRIORITIES = ("high", "normal", "low")
STATUSES = ("open", "closed")
AUTHORS = ("user", "agent")
TYPES = ("instruction", "question", "decision", "reply", "resolution")
# Message types only one side may write. A resolution is either side's close: an agent after the
# work, or the researcher from the dashboard or with `close --author user`.
TYPE_AUTHOR = {"instruction": "user", "decision": "user", "question": "agent"}
OPENING_TYPES = ("instruction", "question")
THREAD_KEYS = {"id", "title", "category", "priority", "status", "related_labs", "created", "updated",
               "messages"}  # full in-memory Thread (meta + messages)
THREAD_META_KEYS = THREAD_KEYS - {"messages"}  # persisted in state.json["threads"]
MESSAGE_FILE_KEYS = {"messages"}  # persisted in threads/<id>.json
MESSAGE_KEYS = {"id", "author", "type", "created", "content"}
LAB_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-[A-Za-z0-9][A-Za-z0-9._-]*$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
THREAD_REF = re.compile(r"\bthread-\d+\b")
THREAD_ID = re.compile(r"^thread-\d{3,}$")
MAX_TITLE = 200


class ThreadsError(Exception):
    """A request the threads store refuses; the message says why."""


def decision_cycle_applied(messages: list) -> bool:
    """True once a researcher decision has already been taken up by an agent reply.

    A clarifying question *before* any agent reply after the decision is still the same concern.
    A new question *after* the agent has already replied is usually a new concern → new thread.
    """
    pending = False
    for message in messages:
        if message.get("author") == "user" and message.get("type") == "decision":
            pending = True
            continue
        if pending and message.get("author") == "agent" and message.get("type") == "reply":
            return True
    return False


def check_hygiene(thread: dict, author: str, kind: str, *, continue_thread: bool = False) -> None:
    """Refuse the agent posts that recreate mega-threads or bury an open question.

    Deliberately narrow (skills/thread-interaction/SKILL.md, Thread hygiene):
    - Hard: never agent-reply on top of your own unanswered question (clears awaiting-reply).
    - Soft: a *new* question after a decision the agent already acknowledged → open a new thread.
      Clarifying questions before that acknowledgment are allowed on the same thread.
    No message-count cap. Researcher posts are never blocked. `--continue-thread` overrides for
    the same open concern.
    """
    if author != "agent" or continue_thread:
        return
    messages = thread["messages"]
    tid = thread["id"]
    last = messages[-1]
    if kind == "reply" and last.get("author") == "agent" and last.get("type") == "question":
        raise ThreadsError(
            f"{tid}: an agent reply after your own question clears the awaiting-reply badge while "
            "the question is still open. Put progress in the lab REPORT.md; if a note is essential, "
            "end with reply --type question restating the open question (or pass --continue-thread)."
        )
    if kind == "question" and decision_cycle_applied(messages):
        raise ThreadsError(
            f"{tid} already has a researcher decision that an agent reply took up. That concern is "
            "done or in progress—open a new thread for a *new* question. Pass --continue-thread "
            "only if this is still the same open concern (e.g. correcting the brief)."
        )


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_path(root: Path) -> Path:
    return root / ".auto-research" / "state.json"


def threads_dir(root: Path) -> Path:
    return root / ".auto-research" / "threads"


def thread_path(root: Path, thread_id: str) -> Path:
    return threads_dir(root) / f"{thread_id}.json"


def threads_path(root: Path) -> Path:
    """Deprecated alias kept for callers that pointed at the old single-file store."""
    return state_path(root)


def valid_stamp(value: object) -> bool:
    if not isinstance(value, str) or not STAMP.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def write_atomic_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def meta_only(thread: dict) -> dict:
    """Persistable Thread row for ``state.json`` (no messages)."""
    return {key: thread[key] for key in (
        "id", "title", "category", "priority", "status", "related_labs", "created", "updated")}


def read_messages_file(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ThreadsError(f"{path} not found") from None
    except json.JSONDecodeError as error:
        raise ThreadsError(f"{path} is not valid JSON: {error}") from None
    if isinstance(data, list):
        return data  # bare list tolerated briefly during migration
    if not isinstance(data, dict) or set(data) != MESSAGE_FILE_KEYS:
        keys = set(data) if isinstance(data, dict) else set()
        raise ThreadsError(
            f"{path} must be {{\"messages\": [...]}} only; "
            f"missing {sorted(MESSAGE_FILE_KEYS - keys)}, unexpected {sorted(keys - MESSAGE_FILE_KEYS)}"
        )
    if not isinstance(data["messages"], list):
        raise ThreadsError(f"{path}: messages must be a list")
    return data["messages"]


def load_messages_payload(path: Path) -> list:
    """Read messages from a thread file (messages-only, or legacy full Thread object)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ThreadsError(f"{path} not found") from None
    except json.JSONDecodeError as error:
        raise ThreadsError(f"{path} is not valid JSON: {error}") from None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "messages" in payload:
        messages = payload["messages"]
        if not isinstance(messages, list):
            raise ThreadsError(f"{path}: messages must be a list")
        return messages
    raise ThreadsError(f"{path} must be {{\"messages\": [...]}}")


def load_threads(root: Path, state: dict) -> list[dict]:
    """Join ``state.threads`` meta with ``threads/<id>.json`` messages (in list order)."""
    metas = state.get("threads")
    if not isinstance(metas, list):
        return []
    out: list[dict] = []
    for meta in metas:
        if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
            continue
        tid = meta["id"]
        path = thread_path(root, tid)
        if path.is_file():
            messages = load_messages_payload(path)
        elif isinstance(meta.get("messages"), list):
            messages = meta["messages"]  # legacy embedded
        else:
            raise ThreadsError(f"thread file missing: {path.relative_to(root)}")
        thread = {**{k: meta[k] for k in THREAD_META_KEYS if k in meta}, "messages": messages}
        out.append(thread)
    return out


def validate_messages(messages: object, *, where: str, created: object = None,
                      updated: object = None, status: object = None) -> list[str]:
    problems: list[str] = []
    if not isinstance(messages, list) or not messages:
        problems.append(f"{where}: messages must be a non-empty list")
        return problems
    previous = None
    for k, message in enumerate(messages, start=1):
        mwhere = f"{where}/msg-{k:03d}"
        if not isinstance(message, dict) or set(message) != MESSAGE_KEYS:
            problems.append(f"{mwhere}: keys must be {sorted(MESSAGE_KEYS)}")
            previous = None
            continue
        if message["id"] != f"msg-{k:03d}":
            problems.append(f"{mwhere}: id {message['id']!r} out of sequence")
        if message["author"] not in AUTHORS:
            problems.append(f"{mwhere}: author {message['author']!r} not in {AUTHORS}")
        if message["type"] not in TYPES:
            problems.append(f"{mwhere}: type {message['type']!r} not in {TYPES}")
        elif TYPE_AUTHOR.get(message["type"], message["author"]) != message["author"]:
            problems.append(f"{mwhere}: a {message['type']} must be written by {TYPE_AUTHOR[message['type']]}")
        if not isinstance(message["content"], str) or not message["content"].strip():
            problems.append(f"{mwhere}: content must be non-empty markdown")
        if not valid_stamp(message["created"]):
            problems.append(f"{mwhere}: created must be an ISO-8601 UTC timestamp")
        elif previous and message["created"] < previous:
            problems.append(f"{mwhere}: created goes backwards in time")
        else:
            previous = message["created"]
    first, last = messages[0], messages[-1]
    if isinstance(first, dict) and first.get("type") not in OPENING_TYPES:
        problems.append(f"{where}: the first message must be an instruction or a question")
    if isinstance(first, dict) and valid_stamp(created) and first.get("created") != created:
        problems.append(f"{where}: created must equal the first message's timestamp")
    if (isinstance(last, dict) and valid_stamp(updated) and valid_stamp(last.get("created"))
            and updated < last["created"]):
        problems.append(f"{where}: updated is older than the last message")
    if status == "closed" and isinstance(last, dict) and last.get("type") != "resolution":
        problems.append(f"{where}: a closed thread must end with a resolution")
    return problems


def validate_meta(meta: object, *, expected_id: str | None = None, where: str | None = None) -> list[str]:
    """Validate a ``state.threads[]`` row (no messages)."""
    problems: list[str] = []
    label = where or (expected_id if isinstance(expected_id, str) else "thread")
    if not isinstance(meta, dict):
        return [f"{label}: must be a JSON object"]
    keys = set(meta)
    if "messages" in keys:
        problems.append(f"{label}: unexpected key 'messages' (messages live in threads/<id>.json)")
        keys = keys - {"messages"}
    if keys != THREAD_META_KEYS:
        problems.append(f"{label}: keys must be {sorted(THREAD_META_KEYS)}; "
                        f"missing {sorted(THREAD_META_KEYS - keys)}, unexpected {sorted(keys - THREAD_META_KEYS)}")
        return problems
    if expected_id is not None and meta["id"] != expected_id:
        problems.append(f"{label}: id {meta['id']!r} should be {expected_id!r}")
    elif not isinstance(meta["id"], str) or not THREAD_ID.match(meta["id"]):
        problems.append(f"{label}: id {meta['id']!r} must look like thread-001")
    where = meta["id"] if isinstance(meta.get("id"), str) else label
    title = meta["title"]
    if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE or "\n" in title:
        problems.append(f"{where}: title must be one non-empty line of at most {MAX_TITLE} characters")
    for key, allowed in (("category", CATEGORIES), ("priority", PRIORITIES), ("status", STATUSES)):
        if meta[key] not in allowed:
            problems.append(f"{where}: {key} {meta[key]!r} not in {allowed}")
    labs = meta["related_labs"]
    if (not isinstance(labs, list) or len(set(map(str, labs))) != len(labs)
            or not all(isinstance(lab, str) and LAB_ID.match(lab) for lab in labs)):
        problems.append(f"{where}: related_labs must be a list of distinct lab ids (YYYY-MM-DD-slug)")
    for key in ("created", "updated"):
        if not valid_stamp(meta[key]):
            problems.append(f"{where}: {key} must be an ISO-8601 UTC timestamp like 2026-01-31T09:00:00Z")
    return problems


def validate_thread(thread: object, *, expected_id: str | None = None, where: str | None = None) -> list[str]:
    """Return schema problems for one full in-memory Thread (meta + messages)."""
    problems: list[str] = []
    label = where or (expected_id if isinstance(expected_id, str) else "thread")
    if not isinstance(thread, dict) or set(thread) != THREAD_KEYS:
        keys = set(thread) if isinstance(thread, dict) else set()
        problems.append(f"{label}: keys must be {sorted(THREAD_KEYS)}; "
                        f"missing {sorted(THREAD_KEYS - keys)}, unexpected {sorted(keys - THREAD_KEYS)}")
        return problems
    problems.extend(validate_meta(
        {k: thread[k] for k in THREAD_META_KEYS},
        expected_id=expected_id, where=label,
    ))
    where = thread["id"] if isinstance(thread.get("id"), str) else label
    problems.extend(validate_messages(
        thread["messages"], where=where,
        created=thread.get("created"), updated=thread.get("updated"), status=thread.get("status"),
    ))
    return problems


def validate_threads_list(threads: object) -> list[str]:
    """Return every schema problem in an ordered full-Threads list (empty list = valid)."""
    if not isinstance(threads, list):
        return ["threads must be a list"]
    problems: list[str] = []
    for n, thread in enumerate(threads, start=1):
        expected = f"thread-{n:03d}"
        problems.extend(validate_thread(thread, expected_id=expected, where=f"threads[{n - 1}]"))
    return problems


def validate_store(root: Path, state: dict, threads: list[dict] | None = None) -> list[str]:
    """Validate ``state.threads`` meta + on-disk message files (or an explicit full list)."""
    problems: list[str] = []
    metas = state.get("threads")
    if not isinstance(metas, list):
        return ['state["threads"] must be a list of Thread meta objects']
    ids: list[str] = []
    for n, meta in enumerate(metas):
        expected = f"thread-{n + 1:03d}"
        problems.extend(validate_meta(meta, expected_id=expected, where=f"threads[{n}]"))
        if isinstance(meta, dict) and isinstance(meta.get("id"), str):
            ids.append(meta["id"])
    if len(ids) != len(set(ids)):
        problems.append("threads must not contain duplicate ids")

    if threads is not None:
        problems.extend(validate_threads_list(threads))
    else:
        for meta in metas:
            if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
                continue
            tid = meta["id"]
            path = thread_path(root, tid)
            rel = f".auto-research/threads/{tid}.json"
            if not path.is_file():
                problems.append(f"{rel} is missing")
                continue
            try:
                messages = read_messages_file(path)
            except ThreadsError as error:
                problems.append(str(error))
                continue
            problems.extend(validate_messages(
                messages, where=tid,
                created=meta.get("created"), updated=meta.get("updated"), status=meta.get("status"),
            ))

    folder = threads_dir(root)
    if folder.is_dir():
        known = set(ids)
        for orphan in sorted(p.name for p in folder.glob("thread-*.json") if p.stem not in known):
            problems.append(f"threads/{orphan} has no entry in state.threads (delete it or add the meta)")
    return problems


def validate(data: object) -> list[str]:
    """Validate an in-memory state that embeds full ``threads`` (unit-test helper)."""
    if not isinstance(data, dict):
        return ["state must be a JSON object"]
    if "threads" not in data:
        return ['state must contain a "threads" list']
    return validate_threads_list(data["threads"])


def seed_checkout(root: Path) -> None:
    scripts = Path(__file__).resolve().parents[2] / "auto-research" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from seed_local import seed_local_files

    seed_local_files(root)


def load(root: Path) -> dict:
    """Load ``state.json`` and join messages so ``state["threads"]`` is full in memory."""
    seed_checkout(root)
    path = state_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ThreadsError(f"{path} not found") from None
    except json.JSONDecodeError as error:
        raise ThreadsError(f"{path} is not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise ThreadsError(f"{path} must contain a JSON object")
    # Migration may rewrite thread_ids / full files into meta + messages-only.
    if "thread_ids" in data or (
        isinstance(data.get("threads"), list)
        and data["threads"]
        and isinstance(data["threads"][0], dict)
        and "messages" in data["threads"][0]
    ):
        seed_checkout(root)
        data = json.loads(path.read_text(encoding="utf-8"))
    problems = validate_store(root, data)
    if problems:
        raise ThreadsError(f"{path} Threads fail validation:\n  " + "\n  ".join(problems))
    data = dict(data)
    data["threads"] = load_threads(root, data)
    return data


def check_append_only(before_threads: list[dict], after_threads: list[dict]) -> None:
    if len(after_threads) < len(before_threads):
        raise ThreadsError("refusing to write: a thread would be removed")
    for a, b in zip(before_threads, after_threads):
        if a["id"] != b["id"] or b["messages"][:len(a["messages"])] != a["messages"]:
            raise ThreadsError(f"refusing to write: existing messages of {a['id']} would change")


@contextmanager
def locked(root: Path):
    """Share the loop-state lock so Threads and tasks never interleave writes."""
    lock_dir = root / ".tmp"
    lock_dir.mkdir(exist_ok=True)
    with open(lock_dir / "loop_state.lock", "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def mutate(root: Path, change):
    """Apply `change(state_with_full_threads)` under the lock; write meta + message files."""
    with locked(root):
        before = load(root)
        after = copy.deepcopy(before)
        result = change(after)
        after["updated"] = now()
        threads = after.get("threads")
        if not isinstance(threads, list):
            raise ThreadsError("internal error: threads list missing after change")
        metas = [meta_only(t) for t in threads]
        to_write = dict(after)
        to_write["threads"] = metas
        to_write.pop("thread_ids", None)
        problems = validate_store(root, to_write, threads=threads)
        if problems:
            raise ThreadsError("refusing to write invalid Threads:\n  " + "\n  ".join(problems))
        check_append_only(before["threads"], threads)
        for thread in threads:
            write_atomic_json(thread_path(root, thread["id"]), {"messages": thread["messages"]})
        write_atomic_json(state_path(root), to_write)
    return result


def find(data: dict, thread_id: str) -> dict:
    thread = next((t for t in data["threads"] if t["id"] == thread_id), None)
    if thread is None:
        raise ThreadsError(f"unknown thread: {thread_id}")
    return thread


def append(thread: dict, author: str, kind: str, content: str) -> dict:
    stamp = max(now(), thread["messages"][-1]["created"])
    message = {"id": f"msg-{len(thread['messages']) + 1:03d}", "author": author, "type": kind,
               "created": stamp, "content": content}
    thread["messages"].append(message)
    thread["updated"] = max(stamp, thread["updated"])
    return message


def blocking_tasks(root: Path) -> dict[str, list[str]]:
    """Map each thread id to the task-list items whose `blocked_on` cites it."""
    path = root / ".auto-research" / "state.json"
    try:
        tasks = json.loads(path.read_text(encoding="utf-8")).get("tasks") or []
    except (OSError, ValueError, AttributeError):
        return {}
    out: dict[str, list[str]] = {}
    for task in tasks if isinstance(tasks, list) else []:
        if not isinstance(task, dict):
            continue
        blocked = task.get("blocked_on")
        text = " ".join(map(str, blocked)) if isinstance(blocked, list) else str(blocked or "")
        for thread_id in dict.fromkeys(THREAD_REF.findall(text)):
            out.setdefault(thread_id, []).append(str(task.get("id")))
    return out


def awaiting(thread: dict, blocks: list[str]) -> str | None:
    """Who the thread waits on. The researcher, only while the latest message is a question that
    holds a task. The agent, after the researcher spoke last. A progress report waits on nobody."""
    if thread["status"] != "open":
        return None
    last = thread["messages"][-1]
    if last["author"] == "user":
        return "agent"
    if last.get("type") == "question" and blocks:
        return "user"
    return None


def summary(thread: dict, blocked: dict[str, list[str]], message: dict | None = None) -> dict:
    blocks = blocked.get(thread["id"], []) if thread["status"] == "open" else []
    out = {"id": thread["id"], "title": thread["title"], "status": thread["status"],
           "category": thread["category"], "priority": thread["priority"],
           "awaiting": awaiting(thread, blocks), "blocks": blocks, "updated": thread["updated"]}
    if message is not None:
        out["message"] = message["id"]
    return out


def read_content(args: argparse.Namespace) -> str:
    if args.content_file is not None:
        source = sys.stdin if args.content_file == "-" else open(args.content_file, encoding="utf-8")
        with source:
            text = source.read()
    else:
        text = args.content
    if text is None or not text.strip():
        raise ThreadsError("content is empty")
    return text.strip("\n")


def check_labs(root: Path, labs: list[str]) -> list[str]:
    for lab in labs:
        if not LAB_ID.match(lab):
            raise ThreadsError(f"not a lab id (expected YYYY-MM-DD-slug): {lab}")
        if not (root / "labs" / lab).is_dir():
            raise ThreadsError(f"no such lab: labs/{lab}")
    return sorted(set(labs))


def cmd_list(root: Path, args: argparse.Namespace) -> list[dict]:
    threads = [t for t in load(root)["threads"] if args.status is None or t["status"] == args.status]
    threads.sort(key=lambda t: t["updated"], reverse=True)
    blocked = blocking_tasks(root)
    return [summary(t, blocked) for t in threads]


def cmd_show(root: Path, args: argparse.Namespace) -> dict:
    return find(load(root), args.thread_id)


def cmd_open(root: Path, args: argparse.Namespace) -> dict:
    kind = args.type or ("question" if args.author == "agent" else "instruction")
    if kind not in OPENING_TYPES:
        raise ThreadsError("a thread opens with a question (agent) or an instruction (user)")
    if TYPE_AUTHOR[kind] != args.author:
        raise ThreadsError(f"a {kind} must be written by {TYPE_AUTHOR[kind]}")
    category = args.category or ("direction" if kind == "instruction" else "decision")
    title = args.title.strip()
    content = read_content(args)
    labs = check_labs(root, args.lab)

    def change(data: dict):
        duplicate = next((t for t in data["threads"]
                          if t["status"] == "open" and t["title"].casefold() == title.casefold()), None)
        if duplicate:
            raise ThreadsError(f"{duplicate['id']} is already open with this title; reply to it instead")
        stamp = now()
        message = {"id": "msg-001", "author": args.author, "type": kind, "created": stamp, "content": content}
        thread = {"id": f"thread-{len(data['threads']) + 1:03d}", "title": title, "category": category,
                  "priority": args.priority, "status": "open", "related_labs": labs, "created": stamp,
                  "updated": stamp, "messages": [message]}
        data["threads"].append(thread)
        return summary(thread, blocking_tasks(root), message)

    return mutate(root, change)


def cmd_reply(root: Path, args: argparse.Namespace) -> dict:
    if args.type == "resolution":
        raise ThreadsError("post a resolution with `close`")
    if TYPE_AUTHOR.get(args.type, args.author) != args.author:
        raise ThreadsError(f"a {args.type} must be written by {TYPE_AUTHOR[args.type]}")
    content = read_content(args)
    labs = check_labs(root, args.lab)

    def change(data: dict):
        thread = find(data, args.thread_id)
        if thread["status"] != "open":
            raise ThreadsError(f"{thread['id']} is closed; reopen it first")
        # Dashboard (and any thin Namespace) may omit the CLI-only flag; default False.
        # Researcher posts are never blocked by hygiene regardless of this value.
        check_hygiene(
            thread, args.author, args.type,
            continue_thread=bool(getattr(args, "continue_thread", False)),
        )
        message = append(thread, args.author, args.type, content)
        thread["related_labs"] = sorted(set(thread["related_labs"]) | set(labs))
        return summary(thread, blocking_tasks(root), message)

    return mutate(root, change)


def cmd_close(root: Path, args: argparse.Namespace) -> dict:
    content = read_content(args)
    author = args.author or "agent"

    def change(data: dict):
        thread = find(data, args.thread_id)
        if thread["status"] != "open":
            raise ThreadsError(f"{thread['id']} is already closed")
        message = append(thread, author, "resolution", content)
        thread["status"] = "closed"
        return summary(thread, blocking_tasks(root), message)

    return mutate(root, change)


def cmd_reopen(root: Path, args: argparse.Namespace) -> dict:
    if TYPE_AUTHOR.get(args.type, args.author) != args.author:
        raise ThreadsError(f"a {args.type} must be written by {TYPE_AUTHOR[args.type]}")
    content = read_content(args)

    def change(data: dict):
        thread = find(data, args.thread_id)
        if thread["status"] != "closed":
            raise ThreadsError(f"{thread['id']} is already open")
        thread["status"] = "open"
        message = append(thread, args.author, args.type, content)
        return summary(thread, blocking_tasks(root), message)

    return mutate(root, change)


def cmd_validate(root: Path, args: argparse.Namespace) -> dict:
    threads = load(root)["threads"]
    n_open = sum(1 for t in threads if t["status"] == "open")
    return {"ok": True, "threads": len(threads), "open": n_open, "closed": len(threads) - n_open}


def render(command: str, result) -> str:
    if command == "list":
        rows = [f"{t['id']}  {t['status']:6s}  {t['priority']:6s}  {t['category']:10s}  "
                f"{'awaiting ' + t['awaiting'] if t['awaiting'] else '-':15s}  {t['updated']}  {t['title']}"
                for t in result]
        return "\n".join(rows) if rows else "(no threads)"
    if command == "show":
        t = result
        head = [f"{t['id']}  [{t['status']}]  {t['category']} / {t['priority']}  {t['title']}",
                f"created {t['created']}  updated {t['updated']}"
                + (f"  labs: {', '.join(t['related_labs'])}" if t["related_labs"] else "")]
        for m in t["messages"]:
            head += ["", f"--- {m['id']}  {m['author']} {m['type']}  {m['created']}", m["content"]]
        return "\n".join(head)
    if command == "validate":
        return f"ok: {result['threads']} threads ({result['open']} open, {result['closed']} closed)"
    waiting = f", awaiting {result['awaiting']}" if result["awaiting"] else ""
    return f"{result['id']} {result['message']}: {command} ({result['status']}{waiting})"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read and append Threads under .auto-research/threads/ (order in state.json).")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="project root holding .auto-research/ (default: this repository)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print machine-readable JSON")
    content = argparse.ArgumentParser(add_help=False)
    source = content.add_mutually_exclusive_group(required=True)
    source.add_argument("--content", help="message markdown")
    source.add_argument("--content-file", help="read the message markdown from a file ('-' for stdin)")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", parents=[common], help="list threads, most recently updated first")
    listing.add_argument("--status", choices=STATUSES)
    showing = commands.add_parser("show", parents=[common], help="print one thread with all messages")
    showing.add_argument("thread_id")

    opening = commands.add_parser("open", parents=[common, content], help="open a new thread")
    opening.add_argument("--title", required=True)
    opening.add_argument("--category", choices=CATEGORIES,
                         help="default: decision for a question, direction for an instruction")
    opening.add_argument("--priority", choices=PRIORITIES, default="normal")
    opening.add_argument("--lab", action="append", default=[], help="related lab id (repeatable)")
    opening.add_argument("--author", choices=AUTHORS, default="agent")
    opening.add_argument("--type", choices=OPENING_TYPES,
                         help="default: question for an agent, instruction for the user")

    replying = commands.add_parser("reply", parents=[common, content], help="append a message to an open thread")
    replying.add_argument("thread_id")
    replying.add_argument("--author", choices=AUTHORS, required=True)
    replying.add_argument("--type", choices=TYPES, default="reply")
    replying.add_argument("--lab", action="append", default=[], help="add a related lab id (repeatable)")
    replying.add_argument(
        "--continue-thread", action="store_true",
        help="agent only: override hygiene (same open concern; never for a new decision or progress dump)")

    closing = commands.add_parser("close", parents=[common, content],
                                  help="append a resolution and close the thread")
    closing.add_argument("thread_id")
    closing.add_argument("--author", choices=AUTHORS, default="agent",
                         help="who is closing (default: agent)")

    reopening = commands.add_parser("reopen", parents=[common, content],
                                    help="reopen a closed thread, recording why")
    reopening.add_argument("thread_id")
    reopening.add_argument("--author", choices=AUTHORS, required=True)
    reopening.add_argument("--type", choices=("instruction", "decision", "reply"), default="reply")

    commands.add_parser("validate", parents=[common], help="check state.threads meta and message files")
    return parser


COMMANDS = {"list": cmd_list, "show": cmd_show, "open": cmd_open, "reply": cmd_reply, "close": cmd_close,
            "reopen": cmd_reopen, "validate": cmd_validate}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        result = COMMANDS[args.command](root, args)
    except ThreadsError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(args.command, result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
