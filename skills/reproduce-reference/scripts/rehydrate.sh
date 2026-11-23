#!/usr/bin/env bash
# Unfold the verified record references/<id>/reproduce/ into a fresh attempt workspace, the reverse
# of promote_attempt.sh. Use it to re-run, benchmark, or compare a promoted reproduction (for example
# during promote-to-lib alignment). The environment is rebuilt by the attempt's own run.sh when
# run_attempt.sh executes it.
#
# Usage: bash skills/reproduce-reference/scripts/rehydrate.sh <id> <attempt> [--force] [--venv]
#   --force : replace an existing attempt workspace of that name (default: refuse).
#   --venv  : also rebuild <attempt>/.venv from venv-freeze.txt with uv (best effort; run.sh is
#             the authoritative, machine-aware recipe).
set -uo pipefail

REF_ID="${1:?reference id required}"
ATTEMPT="${2:?attempt slug required}"
shift 2
FORCE=""; VENV=""
for a in "$@"; do case "$a" in
  --force) FORCE=1 ;;
  --venv)  VENV=1 ;;
  *) echo "unknown flag: $a (use --force and/or --venv)" >&2; exit 2 ;;
esac; done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SRC="$ROOT/references/$REF_ID/reproduce"
DST="$ROOT/references/$REF_ID/attempts/$ATTEMPT"
REGISTRY="$ROOT/skills/fetch-reference/scripts/references_registry.py"

[ -d "$SRC" ] || { echo "references/$REF_ID has no reproduce/ record to rehydrate" >&2; exit 1; }
if [ -d "$DST" ] && [ -z "$FORCE" ]; then
  echo "references/$REF_ID/attempts/$ATTEMPT already exists; refusing (use --force to replace it)" >&2; exit 1
fi
[ -n "$FORCE" ] && rm -rf "$DST"
mkdir -p "$DST"
( cd "$SRC" && tar cf - . ) | ( cd "$DST" && tar xf - )
[ -f "$DST/RESULT.json" ] && cp "$DST/RESULT.json" "$DST/result.json"
python3 "$REGISTRY" sync "$REF_ID" >/dev/null 2>&1 || echo "warn: registry sync failed" >&2

echo "rehydrated references/$REF_ID/reproduce -> references/$REF_ID/attempts/$ATTEMPT/"
[ -f "$DST/run.sh" ]          && echo "  entry:       references/$REF_ID/attempts/$ATTEMPT/run.sh"
[ -f "$DST/venv-freeze.txt" ] && echo "  deps recipe: references/$REF_ID/attempts/$ATTEMPT/venv-freeze.txt"

if [ -n "$VENV" ]; then
  if command -v uv >/dev/null 2>&1 && [ -f "$DST/venv-freeze.txt" ]; then
    if uv venv --system-site-packages "$DST/.venv" \
        && uv pip install --python "$DST/.venv/bin/python" -r "$DST/venv-freeze.txt"; then
      echo "  built references/$REF_ID/attempts/$ATTEMPT/.venv"
    else
      echo "warn: freeze-based rebuild failed; use run.sh through run_attempt.sh instead" >&2
    fi
  else
    echo "warn: --venv needs uv and venv-freeze.txt; use run.sh through run_attempt.sh" >&2
  fi
fi

echo "next: bash skills/reproduce-reference/scripts/run_attempt.sh $REF_ID $ATTEMPT"
