"""Tests for skills/thread-interaction/scripts/thread_interaction.py (run with .venv/bin/pytest)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "thread_interaction.py"
REPO = Path(__file__).resolve().parents[3]

spec = importlib.util.spec_from_file_location("thread_interaction", SCRIPT)
mb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb)

LAB = "2026-09-25-some-lab"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".auto-research").mkdir(exist_ok=True)
    (tmp_path / ".auto-research" / "threads").mkdir(exist_ok=True)
    state = {
        "schema": "auto-research-1",
        "status": "paused",
        "updated": "2026-01-01T00:00:00Z",
        "active_deliverable": None,
        "next_action": "Seeded for tests.",
        "last_action": None,
        "last_supervisor_at": None,
        "idle": None,
        "tasks": [],
        "threads": [],
    }
    (tmp_path / ".auto-research" / "state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "labs" / LAB).mkdir(parents=True)
    return tmp_path


def run(root: Path, *args: str, capsys=None, expect: int = 0):
    code = mb.main(["--root", str(root), *args])
    assert code == expect
    if capsys is not None:
        return capsys.readouterr()
    return None


def stored(root: Path) -> dict:
    return json.loads((root / ".auto-research" / "state.json").read_text(encoding="utf-8"))


def stored_threads(root: Path) -> list[dict]:
    state = stored(root)
    out = []
    for meta in state.get("threads") or []:
        tid = meta["id"]
        messages = json.loads(
            (root / ".auto-research" / "threads" / f"{tid}.json").read_text(encoding="utf-8")
        )["messages"]
        out.append({**meta, "messages": messages})
    return out


def stored_thread(root: Path, thread_id: str = "thread-001") -> dict:
    return next(t for t in stored_threads(root) if t["id"] == thread_id)


def open_question(root: Path, title: str = "Choose the decoder family", **extra) -> None:
    args = ["open", "--title", title, "--category", "decision", "--priority", "normal",
            "--content", "**What this is about** ..."]
    for key, value in extra.items():
        args += [f"--{key}", value]
    run(root, *args)


def block_task(root: Path, thread_id: str) -> None:
    state = stored(root)
    state["tasks"] = [
        {"id": "held-task", "blocked_on": f"researcher decision ({thread_id})"},
        {"id": "free-task", "blocked_on": ""},
    ]
    (root / ".auto-research" / "state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_progress_report_awaits_nobody_even_when_a_task_still_cites_the_thread(root, capsys):
    open_question(root)
    run(root, "reply", "thread-001", "--author", "user", "--type", "decision", "--content", "Option A.")
    capsys.readouterr()
    run(root, "list", "--json")
    assert json.loads(capsys.readouterr().out)[0]["awaiting"] == "agent"
    run(root, "reply", "thread-001", "--author", "agent", "--content", "Option A is running.")
    capsys.readouterr()
    run(root, "list", "--json")
    assert json.loads(capsys.readouterr().out)[0]["awaiting"] is None
    block_task(root, "thread-001")
    run(root, "list", "--json")
    assert json.loads(capsys.readouterr().out)[0]["awaiting"] is None


def test_question_cycle_hands_off_and_closes(root, capsys):
    open_question(root, lab=LAB)
    capsys.readouterr()
    run(root, "list", "--status", "open", "--json")
    listed = json.loads(capsys.readouterr().out)
    assert [t["id"] for t in listed] == ["thread-001"] and listed[0]["awaiting"] is None

    block_task(root, "thread-001")
    run(root, "list", "--status", "open", "--json")
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["awaiting"] == "user" and listed[0]["blocks"] == ["held-task"]

    run(root, "reply", "thread-001", "--author", "user", "--type", "decision", "--content", "Option A.")
    run(root, "reply", "thread-001", "--author", "agent", "--content", "Running option A now.")
    run(root, "close", "thread-001", "--content", "Done: option A, see labs/2026-09-25-some-lab/report.md.")
    thread = stored_thread(root)
    assert thread["status"] == "closed"
    assert thread["related_labs"] == [LAB]
    assert [m["id"] for m in thread["messages"]] == ["msg-001", "msg-002", "msg-003", "msg-004"]
    assert [(m["author"], m["type"]) for m in thread["messages"]] == [
        ("agent", "question"), ("user", "decision"), ("agent", "reply"), ("agent", "resolution")]
    assert thread["updated"] == thread["messages"][-1]["created"]
    assert thread["created"] == thread["messages"][0]["created"]


def test_user_instruction_opens_direction_thread(root):
    run(root, "open", "--author", "user", "--title", "Benchmark the new decoder", "--content", "Do X.")
    thread = stored_thread(root)
    assert thread["category"] == "direction"
    assert (thread["messages"][0]["author"], thread["messages"][0]["type"]) == ("user", "instruction")


def test_thread_ids_follow_existing_threads(root):
    open_question(root, "First")
    open_question(root, "Second")
    run(root, "close", "thread-001", "--content", "Resolved.")
    open_question(root, "Third")
    assert [t["id"] for t in stored_threads(root)] == ["thread-001", "thread-002", "thread-003"]


def test_existing_messages_are_never_rewritten(root):
    open_question(root)
    before = stored_thread(root)["messages"]
    run(root, "reply", "thread-001", "--author", "user", "--type", "decision", "--content", "B")
    run(root, "close", "thread-001", "--content", "Closed with B.")
    run(root, "reopen", "thread-001", "--author", "user", "--content", "B did not work; revisit.")
    after = stored_thread(root)["messages"]
    assert after[:len(before)] == before
    assert stored_thread(root)["status"] == "open"
    assert after[-1]["type"] == "reply" and after[-1]["author"] == "user"


def test_append_only_guard_rejects_edits(root):
    open_question(root)
    before = stored_threads(root)
    after = json.loads(json.dumps(before))
    after[0]["messages"][0]["content"] = "rewritten"
    with pytest.raises(mb.ThreadsError):
        mb.check_append_only(before, after)
    after = json.loads(json.dumps(before))
    after = []
    with pytest.raises(mb.ThreadsError):
        mb.check_append_only(before, after)


def test_closed_thread_rejects_replies_until_reopened(root, capsys):
    open_question(root)
    run(root, "close", "thread-001", "--content", "Resolved.")
    capsys.readouterr()
    run(root, "reply", "thread-001", "--author", "agent", "--content", "late", expect=1)
    assert "reopen it first" in capsys.readouterr().err
    run(root, "close", "thread-001", "--content", "again", expect=1)
    run(root, "reopen", "thread-001", "--author", "agent", "--content", "Result did not replicate.")
    run(root, "reply", "thread-001", "--author", "agent", "--content", "New evidence.")
    run(root, "reopen", "thread-001", "--author", "agent", "--content", "x", expect=1)


@pytest.mark.parametrize("author,kind", [("agent", "decision"), ("agent", "instruction"), ("user", "question")])
def test_type_author_rules(root, author, kind):
    open_question(root)
    run(root, "reply", "thread-001", "--author", author, "--type", kind, "--content", "text", expect=1)


def test_resolution_only_through_close(root):
    open_question(root)
    run(root, "reply", "thread-001", "--author", "agent", "--type", "resolution", "--content", "x", expect=1)


def test_user_close_records_their_resolution(root):
    open_question(root)
    run(root, "close", "thread-001", "--author", "user", "--content", "Withdrawn — no longer needed.")
    thread = stored_thread(root)
    assert thread["status"] == "closed"
    last = thread["messages"][-1]
    assert (last["author"], last["type"], last["content"]) == (
        "user", "resolution", "Withdrawn — no longer needed.")


def test_open_rejects_bad_inputs(root, capsys):
    open_question(root)
    capsys.readouterr()
    run(root, "open", "--title", "choose THE decoder family", "--content", "dup", expect=1)
    assert "already open" in capsys.readouterr().err
    run(root, "open", "--title", "Other", "--lab", "2026-01-01-missing", "--content", "x", expect=1)
    run(root, "open", "--title", "Other", "--lab", "not-a-lab", "--content", "x", expect=1)
    run(root, "open", "--title", "Other", "--content", "   ", expect=1)
    run(root, "open", "--author", "user", "--type", "question", "--title", "Other", "--content", "x", expect=1)
    with pytest.raises(SystemExit):
        mb.main(["--root", str(root), "open", "--title", "Other", "--category", "urgent", "--content", "x"])
    assert len(stored_threads(root)) == 1


def test_unknown_thread(root, capsys):
    run(root, "show", "thread-404", expect=1)
    assert "unknown thread" in capsys.readouterr().err


def test_content_file_and_stdin(root, tmp_path, monkeypatch):
    body = tmp_path / "brief.md"
    body.write_text("**What this is about**\n\nLong brief.\n", encoding="utf-8")
    run(root, "open", "--title", "From file", "--content-file", str(body))
    assert stored_thread(root)["messages"][0]["content"] == "**What this is about**\n\nLong brief."
    run(root, "reply", "thread-001", "--author", "user", "--type", "decision", "--content", "Go.")
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("piped reply\n"))
    run(root, "reply", "thread-001", "--author", "agent", "--content-file", "-")
    assert stored_thread(root)["messages"][-1]["content"] == "piped reply"


def test_reply_adds_related_lab(root):
    open_question(root)
    run(root, "reply", "thread-001", "--author", "user", "--type", "decision", "--content", "Go.")
    run(root, "reply", "thread-001", "--author", "agent", "--lab", LAB, "--content", "Lab created.")
    assert stored_thread(root)["related_labs"] == [LAB]


def test_hygiene_allows_clarifying_question_before_decision_is_taken_up(root):
    open_question(root)
    run(root, "reply", "thread-001", "--author", "user", "--type", "decision", "--content", "Option A.")
    # Same concern: agent still needs a clarification before acknowledging/applying.
    run(root, "reply", "thread-001", "--author", "agent", "--type", "question",
        "--content", "**What this is about:** confirm A means A1 not A2")
    assert stored_thread(root)["messages"][-1]["type"] == "question"


def test_hygiene_refuses_question_after_decision_was_taken_up(root, capsys):
    open_question(root)
    run(root, "reply", "thread-001", "--author", "user", "--type", "decision", "--content", "Option A.")
    run(root, "reply", "thread-001", "--author", "agent", "--content", "Applying Option A.")
    capsys.readouterr()
    run(root, "reply", "thread-001", "--author", "agent", "--type", "question",
        "--content", "**What this is about:** a second concern", expect=1)
    assert "already has a researcher decision" in capsys.readouterr().err
    run(root, "reply", "thread-001", "--author", "agent", "--type", "question", "--continue-thread",
        "--content", "**What this is about:** correction to the same concern")
    assert stored_thread(root)["messages"][-1]["type"] == "question"


def test_hygiene_refuses_reply_on_top_of_own_question(root, capsys):
    open_question(root)
    capsys.readouterr()
    run(root, "reply", "thread-001", "--author", "agent", "--content", "Still training…", expect=1)
    assert "awaiting-reply" in capsys.readouterr().err
    run(root, "reply", "thread-001", "--author", "agent", "--continue-thread",
        "--content", "Note in threads store despite the rule.")
    assert stored_thread(root)["messages"][-1]["content"] == "Note in threads store despite the rule."



def test_write_is_atomic_and_leaves_no_temporary(root):
    path = root / ".auto-research" / "state.json"
    path.chmod(0o644)
    open_question(root)
    assert sorted(p.name for p in (root / ".auto-research").iterdir()) == ["state.json", "tasks", "threads"]
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert path.stat().st_mode & 0o777 == 0o644


def test_invalid_file_is_refused_not_repaired(root, capsys):
    open_question(root)
    path = root / ".auto-research" / "threads" / "thread-001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["messages"][0]["id"] = "msg-007"
    path.write_text(json.dumps(data), encoding="utf-8")
    # Corrupted message id must fail validation on next read/write
    run(root, "list", expect=1)
    assert "out of sequence" in capsys.readouterr().err
    assert json.loads(path.read_text(encoding="utf-8")) == data


def good_thread(**changes) -> dict:
    thread = {"id": "thread-001", "title": "T", "category": "decision", "priority": "normal",
              "status": "closed", "related_labs": [], "created": "2026-06-01T00:00:00Z",
              "updated": "2026-06-02T00:00:00Z",
              "messages": [{"id": "msg-001", "author": "agent", "type": "question",
                            "created": "2026-06-01T00:00:00Z", "content": "Q"},
                           {"id": "msg-002", "author": "agent", "type": "resolution",
                            "created": "2026-06-02T00:00:00Z", "content": "R"}]}
    thread.update(changes)
    return thread


@pytest.mark.parametrize("change,fragment", [
    ({"id": "thread-002"}, "should be"),
    ({"category": "urgent"}, "category"),
    ({"status": "done"}, "status"),
    ({"related_labs": ["x"]}, "related_labs"),
    ({"updated": "2026-06-02"}, "updated"),
    ({"created": "2026-05-01T00:00:00Z"}, "first message"),
    ({"updated": "2026-06-01T12:00:00Z"}, "older than the last message"),
])
def test_validate_reports_schema_problems(change, fragment):
    problems = mb.validate_threads_list([good_thread(**change)])
    assert any(fragment in p for p in problems), problems


def test_validate_message_rules():
    assert mb.validate_threads_list([good_thread()]) == []
    t = good_thread()
    t["messages"][1]["type"] = "reply"
    assert any("end with a resolution" in p for p in mb.validate_threads_list([t]))
    t = good_thread()
    t["messages"][1]["content"] = "  "
    assert any("non-empty" in p for p in mb.validate_threads_list([t]))
    t = good_thread()
    t["messages"][1]["created"] = "2026-05-31T00:00:00Z"
    assert any("backwards" in p for p in mb.validate_threads_list([t]))
    t = good_thread()
    t["messages"][0]["type"] = "reply"
    assert any("first message" in p for p in mb.validate_threads_list([t]))
    t = good_thread()
    t["messages"][1]["author"] = "user"
    assert mb.validate_threads_list([t]) == []
    t = good_thread()
    t["messages"][0]["author"] = "user"
    assert any("must be written by agent" in p for p in mb.validate_threads_list([t]))
    assert mb.validate({"no_threads_key": True})


def test_repository_state_threads_validate():
    """Seeding loop state and validating Threads must succeed."""
    # Ensure a local state exists for this checkout under test isolation
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPO), "validate"],
        cwd=REPO, capture_output=True, text=True,
    )
    # Empty scaffold state should validate; seed only if the checkout is missing it
    if result.returncode != 0:
        subprocess.run(
            [sys.executable, "-c",
             "from pathlib import Path; import sys; "
             "sys.path.insert(0, 'skills/auto-research/scripts'); "
             "from seed_local import seed_local_files; seed_local_files(Path('.'))"],
            cwd=REPO, check=True,
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO), "validate"],
            cwd=REPO, capture_output=True, text=True,
        )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("ok: ")
