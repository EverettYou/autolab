#!/usr/bin/env bash
# Host CPU/memory/disk — not GPU. ps used for top memory only.
set -u

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib" && pwd)/common.sh"

PROBE_STATUS="PASS"
MEM_WARN_GIB="${MEM_WARN_GIB:-8}"
DISK_WARN_PCT="${DISK_WARN_PCT:-90}"

probe_note "## probe: host_resources"

load_1m="$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo "?")"
nproc="$(nproc 2>/dev/null || echo "?")"
probe_kv "load_1m" "$load_1m"
probe_kv "cpu_count" "$nproc"
probe_note "load: ${load_1m} (1m)  cpus: ${nproc}"

if command -v free >/dev/null 2>&1; then
  mem_avail_kib="$(free -k | awk '/^Mem:/ {print $7}')"
  mem_avail_gib="$(awk "BEGIN {printf \"%.1f\", $mem_avail_kib/1024/1024}")"
  probe_kv "mem_avail_gib" "$mem_avail_gib"
  probe_note "mem_avail: ${mem_avail_gib} GiB"
  mem_avail_int="${mem_avail_gib%.*}"
  if [[ "$mem_avail_int" =~ ^[0-9]+$ ]] && [[ "$mem_avail_int" -lt "$MEM_WARN_GIB" ]]; then
    probe_set_status WARN
    probe_note "WARN: mem_avail below ${MEM_WARN_GIB} GiB"
  fi
fi

disk_pct="$(df -P "$REPO_ROOT" 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%')"
probe_kv "disk_repo_pct" "${disk_pct:-?}"
probe_note "disk_repo: ${disk_pct:-?}%"
if [[ "${disk_pct:-0}" =~ ^[0-9]+$ ]] && [[ "$disk_pct" -ge "$DISK_WARN_PCT" ]]; then
  probe_set_status WARN
  probe_note "WARN: repo disk >= ${DISK_WARN_PCT}%"
fi

probe_note "top_mem:"
ps -eo user=,pid=,rss=,cmd= --sort=-rss 2>/dev/null | head -5 | while read -r user pid rss cmd; do
  [[ -z "$pid" ]] && continue
  rss_mib="$(awk "BEGIN {printf \"%.0f\", ${rss:-0}/1024}")"
  probe_note "  user=${user} pid=${pid} rss_mib=${rss_mib} cmd=${cmd}"
done

probe_kv "host_resources_status" "$PROBE_STATUS"
