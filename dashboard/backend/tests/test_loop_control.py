"""Loop control and GPU status helpers for the lab dashboard."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
STATE_SCRIPT = ROOT / "skills" / "auto-research" / "scripts" / "loop_state.py"


def test_nvidia_smi_rows_keep_each_gpu():
    from dashboard.backend.system_status import parse_nvidia_smi

    rows = parse_nvidia_smi(
        "0, NVIDIA H200 NVL, 37, 4096, 143771\n"
        "1, NVIDIA H200 NVL, [N/A], 14, 143771\n"
        "not a row\n"
    )
    assert rows[0] == {
        "index": 0, "name": "NVIDIA H200 NVL", "util_pct": 37,
        "mem_used_mib": 4096, "mem_total_mib": 143771,
    }
    assert rows[1]["index"] == 1 and rows[1]["util_pct"] is None
    assert len(rows) == 2


def test_loop_control_move_reorders_tasks(tmp_path: Path):
    from dashboard.backend import loop_control

    auto = tmp_path / ".auto-research"
    tasks = auto / "tasks"
    tasks.mkdir(parents=True)
    (auto / "state.json").write_text(json.dumps({
        "schema": "auto-research-1",
        "status": "paused",
        "updated": "2026-11-19T00:00:00Z",
        "active_deliverable": None,
        "next_action": "Wait.",
        "last_action": None,
        "tasks": [],
        "threads": [],
    }) + "\n", encoding="utf-8")
    # Seed two tasks through the real script so bodies and locks stay valid.
    for title, slug in (("First task", "first-task"), ("Second task", "second-task")):
        completed = subprocess.run(
            [sys.executable, str(STATE_SCRIPT), "--root", str(tmp_path),
             "task", "add", "--id", slug, "--title", title, "--for", "auto",
             "--gpu", "free", "--time", "5min",
             "--content",
             "## Goal\nFinish it.\n\n## Work\nDo the work.\n\n## Done when\nFinished.\n"],
            cwd=tmp_path, capture_output=True, text=True, check=False,
        )
        assert completed.returncode == 0, completed.stderr
    loop_control.move(tmp_path, "second-task", before="first-task")
    state = json.loads((auto / "state.json").read_text(encoding="utf-8"))
    assert [task["id"] for task in state["tasks"]] == ["second-task", "first-task"]


def test_loop_control_rejects_self_anchor(tmp_path: Path):
    from dashboard.backend import loop_control
    from dashboard.backend.repo import BadRequest

    auto = tmp_path / ".auto-research"
    auto.mkdir()
    (auto / "state.json").write_text("{}", encoding="utf-8")
    with pytest.raises(BadRequest):
        loop_control.move(tmp_path, "a", before="a")
