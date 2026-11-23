"""Tests for skills/auto-research/scripts/loop_state.py (run with .venv/bin/pytest)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loop_state.py"
REPO = Path(__file__).resolve().parents[3]

spec = importlib.util.spec_from_file_location("loop_state", SCRIPT)
loop_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loop_state)

LAB = "2026-09-25-some-lab"
STAMP = "2026-09-25T09:00:00Z"


def thread(number: int, status: str, last_author: str = "agent", last_type: str = "question") -> dict:
    messages = [{"id": "msg-001", "author": "agent", "type": last_type, "created": STAMP, "content": "Q?"}]
    if last_author == "user":
        messages.append({"id": "msg-002", "author": "user", "type": "decision", "created": STAMP, "content": "A."})
    if status == "closed":
        messages.append({"id": f"msg-{len(messages) + 1:03d}", "author": "agent", "type": "resolution",
                         "created": STAMP, "content": "Done."})
    return {"id": f"thread-{number:03d}", "title": f"Thread {number}", "category": "decision",
            "priority": "normal", "status": status, "related_labs": [], "created": STAMP, "updated": STAMP,
            "messages": messages}


def write_threads(root: Path, *threads: dict) -> None:
    path = root / ".auto-research" / "state.json"
    folder = root / ".auto-research" / "threads"
    folder.mkdir(parents=True, exist_ok=True)
    state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "schema": loop_state.SCHEMA, "status": "paused", "updated": STAMP, "active_deliverable": None,
        "next_action": "Run one supervisor tick.",
        "last_action": None, "last_supervisor_at": None, "idle": None, "tasks": [],
    }
    state.setdefault("idle", None)
    state.setdefault("last_supervisor_at", None)
    state.pop("pending_human_thread_id", None)
    state.pop("threads", None)
    # meta in state; messages in files
    state["threads"] = [{k: v for k, v in item.items() if k != "messages"} for item in threads]
    for old in folder.glob("thread-*.json"):
        old.unlink()
    for item in threads:
        (folder / f"{item['id']}.json").write_text(
            json.dumps({"messages": item["messages"]}), encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".auto-research").mkdir(exist_ok=True)
    (tmp_path / "labs" / LAB).mkdir(parents=True)
    (tmp_path / ".auto-research" / "tasks").mkdir(parents=True)
    (tmp_path / ".auto-research" / "threads").mkdir(parents=True)
    state = {"schema": loop_state.SCHEMA, "status": "paused", "updated": STAMP, "active_deliverable": None,
             "next_action": "Run one supervisor tick.",
             "last_action": None, "last_supervisor_at": None, "idle": None, "tasks": [], "threads": []}
    (tmp_path / ".auto-research" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    write_threads(tmp_path, thread(1, "open"), thread(2, "closed"))
    return tmp_path


def run(root: Path, *args: str, capsys=None, expect: int = 0):
    code = loop_state.main(["--root", str(root), *args])
    assert code == expect
    if capsys is not None:
        return capsys.readouterr()
    return None


def stored(root: Path) -> dict:
    return json.loads((root / ".auto-research" / "state.json").read_text(encoding="utf-8"))


TASK_BODY = """## Goal
Do the concrete work.

## Work
Follow the lab report and package API.

## Done when
The test passes.
"""


def add(root: Path, title: str, *extra: str, body: str = TASK_BODY) -> None:
    run(root, "task", "add", "--title", title, "--for", "integrator", "--gpu", "free", "--time", "5min",
        "--content", body, *extra)


def ids(root: Path) -> list[str]:
    return [item["id"] for item in stored(root)["tasks"]]


def test_status_transitions_and_action_log(root, capsys):
    run(root, "start", "--summary", "Loop started.")
    state = stored(root)
    assert state["status"] == "running" and state["last_action"]["summary"] == "Loop started."
    assert state["updated"] != STAMP
    run(root, "log-action", "--summary", "Landed the decoder test.", "--next", "Run the smoke test.")
    state = stored(root)
    assert state["last_action"]["summary"] == "Landed the decoder test."
    assert state["next_action"] == "Run the smoke test."
    run(root, "set-next", "--text", "Harvest the detached run.")
    assert stored(root)["next_action"] == "Harvest the detached run."
    run(root, "pause")
    run(root, "idle", "--reason", "router-empty",
        "--lift-when", "An unblocked task appears or a deliverable is set.",
        "--detail", "Supervisor refill and maintain side-work found nothing runnable.")
    state = stored(root)
    assert state["status"] == "idle"
    assert state["idle"]["reason"] == "router-empty"
    assert "unblocked" in state["idle"]["lift_when"].lower()
    assert isinstance(state["idle"]["fingerprint"], dict)
    capsys.readouterr()
    check = json.loads(run(root, "idle-check", "--json", capsys=capsys).out)
    assert check["probe"] == "unchanged" and check["changed"] is False
    run(root, "start", "--summary", "Lifted idle.")
    assert stored(root)["status"] == "running" and stored(root)["idle"] is None
    run(root, "set-next", "--text", "   ", expect=1)


def test_deliverable_needs_a_real_lab_and_acceptance(root, capsys):
    run(root, "set-deliverable", "--lab", LAB, "--summary", "Ship the figure.",
        "--acceptance", "figure renders", "--acceptance", "numbers match results.json")
    assert stored(root)["active_deliverable"] == {"lab": LAB, "summary": "Ship the figure.",
                                                   "acceptance": ["figure renders", "numbers match results.json"]}
    run(root, "set-deliverable", "--lab", "2026-01-01-missing", "--summary", "x", "--acceptance", "y", expect=1)
    run(root, "set-deliverable", "--lab", LAB, "--summary", "no criteria", expect=1)
    assert "not a lab" in capsys.readouterr().err
    run(root, "set-deliverable", "--clear")
    assert stored(root)["active_deliverable"] is None


def test_status_derives_awaiting_human_from_open_agent_threads(root, capsys):
    write_threads(root, thread(1, "open", last_author="agent"), thread(2, "open", last_author="user"),
                  thread(3, "closed"))
    out = run(root, "status", "--json", capsys=capsys).out
    payload = json.loads(out)
    assert payload["awaiting_human"] == ["thread-001"]
    assert "Threads awaiting researcher: thread-001" in payload["notes"]
    assert "thread-002" in " ".join(payload["notes"])


def test_closed_threads_are_not_awaiting_human(root, capsys):
    write_threads(root, thread(1, "closed"), thread(2, "closed"))
    out = run(root, "status", "--json", capsys=capsys).out
    payload = json.loads(out)
    assert payload["awaiting_human"] == []
    assert "awaiting researcher: none" in run(root, "status", capsys=capsys).out


def test_agent_progress_is_not_awaiting_human(root, capsys):
    write_threads(root, thread(1, "open", last_author="agent", last_type="progress"))
    out = run(root, "status", "--json", capsys=capsys).out
    payload = json.loads(out)
    assert payload["awaiting_human"] == []


def test_task_add_writes_body_and_orders(root, capsys):
    add(root, "Port the relay decoder (serial schedule)")
    add(root, "Audit the port", "--top")
    add(root, "Measure the port", "--after", "audit-the-port")
    add(root, "Write the report", "--before", "port-the-relay-decoder")
    assert ids(root) == ["audit-the-port", "measure-the-port", "write-the-report", "port-the-relay-decoder"]
    item = stored(root)["tasks"][-1]
    assert item["detail"] == ".auto-research/tasks/port-the-relay-decoder.md"
    assert item["blocked_on"] is None and item["related_labs"] == [] and item["for"] == "integrator"
    body = (root / item["detail"]).read_text(encoding="utf-8")
    assert body.startswith("# Port the relay decoder (serial schedule)\n")
    assert "## Goal\n" in body and "## Work\n" in body and "## Done when\n" in body
    add(root, "Audit the port")
    assert ids(root)[-1] == "audit-the-port-2"


def test_task_add_rejects_bad_input(root, capsys):
    run(root, "task", "add", "--title", "x", "--for", "wizard", "--gpu", "free", "--time", "0",
        "--content", "body", expect=1)
    run(root, "task", "add", "--title", "x", "--for", "scout", "--gpu", "free", "--time", "0",
        "--content", "  ", expect=1)
    run(root, "task", "add", "--title", "x", "--for", "scout", "--gpu", "free", "--time", "0",
        "--lab", "2026-01-01-missing", "--content", "body", expect=1)
    with pytest.raises(SystemExit):
        loop_state.main(["--root", str(root), "task", "add", "--title", "x", "--for", "scout",
                         "--gpu", "huge", "--time", "0", "--content", "body"])
    assert ids(root) == []
    assert list((root / ".auto-research" / "tasks").iterdir()) == []


def test_task_body_from_stdin(root, monkeypatch):
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(
        "## Goal\nFrom stdin.\n\n## Work\nDo it.\n\n## Done when\nDone.\n"))
    run(root, "task", "add", "--title", "From stdin", "--for", "scout, reproducer", "--gpu", "light",
        "--time", "1hr", "--lab", LAB, "--content-file", "-")
    item = stored(root)["tasks"][0]
    assert item["for"] == "scout, reproducer" and item["related_labs"] == [LAB]
    assert "## Goal\nFrom stdin." in (root / item["detail"]).read_text(encoding="utf-8")


def test_task_block_rules(root, capsys):
    add(root, "Train the decoder")
    run(root, "task", "block", "train-the-decoder", "--on", "GPU unavailable", expect=1)
    assert "spending-compute" in capsys.readouterr().err
    run(root, "task", "block", "train-the-decoder", "--on", "researcher choice in thread-002", expect=1)
    run(root, "task", "block", "train-the-decoder", "--on", "researcher choice in thread-007", expect=1)
    run(root, "task", "block", "train-the-decoder", "--on", "researcher choice of GPU days in thread-001")
    assert stored(root)["tasks"][0]["blocked_on"] == "researcher choice of GPU days in thread-001"
    capsys.readouterr()
    run(root, "task", "list", "--unblocked", "--json")
    assert json.loads(capsys.readouterr().out) == []
    run(root, "task", "unblock", "train-the-decoder")
    run(root, "task", "unblock", "train-the-decoder", expect=1)
    run(root, "task", "block", "train-the-decoder", "--on", "authors must publish the weights")


def test_task_list_filters_by_gpu_tier(root, capsys):
    add(root, "Free item")
    run(root, "task", "add", "--title", "Heavy item", "--for", "auto", "--gpu", "heavy", "--time", "1d",
        "--content", "## Goal\nTrain.\n\n## Work\nRun training.\n\n## Done when\nCheckpoint registered.")
    capsys.readouterr()
    run(root, "task", "list", "--fits", "light", "--json")
    assert [r["id"] for r in json.loads(capsys.readouterr().out)] == ["free-item"]
    run(root, "task", "list", "--fits", "heavy", "--json")
    rows = json.loads(capsys.readouterr().out)
    assert [(r["rank"], r["id"]) for r in rows] == [(1, "free-item"), (2, "heavy-item")]


def test_task_move_set_show_done(root, capsys):
    add(root, "First")
    add(root, "Second")
    run(root, "task", "move", "second", "--top")
    assert ids(root) == ["second", "first"]
    run(root, "task", "move", "second", "--bottom")
    assert ids(root) == ["first", "second"]
    run(root, "task", "set", "first", "--title", "First, renamed", "--time", "15min", "--lab", LAB)
    item = stored(root)["tasks"][0]
    assert item["id"] == "first" and item["time"] == "15min" and item["related_labs"] == [LAB]
    out = run(root, "task", "show", "first", capsys=capsys).out
    assert "# First, renamed\n" in out and "## Goal\n" in out
    run(root, "task", "set", "first", expect=1)
    run(root, "task", "done", "first", "--summary", "Finished the first item.")
    assert ids(root) == ["second"]
    assert not (root / ".auto-research" / "tasks" / "first.md").exists()
    assert stored(root)["last_action"]["summary"] == "Finished the first item."
    run(root, "task", "done", "first", expect=1)


@pytest.mark.parametrize("damage, message", [
    (lambda s: s.update(schema="other/1"), "schema must be"),
    (lambda s: s.update(status="asleep"), "status"),
    (lambda s: s.update(next_action=""), "next_action"),
    (lambda s: s.update(extra=1), "unexpected ['extra']"),
    (lambda s: s["tasks"][0].update(gpu="huge"), "gpu"),
    (lambda s: s["tasks"][0].update(time="3hr"), "time"),
    (lambda s: s["tasks"][0].update(added="26 Sep"), "added"),
    (lambda s: s["tasks"][0].update(detail=".auto-research/tasks/other.md"), "detail must be"),
    (lambda s: s["tasks"].append(dict(s["tasks"][0])), "duplicate id"),
    (lambda s: s["tasks"][0].update(related_labs=["2026-01-01-missing"]), "not a lab"),
    (lambda s: s.update(orphan_field=1), "unexpected"),
    (lambda s: s.update(last_action={"at": "yesterday", "summary": "x"}), "last_action"),
])
def test_validation_problems(root, capsys, damage, message):
    add(root, "An item")
    state = stored(root)
    damage(state)
    (root / ".auto-research" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    run(root, "validate", expect=1)
    assert message in capsys.readouterr().err


def test_missing_and_orphan_detail_files(root, capsys):
    add(root, "An item")
    (root / ".auto-research" / "tasks" / "stray.md").write_text("# Stray\n", encoding="utf-8")
    run(root, "validate", expect=1)
    assert "stray.md has no task" in capsys.readouterr().err
    run(root, "task", "add", "--title", "Another", "--for", "scout", "--gpu", "free", "--time", "0",
        "--content", "body", expect=1)
    (root / ".auto-research" / "tasks" / "stray.md").unlink()
    (root / ".auto-research" / "tasks" / "an-item.md").unlink()
    run(root, "validate", expect=1)
    assert "detail file .auto-research/tasks/an-item.md is missing" in capsys.readouterr().err


def test_refused_write_leaves_files_untouched(root):
    before = (root / ".auto-research" / "state.json").read_text(encoding="utf-8")
    run(root, "set-deliverable", "--lab", "2026-01-01-missing", "--summary", "x",
        "--acceptance", "y", expect=1)
    assert (root / ".auto-research" / "state.json").read_text(encoding="utf-8") == before
    assert not list((root / ".auto-research").glob(".state.json.*"))


def test_status_reports_waiting_researcher_messages_and_stalls(root, capsys):
    write_threads(root, thread(1, "open", last_author="user"), thread(2, "closed"))
    state = stored(root)
    state.update(status="running", last_action={"at": "2026-01-01T00:00:00Z", "summary": "Old action."})
    (root / ".auto-research" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    out = run(root, "status", capsys=capsys).out
    assert "thread-001" in out and "no action logged" in out and "refill the tasks" in out


def test_task_body_rejects_freeform_sections(root, capsys):
    run(root, "task", "add", "--title", "Freeform", "--for", "auto", "--gpu", "free", "--time", "0",
        "--content", "Just a paragraph with Done when buried in prose.", expect=1)
    assert "headings must be exactly" in capsys.readouterr().err
    assert ids(root) == []


def test_check_task_body_accepts_canonical_shape():
    text = "# Title\n\n## Goal\nG.\n\n## Work\nW.\n\n## Done when\nD.\n"
    assert loop_state.check_task_body(text) == []
    assert "###" in loop_state.check_task_body("# T\n\n## Goal\nG\n\n## Work\n### nope\n\n## Done when\nD\n")[0]


def test_slugify_trims_parentheticals_and_stopwords():
    assert loop_state.slugify("Re-measure the BP anchor (serial) under", set()) == "re-measure-the-bp-anchor"
    assert loop_state.slugify("x" * 80, set()) == "item"
    long = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    assert len(loop_state.slugify(long, set())) <= loop_state.MAX_SLUG


def test_repository_state_is_valid():
    done = subprocess.run([sys.executable, str(SCRIPT), "--root", str(REPO), "validate"],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr


def test_running_flag_without_a_scheduler_is_not_live(root, capsys):
    out = run(root, "start", "--summary", "Loop started.", capsys=capsys).out
    assert "no scheduler is registered" in out
    status = run(root, "status", "--json", capsys=capsys).out
    live = json.loads(status)
    assert live["liveness"]["verdict"] == "UNSCHEDULED"
    assert live["notes"][0].startswith("LOOP NOT TICKING")


def test_scheduler_register_verify_and_stale(root, capsys):
    run(root, "start", "--summary", "Loop started.")
    run(root, "scheduler", "--set", "session-cron", "abc123", "--every-min", "12", "--owner", "claude")
    capsys.readouterr()
    live = json.loads(run(root, "status", "--json", capsys=capsys).out)["liveness"]
    assert live["verdict"] == "live"
    assert "owner=claude" in live["detail"]
    run(root, "scheduler", "--verify", "abc123", "zzz", capsys=capsys)
    # a registered job that CronList does not show is dead: refused, and the registration is dropped
    run(root, "scheduler", "--verify", "other", expect=1)
    assert not (root / ".auto-research" / "scheduler.json").exists()
    capsys.readouterr()
    assert json.loads(run(root, "status", "--json", capsys=capsys).out)["liveness"]["verdict"] == "UNSCHEDULED"
    run(root, "scheduler", "--verify", expect=1)


def test_registered_scheduler_with_old_last_action_is_stale(root, capsys):
    run(root, "start", "--summary", "Loop started.")
    run(root, "scheduler", "--set", "session-cron", "abc123", "--every-min", "12", "--owner", "claude")
    state = stored(root)
    state["last_action"]["at"] = "2026-01-01T00:00:00Z"
    (root / ".auto-research" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    capsys.readouterr()
    live = json.loads(run(root, "status", "--json", capsys=capsys).out)["liveness"]
    assert live["verdict"] == "STALE"


def test_pause_deregisters_the_scheduler_and_says_to_stop_the_job(root, capsys):
    run(root, "start")
    run(root, "scheduler", "--set", "session-cron", "abc123", "--every-min", "12", "--owner", "claude")
    out = run(root, "pause", capsys=capsys).out
    assert "owner=claude" in out and not (root / ".auto-research" / "scheduler.json").exists()


def test_scheduler_set_rejects_bad_input(root):
    run(root, "scheduler", "--set", "nonsense", "x", "--every-min", "12", "--owner", "claude", expect=1)
    run(root, "scheduler", "--set", "session-cron", "--every-min", "12", "--owner", "claude", expect=1)
    run(root, "scheduler", "--set", "session-cron", "abc", "--owner", "claude", expect=1)
    run(root, "scheduler", "--set", "session-cron", "abc", "--every-min", "12", expect=1)
    run(root, "scheduler", "--set", "runner", "pid1", "--every-min", "12", "--owner", "cursor", expect=1)


def test_scheduler_requires_owner_and_records_it(root, capsys):
    run(root, "start", "--summary", "Loop started.")
    capsys.readouterr()
    out = run(root, "scheduler", "--set", "runner", "4242", "--every-min", "12", "--owner", "codex",
              "--json", capsys=capsys).out
    entry = json.loads(out)
    assert entry["owner"] == "codex" and entry["kind"] == "runner"
    stored_sched = json.loads((root / ".auto-research" / "scheduler.json").read_text(encoding="utf-8"))
    assert stored_sched["owner"] == "codex"


def test_log_action_supervisor_updates_last_supervisor_at(root, capsys, monkeypatch):
    # Each mutate calls now() once inside change and once for state["updated"].
    stamps = (f"2026-11-23T12:{i:02d}:00Z" for i in range(20))
    monkeypatch.setattr(loop_state, "now", lambda: next(stamps))
    run(root, "start", "--summary", "Loop started.")
    capsys.readouterr()
    assert stored(root)["last_supervisor_at"] is None
    out = run(root, "log-action", "--summary", "supervisor: refilled tasks.",
              "--kind", "supervisor", "--json", capsys=capsys).out
    payload = json.loads(out)
    assert payload["kind"] == "supervisor"
    first_sup = stored(root)["last_supervisor_at"]
    assert first_sup == stored(root)["last_action"]["at"]
    assert payload["last_supervisor_at"] == first_sup
    run(root, "log-action", "--summary", "research: advanced the lab.", "--kind", "research")
    assert stored(root)["last_supervisor_at"] == first_sup
    run(root, "log-action", "--summary", "supervisor: hygiene pass.")  # prefix alone
    assert stored(root)["last_supervisor_at"] != first_sup
    assert stored(root)["last_supervisor_at"] == stored(root)["last_action"]["at"]


def _status_json(root, capsys) -> dict:
    capsys.readouterr()
    return json.loads(run(root, "status", "--json", capsys=capsys).out)


def test_suggested_tick_kind_forces_supervisor_and_idle(root, capsys):
    run(root, "start", "--summary", "Loop started.")
    add(root, "Runnable work")
    # Never supervised → forced supervisor even with a runnable task.
    suggestion = _status_json(root, capsys)["suggested_kind"]
    assert suggestion["kind"] == "supervisor" and suggestion["forced"] is True
    assert "no supervisor" in suggestion["reason"]

    run(root, "log-action", "--summary", "supervisor: baseline.", "--kind", "supervisor")
    # Fresh supervisor + runnable task → suggested research (not forced).
    suggestion = _status_json(root, capsys)["suggested_kind"]
    assert suggestion["kind"] == "research" and suggestion["forced"] is False

    # Empty queue + no deliverable → forced supervisor.
    run(root, "task", "done", "runnable-work")
    suggestion = _status_json(root, capsys)["suggested_kind"]
    assert suggestion["kind"] == "supervisor" and suggestion["forced"] is True
    assert "no unblocked task" in suggestion["reason"]

    # Overdue supervisor interval → forced even with a task.
    add(root, "More work")
    state = stored(root)
    state["last_supervisor_at"] = "2026-01-01T00:00:00Z"
    (root / ".auto-research" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    suggestion = _status_json(root, capsys)["suggested_kind"]
    assert suggestion["kind"] == "supervisor" and suggestion["forced"] is True
    assert "min ago" in suggestion["reason"]

    run(root, "idle", "--reason", "router-empty",
        "--lift-when", "An unblocked task appears.",
        "--detail", "Nothing runnable after refill.")
    suggestion = _status_json(root, capsys)["suggested_kind"]
    assert suggestion == {"kind": "idle-probe", "forced": True, "reason": "status is idle"}


def test_loop_runner_prompt_embeds_suggested_kind(root):
    runner_path = Path(__file__).resolve().parents[1] / "scripts" / "loop_runner.py"
    spec_r = importlib.util.spec_from_file_location("loop_runner", runner_path)
    runner = importlib.util.module_from_spec(spec_r)
    spec_r.loader.exec_module(runner)

    run(root, "start", "--summary", "Loop started.")
    prompt = runner.build_prompt(root)
    assert "suggested_kind=supervisor" in prompt and "forced=true" in prompt
    assert "You MUST run a supervisor tick" in prompt

    add(root, "Work item")
    run(root, "log-action", "--summary", "supervisor: ok.", "--kind", "supervisor")
    prompt = runner.build_prompt(root)
    assert "suggested_kind=research" in prompt and "forced=false" in prompt
