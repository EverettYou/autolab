"""The machine the auto-research loop runs on: agent, live runtime facts, and GPU use.

Runtime labels are composed from live facts (resolve_policy / nvidia-smi / torch), not from
branded machine dossier ids. GPU numbers come from ``nvidia-smi`` when available.
"""

from __future__ import annotations

import importlib.util
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

_facts_lock = threading.Lock()
_facts_cache: tuple[float, dict[str, str]] | None = None


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
            timeout=12,
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


def _accelerator_label(gpu_rows: list[dict], facts: dict[str, str]) -> str:
    if gpu_rows:
        names = [g["name"] for g in gpu_rows if g.get("name")]
        if names:
            # Collapse identical names: "2× NVIDIA H200 NVL"
            first = names[0]
            if all(n == first for n in names):
                return f"{len(names)}× {first}"
            return ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
    model = facts.get("FACT_GPU_MODEL") or ""
    if model:
        return model
    if facts.get("FACT_HAS_MPS") == "1":
        return "Apple MPS"
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


def runtime() -> dict:
    """Live capability + human labels (no hostname by default; privacy)."""
    facts = _policy_facts()
    gpu_rows = gpus()
    capability = facts.get("RUNTIME_CAPABILITY") or "host"
    kind = _runtime_kind(facts)
    accel = _accelerator_label(gpu_rows, facts)
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
