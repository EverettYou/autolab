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


def test_short_gpu_name_drops_board_suffix():
    from dashboard.backend.system_status import _accelerator_label, short_gpu_name

    assert short_gpu_name("NVIDIA B300 SXM6 AC") == "NVIDIA B300"
    assert short_gpu_name("NVIDIA H200 NVL") == "NVIDIA H200"
    rows = [
        {"index": i, "name": "NVIDIA B300 SXM6 AC", "util_pct": None,
         "mem_used_mib": None, "mem_total_mib": None}
        for i in range(8)
    ]
    assert _accelerator_label(rows, {}) == "8× NVIDIA B300"


def test_gpus_from_proc_reads_model_and_minor(tmp_path: Path):
    from dashboard.backend.system_status import gpus_from_proc

    gpu = tmp_path / "0000:01:00.0"
    gpu.mkdir()
    (gpu / "information").write_text(
        "Model: \t\t NVIDIA B300 SXM6 AC\nDevice Minor: \t 3\n",
        encoding="utf-8",
    )
    rows = gpus_from_proc(tmp_path)
    assert rows == [{
        "index": 3,
        "name": "NVIDIA B300 SXM6 AC",
        "util_pct": None,
        "mem_used_mib": None,
        "mem_total_mib": None,
    }]


def test_gpus_falls_back_to_proc_after_timeout(monkeypatch):
    import dashboard.backend.system_status as status
    import subprocess

    monkeypatch.setattr(
        status,
        "_run_nvidia_smi",
        lambda: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=1)),
    )
    monkeypatch.setattr(
        status,
        "gpus_from_proc",
        lambda: [{"index": 0, "name": "NVIDIA B300 SXM6 AC", "util_pct": None,
                  "mem_used_mib": None, "mem_total_mib": None}],
    )
    status._gpu_cache = None
    status._gpu_cooldown_until = 0.0
    rows = status.gpus()
    assert rows[0]["name"] == "NVIDIA B300 SXM6 AC"
    assert "B300" in status._accelerator_label(rows, {})


def test_gpus_caches_and_skips_during_cooldown(monkeypatch):
    import dashboard.backend.system_status as status

    calls = {"n": 0}

    def fake_run():
        calls["n"] += 1
        return [{"index": 0, "name": "GPU", "util_pct": 1, "mem_used_mib": 1, "mem_total_mib": 2}]

    monkeypatch.setattr(status, "_run_nvidia_smi", fake_run)
    status._gpu_cache = None
    status._gpu_cooldown_until = 0.0

    first = status.gpus()
    second = status.gpus()
    assert first == second
    assert calls["n"] == 1  # TTL cache, not a second nvidia-smi


def test_gpus_cooldown_after_timeout(monkeypatch):
    import dashboard.backend.system_status as status
    import subprocess

    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=1)

    monkeypatch.setattr(status, "_run_nvidia_smi", boom)
    monkeypatch.setattr(
        status,
        "gpus_from_proc",
        lambda: [{"index": 0, "name": "NVIDIA B300 SXM6 AC", "util_pct": None,
                  "mem_used_mib": None, "mem_total_mib": None}],
    )
    status._gpu_cache = None
    status._gpu_cooldown_until = 0.0

    first = status.gpus()
    assert first[0]["name"] == "NVIDIA B300 SXM6 AC"
    assert calls["n"] == 1
    assert status.gpus() == first
    assert calls["n"] == 1  # cooldown/cache must not respawn nvidia-smi


def test_collect_probes_gpus_once(monkeypatch, tmp_path: Path):
    import dashboard.backend.system_status as status

    calls = {"n": 0}

    def fake_gpus():
        calls["n"] += 1
        return [{"index": 0, "name": "GPU", "util_pct": 0, "mem_used_mib": 0, "mem_total_mib": 1}]

    monkeypatch.setattr(status, "gpus", fake_gpus)
    monkeypatch.setattr(status, "agent", lambda root: {"id": None, "name": None, "running": False, "in_tick": False})
    monkeypatch.setattr(status, "_policy_facts", lambda: {"RUNTIME_CAPABILITY": "host"})

    out = status.collect(tmp_path)
    assert calls["n"] == 1
    assert out["gpus"][0]["name"] == "GPU"
    assert "GPU" in out["runtime"]["machine"]


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
        "last_supervisor_at": None,
        "idle": None,
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
