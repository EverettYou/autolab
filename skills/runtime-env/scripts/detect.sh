#!/usr/bin/env bash
# runtime-env fingerprint — read-only. Prints signals used to match a machine profile.
# Safe to run anywhere; touches nothing.
set -u

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/profile_signals.sh
source "$_SCRIPT_DIR/lib/profile_signals.sh"

echo "## runtime-env fingerprint"

# --- container? ---
if [ -f /.dockerenv ]; then echo "container: yes (/.dockerenv)"; else echo "container: no /.dockerenv"; fi
grep -aqE "docker|kubepods|containerd|lxc" /proc/1/cgroup 2>/dev/null && echo "cgroup: container markers present"

# --- os ---
echo "os: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"

# --- nested container runtime? ---
runtimes=""
for c in docker podman nerdctl; do command -v "$c" >/dev/null 2>&1 && runtimes="$runtimes $c"; done
echo "container_runtime:${runtimes:- none}"
[ -S /var/run/docker.sock ] && echo "docker_sock: present" || echo "docker_sock: absent"

# --- edencode CLI (host tool; absent inside the launched dev container) ---
command -v edencode >/dev/null 2>&1 && echo "edencode_cli: present" || echo "edencode_cli: absent"

# --- gpu: mapped vs usable ---
ls /dev/nvidia* >/dev/null 2>&1 && echo "gpu_devices: $(ls /dev/nvidia* 2>/dev/null | tr '\n' ' ')" || echo "gpu_devices: none"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>&1 | head -2 | sed 's/^/nvidia_smi: /'
else
  echo "nvidia_smi: not installed"
fi

# --- python env tooling + torch/cuda ---
PY_BIN=""
for c in python python3; do
  command -v "$c" >/dev/null 2>&1 && PY_BIN="$c" && break
done
if [ -n "$PY_BIN" ]; then
  echo "python: $($PY_BIN --version 2>&1) ($PY_BIN)"
else
  echo "python: not found"
fi
for t in uv pip; do command -v "$t" >/dev/null 2>&1 && echo "tool: $t -> $(command -v $t)"; done
if [ -n "$PY_BIN" ]; then
  "$PY_BIN" - <<'PY' 2>/dev/null || echo "torch: not importable"
import torch
print("torch:", torch.__version__, "cuda_avail", torch.cuda.is_available(), "ndev", torch.cuda.device_count())
PY
else
  echo "torch: not importable"
fi

# --- identity ---
echo "whoami: $(whoami) | home: ${HOME:-?} | host: $(hostname)"

# --- profile (same rules as match_profile.sh) ---
echo "matched_profile: $(profile_match_id)"
