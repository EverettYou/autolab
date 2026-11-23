#!/usr/bin/env bash
# Generic GPU probe — nvidia-smi / pynvml / torch mem in the current mount namespace.
set -u

_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../scripts/lib"
# shellcheck source=../../scripts/lib/common.sh
source "$_LIB/common.sh"
# shellcheck source=../../scripts/lib/gpu_common.sh
source "$_LIB/gpu_common.sh"

GPU_PROBE_LABEL="generic"
GPU_COUNT_EXPECTED=0
GPU_LIST_PROCS=0
GPU_NVIDIA_SMI_SOURCE="nvidia_smi"

gpu_run_probe
