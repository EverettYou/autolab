# Shared GPU probe logic — source after common.sh.
# Profile scripts set: GPU_PROBE_LABEL, GPU_COUNT_EXPECTED (0 = all GPUs for avail_heavy),
# GPU_LIST_PROCS (1 = emit per-GPU compute PIDs), GPU_NVIDIA_SMI_SOURCE.
set -u

GPU_IDLE_UTIL_MAX="${GPU_IDLE_UTIL_MAX:-10}"
GPU_MIN_FREE_GIB_HEAVY="${GPU_MIN_FREE_GIB_HEAVY:-20}"
GPU_COUNT_EXPECTED="${GPU_COUNT_EXPECTED:-0}"
GPU_LIST_PROCS="${GPU_LIST_PROCS:-0}"
GPU_NVIDIA_SMI_SOURCE="${GPU_NVIDIA_SMI_SOURCE:-nvidia_smi}"
GPU_PROBE_LABEL="${GPU_PROBE_LABEL:-generic}"

gpu_count=0
idle_gpus=0
GPU_PROBE_SOURCE="none"

gpu_emit_line() {
  local idx="$1" util="$2" mem_used_mib="$3" mem_total_mib="$4"
  local mem_used_gib mem_total_gib free_gib
  mem_used_gib="$(awk "BEGIN {printf \"%.1f\", $mem_used_mib/1024}")"
  mem_total_gib="$(awk "BEGIN {printf \"%.1f\", $mem_total_mib/1024}")"
  free_gib="$(awk "BEGIN {printf \"%.1f\", ($mem_total_mib-$mem_used_mib)/1024}")"
  probe_kv "gpu${idx}_util_pct" "${util}"
  probe_kv "gpu${idx}_mem_used_gib" "${mem_used_gib}"
  probe_kv "gpu${idx}_mem_total_gib" "${mem_total_gib}"
  probe_kv "gpu${idx}_mem_free_gib" "${free_gib}"
  probe_note "gpu${idx}: util=${util}% mem=${mem_used_gib}/${mem_total_gib} GiB free=${free_gib} GiB"
  gpu_count=$((gpu_count + 1))
  if [[ "$util" != "unknown" ]] && [[ "$util" -le "$GPU_IDLE_UTIL_MAX" ]]; then
    local free_mib=$((mem_total_mib - mem_used_mib))
    local min_free_mib
    min_free_mib="$(awk "BEGIN {printf \"%.0f\", $GPU_MIN_FREE_GIB_HEAVY * 1024}")"
    if [[ "$free_mib" -ge "$min_free_mib" ]]; then
      idle_gpus=$((idle_gpus + 1))
    fi
  fi
}

gpu_emit_procs_nvidia_smi() {
  [[ "$GPU_LIST_PROCS" -eq 1 ]] || return 0
  local idx max_idx
  max_idx=$((gpu_count > 0 ? gpu_count - 1 : 0))
  for idx in $(seq 0 "$max_idx"); do
    local procs n=0
    procs="$(nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader -i "$idx" 2>/dev/null | sed '/^$/d')"
    if [[ -z "$procs" ]]; then
      probe_note "gpu${idx}_procs: (none)"
      probe_kv "gpu${idx}_proc_count" "0"
      continue
    fi
    while IFS= read -r line; do
      local pid pname mem ps_line user etime cmd tag
      pid="$(echo "$line" | cut -d',' -f1 | tr -d ' ')"
      pname="$(echo "$line" | cut -d',' -f2 | tr -d ' ')"
      mem="$(echo "$line" | cut -d',' -f3 | tr -d ' ')"
      [[ -z "$pid" || "$pid" == "pid" ]] && continue
      ps_line="$(ps -o user=,etime=,cmd= -p "$pid" 2>/dev/null || true)"
      user="$(echo "$ps_line" | awk '{print $1}')"
      etime="$(echo "$ps_line" | awk '{print $2}')"
      cmd="$(echo "$ps_line" | cut -d' ' -f3-)"
      [[ -z "$cmd" ]] && cmd="$pname"
      tag="$(tag_gpu_pid "$pid" "$cmd")"
      probe_note "gpu${idx}_proc: pid=${pid} tag=${tag} user=${user:-?} mem=${mem} etime=${etime:-?} cmd=${cmd}"
      n=$((n + 1))
    done <<< "$procs"
    probe_kv "gpu${idx}_proc_count" "$n"
  done
}

gpu_read_nvidia_smi() {
  command -v nvidia-smi >/dev/null 2>&1 || return 1
  nvidia-smi -L >/dev/null 2>&1 || return 1
  GPU_PROBE_SOURCE="$GPU_NVIDIA_SMI_SOURCE"
  local idx=0
  while IFS= read -r line; do
    local util used total
    util="$(echo "$line" | cut -d',' -f1 | tr -d ' %')"
    used="$(echo "$line" | cut -d',' -f2 | tr -d ' MiB')"
    total="$(echo "$line" | cut -d',' -f3 | tr -d ' MiB')"
    gpu_emit_line "$idx" "$util" "$used" "$total"
    idx=$((idx + 1))
  done < <(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null)
  gpu_emit_procs_nvidia_smi
  return 0
}

gpu_read_pynvml() {
  local out
  out="$(python3 - <<'PY' 2>/dev/null
try:
    import pynvml
except ImportError:
    raise SystemExit(1)
pynvml.nvmlInit()
try:
    for i in range(pynvml.nvmlDeviceGetCount()):
        h = pynvml.nvmlDeviceGetHandleByIndex(i)
        util = pynvml.nvmlDeviceGetUtilizationRates(h).gpu
        mem = pynvml.nvmlDeviceGetMemoryInfo(h)
        print(f"{i},{util},{mem.used//1048576},{mem.total//1048576}")
finally:
    pynvml.nvmlShutdown()
PY
)" || return 1
  GPU_PROBE_SOURCE="pynvml"
  while IFS= read -r line; do
    gpu_emit_line "$(echo "$line" | cut -d',' -f1)" "$(echo "$line" | cut -d',' -f2)" \
      "$(echo "$line" | cut -d',' -f3)" "$(echo "$line" | cut -d',' -f4)"
  done <<< "$out"
  return 0
}

gpu_read_torch_mem() {
  local out
  out="$(python3 - <<'PY' 2>/dev/null
import torch
if not torch.cuda.is_available():
    raise SystemExit(1)
for i in range(torch.cuda.device_count()):
    free, total = torch.cuda.mem_get_info(i)
    used = total - free
    print(f"{i},unknown,{used//1048576},{total//1048576}")
PY
)" || return 1
  GPU_PROBE_SOURCE="torch_mem_only"
  probe_set_status WARN
  probe_note "WARN: GPU util unknown (torch mem only) — do not infer saturation from ps CPU%"
  while IFS= read -r line; do
    gpu_emit_line "$(echo "$line" | cut -d',' -f1)" "$(echo "$line" | cut -d',' -f2)" \
      "$(echo "$line" | cut -d',' -f3)" "$(echo "$line" | cut -d',' -f4)"
  done <<< "$out"
  return 0
}

gpu_finalize_avail_tier() {
  probe_kv "GPU_PROBE_SOURCE" "$GPU_PROBE_SOURCE"
  probe_kv "gpu_count" "$gpu_count"

  local heavy_bar="$GPU_COUNT_EXPECTED"
  [[ "$heavy_bar" -eq 0 ]] && heavy_bar="$gpu_count"

  local avail_tier="avail_none"
  if [[ "$heavy_bar" -ge 1 && "$idle_gpus" -ge "$heavy_bar" && "$gpu_count" -ge "$heavy_bar" ]]; then
    avail_tier="avail_heavy"
  elif [[ "$idle_gpus" -ge 1 ]]; then
    avail_tier="avail_light"
  fi
  probe_kv "AVAIL_TIER" "$avail_tier"
  probe_note "note: idle_gpus ${idle_gpus}/${gpu_count} util_max ${GPU_IDLE_UTIL_MAX}%"
  probe_kv "gpu_probe_status" "$PROBE_STATUS"
}

gpu_run_probe() {
  probe_note "## probe: gpu (${GPU_PROBE_LABEL})"
  if gpu_read_nvidia_smi; then
    :
  elif gpu_read_pynvml; then
    :
  elif gpu_read_torch_mem; then
    :
  else
    probe_set_status FAIL
    GPU_PROBE_SOURCE="unavailable"
    probe_note "FAIL: no NVML path (nvidia-smi, pynvml, torch.cuda all failed)"
  fi
  gpu_finalize_avail_tier
}
