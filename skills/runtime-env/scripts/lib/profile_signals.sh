# Shared machine-profile signals — source from match_profile.sh and detect.sh.
# Usage: source this file, then call profile_match_id (prints profile id to stdout).
set -u

profile_collect_signals() {
  _rt_in_container=0
  [ -f /.dockerenv ] && _rt_in_container=1

  _rt_has_edencode=0
  command -v edencode >/dev/null 2>&1 && _rt_has_edencode=1

  _rt_has_docker=0
  command -v docker >/dev/null 2>&1 && _rt_has_docker=1
  command -v podman >/dev/null 2>&1 && _rt_has_docker=1

  _rt_has_nvidia_dev=0
  ls /dev/nvidia[0-9]* >/dev/null 2>&1 && _rt_has_nvidia_dev=1

  _rt_gpu_name=""
  if command -v nvidia-smi >/dev/null 2>&1; then
    _rt_gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)"
  fi

  _rt_torch_cu124=0
  python - <<'PY' >/dev/null 2>&1 && _rt_torch_cu124=1
import torch
v = torch.__version__
assert "+cu" in v and torch.cuda.is_available() is not None
PY
}

profile_match_id() {
  profile_collect_signals
  if [[ $_rt_in_container -eq 1 && $_rt_has_nvidia_dev -eq 1 \
        && $_rt_has_edencode -eq 0 && $_rt_has_docker -eq 0 \
        && "$_rt_gpu_name" == *B300* ]]; then
    echo "edencode-b300"
  elif [[ $_rt_in_container -eq 1 && $_rt_has_nvidia_dev -eq 1 && $_rt_torch_cu124 -eq 1 \
        && $_rt_has_edencode -eq 0 && $_rt_has_docker -eq 0 ]]; then
    echo "edencode-h200"
  elif [[ $_rt_in_container -eq 0 && $_rt_has_docker -eq 1 ]]; then
    echo "generic-host-with-docker"
  elif [[ $_rt_in_container -eq 1 ]]; then
    echo "generic-container"
  else
    echo "unknown"
  fi
}
