#!/usr/bin/env bash
# Python / torch / repo venv sanity for repro RUN.
set -u

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/common.sh"

PROBE_STATUS="PASS"

probe_note "## probe: python_env"

py_ver="$(python3 --version 2>&1 || echo unknown)"
probe_kv "python_version" "$py_ver"
probe_note "python: ${py_ver}"

torch_line="$(python3 - <<'PY' 2>/dev/null || echo "torch: unavailable"
import torch
print(f"torch {torch.__version__} cuda_avail={torch.cuda.is_available()} ndev={torch.cuda.device_count()}")
PY
)"
probe_note "$torch_line"
if [[ "$torch_line" == "torch: unavailable" ]]; then
  probe_set_status WARN
fi
probe_kv "torch_line" "$torch_line"

venv="${REPO_ROOT}/.venv"
if [[ -d "$venv" ]]; then
  probe_kv "repo_venv" "present"
  probe_note "repo_venv: present ($venv)"
else
  probe_kv "repo_venv" "absent"
  probe_note "repo_venv: absent (run setup_venv.sh if needed)"
fi

probe_kv "python_env_status" "$PROBE_STATUS"
