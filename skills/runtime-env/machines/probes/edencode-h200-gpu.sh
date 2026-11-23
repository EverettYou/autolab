#!/usr/bin/env bash
# EdenCode H200 dev container — GPU probe via container NVML (host GPUs, driver-mapped).
set -u

_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../scripts/lib"
# shellcheck source=../../scripts/lib/common.sh
source "$_LIB/common.sh"
# shellcheck source=../../scripts/lib/gpu_common.sh
source "$_LIB/gpu_common.sh"

GPU_PROBE_LABEL="edencode-h200"
GPU_COUNT_EXPECTED=2
GPU_LIST_PROCS=1
GPU_NVIDIA_SMI_SOURCE="container_nvidia_smi"

gpu_run_probe
