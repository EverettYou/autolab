#!/usr/bin/env python3
"""Same-owner headless schedule for auto-research ticks while status is running or idle.

Ownership: whoever starts the loop must tick as that same agent product. This process is only a
timer that wakes **the owner's** CLI (``--owner claude|codex``). It must never start another
product's agent (e.g. a Cursor session must not ``serve --owner codex``).

``running`` ticks do research/supervisor work. ``idle`` ticks should only cheap-probe
(``loop_state.py idle-check``) until lift conditions fire. ``pause`` stops this loop.
Register the schedule with the same owner: ``scheduler --set runner <pid> --every-min N --owner <self>``.

``EMLAB_LOOP_INTERVAL`` is the wait between ticks in seconds (default 720).
``EMLAB_LOOP_TICK_ARGV``, a JSON list of strings, replaces the agent command (tests only).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# CLI wake templates for owners that have no in-session cron. Key == scheduler --owner.
# "{root}" and "{prompt}" are filled per tick. Do not add a path that lets one product wake another.
RUNNER_ARGV = {
    "claude": ["claude", "-p", "--permission-mode", "bypassPermissions", "--permission-prompts", "none", "{prompt}"],  # rules-lint: allow
    # --approve-for-me already uses workspace-write; do not also pass --sandbox (CLI rejects the pair).
    "codex": ["codex", "exec", "--approve-for-me", "-C", "{root}", "{prompt}"],
}
OWNERS = tuple(RUNNER_ARGV)
DEFAULT_INTERVAL = 12 * 60
TICK_TIMEOUT = 45 * 60
PROMPT_BASE = (
    "Follow skills/auto-research/SKILL.md and run one tick. "
    "Orient from the files first (`loop_state.py status`). "
    "If status is idle, run loop_state.py idle-check only "
    "(cheap probe — do not load the full research context unless lift_when is met, then start). "
    "If status is paused or missing, do not start work. "
    "You are the owner of this loop; do not hand ticks to another agent."
)

ACTIVE_STATUSES = frozenset({"running", "idle"})


def _loop_state():
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import loop_state as mod  # noqa: WPS433

    return mod


def build_prompt(root: Path) -> str:
    """Single wake prompt with a program-level suggested_kind (forced when overdue/events)."""
    mod = _loop_state()
    try:
        raw = json.loads((root / ".auto-research" / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("idle", None)
    raw.setdefault("last_supervisor_at", None)
    raw.setdefault("tasks", [])
    suggestion = mod.suggested_tick_kind(raw)
    kind = suggestion.get("kind") or "research"
    forced = bool(suggestion.get("forced"))
    reason = suggestion.get("reason") or ""
    duty = (
        f"This wake's suggested_kind={kind} (forced={'true' if forced else 'false'}: {reason}). "
    )
    if forced:
        duty += f"You MUST run a {kind} tick. "
    elif kind == "research":
        duty += "Default to a research tick unless SKILL event rules say supervisor. "
    return PROMPT_BASE + " " + duty


def scratch(root: Path) -> Path:
    path = root / ".tmp" / "auto-research"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pid_path(root: Path) -> Path:
    return root / ".tmp" / "auto-research" / "scheduler.json"


def choice_path(root: Path) -> Path:
    return root / ".tmp" / "auto-research" / "runner"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_status(root: Path) -> str:
    path = root / ".auto-research" / "state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    status = data.get("status") if isinstance(data, dict) else ""
    return status if isinstance(status, str) else ""


def read_registered_owner(root: Path) -> str | None:
    path = root / ".auto-research" / "scheduler.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("kind") != "runner":
        return None
    owner = data.get("owner")
    return owner if isinstance(owner, str) else None


def alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_record(root: Path) -> dict:
    path = pid_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_record(root: Path, record: dict) -> None:
    path = pid_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def interval() -> float:
    raw = os.environ.get("EMLAB_LOOP_INTERVAL", "")
    if not raw:
        return float(DEFAULT_INTERVAL)
    try:
        value = float(raw)
    except ValueError:
        return float(DEFAULT_INTERVAL)
    return max(0.0, value)


def tick_argv(root: Path, owner: str) -> list[str]:
    raw = os.environ.get("EMLAB_LOOP_TICK_ARGV", "")
    if raw:
        argv = json.loads(raw)
        if not isinstance(argv, list) or not argv or not all(isinstance(part, str) for part in argv):
            raise SystemExit("EMLAB_LOOP_TICK_ARGV must be a non-empty JSON list of strings")
        return argv
    template = RUNNER_ARGV.get(owner)
    if template is None:
        raise SystemExit(f"unknown owner {owner!r}; loop_runner can only wake {OWNERS}")
    binary = shutil.which(template[0])
    if not binary:
        raise SystemExit(f"{template[0]} is not on PATH")
    prompt = build_prompt(root)
    return [binary] + [part.format(root=root, prompt=prompt) for part in template[1:]]


def wait_while_active(root: Path) -> bool:
    """Sleep until the interval passes. Return False if the loop was paused (not idle)."""
    deadline = time.monotonic() + interval()
    while time.monotonic() < deadline:
        if read_status(root) not in ACTIVE_STATUSES:
            return False
        time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
    return read_status(root) in ACTIVE_STATUSES


def serve(root: Path, owner: str) -> int:
    registered = read_registered_owner(root)
    if registered and registered != owner:
        raise SystemExit(
            f"refusing to serve as owner={owner!r}: scheduler.json is owned by {registered!r}. "
            "Who starts the loop ticks as that owner; do not start another agent's runner."
        )
    record = read_record(root)
    other = record.get("pid")
    if isinstance(other, int) and other != os.getpid() and alive(other):
        other_owner = record.get("owner")
        if other_owner and other_owner != owner:
            raise SystemExit(
                f"refusing to serve as owner={owner!r}: a runner for owner={other_owner!r} "
                f"is already alive (pid {other})"
            )
        return 0
    state = {
        "pid": os.getpid(), "owner": owner, "runner": owner, "started": now(), "ticks": 0,
        "tick_pid": None,
    }
    write_record(root, state)
    choice = choice_path(root)
    choice.parent.mkdir(parents=True, exist_ok=True)
    choice.write_text(owner + "\n", encoding="utf-8")
    log_path = scratch(root) / "scheduler.log"
    try:
        while read_status(root) in ACTIVE_STATUSES:
            argv = tick_argv(root, owner)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"{now()} tick owner={owner} status={read_status(root)} cmd={argv[0]}\n")
                log.flush()
                try:
                    proc = subprocess.Popen(argv, cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                except OSError as exc:
                    log.write(f"{now()} failed to start tick: {exc}\n")
                    if not wait_while_active(root):
                        break
                    continue
                state["tick_pid"] = proc.pid
                write_record(root, state)
                try:
                    proc.wait(timeout=TICK_TIMEOUT)
                except subprocess.TimeoutExpired:
                    log.write(f"{now()} tick exceeded {TICK_TIMEOUT}s and was stopped\n")
                    proc.kill()
                    proc.wait(timeout=10)
            state["tick_pid"] = None
            state["ticks"] = int(state.get("ticks") or 0) + 1
            write_record(root, state)
            if not wait_while_active(root):
                break
    finally:
        current = read_record(root)
        if current.get("pid") == os.getpid():
            current["pid"] = None
            current["tick_pid"] = None
            write_record(root, current)
    return 0


def snapshot(root: Path) -> dict:
    record = read_record(root)
    pid = record.get("pid") if isinstance(record.get("pid"), int) else None
    running = alive(pid)
    if pid and not running:
        pid = None
    tick = record.get("tick_pid") if isinstance(record.get("tick_pid"), int) else None
    choice = ""
    try:
        choice = choice_path(root).read_text(encoding="utf-8").strip()
    except OSError:
        choice = ""
    owner = record.get("owner") if running and isinstance(record.get("owner"), str) else choice
    if owner not in OWNERS:
        # legacy runner field
        legacy = record.get("runner") if running and isinstance(record.get("runner"), str) else choice
        owner = legacy if legacy in OWNERS else None
    return {
        "available": list(OWNERS) if os.environ.get("EMLAB_LOOP_TICK_ARGV") else [name for name in OWNERS if shutil.which(name)],
        "owner": owner,
        "runner": owner,  # alias for older dashboards
        "alive": running,
        "pid": pid,
        "ticks": int(record.get("ticks") or 0),
        "in_tick": bool(running and tick and alive(tick)),
        "started": record.get("started") if running else None,
        "interval_s": int(interval()),
        "registered_owner": read_registered_owner(root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Same-owner headless schedule: wake only this agent's CLI while status is running."
    )
    parser.add_argument("--root", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    serve_cmd = sub.add_parser("serve", help="run the schedule in this process for --owner")
    serve_cmd.add_argument(
        "--owner",
        required=True,
        choices=OWNERS,
        help="this agent product; ticks wake only this CLI (never another product)",
    )
    # Deprecated alias: kept so old scripts fail loudly if they pass a different product.
    serve_cmd.add_argument("--runner", choices=OWNERS, help=argparse.SUPPRESS)
    sub.add_parser("status", help="print the scheduler snapshot as JSON")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == "status":
        print(json.dumps(snapshot(root), indent=2))
        return 0
    owner = args.owner
    if args.runner and args.runner != owner:
        raise SystemExit(
            f"--runner {args.runner!r} disagrees with --owner {owner!r}: "
            "who starts the loop must tick as that same owner"
        )
    return serve(root, owner)


if __name__ == "__main__":
    sys.exit(main())
