#!/usr/bin/env bash
# Network reachability for scout / pip — read-only HEAD/GET probes.
set -u

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib" && pwd)/common.sh"

PROBE_STATUS="PASS"
NET_TIMEOUT="${NET_TIMEOUT:-10}"

_check_url() {
  local name="$1" url="$2"
  local code latency
  local start end
  start="$(date +%s%N 2>/dev/null || date +%s)"
  code="$(run_with_timeout "$NET_TIMEOUT" curl -sS -o /dev/null -w '%{http_code}' --max-time "$NET_TIMEOUT" "$url" 2>/dev/null || echo "000")"
  end="$(date +%s%N 2>/dev/null || date +%s)"
  if [[ "$start" =~ [0-9]{10,} ]]; then
    latency="$(( (end - start) / 1000000 ))"
  else
    latency="$(( end - start ))"
  fi
  local status="PASS"
  if [[ "$code" == "000" ]]; then
    status="FAIL"
    probe_set_status FAIL
  elif [[ "$code" -ge 400 && "$code" != "403" ]]; then
    status="WARN"
    probe_set_status WARN
  fi
  probe_kv "${name}_http" "$code"
  probe_kv "${name}_status" "$status"
  probe_kv "${name}_latency_ms" "$latency"
  probe_note "${name}: ${status} http=${code} latency_ms=${latency}"
}

probe_note "## probe: network"

if ! command -v curl >/dev/null 2>&1; then
  probe_set_status FAIL
  probe_note "FAIL: curl not installed"
  probe_kv "network_probe_status" "FAIL"
  exit 0
fi

_check_url "arxiv_export" "https://export.arxiv.org/api/query?search_query=all:electron&max_results=1"
_check_url "arxiv_site" "https://arxiv.org/"
_check_url "github_api" "https://api.github.com/"
_check_url "github_site" "https://github.com/"
_check_url "pypi" "https://pypi.org/simple/"

probe_kv "network_probe_status" "$PROBE_STATUS"
