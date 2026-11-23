# Collect live runtime facts and derive RUNTIME_CAPABILITY.
# Source from detect.sh, resolve_policy.sh, setup_venv.sh, scripts/probes/*.sh.
set -u

runtime_collect_facts() {
  RT_IN_CONTAINER=0
  [ -f /.dockerenv ] && RT_IN_CONTAINER=1

  RT_HAS_DOCKER=0
  command -v docker >/dev/null 2>&1 && RT_HAS_DOCKER=1
  command -v podman >/dev/null 2>&1 && RT_HAS_DOCKER=1

  RT_OS_FAMILY="$(uname -s 2>/dev/null || echo unknown)"

  RT_HAS_NVIDIA_DEV=0
  ls /dev/nvidia[0-9]* >/dev/null 2>&1 && RT_HAS_NVIDIA_DEV=1

  RT_GPU_MODEL=""
  if command -v nvidia-smi >/dev/null 2>&1; then
    RT_GPU_MODEL="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)"
  fi

  RT_HAS_CUDA_TORCH=0
  python3 - <<'PY' >/dev/null 2>&1 && RT_HAS_CUDA_TORCH=1
import torch
assert torch.cuda.is_available()
PY

  RT_HAS_MPS=0
  python3 - <<'PY' >/dev/null 2>&1 && RT_HAS_MPS=1
import torch
assert torch.backends.mps.is_available()
PY
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
