#!/usr/bin/env python3
"""Durable state of the research loop: `.auto-research/state.json`, `tasks/<id>.md`, `threads/<id>.json`.

Run from the repository root:

    .venv/bin/python skills/auto-research/scripts/loop_state.py <command> ...

Commands: status, start, pause, idle, idle-check, set-next, set-deliverable, log-action,
task {list,show,add,move,set,done,block,unblock}, validate. Every write validates the result
(including the task detail files, lab ids, and Threads) and replaces the
state file atomically under an exclusive lock; nothing is written when validation fails.

Task order and scheduling fields live in ``state.tasks``; bodies in ``tasks/<id>.md``.
Thread meta (ordered) lives in ``state.threads``; message lists in ``threads/<id>.json``.
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
from datetime import date, datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "auto-research-1"
STATUSES = ("running", "paused", "idle")
SCHEDULER_KINDS = ("session-cron", "runner", "external")
# Who owns the loop: the agent product that started it and must perform ticks itself.
SCHEDULER_OWNERS = ("claude", "codex", "cursor")
STATE_KEYS = {"schema", "status", "updated", "active_deliverable", "next_action",
              "last_action", "last_supervisor_at", "idle", "tasks", "threads"}
THREAD_META_KEYS = {"id", "title", "category", "priority", "status", "related_labs",
                    "created", "updated"}
ITEM_KEYS = {"id", "title", "for", "gpu", "time", "blocked_on", "related_labs", "detail", "added"}
IDLE_KEYS = {"reason", "detail", "lift_when", "since", "fingerprint"}
IDLE_REASONS = ("router-empty", "repeated-tick", "supervisor-refill-failed", "other")
TICK_KINDS = ("research", "supervisor", "idle-probe")
ROLES = ("scout", "reproducer", "integrator", "auditor", "maintain", "auto", "all")
GPU_TIERS = ("free", "light", "heavy")
TIME_TIERS = ("0", "1min", "5min", "15min", "30min", "1hr", "2hr", "4hr", "8hr", "1d", "2d")
# Enter idle only after side work / supervisor refill also failed; see SKILL.md.
REPEATED_TICK_IDLE_AFTER = 5
# Soft cadence: after this many minutes without a supervisor tick, status/runner force one.
SUPERVISOR_MAX_MINUTES = 60
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OWNER_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
LAB_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-[A-Za-z0-9][A-Za-z0-9._-]*$")
THREAD_ID = re.compile(r"^thread-\d{3,}$")
THREAD_REF = re.compile(r"\bthread-\d{3,}\b")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# Resource conditions are routed through `gpu`/`time` and a live snapshot, never through `blocked_on`.
RESOURCE_WORDS = re.compile(r"\b(gpus?|cuda|nvml|vram|h200s?|runtime|wall[- ]?clock|time ?caps?|credits?|"
                            r"outages?)\b", re.IGNORECASE)
STOPWORDS = {"a", "an", "the", "to", "of", "at", "on", "and", "or", "is", "for", "in", "not", "so", "by",
             "with", "re", "vs", "from", "as", "it", "its", "be", "one", "no", "when", "may", "who", "what",
             "that", "than", "if", "are", "was", "under", "against", "into", "past", "near", "via"}
MAX_SLUG = 60


class StateError(Exception):
    """A request the loop state refuses; the message says why."""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_path(root: Path) -> Path:
    return root / ".auto-research" / "state.json"


def detail_path(item_id: str) -> str:
    return f".auto-research/tasks/{item_id}.md"


TASK_BODY_SECTIONS = ("Goal", "Work", "Done when")


def check_task_body(text: str) -> list[str]:
    """Return problems in a task body (contract: .auto-research/tasks/README.md)."""
    if not isinstance(text, str) or not text.strip():
        return ["detail file is empty"]
    problems: list[str] = []
    if not text.startswith("# "):
        problems.append("detail file must start with a '# <title>' line")
        return problems
    lines = text.splitlines()
    title = lines[0][2:].strip()
    if not title:
        problems.append("detail file title after '# ' must be non-empty")
    headings: list[str] = []
    for index, line in enumerate(lines):
        if index > 0 and line.startswith("# ") and not line.startswith("## "):
            problems.append("only one top-level '# <title>' is allowed")
        if line.startswith("###"):
            problems.append(f"no ### headings (found {line!r}); use only ## Goal / ## Work / ## Done when")
        if line.startswith("## "):
            headings.append(line[3:].strip())
    if headings != list(TASK_BODY_SECTIONS):
        problems.append(
            f"## headings must be exactly {list(TASK_BODY_SECTIONS)} in that order; found {headings}"
        )
        return problems
    # Section bodies: text between this ## and the next ## / EOF, ignoring blanks.
    for n, name in enumerate(TASK_BODY_SECTIONS):
        start = next(i for i, line in enumerate(lines) if line == f"## {name}")
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break
        body_lines = [line for line in lines[start + 1:end] if line.strip()]
        if not body_lines:
            problems.append(f"## {name} must contain at least one non-blank line")
    return problems


def threads_dir(root: Path) -> Path:
    return root / ".auto-research" / "threads"


def thread_path(root: Path, thread_id: str) -> Path:
    return threads_dir(root) / f"{thread_id}.json"


def valid_stamp(value: object) -> bool:
    if not isinstance(value, str) or not STAMP.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def valid_day(value: object) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def roles_of(value: str) -> list[str]:
    return [part.strip() for part in value.split(",")]


def slugify(title: str, taken: set[str]) -> str:
    text = re.sub(r"\([^)]*\)", " ", title).replace("'", "").replace("\u2019", "")
    words = [w for w in re.sub(r"[^a-z0-9]+", "-", text.lower()).split("-") if w]
    out: list[str] = []
    for word in words:
        if len("-".join(out + [word])) > MAX_SLUG:
            break
        out.append(word)
    while len(out) > 1 and out[-1] in STOPWORDS:
        out.pop()
    base = "-".join(out) or "item"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def read_threads(root: Path, state: dict) -> dict[str, dict]:
    """Index Threads: meta from ``state.threads``, messages from ``threads/<id>.json``."""
    metas = state.get("threads")
    if not isinstance(metas, list):
        return {}
    out: dict[str, dict] = {}
    for meta in metas:
        if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
            continue
        tid = meta["id"]
        thread = {k: meta[k] for k in THREAD_META_KEYS if k in meta}
        path = thread_path(root, tid)
        messages: list = []
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
                messages = payload["messages"]
            elif isinstance(payload, list):
                messages = payload
        thread["messages"] = messages
        out[tid] = thread
    return out


def lab_exists(root: Path, lab: str) -> bool:
    return bool(LAB_ID.match(lab)) and (root / "labs" / lab).is_dir()


def validate(root: Path, data: object) -> list[str]:
    """Return every problem in a parsed state file (empty list = valid)."""
    internal, external = check(root, data)
    return internal + external


def check(root: Path, data: object) -> tuple[list[str], list[str]]:
    """Split problems into internal ones and external ones.

    External problems concern files other writers change (labs, discussion threads); a write may
    proceed past them as long as it adds none, so that the command fixing one is never refused.
    """
    if not isinstance(data, dict):
        return ["state must be a JSON object"], []
    # Older checkouts omit idle / last_supervisor_at; treat as null without rewriting the caller.
    if "idle" not in data or "last_supervisor_at" not in data:
        data = {
            **data,
            "idle": data.get("idle", None),
            "last_supervisor_at": data.get("last_supervisor_at", None),
        }
    if set(data) != STATE_KEYS:
        return [f"state keys must be {sorted(STATE_KEYS)}; missing {sorted(STATE_KEYS - set(data))}, "
                f"unexpected {sorted(set(data) - STATE_KEYS)}"], []
    problems: list[str] = []
    external: list[str] = []
    if data["schema"] != SCHEMA:
        problems.append(f"schema must be {SCHEMA!r}")
    if data["status"] not in STATUSES:
        problems.append(f"status {data['status']!r} not in {STATUSES}")
    if not valid_stamp(data["updated"]):
        problems.append("updated must be an ISO-8601 UTC timestamp like 2026-01-31T09:00:00Z")
    if not isinstance(data["next_action"], str) or not data["next_action"].strip():
        problems.append("next_action must be a concrete, non-empty sentence")

    deliverable = data["active_deliverable"]
    if deliverable is not None:
        if not isinstance(deliverable, dict) or set(deliverable) != {"lab", "summary", "acceptance"}:
            problems.append("active_deliverable must be null or {lab, summary, acceptance}")
        else:
            if not isinstance(deliverable["lab"], str) or not lab_exists(root, deliverable["lab"]):
                external.append(f"active_deliverable.lab {deliverable['lab']!r} is not a lab under labs/")
            if not isinstance(deliverable["summary"], str) or not deliverable["summary"].strip():
                problems.append("active_deliverable.summary must be non-empty")
            acceptance = deliverable["acceptance"]
            if (not isinstance(acceptance, list) or not acceptance
                    or not all(isinstance(a, str) and a.strip() for a in acceptance)):
                problems.append("active_deliverable.acceptance must be a non-empty list of criteria")

    last = data["last_action"]
    if last is not None and (not isinstance(last, dict) or set(last) != {"at", "summary"}
                             or not valid_stamp(last["at"])
                             or not isinstance(last["summary"], str) or not last["summary"].strip()):
        problems.append("last_action must be null or {at: ISO-8601 UTC, summary: non-empty}")

    last_sup = data.get("last_supervisor_at")
    if last_sup is not None and not valid_stamp(last_sup):
        problems.append("last_supervisor_at must be null or an ISO-8601 UTC timestamp")

    idle = data.get("idle")
    if data["status"] == "idle":
        if not isinstance(idle, dict) or set(idle) != IDLE_KEYS:
            problems.append(
                "when status is idle, idle must be "
                "{reason, detail, lift_when, since, fingerprint}"
            )
        else:
            if idle["reason"] not in IDLE_REASONS:
                problems.append(f"idle.reason {idle['reason']!r} not in {IDLE_REASONS}")
            if not isinstance(idle["detail"], str) or not idle["detail"].strip():
                problems.append("idle.detail must be a non-empty explanation of why idle was entered")
            if not isinstance(idle["lift_when"], str) or not idle["lift_when"].strip():
                problems.append("idle.lift_when must be a concrete, checkable exit condition")
            if not valid_stamp(idle["since"]):
                problems.append("idle.since must be an ISO-8601 UTC timestamp")
            if not isinstance(idle["fingerprint"], dict):
                problems.append("idle.fingerprint must be a JSON object (cheap probe snapshot)")
    elif idle is not None:
        problems.append("idle must be null unless status is idle")

    metas = data.get("threads")
    if not isinstance(metas, list):
        problems.append("threads must be a list of Thread meta objects (no messages)")
        threads = None
    else:
        ids: list[str] = []
        for n, meta in enumerate(metas):
            where = f"threads[{n}]"
            if not isinstance(meta, dict):
                problems.append(f"{where}: must be a JSON object")
                continue
            keys = set(meta)
            if "messages" in keys:
                problems.append(f"{where}: unexpected key 'messages' "
                                "(messages live in .auto-research/threads/<id>.json)")
                keys = keys - {"messages"}
            if keys != THREAD_META_KEYS:
                problems.append(f"{where}: keys must be {sorted(THREAD_META_KEYS)}; "
                                f"missing {sorted(THREAD_META_KEYS - keys)}, "
                                f"unexpected {sorted(keys - THREAD_META_KEYS)}")
                continue
            expected = f"thread-{n + 1:03d}"
            tid = meta["id"]
            if tid != expected:
                problems.append(f"{where}: id {tid!r} should be {expected!r}")
            ids.append(tid)
            path = thread_path(root, tid) if isinstance(tid, str) else None
            if path is not None and not path.is_file():
                external.append(f"thread file .auto-research/threads/{tid}.json is missing")
        if len(ids) != len(set(ids)):
            problems.append("threads must not contain duplicate ids")
        folder = threads_dir(root)
        if folder.is_dir():
            known = set(ids)
            for orphan in sorted(p.name for p in folder.glob("thread-*.json") if p.stem not in known):
                problems.append(f"threads/{orphan} has no entry in state.threads")
        threads = read_threads(root, data)

    tasks = data["tasks"]
    if not isinstance(tasks, list):
        problems.append("tasks must be a list")
        return problems, external
    seen: set[str] = set()
    for n, item in enumerate(tasks):
        where = f"tasks[{n}]"
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            keys = set(item) if isinstance(item, dict) else set()
            problems.append(f"{where}: keys must be {sorted(ITEM_KEYS)}; missing {sorted(ITEM_KEYS - keys)}, "
                            f"unexpected {sorted(keys - ITEM_KEYS)}")
            continue
        item_id = item["id"]
        if not isinstance(item_id, str) or not SLUG.match(item_id):
            problems.append(f"{where}: id {item_id!r} is not a kebab-case slug")
            continue
        where = item_id
        if item_id in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(item_id)
        if not isinstance(item["title"], str) or not item["title"].strip() or "\n" in item["title"]:
            problems.append(f"{where}: title must be one non-empty line")
        if not isinstance(item["for"], str) or not all(r in ROLES for r in roles_of(item["for"])):
            problems.append(f"{where}: for {item['for']!r} must be a comma-separated subset of {ROLES}")
        if item["gpu"] not in GPU_TIERS:
            problems.append(f"{where}: gpu {item['gpu']!r} not in {GPU_TIERS}")
        if item["time"] not in TIME_TIERS:
            problems.append(f"{where}: time {item['time']!r} not in {TIME_TIERS}")
        blocked = item["blocked_on"]
        if blocked is not None and (not isinstance(blocked, str) or not blocked.strip()):
            problems.append(f"{where}: blocked_on must be null or a non-empty reason")
        elif isinstance(blocked, str) and threads is not None:
            for ref in THREAD_REF.findall(blocked):
                if ref not in threads:
                    external.append(f"{where}: blocked_on cites {ref}, which does not exist")
                elif threads[ref]["status"] != "open":
                    external.append(f"{where}: blocked_on cites {ref}, which is closed: apply it and unblock")
        labs = item["related_labs"]
        if not isinstance(labs, list) or len(set(map(str, labs))) != len(labs):
            problems.append(f"{where}: related_labs must be a list of distinct lab ids")
        else:
            for lab in labs:
                if not isinstance(lab, str) or not lab_exists(root, lab):
                    external.append(f"{where}: related lab {lab!r} is not a lab under labs/")
        if item["detail"] != detail_path(item_id):
            problems.append(f"{where}: detail must be {detail_path(item_id)!r}")
        else:
            path = root / item["detail"]
            if not path.is_file():
                problems.append(f"{where}: detail file {item['detail']} is missing")
            else:
                for msg in check_task_body(path.read_text(encoding="utf-8")):
                    problems.append(f"{where}: {msg}")
        if not valid_day(item["added"]):
            problems.append(f"{where}: added must be a YYYY-MM-DD date")
    folder = root / ".auto-research" / "tasks"
    if folder.is_dir():
        for orphan in sorted(
            p.name for p in folder.glob("*.md")
            if p.stem not in seen and p.name != "README.md"
        ):
            problems.append(f"tasks/{orphan} has no task (delete it or add the item)")
    return problems, external


def seed_checkout(root: Path) -> None:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from seed_local import seed_local_files

    seed_local_files(root)


def load(root: Path, strict: bool = True) -> tuple[dict, list[str]]:
    """Parse and check the state; return it with its external problems (none when strict)."""
    seed_checkout(root)
    path = state_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StateError(f"{path} not found") from None
    except json.JSONDecodeError as error:
        raise StateError(f"{path} is not valid JSON: {error}") from None
    if isinstance(data, dict):
        # Drop retired fields; seed_local migrates thread_ids / embedded messages.
        data.pop("pending_human_thread_id", None)
        data.pop("thread_ids", None)
        if "threads" not in data:
            data["threads"] = []
        # Pre-idle schema: missing key means not idle.
        if "idle" not in data:
            data["idle"] = None
        # Pre-kind schema: missing last_supervisor_at means never supervised.
        if "last_supervisor_at" not in data:
            data["last_supervisor_at"] = None
        if data.get("status") != "idle" and data.get("idle") is not None:
            # Stale idle blob after a hand-edit to status — normalize on load for mutate.
            if not strict:
                data["idle"] = None
    internal, external = check(root, data)
    problems = internal + external if strict else internal
    if problems:
        raise StateError(f"{path} fails validation:\n  " + "\n  ".join(problems))
    return data, external


@contextmanager
def locked(root: Path):
    lock_dir = root / ".tmp"
    lock_dir.mkdir(exist_ok=True)
    with open(lock_dir / "loop_state.lock", "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def mutate(root: Path, change, files: dict[str, str | None] | None = None):
    """Apply `change(state)` under the lock, then write detail files and a validated state.

    `files` maps a repository-relative detail path to its new text, or None to delete it; `change`
    may add entries to it.
    """
    files = {} if files is None else files
    with locked(root):
        before, known = load(root, strict=False)
        state = copy.deepcopy(before)
        result = change(state, files)
        state["updated"] = now()
        backup: dict[str, str | None] = {}
        for rel, text in files.items():
            path = root / rel
            backup[rel] = path.read_text(encoding="utf-8") if path.exists() else None
            if text is None:
                path.unlink(missing_ok=True)
            else:
                write_atomic(path, text)
        internal, external = check(root, state)
        problems = internal + [p for p in external if p not in known]
        if problems:
            for rel, text in backup.items():
                path = root / rel
                if text is None:
                    path.unlink(missing_ok=True)
                else:
                    write_atomic(path, text)
            raise StateError("refusing to write an invalid state:\n  " + "\n  ".join(problems))
        write_atomic(state_path(root), json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    return result


def find_item(state: dict, item_id: str) -> tuple[int, dict]:
    for n, item in enumerate(state["tasks"]):
        if item["id"] == item_id:
            return n, item
    raise StateError(f"no task {item_id!r}")


def read_body(args: argparse.Namespace) -> str:
    if getattr(args, "content_file", None) is not None:
        source = sys.stdin if args.content_file == "-" else open(args.content_file, encoding="utf-8")
        with source:
            text = source.read()
    else:
        text = getattr(args, "content", None)
    if text is None or not text.strip():
        raise StateError(
            "the item body is empty: give ## Goal / ## Work / ## Done when "
            "(see .auto-research/tasks/README.md)"
        )
    return text.strip("\n")


def check_blocker(root: Path, reason: str) -> str:
    reason = reason.strip()
    if not reason:
        raise StateError("a blocker needs a reason")
    refs = THREAD_REF.findall(reason)
    threads: dict[str, dict] = {}
    if refs:
        state, _ = load(root, strict=False)
        threads = read_threads(root, state)
    for ref in refs:
        if ref not in threads:
            raise StateError(f"{ref} does not exist in .auto-research/threads/")
        if threads[ref]["status"] != "open":
            raise StateError(f"{ref} is closed; it cannot block anything")
    if not refs and RESOURCE_WORDS.search(reason):
        raise StateError("GPU availability, run time, credits, outages and push failures are routed through "
                         "gpu/time and a live snapshot, not blocked_on (skills/auto-research/references/spending-compute.md); "
                         "block only on a researcher decision (cite its thread) or an external act")
    return reason


def insert_at(tasks: list, item: dict, args: argparse.Namespace) -> None:
    if getattr(args, "top", False):
        tasks.insert(0, item)
    elif getattr(args, "before", None):
        tasks.insert(find_item({"tasks": tasks}, args.before)[0], item)
    elif getattr(args, "after", None):
        tasks.insert(find_item({"tasks": tasks}, args.after)[0] + 1, item)
    else:
        tasks.append(item)


def scheduler_path(root: Path) -> Path:
    return root / ".auto-research" / "scheduler.json"


def read_scheduler(root: Path) -> dict | None:
    """The registered tick scheduler, or None. Runtime-only (gitignored); not scaffold.

    Requires ``owner``: the agent product that started the loop and must tick in its own session.
    """
    try:
        data = json.loads(scheduler_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    owner = data.get("owner") if isinstance(data, dict) else None
    ok = (isinstance(data, dict) and data.get("kind") in SCHEDULER_KINDS and isinstance(data.get("id"), str)
          and isinstance(data.get("every_min"), int) and data["every_min"] > 0
          and isinstance(owner, str) and OWNER_SLUG.match(owner))
    return data if ok else None


def liveness(root: Path, state: dict) -> dict:
    """Is the loop actually ticking? `status: running` is a flag; this is the evidence.

    Live needs a registered scheduler AND a logged action newer than two intervals. Whether a
    session cron job still exists is only visible to the agent (the job list): `scheduler --verify`.
    The scheduler's ``owner`` is who must perform ticks; other agents must not start ticks for them.
    """
    if state["status"] == "idle":
        sched = read_scheduler(root)
        idle = state.get("idle") if isinstance(state.get("idle"), dict) else {}
        reason = idle.get("reason", "?")
        if sched is None:
            return {
                "verdict": "idle-unscheduled",
                "detail": (
                    f"status is idle (reason={reason}) but no scheduler is registered — "
                    "probes will not fire until a schedule is registered or the researcher starts the loop"
                ),
            }
        return {
            "verdict": "idle-probe",
            "detail": (
                f"idle (reason={reason}); {sched['kind']} {sched['id']} (owner={sched['owner']}) "
                f"should run cheap `$L idle-check` probes every {sched['every_min']} min"
            ),
        }
    if state["status"] != "running":
        return {"verdict": "not-running", "detail": f"status is {state['status']}; no ticks are expected"}
    sched = read_scheduler(root)
    if sched is None:
        return {"verdict": "UNSCHEDULED", "detail": "status says running but no scheduler is registered, so "
                "nothing fires ticks; create one and register it with `scheduler --set … --owner <self>`"}
    last = state["last_action"]
    limit_min = 2 * sched["every_min"] + 5
    age_min = hours_since(last["at"]) * 60 if last else None
    owned = f"owner={sched['owner']}"
    if age_min is None or age_min > limit_min:
        age = "never" if age_min is None else f"{age_min:.0f} min ago"
        return {"verdict": "STALE", "detail": f"{sched['kind']} {sched['id']} ({owned}) is registered (every "
                f"{sched['every_min']} min) but the last action was {age}; it is not ticking, "
                "check it with `scheduler --verify`"}
    return {"verdict": "live", "detail": f"{sched['kind']} {sched['id']} ({owned}) every "
            f"{sched['every_min']} min, last action {age_min:.0f} min ago"}


def hours_since(stamp: str) -> float:
    then = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def minutes_since(stamp: str) -> float:
    return hours_since(stamp) * 60


def infer_tick_kind(summary: str, explicit: str | None = None) -> str | None:
    """Return research/supervisor from --kind or a ``supervisor:`` / ``research:`` summary prefix."""
    if explicit:
        kind = explicit.strip().lower()
        if kind not in ("research", "supervisor"):
            raise StateError(f"--kind must be research or supervisor, not {explicit!r}")
        return kind
    text = summary.strip().lower()
    if text.startswith("supervisor:"):
        return "supervisor"
    if text.startswith("research:"):
        return "research"
    return None


def suggested_tick_kind(
    state: dict,
    *,
    supervisor_max_minutes: float = SUPERVISOR_MAX_MINUTES,
    stall_hours: float = 2.0,
) -> dict:
    """Program-level kind signal for the next wake (status + loop_runner).

    Returns ``{kind, forced, reason}``. When ``forced`` is true the agent must run that kind.
    Event forces (empty runnable queue, stall) and the supervisor interval share this path;
    research-step choice inside a research tick stays heuristic.
    """
    status = state.get("status")
    if status == "idle":
        return {"kind": "idle-probe", "forced": True, "reason": "status is idle"}
    if status != "running":
        return {"kind": None, "forced": False, "reason": f"status is {status}; do not tick"}

    reasons: list[str] = []
    last_sup = state.get("last_supervisor_at")
    if last_sup is None:
        reasons.append("no supervisor tick recorded yet")
    elif minutes_since(last_sup) >= supervisor_max_minutes:
        reasons.append(
            f"last supervisor {minutes_since(last_sup):.0f} min ago "
            f"(>= {supervisor_max_minutes:g} min)"
        )

    unblocked = [i for i in state.get("tasks") or [] if i.get("blocked_on") is None]
    if not unblocked and state.get("active_deliverable") is None:
        reasons.append("no unblocked task and no deliverable")

    last = state.get("last_action")
    if isinstance(last, dict) and valid_stamp(last.get("at")) and hours_since(last["at"]) > stall_hours:
        reasons.append(
            f"no action logged for {hours_since(last['at']):.1f} h while running (stall)"
        )

    if reasons:
        return {"kind": "supervisor", "forced": True, "reason": "; ".join(reasons)}
    return {
        "kind": "research",
        "forced": False,
        "reason": (
            f"within supervisor interval "
            f"(last supervisor {minutes_since(last_sup):.0f} min ago)"
        ),
    }


def fits(item: dict, tier: str) -> bool:
    return GPU_TIERS.index(item["gpu"]) <= GPU_TIERS.index(tier)


def idle_fingerprint(root: Path, state: dict) -> dict:
    """Cheap snapshot for the next idle probe — compare without loading the full research context."""
    threads = read_threads(root, state)
    open_threads = [t for t in threads.values() if t.get("status") == "open"]

    def _last(t: dict) -> dict | None:
        msgs = t.get("messages") or []
        return msgs[-1] if msgs else None

    awaiting_human = [
        t["id"] for t in open_threads
        if (m := _last(t)) and m.get("author") == "agent" and m.get("type") == "question"
    ]
    unblocked = [i["id"] for i in state["tasks"] if i["blocked_on"] is None]
    blocked = [
        {"id": i["id"], "blocked_on": i["blocked_on"]}
        for i in state["tasks"] if i["blocked_on"] is not None
    ]
    deliverable = state.get("active_deliverable")
    return {
        "next_action": state.get("next_action") or "",
        "deliverable_lab": deliverable["lab"] if isinstance(deliverable, dict) else None,
        "unblocked_task_ids": unblocked,
        "blocked_tasks": blocked,
        "open_thread_ids": [t["id"] for t in open_threads],
        "awaiting_human": awaiting_human,
        "task_count": len(state.get("tasks") or []),
    }


def fingerprint_changed(stored: dict, current: dict) -> list[str]:
    """Return human-readable keys that differ between idle entry fingerprint and now."""
    changes: list[str] = []
    keys = sorted(set(stored) | set(current))
    for key in keys:
        if stored.get(key) != current.get(key):
            changes.append(key)
    return changes


# ---------------------------------------------------------------- commands

def cmd_status(root: Path, args: argparse.Namespace) -> dict:
    state, external = load(root, strict=False)
    threads = read_threads(root, state)
    open_threads = [t for t in threads.values() if t.get("status") == "open"]
    notes = list(external)
    def _last(t: dict) -> dict | None:
        msgs = t.get("messages") or []
        return msgs[-1] if msgs else None

    awaiting_agent = [
        t["id"] for t in open_threads
        if (m := _last(t)) and m.get("author") == "user"
    ]
    # Match dashboard sections._thread_item: open + last message is an agent question.
    awaiting_human = [
        t["id"] for t in open_threads
        if (m := _last(t)) and m.get("author") == "agent" and m.get("type") == "question"
    ]
    if awaiting_agent:
        notes.append(f"researcher messages await an agent in {', '.join(awaiting_agent)}: handle them first")
    if awaiting_human:
        notes.append(f"Threads awaiting researcher: {', '.join(awaiting_human)}")
    if state["status"] == "running" and state["last_action"] and hours_since(state["last_action"]["at"]) > args.stall_hours:
        notes.append(f"no action logged for {hours_since(state['last_action']['at']):.1f} h while running: "
                     "run a supervisor tick and check for a stall")
    live = liveness(root, state)
    if state["status"] == "running" and live["verdict"] != "live":
        notes.insert(0, f"LOOP NOT TICKING ({live['verdict']}): {live['detail']}. Do not tell the researcher "
                     "it is running.")
    if state["status"] == "idle":
        idle = state.get("idle") or {}
        notes.insert(
            0,
            "IDLE PROBE: run `$L idle-check` first — do not load the full research context unless "
            f"lift_when is met (reason={idle.get('reason')!r}; lift_when={idle.get('lift_when')!r})",
        )
    unblocked = [i for i in state["tasks"] if i["blocked_on"] is None]
    if state["status"] == "running" and not unblocked and state["active_deliverable"] is None:
        notes.append("no unblocked task and no deliverable: refill the tasks in a supervisor tick")
    suggestion = suggested_tick_kind(
        state,
        supervisor_max_minutes=args.supervisor_max_min,
        stall_hours=args.stall_hours,
    )
    if suggestion["kind"] and state["status"] in ("running", "idle"):
        forced = "FORCED" if suggestion["forced"] else "suggested"
        # Append (do not prepend): LOOP NOT TICKING / IDLE PROBE stay first.
        notes.append(
            f"tick kind {forced}: {suggestion['kind']} ({suggestion['reason']})",
        )
    return {"status": state["status"], "liveness": live, "updated": state["updated"],
            "next_action": state["next_action"], "active_deliverable": state["active_deliverable"],
            "last_action": state["last_action"],
            "last_supervisor_at": state.get("last_supervisor_at"),
            "idle": state.get("idle"),
            "suggested_kind": suggestion,
            "awaiting_human": awaiting_human,
            "tasks": {"total": len(state["tasks"]), "unblocked": len(unblocked),
                        "blocked": len(state["tasks"]) - len(unblocked),
                        "top": [{"id": i["id"], "gpu": i["gpu"], "time": i["time"], "for": i["for"]}
                                for i in unblocked[:5]]},
            "open_threads": len(open_threads), "notes": notes}


def set_status(value: str):
    """start / pause only. Idle requires reason + lift_when via ``cmd_idle``."""
    def command(root: Path, args: argparse.Namespace) -> dict:
        def change(state, files):
            state["status"] = value
            state["idle"] = None
            if args.summary:
                state["last_action"] = {"at": now(), "summary": args.summary.strip()}
            return {"status": value, "idle": None}
        result = mutate(root, change)
        sched = read_scheduler(root)
        if value == "running" and sched is None:
            result["warning"] = ("status is only a flag: no scheduler is registered, so no ticks will fire. "
                                 "create a schedule this agent owns, then "
                                 "`scheduler --set <kind> <id> --every-min N --owner <self>`")
        # pause stops ticks; idle keeps the scheduler so cheap probes can still fire.
        if value == "paused" and sched is not None:
            scheduler_path(root).unlink()
            result["scheduler_cleared"] = (f"deregistered {sched['kind']} {sched['id']} "
                                           f"(owner={sched['owner']}); stop the owner's schedule too")
        return result
    return command


def cmd_idle(root: Path, args: argparse.Namespace) -> dict:
    """Enter idle as a backstop with an explicit reason and lift condition."""
    reason = (args.reason or "").strip()
    lift_when = (args.lift_when or "").strip()
    detail = (args.detail or args.summary or "").strip()
    if reason not in IDLE_REASONS:
        raise StateError(f"--reason must be one of {IDLE_REASONS}")
    if not lift_when:
        raise StateError("--lift-when is required: a concrete condition the next tick can check")
    if not detail:
        raise StateError("give --detail (or --summary) explaining why idle was entered after seeking work")

    def change(state, files):
        fingerprint = idle_fingerprint(root, state)
        if getattr(args, "fingerprint_json", None):
            try:
                override = json.loads(args.fingerprint_json)
            except json.JSONDecodeError as error:
                raise StateError(f"--fingerprint-json is not valid JSON: {error}") from error
            if not isinstance(override, dict):
                raise StateError("--fingerprint-json must be a JSON object")
            fingerprint = override
        if args.same_tick_streak is not None:
            fingerprint["same_tick_streak"] = int(args.same_tick_streak)
        state["status"] = "idle"
        state["idle"] = {
            "reason": reason,
            "detail": detail,
            "lift_when": lift_when,
            "since": now(),
            "fingerprint": fingerprint,
        }
        summary = args.summary.strip() if args.summary else f"idle ({reason}): {detail}"
        state["last_action"] = {"at": now(), "summary": summary}
        return {"status": "idle", "idle": state["idle"]}

    return mutate(root, change)


def cmd_idle_check(root: Path, args: argparse.Namespace) -> dict:
    """Cheap probe: compare current fingerprint to the one stored when idle was entered."""
    state, _ = load(root, strict=False)
    if state["status"] != "idle" or not isinstance(state.get("idle"), dict):
        return {
            "status": state["status"],
            "idle": state.get("idle"),
            "probe": "not-idle",
            "changed": False,
            "changes": [],
            "advice": "status is not idle — run a normal tick (or `$L start` if paused)",
        }
    idle = state["idle"]
    current = idle_fingerprint(root, state)
    stored = idle.get("fingerprint") if isinstance(idle.get("fingerprint"), dict) else {}
    changes = fingerprint_changed(stored, current)
    changed = bool(changes)
    return {
        "status": "idle",
        "idle": idle,
        "probe": "changed" if changed else "unchanged",
        "changed": changed,
        "changes": changes,
        "fingerprint": current,
        "advice": (
            f"fingerprint moved ({', '.join(changes)}); re-read lift_when="
            f"{idle.get('lift_when')!r} — if met, `$L start` and resume the main loop"
            if changed else
            f"unchanged since idle; lift_when={idle.get('lift_when')!r} — end the tick without "
            "loading the full research context"
        ),
    }


def cmd_scheduler(root: Path, args: argparse.Namespace) -> dict:
    """Record, check, or clear what fires the ticks (AGENTS.md: state what the next reader opens).

    Ownership: ``--owner`` is the agent product that started the loop and must tick in its own
    session. Do not register another product as owner or wake another product's CLI.
    """
    modes = [bool(args.set_), args.clear, args.verify]
    if sum(modes) > 1:
        raise StateError("give one of --set, --clear, --verify (or none to show)")
    current = read_scheduler(root)
    if args.set_:
        owner = (args.owner or "").strip().lower()
        if (args.set_ not in SCHEDULER_KINDS or len(args.job_ids) != 1 or not args.every_min
                or args.every_min < 1 or not OWNER_SLUG.match(owner)):
            raise StateError(
                f"--set needs KIND in {SCHEDULER_KINDS}, one job id, --every-min N, and "
                f"--owner <this-agent> (known: {', '.join(SCHEDULER_OWNERS)}; or another lowercase slug)"
            )
        if args.set_ == "runner" and owner not in ("claude", "codex"):
            raise StateError(
                "kind=runner may only wake claude or codex CLIs; for cursor (or others) use "
                "session-cron / product automations so ticks stay in that agent's own session"
            )
        entry = {
            "kind": args.set_,
            "id": args.job_ids[0],
            "every_min": args.every_min,
            "owner": owner,
            "registered": now(),
        }
        write_atomic(scheduler_path(root), json.dumps(entry, indent=2) + "\n")
        return entry
    if args.clear:
        if current is not None:
            scheduler_path(root).unlink()
        return {"cleared": current}
    if args.verify:
        if current is None:
            raise StateError("no scheduler registered: nothing is firing ticks")
        if current["kind"] != "session-cron":
            raise StateError(f"cannot verify a {current['kind']} scheduler here; check its process and the "
                             "last_action time")
        if current["id"] not in args.job_ids:
            scheduler_path(root).unlink()
            raise StateError(f"registered session cron {current['id']} is not in the job list {args.job_ids or '(empty)'}: "
                             "it is dead (session restarted or job expired); registration cleared, create a new one")
        return {"verified": current}
    return {"scheduler": current}


def cmd_set_next(root: Path, args: argparse.Namespace) -> dict:
    text = args.text.strip()
    if not text:
        raise StateError("next_action must be a concrete sentence")

    def change(state, files):
        state["next_action"] = text
        return {"next_action": text}
    return mutate(root, change)


def cmd_set_deliverable(root: Path, args: argparse.Namespace) -> dict:
    if args.clear:
        if args.lab or args.summary or args.acceptance:
            raise StateError("--clear takes no other options")
        value = None
    else:
        if not (args.lab and args.summary and args.acceptance):
            raise StateError("set-deliverable needs --lab, --summary and at least one --acceptance (or --clear)")
        value = {"lab": args.lab, "summary": args.summary.strip(), "acceptance": [a.strip() for a in args.acceptance]}

    def change(state, files):
        state["active_deliverable"] = value
        return {"active_deliverable": value}
    return mutate(root, change)


def cmd_log_action(root: Path, args: argparse.Namespace) -> dict:
    summary = args.summary.strip()
    if not summary:
        raise StateError("an action summary is required")
    kind = infer_tick_kind(summary, getattr(args, "kind", None))

    def change(state, files):
        stamp = now()
        state["last_action"] = {"at": stamp, "summary": summary}
        if kind == "supervisor":
            state["last_supervisor_at"] = stamp
        if args.next:
            state["next_action"] = args.next.strip()
        out = {"last_action": state["last_action"], "next_action": state["next_action"],
               "last_supervisor_at": state.get("last_supervisor_at"), "kind": kind}
        return out
    return mutate(root, change)


def cmd_task_list(root: Path, args: argparse.Namespace) -> list[dict]:
    items = load(root, strict=False)[0]["tasks"]
    rows = []
    for rank, item in enumerate(items, start=1):
        if args.unblocked and item["blocked_on"] is not None:
            continue
        if args.blocked and item["blocked_on"] is None:
            continue
        if args.fits and not fits(item, args.fits):
            continue
        rows.append({"rank": rank, **item})
    return rows


def cmd_task_show(root: Path, args: argparse.Namespace) -> dict:
    _, item = find_item(load(root, strict=False)[0], args.item_id)
    return {**item, "body": (root / item["detail"]).read_text(encoding="utf-8")}


def cmd_task_add(root: Path, args: argparse.Namespace) -> dict:
    title = args.title.strip()
    body = read_body(args)
    blocked = check_blocker(root, args.blocked_on) if args.blocked_on else None
    for lab in args.lab:
        if not lab_exists(root, lab):
            raise StateError(f"no such lab: labs/{lab}")

    def change(state, files):
        taken = {i["id"] for i in state["tasks"]}
        if args.id:
            if not SLUG.match(args.id) or args.id in taken:
                raise StateError(f"id {args.id!r} is not a free kebab-case slug")
            item_id = args.id
        else:
            item_id = slugify(title, taken)
        item = {"id": item_id, "title": title, "for": ", ".join(roles_of(args.for_)), "gpu": args.gpu,
                "time": args.time, "blocked_on": blocked, "related_labs": sorted(set(args.lab)),
                "detail": detail_path(item_id), "added": date.today().isoformat()}
        insert_at(state["tasks"], item, args)
        files[item["detail"]] = f"# {title}\n\n{body}\n"
        return {"added": item_id, "rank": state["tasks"].index(item) + 1}
    return mutate(root, change)


def cmd_task_move(root: Path, args: argparse.Namespace) -> dict:
    def change(state, files):
        n, item = find_item(state, args.item_id)
        del state["tasks"][n]
        if args.bottom:
            state["tasks"].append(item)
        else:
            insert_at(state["tasks"], item, args)
        return {"moved": item["id"], "rank": state["tasks"].index(item) + 1}
    return mutate(root, change)


def cmd_task_set(root: Path, args: argparse.Namespace) -> dict:
    if not any([args.title, args.for_, args.gpu, args.time, args.lab]):
        raise StateError("nothing to change")
    for lab in args.lab:
        if not lab_exists(root, lab):
            raise StateError(f"no such lab: labs/{lab}")

    def change(state, files):
        _, item = find_item(state, args.item_id)
        if args.title:
            item["title"] = args.title.strip()
            path = root / item["detail"]
            lines = path.read_text(encoding="utf-8").split("\n")
            lines[0] = f"# {item['title']}"
            files[item["detail"]] = "\n".join(lines)
        if args.for_:
            item["for"] = ", ".join(roles_of(args.for_))
        if args.gpu:
            item["gpu"] = args.gpu
        if args.time:
            item["time"] = args.time
        if args.lab:
            item["related_labs"] = sorted(set(item["related_labs"]) | set(args.lab))
        return {"updated": item["id"]}
    return mutate(root, change)


def cmd_task_done(root: Path, args: argparse.Namespace) -> dict:
    def change(state, files):
        n, item = find_item(state, args.item_id)
        del state["tasks"][n]
        files[item["detail"]] = None
        if args.summary:
            state["last_action"] = {"at": now(), "summary": args.summary.strip()}
        return {"removed": item["id"], "remaining": len(state["tasks"])}
    return mutate(root, change)


def cmd_task_block(root: Path, args: argparse.Namespace) -> dict:
    reason = check_blocker(root, args.on)

    def change(state, files):
        _, item = find_item(state, args.item_id)
        item["blocked_on"] = reason
        return {"blocked": item["id"], "on": reason}
    return mutate(root, change)


def cmd_task_unblock(root: Path, args: argparse.Namespace) -> dict:
    def change(state, files):
        _, item = find_item(state, args.item_id)
        if item["blocked_on"] is None:
            raise StateError(f"{item['id']} is not blocked")
        item["blocked_on"] = None
        return {"unblocked": item["id"]}
    return mutate(root, change)


def cmd_validate(root: Path, args: argparse.Namespace) -> dict:
    state, _ = load(root)
    return {"ok": True, "status": state["status"], "tasks": len(state["tasks"])}


# ---------------------------------------------------------------- output

def render(command: str, result) -> str:
    if command == "status":
        r = result
        lines = [f"status: {r['status']} (updated {r['updated']})",
                 f"loop: {r['liveness']['verdict']}: {r['liveness']['detail']}", f"next: {r['next_action']}"]
        d = r["active_deliverable"]
        lines.append(f"deliverable: {d['lab']}: {d['summary']} ({len(d['acceptance'])} acceptance criteria)"
                     if d else "deliverable: none")
        awaiting = r.get("awaiting_human") or []
        lines.append(
            "awaiting researcher: " + (", ".join(awaiting) if awaiting else "none")
        )
        idle = r.get("idle")
        if isinstance(idle, dict):
            lines.append(
                f"idle: reason={idle.get('reason')} since={idle.get('since')} "
                f"lift_when={idle.get('lift_when')!r}"
            )
            lines.append(f"idle detail: {idle.get('detail')}")
        if r["last_action"]:
            lines.append(f"last action: {r['last_action']['at']} {r['last_action']['summary']}")
        last_sup = r.get("last_supervisor_at")
        lines.append(f"last supervisor: {last_sup}" if last_sup else "last supervisor: never")
        suggestion = r.get("suggested_kind") or {}
        if suggestion.get("kind"):
            forced = "forced" if suggestion.get("forced") else "suggested"
            lines.append(
                f"tick kind ({forced}): {suggestion['kind']} — {suggestion.get('reason')}"
            )
        b = r["tasks"]
        lines.append(f"tasks: {b['total']} items ({b['unblocked']} unblocked, {b['blocked']} blocked); "
                     f"open threads: {r['open_threads']}")
        lines += [f"  {i['id']}  [gpu {i['gpu']}, time {i['time']}, for {i['for']}]" for i in b["top"]]
        lines += [f"note: {n}" for n in r["notes"]]
        return "\n".join(lines)
    if command == "idle-check":
        r = result
        lines = [
            f"idle-check: {r.get('probe')} (status={r.get('status')})",
            f"advice: {r.get('advice')}",
        ]
        if r.get("changes"):
            lines.append("changes: " + ", ".join(r["changes"]))
        idle = r.get("idle")
        if isinstance(idle, dict):
            lines.append(f"lift_when: {idle.get('lift_when')}")
            lines.append(f"reason: {idle.get('reason')}")
        return "\n".join(lines)
    if command == "task list":
        return "\n".join(
            f"{r['rank']:3d}. {r['id']}  [gpu {r['gpu']}, time {r['time']}, for {r['for']}]"
            + (f"  BLOCKED: {r['blocked_on']}" if r["blocked_on"] else "") for r in result) or "(no items)"
    if command == "task show":
        r = result
        meta = (f"id: {r['id']}\nfor: {r['for']}  gpu: {r['gpu']}  time: {r['time']}  added: {r['added']}\n"
                f"blocked_on: {r['blocked_on'] or '-'}\nrelated_labs: {', '.join(r['related_labs']) or '-'}\n")
        return meta + "\n" + r["body"].rstrip("\n")
    if command == "validate":
        return f"ok: status {result['status']}, {result['tasks']} tasks"
    return json.dumps(result, ensure_ascii=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read and update .auto-research/state.json.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="project root holding .auto-research/ (default: this repository)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print machine-readable JSON")
    where = argparse.ArgumentParser(add_help=False)
    position = where.add_mutually_exclusive_group()
    position.add_argument("--top", action="store_true", help="highest priority")
    position.add_argument("--before", metavar="ID", help="insert just above this item")
    position.add_argument("--after", metavar="ID", help="insert just below this item")
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", parents=[common], help="summarize state, tasks and threads store")
    status.add_argument("--stall-hours", type=float, default=2.0,
                        help="warn when running with no logged action for this long (default 2)")
    status.add_argument(
        "--supervisor-max-min", type=float, default=SUPERVISOR_MAX_MINUTES,
        help=f"force suggested_kind=supervisor after this many minutes (default {SUPERVISOR_MAX_MINUTES})",
    )
    for name, text in (("start", "set status running (clears idle)"),
                       ("pause", "set status paused; clears idle and deregisters the scheduler")):
        sub = commands.add_parser(name, parents=[common], help=text)
        sub.add_argument("--summary", help="also record this as the last action")
    idle_cmd = commands.add_parser(
        "idle", parents=[common],
        help="enter idle backstop with --reason and --lift-when (keeps scheduler for probes)",
    )
    idle_cmd.add_argument("--reason", required=True, choices=IDLE_REASONS,
                          help="why idle after seeking work / supervisor refill failed")
    idle_cmd.add_argument("--lift-when", required=True,
                          help="concrete exit condition the next idle-check tick can evaluate")
    idle_cmd.add_argument("--detail", help="why idle was entered (defaults to --summary)")
    idle_cmd.add_argument("--summary", help="also recorded as last_action (defaults to idle detail)")
    idle_cmd.add_argument("--same-tick-streak", type=int, metavar="N",
                          help=f"for repeated-tick: how many identical ticks (use >={REPEATED_TICK_IDLE_AFTER})")
    idle_cmd.add_argument("--fingerprint-json", help="optional JSON object overriding the auto fingerprint")
    commands.add_parser(
        "idle-check", parents=[common],
        help="cheap idle probe: compare fingerprint / report whether to lift",
    )
    nxt = commands.add_parser("set-next", parents=[common], help="set next_action")
    nxt.add_argument("--text", required=True)
    deliverable = commands.add_parser("set-deliverable", parents=[common], help="set or clear active_deliverable")
    deliverable.add_argument("--lab")
    deliverable.add_argument("--summary")
    deliverable.add_argument("--acceptance", action="append", default=[], help="acceptance criterion (repeatable)")
    deliverable.add_argument("--clear", action="store_true")
    action = commands.add_parser("log-action", parents=[common], help="record the last substantive action")
    action.add_argument("--summary", required=True)
    action.add_argument("--next", help="also set next_action")
    action.add_argument(
        "--kind", choices=("research", "supervisor"),
        help="tick kind; supervisor updates last_supervisor_at (also inferred from summary prefix)",
    )
    sched = commands.add_parser("scheduler", parents=[common],
                                help="record or check what fires the ticks (status alone proves nothing)")
    sched.add_argument("--set", dest="set_", metavar="KIND", help=f"register a scheduler, KIND in {SCHEDULER_KINDS}")
    sched.add_argument("--owner", help="agent product that owns ticks (must be this agent; never another)")
    sched.add_argument("--every-min", type=int, help="tick interval in minutes (with --set)")
    sched.add_argument("--clear", action="store_true", help="deregister")
    sched.add_argument("--verify", action="store_true",
                       help="pass the ids the job list shows; fails and deregisters if the registered job is not there")
    sched.add_argument("job_ids", nargs="*", help="the job id (with --set) or the ids the job list shows (with --verify)")
    commands.add_parser("validate", parents=[common], help="check state.json and the task files")

    tasks = commands.add_parser("task", help="work with the tasks")
    items = tasks.add_subparsers(dest="task_command", required=True)
    listing = items.add_parser("list", parents=[common], help="list items in priority order")
    state_filter = listing.add_mutually_exclusive_group()
    state_filter.add_argument("--unblocked", action="store_true")
    state_filter.add_argument("--blocked", action="store_true")
    listing.add_argument("--fits", choices=GPU_TIERS, help="only items runnable at this available GPU tier")
    showing = items.add_parser("show", parents=[common], help="print one item with its body")
    showing.add_argument("item_id")
    adding = items.add_parser("add", parents=[common, where], help="add an item (default: lowest priority)")
    adding.add_argument("--title", required=True)
    adding.add_argument("--for", dest="for_", required=True, help=f"comma-separated roles from {', '.join(ROLES)}")
    adding.add_argument("--gpu", choices=GPU_TIERS, required=True)
    adding.add_argument("--time", choices=TIME_TIERS, required=True)
    adding.add_argument("--lab", action="append", default=[], help="related lab id (repeatable)")
    adding.add_argument("--blocked-on")
    adding.add_argument("--id", help="explicit slug (default: derived from the title)")
    body = adding.add_mutually_exclusive_group(required=True)
    body.add_argument("--content",
                      help="body under the title: ## Goal / ## Work / ## Done when (see tasks/README.md)")
    body.add_argument("--content-file", help="read that body from a file ('-' for stdin)")
    moving = items.add_parser("move", parents=[common, where], help="change an item's priority")
    moving.add_argument("item_id")
    moving.add_argument("--bottom", action="store_true", help="lowest priority")
    setting = items.add_parser("set", parents=[common], help="change an item's title or routing fields")
    setting.add_argument("item_id")
    setting.add_argument("--title")
    setting.add_argument("--for", dest="for_")
    setting.add_argument("--gpu", choices=GPU_TIERS)
    setting.add_argument("--time", choices=TIME_TIERS)
    setting.add_argument("--lab", action="append", default=[], help="add a related lab id (repeatable)")
    done = items.add_parser("done", parents=[common], help="delete a finished or dropped item and its body")
    done.add_argument("item_id")
    done.add_argument("--summary", help="also record this as the last action")
    block = items.add_parser("block", parents=[common], help="block one item on a researcher decision or external act")
    block.add_argument("item_id")
    block.add_argument("--on", required=True, help="the reason; cite the discussion thread when there is one")
    unblock = items.add_parser("unblock", parents=[common], help="clear an item's blocker")
    unblock.add_argument("item_id")
    return parser


COMMANDS = {
    "status": cmd_status, "start": set_status("running"), "pause": set_status("paused"),
    "idle": cmd_idle, "idle-check": cmd_idle_check,
    "set-next": cmd_set_next, "set-deliverable": cmd_set_deliverable,
    "scheduler": cmd_scheduler, "log-action": cmd_log_action, "validate": cmd_validate,
    "task list": cmd_task_list, "task show": cmd_task_show, "task add": cmd_task_add,
    "task move": cmd_task_move, "task set": cmd_task_set, "task done": cmd_task_done,
    "task block": cmd_task_block, "task unblock": cmd_task_unblock,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    name = args.command if args.command != "task" else f"task {args.task_command}"
    root = args.root.resolve()
    try:
        result = COMMANDS[name](root, args)
    except StateError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(name, result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
