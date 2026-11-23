#!/usr/bin/env bash
# runtime-env fingerprint — read-only. Prints live facts + resolved policy.
# Safe to run anywhere; touches nothing.
set -u

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/resolve_policy.sh
source "$_SCRIPT_DIR/lib/resolve_policy.sh"

resolve_policy

echo "## runtime-env fingerprint"

if [ -f /.dockerenv ]; then echo "container: yes (/.dockerenv)"; else echo "container: no /.dockerenv"; fi
grep -aqE "docker|kubepods|containerd|lxc" /proc/1/cgroup 2>/dev/null && echo "cgroup: container markers present"

if [ -f /etc/os-release ]; then
  echo "os: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
else
  echo "os: ${RT_OS_FAMILY:-unknown}"
fi

runtimes=""
for c in docker podman nerdctl; do command -v "$c" >/dev/null 2>&1 && runtimes="$runtimes $c"; done
echo "container_runtime:${runtimes:- none}"
[ -S /var/run/docker.sock ] && echo "docker_sock: present" || echo "docker_sock: absent"

ls /dev/nvidia* >/dev/null 2>&1 && echo "gpu_devices: $(ls /dev/nvidia* 2>/dev/null | tr '\n' ' ')" || echo "gpu_devices: none"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>&1 | head -2 | sed 's/^/nvidia_smi: /'
else
  echo "nvidia_smi: not installed"
fi
echo "fact_gpu_model: ${RT_GPU_MODEL:-}"

PY_BIN=""
for c in python3 python; do
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
mps = getattr(getattr(torch.backends, "mps", None), "is_available", lambda: False)()
print("torch:", torch.__version__, "cuda_avail", torch.cuda.is_available(), "ndev", torch.cuda.device_count(), "mps", mps)
PY
else
  echo "torch: not importable"
fi

echo "whoami: $(whoami) | home: ${HOME:-?}"
echo "runtime_capability: ${RUNTIME_CAPABILITY}"
echo "policy_isolation: ${POLICY_ISOLATION}"
echo "policy_untrusted_code: ${POLICY_UNTRUSTED_CODE}"
echo "policy_venv_mode: ${POLICY_VENV_MODE}"
