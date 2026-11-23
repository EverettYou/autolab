"""The machine the auto-research loop runs on: agent, runtime profile, and live GPU use.

The runtime profile is the one ``skills/runtime-env`` matches. GPU numbers come from
``nvidia-smi``, the same source that probe uses. Neither call changes the machine.
"""

from __future__ import annotations

import importlib.util
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_RUNNER = _REPO / "skills" / "auto-research" / "scripts" / "loop_runner.py"
_PROFILE = _REPO / "skills" / "runtime-env" / "scripts" / "lib" / "match_profile.sh"
_PROFILE_TTL = 300.0
_HEX_HOST = re.compile(r"[0-9a-f]{12}")

# Labels from skills/runtime-env/machines. The profile id stays the skill's word.
_PROFILES = {
    "edencode-b300": {"machine": "EdenCode B300", "runtime": "Dev container"},
    "edencode-h200": {"machine": "EdenCode H200", "runtime": "Dev container"},
    "generic-host-with-docker": {"machine": "This host", "runtime": "Docker on the host"},
    "generic-container": {"machine": "This container", "runtime": "Container"},
    "unknown": {"machine": "This machine", "runtime": "This machine"},
}
_AGENTS = {"claude": "Claude", "codex": "Codex"}

_profile_lock = threading.Lock()
_profile_cache: tuple[float, str] | None = None


def parse_nvidia_smi(text: str) -> list[dict]:
    """Rows from ``nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total``."""
    gpus = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        index, name, util, used, total = parts[:5]
        try:
            gpus.append({
                "index": int(index),
                "name": name,
                "util_pct": int(util) if util.isdigit() else None,
                "mem_used_mib": int(used),
                "mem_total_mib": int(total),
            })
        except ValueError:
            continue
    return gpus


def _runner():
    name = "em_boundary_loop_runner"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, _RUNNER)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def agent(root: Path) -> dict:
    """Which agent the scheduler last chose, and whether that process is alive."""
    module = _runner()
    snap = module.snapshot(root) if module is not None else {}
    runner = snap.get("runner")
    name = _AGENTS.get(runner) if isinstance(runner, str) else None
    return {
        "id": runner if isinstance(runner, str) else None,
        "name": name,
        "running": bool(snap.get("alive")),
        "in_tick": bool(snap.get("in_tick")),
    }


def _profile_id() -> str:
    global _profile_cache
    now = time.monotonic()
    with _profile_lock:
        if _profile_cache is not None and now - _profile_cache[0] < _PROFILE_TTL:
            return _profile_cache[1]
    profile = "unknown"
    try:
        completed = subprocess.run(
            ["bash", str(_PROFILE)], capture_output=True, text=True, timeout=8, check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            profile = completed.stdout.strip().splitlines()[-1]
    except (OSError, subprocess.TimeoutExpired):
        profile = "unknown"
    if profile not in _PROFILES:
        profile = "unknown"
    with _profile_lock:
        _profile_cache = (time.monotonic(), profile)
    return profile


def _host() -> str | None:
    name = socket.gethostname().strip()
    if not name or _HEX_HOST.fullmatch(name):
        return None
    return name


def runtime() -> dict:
    """The runtime-env machine profile, plus a hostname when it names a machine."""
    profile = _profile_id()
    labels = _PROFILES[profile]
    host = _host()
    machine = labels["machine"]
    if host and profile in {"unknown", "generic-host-with-docker", "generic-container"}:
        machine = host
    return {"profile": profile, "runtime": labels["runtime"], "machine": machine, "host": host}


def gpus() -> list[dict]:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    return parse_nvidia_smi(completed.stdout)


def collect(root: Path) -> dict:
    return {"agent": agent(root), "runtime": runtime(), "gpus": gpus()}
