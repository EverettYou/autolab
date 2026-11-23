# runtime-env shared helpers — source from probes/snapshot, do not execute directly.
set -u

_RTENV_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RTENV_SKILL_ROOT="$(cd "$_RTENV_LIB_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$RTENV_SKILL_ROOT/../.." && pwd)"
PROBES_DIR="$RTENV_SKILL_ROOT/scripts/probes"
CACHE_DIR="${REPO_ROOT}/.cache/runtime-env"

# Flat key=value lines collected for JSON footer (space-separated keys in SNAPSHOT_FIELDS).
SNAPSHOT_FIELDS=""

probe_kv() {
  local key="$1" val="$2"
  printf '%s=%s\n' "$key" "$val"
  SNAPSHOT_FIELDS="${SNAPSHOT_FIELDS} ${key}"
}

# Human-readable line (not parsed as KEY=value by snapshot).
probe_note() {
  printf '%s\n' "$*"
}

run_with_timeout() {
  local secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  else
    "$@"
  fi
}

# Overall probe status for this probe module: PASS | WARN | FAIL | SKIP
PROBE_STATUS="PASS"

probe_set_status() {
  local new="$1"
  case "$PROBE_STATUS" in
    FAIL) return 0 ;;
    WARN) [[ "$new" == FAIL ]] && PROBE_STATUS="FAIL" ;;
    PASS) PROBE_STATUS="$new" ;;
  esac
}

overall_rank() {
  case "$1" in
    FAIL) echo 3 ;;
    DEGRADED) echo 2 ;;
    PASS) echo 1 ;;
    *) echo 0 ;;
  esac
}

merge_overall() {
  local cur="$1" new="$2"
  if [[ "$(overall_rank "$new")" -gt "$(overall_rank "$cur")" ]]; then
    echo "$new"
  else
    echo "$cur"
  fi
}

# Tag GPU compute PID as repo | foreign | unknown using the loop state, cmdline paths, and cwd.
tag_gpu_pid() {
  local pid="$1"
  local cmd="${2:-}"
  local state="${REPO_ROOT}/.auto-research/state.json"
  local cwd=""
  if [[ -f "$state" ]] && grep -qE "(^|[^0-9])${pid}([^0-9]|$)" "$state" 2>/dev/null; then
    echo "repo"
    return
  fi
  if [[ "$cmd" == *"${REPO_ROOT}/references/"* ]] || [[ "$cmd" == *"${REPO_ROOT}/labs/"* ]] \
    || [[ "$cmd" == *"${REPO_ROOT}/lib/"* ]]; then
    echo "repo"
    return
  fi
  cwd="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"
  if [[ -n "$cwd" ]] && { [[ "$cwd" == "$REPO_ROOT" ]] || [[ "$cwd" == "$REPO_ROOT"/* ]]; }; then
    echo "repo"
    return
  fi
  if [[ -n "$cmd" ]]; then
    echo "foreign"
    return
  fi
  echo "unknown"
}
