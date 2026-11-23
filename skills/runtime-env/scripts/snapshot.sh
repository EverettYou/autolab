#!/usr/bin/env bash
# runtime-env snapshot orchestrator — composable read-only probes with optional cache.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

BUNDLE=""
PROBE=""
JSON_OUT=0
MAX_AGE=0

usage() {
  cat <<'EOF'
Usage: snapshot.sh --bundle <name> | --probe <name> [options]

Bundles: fingerprint, router, scout, repro-run, train-launch, full

Options:
  --json          Flat JSON output (default: human text + KEY=value footer)
  --max-age SEC   Reuse cached snapshot if younger than SEC seconds
  -h, --help      This help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle) BUNDLE="$2"; shift 2 ;;
    --probe) PROBE="$2"; shift 2 ;;
    --json) JSON_OUT=1; shift ;;
    --max-age) MAX_AGE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$BUNDLE" && -z "$PROBE" ]]; then
  usage >&2
  exit 2
fi

CACHE_KEY="${BUNDLE:-probe_${PROBE}}"
CACHE_TXT="${CACHE_DIR}/snapshot-${CACHE_KEY}.txt"
CACHE_JSON="${CACHE_DIR}/snapshot-${CACHE_KEY}.json"
CACHE_META="${CACHE_DIR}/snapshot-${CACHE_KEY}.meta"
CACHE_EXIT="${CACHE_DIR}/snapshot-${CACHE_KEY}.exit"

mkdir -p "$CACHE_DIR"

if [[ "$MAX_AGE" -gt 0 && -f "$CACHE_TXT" && -f "$CACHE_META" ]]; then
  cached_at="$(cat "$CACHE_META" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  if [[ $((now - cached_at)) -le "$MAX_AGE" ]]; then
    if [[ "$JSON_OUT" -eq 1 && -f "$CACHE_JSON" ]]; then
      cat "$CACHE_JSON"
    else
      cat "$CACHE_TXT"
      echo ""
      echo "# cached (max-age=${MAX_AGE}s)"
    fi
    exit "$(cat "$CACHE_EXIT" 2>/dev/null || echo 0)"
  fi
fi

declare -a PROBE_LIST=()
case "$BUNDLE" in
  fingerprint) PROBE_LIST=(fingerprint) ;;
  router) PROBE_LIST=(fingerprint gpu host_resources) ;;
  scout) PROBE_LIST=(network git_ssh) ;;
  repro-run) PROBE_LIST=(fingerprint python_env gpu) ;;
  train-launch) PROBE_LIST=(gpu host_resources) ;;
  full) PROBE_LIST=(fingerprint gpu host_resources network git_ssh python_env) ;;
  "") PROBE_LIST=("$PROBE") ;;
  *)
    echo "Unknown bundle: $BUNDLE" >&2
    exit 2
    ;;
esac

# shellcheck source=lib/resolve_policy.sh
source "$SCRIPT_DIR/lib/resolve_policy.sh"
resolve_policy
export RUNTIME_CAPABILITY POLICY_ISOLATION POLICY_UNTRUSTED_CODE POLICY_VENV_MODE
SNAPSHOT_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BUNDLE_LABEL="${BUNDLE:-probe:${PROBE}}"

PROBE_OUTPUT=""
for p in "${PROBE_LIST[@]}"; do
  script="${PROBES_DIR}/${p}.sh"
  if [[ ! -f "$script" ]]; then
    echo "Missing probe: $script" >&2
    exit 2
  fi
  block="$(bash "$script" 2>&1)" || true
  PROBE_OUTPUT+="${block}"$'\n\n'
done

# Parse KEY=value (uppercase key) into a kv file for JSON
KV_FILE="$(mktemp)"
trap 'rm -f "$KV_FILE"' EXIT

{
  echo "SNAPSHOT_TIME=${SNAPSHOT_TIME}"
  echo "BUNDLE=${BUNDLE_LABEL}"
  echo "RUNTIME_CAPABILITY=${RUNTIME_CAPABILITY}"
  echo "POLICY_ISOLATION=${POLICY_ISOLATION}"
  echo "POLICY_UNTRUSTED_CODE=${POLICY_UNTRUSTED_CODE}"
  echo "POLICY_VENV_MODE=${POLICY_VENV_MODE}"
} > "$KV_FILE"

while IFS= read -r line; do
  if [[ "$line" =~ ^([a-zA-Z][a-zA-Z0-9_]*)=(.*)$ ]]; then
    echo "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
  fi
done <<< "$PROBE_OUTPUT" | awk -F= '!seen[$1]++' >> "$KV_FILE"

OVERALL="PASS"
while IFS= read -r line; do
  [[ "$line" =~ _status= ]] || continue
  val="${line#*=}"
  case "$val" in
    FAIL) OVERALL="FAIL" ;;
    WARN) [[ "$OVERALL" != FAIL ]] && OVERALL="DEGRADED" ;;
  esac
done < "$KV_FILE"
echo "OVERALL=${OVERALL}" >> "$KV_FILE"

EXIT_CODE=0
case "$OVERALL" in
  FAIL) EXIT_CODE=2 ;;
  DEGRADED) EXIT_CODE=1 ;;
esac

# Human output
{
  echo "# runtime-env snapshot bundle=${BUNDLE_LABEL} capability=${RUNTIME_CAPABILITY}"
  echo ""
  printf '%s' "$PROBE_OUTPUT"
  echo "---"
  awk -F= '!seen[$1]++' "$KV_FILE" | grep -E '^(SNAPSHOT_TIME|BUNDLE|RUNTIME_CAPABILITY|POLICY_ISOLATION|POLICY_UNTRUSTED_CODE|POLICY_VENV_MODE|OVERALL|AVAIL_TIER|GPU_PROBE_SOURCE)=' || true
} | tee "$CACHE_TXT" | { [[ "$JSON_OUT" -eq 1 ]] || cat; }

python3 - "$KV_FILE" "$CACHE_JSON" <<'PY'
import json, sys
kv_path, json_path = sys.argv[1], sys.argv[2]
obj = {}
with open(kv_path) as f:
    for line in f:
        line = line.strip()
        if not line or '=' not in line:
            continue
        k, v = line.split('=', 1)
        obj[k] = v
with open(json_path, 'w') as f:
    json.dump(obj, f, indent=2, sort_keys=True)
if len(sys.argv) > 3 and sys.argv[3] == '--print':
    print(json.dumps(obj, indent=2, sort_keys=True))
PY

if [[ "$JSON_OUT" -eq 1 ]]; then
  cat "$CACHE_JSON"
fi

date +%s > "$CACHE_META"
echo "$EXIT_CODE" > "$CACHE_EXIT"
exit "$EXIT_CODE"
