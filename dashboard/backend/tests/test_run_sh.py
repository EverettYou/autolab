"""run.sh fail-closed checks and an isolated start/stop cycle for the lab dashboard."""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "run.sh"
requires_repo_env = pytest.mark.skipif(
    not (REPO_ROOT / ".venv" / "bin" / "python").exists(),
    reason="needs repository .venv",
)


def run(script: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.endswith("_DASHBOARD_PORT")
        and not key.endswith("_DASHBOARD_HOST")
        and not key.startswith("LAB_DASHBOARD_")
    }
    environment.update(env or {})
    return subprocess.run(
        ["bash", str(script), *args], capture_output=True, text=True, timeout=90, env=environment,
    )


def scratch_copy(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    shutil.copy2(SCRIPT, root / "run.sh")
    os.chmod(root / "run.sh", 0o755)
    return root / "run.sh"


def scratch_root(tmp_path: Path, folders=None) -> Path:
    script = scratch_copy(tmp_path)
    for name in (".venv", "dashboard"):
        os.symlink(REPO_ROOT / name, script.parent / name)
    if (REPO_ROOT / "lib").is_dir():
        os.symlink(REPO_ROOT / "lib", script.parent / "lib")
    # seed_local imports skills/auto-research/scripts
    skills = script.parent / "skills" / "auto-research" / "scripts"
    skills.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(REPO_ROOT / "skills" / "auto-research" / "scripts", skills)
    for name in (folders or (
        "references", "labs", "wiki", "notes", ".auto-research",
    )):
        (script.parent / name).mkdir(exist_ok=True)
    (script.parent / "skills").mkdir(exist_ok=True)
    wiki = script.parent / "wiki"
    if wiki.is_dir():
        (wiki / "README.md").write_text("# Research Wiki\n", encoding="utf-8")
    auto = script.parent / ".auto-research"
    if auto.is_dir():
        (auto / "README.md").write_text("# Auto Research\n", encoding="utf-8")
        if (REPO_ROOT / ".auto-research" / "state.json").is_file():
            shutil.copy2(REPO_ROOT / ".auto-research" / "state.json", auto / "state.json")
    (script.parent / "config.yml").write_text(
        "name: harness-lab\n"
        "features:\n"
        "  notes: false\n"
        "  lib: false\n"
        "package: null\n",
        encoding="utf-8",
    )
    return script


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_syntax_and_executable():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
    assert os.access(SCRIPT, os.X_OK)
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n") or text.startswith("#!/bin/bash\n")


def test_help():
    result = run(SCRIPT, "help")
    assert result.returncode == 0
    for word in ("start", "stop", "restart", "status", "logs", "foreground", "check"):
        assert word in result.stdout
    assert "Usage:" in result.stdout


def test_unknown_command(tmp_path):
    result = run(scratch_copy(tmp_path), "bogus")
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_refuses_without_venv_when_setup_unavailable(tmp_path):
    script = scratch_copy(tmp_path)
    (script.parent / "config.yml").write_text("name: harness-lab\n", encoding="utf-8")
    result = run(script, "check")
    assert result.returncode == 1
    assert ".venv/bin/python is missing" in result.stderr
    assert "setup_venv.sh" in result.stderr


def test_recovers_missing_venv_via_setup_script(tmp_path):
    script = scratch_copy(tmp_path)
    root = script.parent
    (root / "config.yml").write_text("name: harness-lab\n", encoding="utf-8")
    setup = root / "skills" / "runtime-env" / "scripts" / "setup_venv.sh"
    setup.parent.mkdir(parents=True)
    setup.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"\n'
        'mkdir -p "$ROOT/.venv/bin"\n'
        'ln -sfn "$(command -v python3)" "$ROOT/.venv/bin/python"\n',
        encoding="utf-8",
    )
    os.chmod(setup, 0o755)
    result = run(script, "check")
    assert (root / ".venv" / "bin" / "python").exists()
    assert result.returncode == 1  # recovered python, then fails later env checks
    assert "delegating to skills/runtime-env/scripts/setup_venv.sh" in result.stdout


@requires_repo_env
def test_check_passes_in_real_repo():
    result = run(SCRIPT, "check")
    assert result.returncode == 0
    assert "Dashboard configuration is valid" in result.stdout


def test_invalid_port_rejected(tmp_path):
    script = scratch_root(tmp_path)
    result = run(script, "check", env={"LAB_DASHBOARD_PORT": "99999"})
    assert result.returncode == 1
    assert "port" in result.stderr.lower()


@requires_repo_env
def test_refuses_missing_required_folder(tmp_path):
    script = scratch_root(tmp_path, folders=("references", "labs", "notes", "skills", ".auto-research"))
    result = run(script, "check")
    assert result.returncode == 1
    assert "required folder wiki/" in result.stderr


@requires_repo_env
def test_status_and_stop_when_not_running(tmp_path):
    script = scratch_root(tmp_path)
    env = {"LAB_DASHBOARD_PORT": str(free_port())}
    status = run(script, "status", env=env)
    assert status.returncode != 0
    assert "STOPPED" in status.stdout or "not running" in status.stdout.lower()
    stop = run(script, "stop", env=env)
    assert stop.returncode == 0
    assert "STOPPED" in stop.stdout or "not running" in stop.stdout.lower()


@requires_repo_env
def test_start_status_stop_on_free_port(tmp_path):
    script = scratch_root(tmp_path)
    port = free_port()
    env = {"LAB_DASHBOARD_PORT": str(port)}
    pid_file = script.parent / ".cache" / "dashboard" / "process"
    try:
        start = run(script, "start", env=env)
        assert start.returncode == 0, start.stderr
        assert "RUNNING" in start.stdout
        assert f"http://127.0.0.1:{port}/" in start.stdout
        assert pid_file.is_file()
        pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=10) as response:
            health = json.load(response)
        assert health["ok"] is True
        assert health["pid"] == pid
        assert health["name"] == "harness-lab"
        assert Path(health["root"]).resolve() == script.parent.resolve()
        status = run(script, "status", env=env)
        assert status.returncode == 0 and "RUNNING" in status.stdout
        stop = run(script, "stop", env=env)
        assert stop.returncode == 0 and "STOPPED" in stop.stdout
        assert not pid_file.exists()
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text(encoding="utf-8").splitlines()[0]), signal.SIGTERM)
            except (ValueError, ProcessLookupError, OSError):
                pass


@requires_repo_env
def test_start_takes_over_stale_fingerprint(tmp_path):
    script = scratch_root(tmp_path)
    port = free_port()
    env = {"LAB_DASHBOARD_PORT": str(port)}
    pid_file = script.parent / ".cache" / "dashboard" / "process"
    try:
        first = run(script, "start", env=env)
        assert first.returncode == 0, first.stderr
        old_pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0])
        # Invalidate the saved fingerprint so start claims the same checkout's listener.
        state = script.parent / ".cache" / "dashboard" / "dashboard.state"
        state.write_text("fingerprint=deadbeef\n", encoding="utf-8")
        second = run(script, "start", env=env)
        assert second.returncode == 0, second.stderr
        assert "RUNNING" in second.stdout
        new_pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0])
        assert new_pid != old_pid
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=10) as response:
            health = json.load(response)
        assert health["pid"] == new_pid
        assert Path(health["root"]).resolve() == script.parent.resolve()
        stop = run(script, "stop", env=env)
        assert stop.returncode == 0
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text(encoding="utf-8").splitlines()[0]), signal.SIGTERM)
            except (ValueError, ProcessLookupError, OSError):
                pass
