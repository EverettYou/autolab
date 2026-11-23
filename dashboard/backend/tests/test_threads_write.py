"""Threads writes go through the thread-interaction contract into threads/<id>.json."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def threads_root(tmp_path: Path) -> Path:
    (tmp_path / ".auto-research").mkdir(exist_ok=True)
    (tmp_path / ".auto-research" / "threads").mkdir(exist_ok=True)
    (tmp_path / "skills/thread-interaction/scripts").mkdir(parents=True)
    shutil.copy(
        ROOT / "skills/thread-interaction/scripts/thread_interaction.py",
        tmp_path / "skills/thread-interaction/scripts/thread_interaction.py",
    )
    (tmp_path / "skills/auto-research/scripts").mkdir(parents=True)
    shutil.copy(
        ROOT / "skills/auto-research/scripts/seed_local.py",
        tmp_path / "skills/auto-research/scripts/seed_local.py",
    )
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
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )
    return tmp_path


def test_open_and_reply_through_threads_write(threads_root: Path):
    from dashboard.backend.app import App
    from dashboard.backend import threads_write

    app = App(threads_root)
    opened = threads_write.open_thread(app, {
        "title": "Harness check",
        "content": "Please confirm the Threads path.",
        "category": "direction",
        "priority": "normal",
    })
    assert opened["id"] == "thread-001"
    assert opened["status"] == "open"
    replied = threads_write.reply_thread(app, "thread-001", {
        "content": "Acknowledged.",
        "type": "reply",
    })
    assert replied["id"] == "thread-001"
    assert replied["messages"][-1]["content"] == "Acknowledged."
    state = json.loads((threads_root / ".auto-research/state.json").read_text(encoding="utf-8"))
    assert [t["id"] for t in state["threads"]] == ["thread-001"]
    assert "messages" not in state["threads"][0]
    payload = json.loads(
        (threads_root / ".auto-research/threads/thread-001.json").read_text(encoding="utf-8"))
    assert set(payload) == {"messages"}
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["author"] == "user"
