#!/usr/bin/env bash
# GPU probe — thresholds from live product name; logic in lib/gpu_common.sh.
set -u

_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)"
# shellcheck source=../lib/common.sh
source "$_LIB/common.sh"
# shellcheck source=../lib/runtime_facts.sh
source "$_LIB/runtime_facts.sh"
# shellcheck source=../lib/gpu_common.sh
source "$_LIB/gpu_common.sh"

runtime_collect_facts
EXPECTED="$(runtime_gpu_count_expected)"

GPU_PROBE_LABEL="generic"
GPU_COUNT_EXPECTED="$EXPECTED"
GPU_LIST_PROCS=0
GPU_NVIDIA_SMI_SOURCE="nvidia_smi"

if [[ $RT_IN_CONTAINER -eq 1 && $RT_HAS_NVIDIA_DEV -eq 1 ]]; then
  GPU_NVIDIA_SMI_SOURCE="container_nvidia_smi"
  GPU_LIST_PROCS=1
fi

if [[ "$EXPECTED" -gt 0 ]]; then
  GPU_PROBE_LABEL="gpu:${RT_GPU_MODEL:-unknown}"
fi

export RUNTIME_CAPABILITY="${RUNTIME_CAPABILITY:-$(runtime_capability_id)}"

gpu_run_probe
