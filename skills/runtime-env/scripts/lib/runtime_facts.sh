# Collect live runtime facts and derive RUNTIME_CAPABILITY.
# Source from detect.sh, resolve_policy.sh, setup_venv.sh, scripts/probes/*.sh.
set -u

# Optional probes must never hang the caller. >1s with no reply is already wrong.
_RUNTIME_PROBE_TIMEOUT_SEC="${RUNTIME_PROBE_TIMEOUT_SEC:-1}"

_runtime_timeout() {
  # usage: _runtime_timeout <cmd...>  — runs under `timeout` when available
  if command -v timeout >/dev/null 2>&1; then
    timeout "$_RUNTIME_PROBE_TIMEOUT_SEC" "$@"
  else
    "$@"
  fi
}

RT_FACTS_READY=0

runtime_collect_facts() {
  # Idempotent within a shell: resolve_policy used to call this twice (defaults +
  # capability_id), stacking timed-out torch probes into multi-second stalls.
  if [ "${RT_FACTS_READY:-0}" = 1 ]; then
    return 0
  fi

  RT_IN_CONTAINER=0
  if [ -f /.dockerenv ]; then
    RT_IN_CONTAINER=1
  fi

  RT_HAS_DOCKER=0
  if command -v docker >/dev/null 2>&1 || command -v podman >/dev/null 2>&1; then
    RT_HAS_DOCKER=1
  fi

  RT_OS_FAMILY="$(uname -s 2>/dev/null || echo unknown)"

  RT_HAS_NVIDIA_DEV=0
  if ls /dev/nvidia[0-9]* >/dev/null 2>&1; then
    RT_HAS_NVIDIA_DEV=1
  fi

  RT_GPU_MODEL=""
  if command -v nvidia-smi >/dev/null 2>&1; then
    RT_GPU_MODEL="$(_runtime_timeout nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)"
  fi
  # NVML/smi can hang while /proc still lists the cards — prefer that over an empty model.
  if [ -z "$RT_GPU_MODEL" ] && [ -d /proc/driver/nvidia/gpus ]; then
    RT_GPU_MODEL="$(
      for info in /proc/driver/nvidia/gpus/*/information; do
        [ -f "$info" ] || continue
        sed -n 's/^Model:[[:space:]]*//p' "$info" | head -1
        break
      done
    )"
  fi

  # Optional accelerator probes: failure/timeout only means the flag stays 0.
  # Always use if/fi (never leave a failing `cmd && flag=1` as the function's last
  # command — under `set -e` that makes the whole caller abort with no message).
  # Wrap with timeout so a wedged CUDA stack cannot block setup_venv / resolve_policy.
  RT_HAS_CUDA_TORCH=0
  if _runtime_timeout python3 - <<'PY' >/dev/null 2>&1
import torch
assert torch.cuda.is_available()
PY
  then
    RT_HAS_CUDA_TORCH=1
  fi

  RT_HAS_MPS=0
  if _runtime_timeout python3 - <<'PY' >/dev/null 2>&1
import torch
assert torch.backends.mps.is_available()
PY
  then
    RT_HAS_MPS=1
  fi

  RT_FACTS_READY=1
  return 0
}

# Prints capability tag to stdout (no vendor/person names).
runtime_capability_id() {
  runtime_collect_facts
  if [[ $RT_IN_CONTAINER -eq 1 ]]; then
    if [[ "$RT_GPU_MODEL" == *B300* ]]; then
      echo "container+B300"
    elif [[ "$RT_GPU_MODEL" == *H200* ]]; then
      echo "container+H200"
    else
      echo "container"
    fi
  elif [[ $RT_HAS_DOCKER -eq 1 ]]; then
    echo "host+docker"
  elif [[ "$RT_OS_FAMILY" == Darwin ]]; then
    echo "host+Darwin"
  else
    echo "host"
  fi
}

# Expected GPU count from live product name (0 = unset / unknown topology).
runtime_gpu_count_expected() {
  runtime_collect_facts
  case "$RT_GPU_MODEL" in
    *B300*) echo 8 ;;
    *H200*) echo 2 ;;
    *) echo 0 ;;
  esac
}
