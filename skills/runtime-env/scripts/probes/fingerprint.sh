#!/usr/bin/env bash
# Fingerprint probe — detect.sh (facts + policy) as uniform snapshot kv.
set -u

_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)"
# shellcheck source=../lib/common.sh
source "$_LIB/common.sh"
# shellcheck source=../lib/resolve_policy.sh
source "$_LIB/resolve_policy.sh"

probe_note "## probe: fingerprint"
bash "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/detect.sh"

resolve_policy
probe_kv "RUNTIME_CAPABILITY" "$RUNTIME_CAPABILITY"
probe_kv "POLICY_ISOLATION" "$POLICY_ISOLATION"
probe_kv "POLICY_UNTRUSTED_CODE" "$POLICY_UNTRUSTED_CODE"
probe_kv "POLICY_VENV_MODE" "$POLICY_VENV_MODE"
probe_kv "FACT_IN_CONTAINER" "$RT_IN_CONTAINER"
probe_kv "FACT_HAS_DOCKER" "$RT_HAS_DOCKER"
probe_kv "FACT_OS_FAMILY" "$RT_OS_FAMILY"
probe_kv "FACT_GPU_MODEL" "$RT_GPU_MODEL"
probe_kv "FACT_HAS_NVIDIA_DEV" "$RT_HAS_NVIDIA_DEV"
probe_kv "FACT_HAS_CUDA_TORCH" "$RT_HAS_CUDA_TORCH"
probe_kv "FACT_HAS_MPS" "$RT_HAS_MPS"
probe_kv "fingerprint_status" "PASS"
