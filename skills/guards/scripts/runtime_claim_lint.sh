#!/usr/bin/env bash
# Warn when records claim GPU utilization without snapshot evidence (non-blocking, always exit 0).
# Usage: runtime_claim_lint.sh [FILE ...]   (default: wiki/records/synthesis/*.md)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

WARN=0
shopt -s nullglob

check_file() {
  local f="$1"
  # Skip if file cites SNAPSHOT_TIME or snapshot.sh output
  if grep -qE 'SNAPSHOT_TIME=|snapshot\.sh|gpu_snapshot|AVAIL_TIER=' "$f" 2>/dev/null; then
    return 0
  fi
  if grep -qE '[0-9]{1,3}%[[:space:]]*util|at[[:space:]]+[0-9]{1,3}%|H200s?[[:space:]]+at[[:space:]]+[0-9]|both GPUs? at[[:space:]]+[0-9]' "$f" 2>/dev/null; then
    echo "WARN: $f — GPU util claim without SNAPSHOT_TIME (run skills/runtime-env/scripts/snapshot.sh --bundle maintain)"
    WARN=1
  fi
}

echo "== runtime_claim_lint (warn-only) =="

if [ "$#" -gt 0 ]; then
  files=("$@")
else
  files=(wiki/records/synthesis/*.md)
fi
for f in "${files[@]}"; do
  [[ -f "$f" ]] || continue
  check_file "$f"
done

if [[ $WARN -eq 0 ]]; then
  echo "OK: no unchecked GPU util claims in ${#files[@]} file(s)"
fi
exit 0
