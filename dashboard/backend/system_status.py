"""The machine the auto-research loop runs on: agent, live runtime facts, and GPU use.

Runtime labels are composed from live facts (resolve_policy / nvidia-smi / torch), not from
branded machine dossier ids. GPU numbers come from ``nvidia-smi`` when available.

GPU probing is deliberately timid: short timeout, single-flight mutex, TTL cache, and a
cooldown after timeout/failure so a wedged driver cannot accumulate stuck ``nvidia-smi``
children or starve other users of NVML.
"""

from __future__ import annotations

import importlib.util
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_RUNNER = _REPO / "skills" / "auto-research" / "scripts" / "loop_runner.py"
_RESOLVE = _REPO / "skills" / "runtime-env" / "scripts" / "lib" / "resolve_policy.sh"
_FACTS_TTL = 300.0
_AGENTS = {"claude": "Claude", "codex": "Codex"}

# nvidia-smi is a shared host resource. >1s with no reply is already pathological.
_GPU_PROBE_TIMEOUT = 1.0
_GPU_CACHE_TTL = 15.0
_GPU_COOLDOWN = 60.0

_facts_lock = threading.Lock()
_facts_cache: tuple[float, dict[str, str]] | None = None

_gpu_lock = threading.Lock()
_gpu_cache: tuple[float, list[dict]] | None = None
_gpu_cooldown_until = 0.0


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


def gpus_from_proc(proc_root: Path | None = None) -> list[dict]:
    """Inventory from ``/proc/driver/nvidia/gpus/*/information`` (no NVML, no util/mem).

    Used when ``nvidia-smi`` times out or wedges so the UI does not lie with "CPU only"
    while eight B300 device nodes are sitting in the container.
    """
    root = proc_root or Path("/proc/driver/nvidia/gpus")
    if not root.is_dir():
        return []
    rows: list[dict] = []
    for info in sorted(root.glob("*/information")):
        try:
            text = info.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        model = ""
        minor: int | None = None
        for line in text.splitlines():
            if line.startswith("Model:"):
                model = line.split(":", 1)[1].strip()
            elif line.startswith("Device Minor:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    minor = int(raw)
                except ValueError:
                    minor = None
        if not model or minor is None:
            continue
        rows.append({
            "index": minor,
            "name": model,
            "util_pct": None,
            "mem_used_mib": None,
            "mem_total_mib": None,
        })
    rows.sort(key=lambda row: row["index"])
    return rows


def _nvidia_devices_present() -> bool:
    if Path("/proc/driver/nvidia/gpus").is_dir() and any(Path("/proc/driver/nvidia/gpus").iterdir()):
        return True
    return any(Path("/dev").glob("nvidia[0-9]*"))


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


def _policy_facts() -> dict[str, str]:
    global _facts_cache
    now = time.monotonic()
    with _facts_lock:
        if _facts_cache is not None and now - _facts_cache[0] < _FACTS_TTL:
            return dict(_facts_cache[1])
    facts: dict[str, str] = {}
    try:
        completed = subprocess.run(
            ["bash", str(_RESOLVE)],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if completed.returncode == 0:
            for line in completed.stdout.splitlines():
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                facts[key.strip()] = val.strip()
    except (OSError, subprocess.TimeoutExpired):
        facts = {}
    with _facts_lock:
        _facts_cache = (time.monotonic(), dict(facts))
    return facts


def short_gpu_name(name: str) -> str:
    """Compact display name: ``NVIDIA B300 SXM6 AC`` → ``NVIDIA B300``."""
    parts = name.strip().split()
    if len(parts) >= 2 and parts[0].upper() == "NVIDIA":
        product = parts[1]
        # Datacenter product codes (B300, H200, A100, L40S, GH200, …).
        if re.fullmatch(r"[A-Za-z]{1,3}\d{2,4}[A-Za-z]?", product):
            return f"NVIDIA {product}"
    return name.strip()


def _accelerator_label(gpu_rows: list[dict], facts: dict[str, str]) -> str:
    if gpu_rows:
        names = [short_gpu_name(g["name"]) for g in gpu_rows if g.get("name")]
        if names:
            # Collapse identical names: "8× NVIDIA B300"
            first = names[0]
            if all(n == first for n in names):
                return f"{len(names)}× {first}"
            return ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
    model = short_gpu_name(facts.get("FACT_GPU_MODEL") or "") if facts.get("FACT_GPU_MODEL") else ""
    if model:
        return model
    if facts.get("FACT_HAS_MPS") == "1":
        return "Apple MPS"
    # Devices present but NVML/smi probe failed — never claim "CPU only".
    if facts.get("FACT_HAS_NVIDIA_DEV") == "1" or _nvidia_devices_present():
        return "NVIDIA (stats unavailable)"
    return "CPU only"


def _runtime_kind(facts: dict[str, str]) -> str:
    isolation = facts.get("POLICY_ISOLATION", "")
    if isolation == "this-container" or facts.get("FACT_IN_CONTAINER") == "1":
        return "Dev container"
    if isolation == "docker-attempt" or facts.get("FACT_HAS_DOCKER") == "1":
        return "Host · Docker"
    os_family = facts.get("FACT_OS_FAMILY", "")
    if os_family == "Darwin":
        return "Host · Darwin"
    return "Host"


def runtime(gpu_rows: list[dict] | None = None) -> dict:
    """Live capability + human labels (no hostname by default; privacy)."""
    facts = _policy_facts()
    rows = gpus() if gpu_rows is None else gpu_rows
    capability = facts.get("RUNTIME_CAPABILITY") or "host"
    kind = _runtime_kind(facts)
    accel = _accelerator_label(rows, facts)
    machine = f"{kind} · {accel}" if accel else kind
    return {
        "profile": capability,  # API field kept; value is RUNTIME_CAPABILITY
        "capability": capability,
        "runtime": kind,
        "machine": machine,
        "host": None,
        "isolation": facts.get("POLICY_ISOLATION"),
        "untrusted_code": facts.get("POLICY_UNTRUSTED_CODE"),
        "venv_mode": facts.get("POLICY_VENV_MODE"),
    }


def _kill_probe(proc: subprocess.Popen[str]) -> None:
    """Best-effort tear-down. D-state children may ignore signals; cooldown stops respawn."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.communicate(timeout=0.2)
    except Exception:
        pass


def _run_nvidia_smi() -> list[dict]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, _stderr = proc.communicate(timeout=_GPU_PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_probe(proc)
        raise
    if proc.returncode != 0:
        return []
    return parse_nvidia_smi(stdout or "")


def _cache_gpu_rows(rows: list[dict]) -> list[dict]:
    global _gpu_cache
    _gpu_cache = (time.monotonic(), rows)
    return [dict(row) for row in rows]


def gpus() -> list[dict]:
    """Cached, single-flight GPU snapshot. Never piles concurrent ``nvidia-smi`` calls.

    On smi timeout/failure, fall back to ``/proc/driver/nvidia`` inventory (names only)
    and keep the smi cooldown so we do not keep wedging NVML.
    """
    global _gpu_cache, _gpu_cooldown_until
    now = time.monotonic()
    with _gpu_lock:
        if _gpu_cache is not None and now - _gpu_cache[0] < _GPU_CACHE_TTL:
            return [dict(row) for row in _gpu_cache[1]]
        if now < _gpu_cooldown_until:
            if _gpu_cache is not None:
                return [dict(row) for row in _gpu_cache[1]]
            return _cache_gpu_rows(gpus_from_proc())
        try:
            rows = _run_nvidia_smi()
            if not rows:
                rows = gpus_from_proc()
            return _cache_gpu_rows(rows)
        except subprocess.TimeoutExpired:
            _gpu_cooldown_until = time.monotonic() + _GPU_COOLDOWN
            if _gpu_cache is not None:
                return [dict(row) for row in _gpu_cache[1]]
            return _cache_gpu_rows(gpus_from_proc())
        except OSError:
            _gpu_cooldown_until = time.monotonic() + _GPU_COOLDOWN
            if _gpu_cache is not None:
                return [dict(row) for row in _gpu_cache[1]]
            return _cache_gpu_rows(gpus_from_proc())


def collect(root: Path) -> dict:
    # One GPU probe per status payload (runtime label reuses the same rows).
    gpu_rows = gpus()
    return {"agent": agent(root), "runtime": runtime(gpu_rows), "gpus": gpu_rows}
