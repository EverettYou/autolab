#!/usr/bin/env bash
# Resolve POLICY_* from live facts + optional local override.
# Usage:
#   source resolve_policy.sh && resolve_policy   # sets POLICY_* in the shell
#   bash resolve_policy.sh                      # prints KEY=value lines
set -u

_RESOLVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runtime_facts.sh
source "$_RESOLVE_DIR/runtime_facts.sh"

_resolve_policy_defaults() {
  runtime_collect_facts
  POLICY_ISOLATION="host-control-plane"
  POLICY_UNTRUSTED_CODE="forbid"
  POLICY_VENV_MODE="inherit-baseline"
  # Where the canonical repo .venv may be built:
  #   here              — bare host (no docker) or already inside a container
  #   require-container — host has docker/podman; do not pollute the host control plane
  POLICY_REPO_VENV="here"

  if [[ $RT_IN_CONTAINER -eq 1 ]]; then
    POLICY_ISOLATION="this-container"
    POLICY_UNTRUSTED_CODE="allow-in-attempt-workspace"
    POLICY_REPO_VENV="here"
  elif [[ $RT_HAS_DOCKER -eq 1 ]]; then
    POLICY_ISOLATION="docker-attempt"
    POLICY_UNTRUSTED_CODE="only-in-container"
    POLICY_REPO_VENV="require-container"
  fi

  if [[ "${SETUP_VENV_ISOLATED:-0}" = "1" || "${SETUP_VENV_ISOLATED:-}" = "true" ]]; then
    POLICY_VENV_MODE="isolated"
  fi
}

_resolve_policy_apply_local() {
  local path=""
  if [[ -n "${AUTOLAB_RUNTIME_POLICY:-}" && -f "${AUTOLAB_RUNTIME_POLICY}" ]]; then
    path="$AUTOLAB_RUNTIME_POLICY"
  elif [[ -f "${HOME:-}/.config/autolab/runtime-policy.json" ]]; then
    path="${HOME}/.config/autolab/runtime-policy.json"
  else
    return 0
  fi
  # shellcheck disable=SC2034
  eval "$(
    POLICY_ISOLATION="$POLICY_ISOLATION" \
    POLICY_UNTRUSTED_CODE="$POLICY_UNTRUSTED_CODE" \
    POLICY_VENV_MODE="$POLICY_VENV_MODE" \
    POLICY_REPO_VENV="$POLICY_REPO_VENV" \
    python3 - "$path" <<'PY'
import json, os, sys
path = sys.argv[1]
try:
    data = json.loads(open(path, encoding="utf-8").read())
except (OSError, json.JSONDecodeError) as e:
    print(f'echo "[resolve_policy] WARN: ignore local override {path}: {e}" >&2')
    raise SystemExit(0)
allowed = {
    "isolation": "POLICY_ISOLATION",
    "untrusted_code": "POLICY_UNTRUSTED_CODE",
    "venv.mode": "POLICY_VENV_MODE",
    "venv_mode": "POLICY_VENV_MODE",
    "repo_venv": "POLICY_REPO_VENV",
    "venv.repo": "POLICY_REPO_VENV",
}
for key, env_name in allowed.items():
    if key in data and isinstance(data[key], str) and data[key].strip():
        val = data[key].strip().replace("'", "'\"'\"'")
        print(f"{env_name}='{val}'")
PY
  )"
}

resolve_policy() {
  _resolve_policy_defaults
  _resolve_policy_apply_local
  RUNTIME_CAPABILITY="$(runtime_capability_id)"
  export POLICY_ISOLATION POLICY_UNTRUSTED_CODE POLICY_VENV_MODE POLICY_REPO_VENV RUNTIME_CAPABILITY
}

# When executed (not sourced), print kv for probes/snapshot.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  resolve_policy
  echo "RUNTIME_CAPABILITY=${RUNTIME_CAPABILITY}"
  echo "POLICY_ISOLATION=${POLICY_ISOLATION}"
  echo "POLICY_UNTRUSTED_CODE=${POLICY_UNTRUSTED_CODE}"
  echo "POLICY_VENV_MODE=${POLICY_VENV_MODE}"
  echo "POLICY_REPO_VENV=${POLICY_REPO_VENV}"
  echo "FACT_IN_CONTAINER=${RT_IN_CONTAINER}"
  echo "FACT_HAS_DOCKER=${RT_HAS_DOCKER}"
  echo "FACT_OS_FAMILY=${RT_OS_FAMILY}"
  echo "FACT_GPU_MODEL=${RT_GPU_MODEL}"
  echo "FACT_HAS_NVIDIA_DEV=${RT_HAS_NVIDIA_DEV}"
  echo "FACT_HAS_CUDA_TORCH=${RT_HAS_CUDA_TORCH}"
  echo "FACT_HAS_MPS=${RT_HAS_MPS}"
fi
