"""Tests for skills/auto-research/scripts/auto_research_lint.py."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "auto_research_lint.py"
spec = importlib.util.spec_from_file_location("auto_research_lint", SCRIPT)
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)

STAMP = "2026-01-01T00:00:00Z"
SCHEMA = "auto-research-1"


def write_state(root: Path, **overrides) -> dict:
    state = {
        "schema": SCHEMA,
        "status": "paused",
        "updated": STAMP,
        "active_deliverable": None,
        "next_action": "Run one supervisor tick.",
        "last_action": None,
        "last_supervisor_at": None,
        "idle": None,
        "tasks": [],
        "threads": [],
    }
    state.update(overrides)
    auto = root / ".auto-research"
    auto.mkdir(parents=True, exist_ok=True)
    (auto / "tasks").mkdir(exist_ok=True)
    (auto / "threads").mkdir(exist_ok=True)
    (auto / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def write_thread(root: Path, thread_id: str = "thread-001", **changes) -> dict:
    thread = {
        "id": thread_id,
        "title": "Choose an option",
        "category": "decision",
        "priority": "normal",
        "status": "open",
        "related_labs": [],
        "created": STAMP,
        "updated": STAMP,
        "messages": [{
            "id": "msg-001",
            "author": "agent",
            "type": "question",
            "created": STAMP,
            "content": "Which option?",
        }],
    }
    thread.update(changes)
    path = root / ".auto-research" / "threads" / f"{thread_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"messages": thread["messages"]}, indent=2) + "\n", encoding="utf-8")
    return thread


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write_state(tmp_path)
    return tmp_path


def test_ok_empty_store(root, capsys):
    assert lint.main(["--root", str(root)]) == 0
    assert "ok" in capsys.readouterr().out


def test_reports_missing_state_key(root, capsys):
    state = json.loads((root / ".auto-research" / "state.json").read_text(encoding="utf-8"))
    del state["next_action"]
    (root / ".auto-research" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert lint.main(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "missing" in err and "next_action" in err
    assert ".auto-research/README.md" in err


def test_reports_bad_task_keys_and_orphan_body(root, capsys):
    write_state(root, tasks=[{
        "id": "broken-task",
        "title": "Broken",
        # missing several required keys on purpose
    }])
    (root / ".auto-research" / "tasks" / "stray.md").write_text("# Stray\n", encoding="utf-8")
    assert lint.main(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "broken-task" in err or "tasks[0]" in err
    assert "missing" in err
    assert "stray.md" in err


def test_reports_thread_message_schema(root, capsys):
    write_thread(root)
    write_state(root, threads=[{
        "id": "thread-001", "title": "Choose an option", "category": "decision",
        "priority": "normal", "status": "open", "related_labs": [],
        "created": STAMP, "updated": STAMP,
    }])
    path = root / ".auto-research" / "threads" / "thread-001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["messages"][0]["id"] = "msg-007"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert lint.main(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "threads/thread-001.json" in err
    assert "out of sequence" in err


def test_reports_orphan_thread_file(root, capsys):
    write_thread(root, "thread-009")
    assert lint.main(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "thread-009.json" in err
    assert "orphan" in err or "state.threads" in err or "threads" in err


def test_reports_retired_thread_ids_key(root, capsys):
    path = root / ".auto-research" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["thread_ids"] = []
    path.write_text(json.dumps(state), encoding="utf-8")
    assert lint.main(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "unexpected key 'thread_ids'" in err


def test_json_output(root, capsys):
    write_state(root, status="asleep")
    assert lint.main(["--root", str(root), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert any("status" in f for f in payload["findings"])
