#!/usr/bin/env bash
# Run a reproduction attempt under a host-side wall-clock cap and write
# references/<id>/attempts/<attempt>/result.json.
#
# Two outcome fields:
#   status  = mechanical: did the attempt run to completion (success|failed)? Set here.
#   verdict = scientific: does it reproduce the paper's claims (reproduced|partial|...)? Left
#             "unevaluated" here; set only after the reproduction review accepts the attempt.
#             promote_attempt.sh refuses to promote until it is reproduced|partial.
#
# Execution mode follows the runtime-env decision table:
#   docker mode: on a host (not inside a container) with docker and an attempt Dockerfile; builds a
#                per-attempt image and runs it with --network none and only output/ mounted.
#   venv mode:   otherwise; runs the attempt's run.sh here under the cap. Isolation is the
#                container itself; run-time network is not namespaced.
#
# Usage: bash skills/reproduce-reference/scripts/run_attempt.sh <id> <attempt> [timeout_seconds]
# Default timeout: the 1800 s smoke cap. For a queued TIME tier use
#   timeout = min(2 * $(bash skills/guards/scripts/parse_time.sh <tier>), cap).
# Long GPU training is launched detached by the attempt itself, not blocked on here.
set -uo pipefail

REF_ID="${1:?reference id required}"
ATTEMPT="${2:?attempt slug required}"
TIMEOUT="${3:-1800}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ATTEMPT_DIR="$ROOT/references/$REF_ID/attempts/$ATTEMPT"
RESULT_FILE="$ATTEMPT_DIR/result.json"
OUTPUT_DIR="$ATTEMPT_DIR/output"
REGISTRY="$ROOT/skills/fetch-reference/scripts/references_registry.py"
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)

case "$TIMEOUT" in ''|*[!0-9]*) echo "timeout must be whole seconds: $TIMEOUT" >&2; exit 2 ;; esac
[ -f "$ROOT/references/$REF_ID/provenance.json" ] || {
  echo "references/$REF_ID is not a registered reference (run fetch-reference first)" >&2; exit 2; }
[ -d "$ATTEMPT_DIR" ] || {
  echo "no workspace references/$REF_ID/attempts/$ATTEMPT (create it during IMPLEMENT)" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"

write_result() {  # status  failure(JSON null|"quoted")  summary  exit_code  mode
  local end; end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  cat >"$RESULT_FILE" <<EOF
{
  "reference": "$REF_ID",
  "attempt": "$ATTEMPT",
  "status": "$1",
  "failure_mode": $2,
  "verdict": "unevaluated",
  "verdict_note": "",
  "summary": "$3",
  "metrics": {},
  "artifacts": ["output"],
  "mode": "$5",
  "started_at": "$START",
  "ended_at": "$end",
  "exit_code": $4
}
EOF
  echo "wrote references/$REF_ID/attempts/$ATTEMPT/result.json ($1, mode=$5)"
  python3 "$REGISTRY" sync "$REF_ID" >/dev/null 2>&1 \
    || echo "warn: could not record the attempt in references/$REF_ID/provenance.json" >&2
}

map_exit() {  # exit_code mode
  case "$1" in
    0)   write_result "success" "null" "$2 run completed" 0 "$2" ;;
    124) write_result "failed" "\"timeout\"" "wall-clock cap (${TIMEOUT}s) exceeded" 124 "$2" ;;
    *)   write_result "failed" "\"runtime_crash\"" "attempt exited with code $1" "$1" "$2" ;;
  esac
}

SNAPSHOT_SH="$ROOT/skills/runtime-env/scripts/snapshot.sh"
if [ -f "$SNAPSHOT_SH" ]; then
  echo "== runtime-env repro-run snapshot ==" >&2
  bash "$SNAPSHOT_SH" --bundle repro-run --max-age 60 >&2 || true
fi

if [ ! -f /.dockerenv ] && command -v docker >/dev/null 2>&1 && [ -f "$ATTEMPT_DIR/Dockerfile" ]; then
  IMAGE="lab-attempt-$(printf '%s-%s' "$REF_ID" "$ATTEMPT" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9.-' '-'):local"
  if ! docker build -t "$IMAGE" "$ATTEMPT_DIR"; then
    write_result "failed" "\"build_error\"" "docker build failed" 1 "docker"; exit 1
  fi
  timeout "$TIMEOUT" docker run --rm --network none \
    -v "$OUTPUT_DIR:/workspace/output:rw" "$IMAGE"
  map_exit "$?" "docker"; exit 0
fi

if [ ! -f "$ATTEMPT_DIR/run.sh" ]; then
  write_result "failed" "\"build_error\"" "venv mode: missing run.sh" 1 "venv"; exit 1
fi
echo "venv mode: bash run.sh (cap ${TIMEOUT}s). Run-time network is not namespaced in venv mode;" >&2
echo "isolation is this container." >&2
( cd "$ATTEMPT_DIR" && timeout "$TIMEOUT" bash run.sh "$OUTPUT_DIR" )
map_exit "$?" "venv"
