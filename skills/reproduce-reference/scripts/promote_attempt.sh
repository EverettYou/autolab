#!/usr/bin/env bash
# Promote an accepted attempt to the tracked verified record references/<id>/reproduce/.
# Copies the distilled artifacts (recipe, code, configs, small results), not the workspace: excludes
# virtual environments, git metadata and bytecode, freezes the venv deps for restore, renames result.json to
# RESULT.json, warns on files over 10 MB and refuses files over 100 MB (they cannot be pushed).
# Then records the reproduction and status in references/<id>/provenance.json and rebuilds
# references/references.json.
#
# Usage: bash skills/reproduce-reference/scripts/promote_attempt.sh <id> <attempt> [--update] [--force]
#   --update : merge into an existing reproduce/ record (files with the same name are replaced).
#              Without it an existing non-empty record is never touched.
#   --force  : skip the result/gate/verdict checks (record why in the reproduce/README.md).
set -uo pipefail

REF_ID="${1:?reference id required}"
ATTEMPT="${2:?attempt slug required}"
shift 2
FORCE=""; UPDATE=""
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --update) UPDATE=1 ;;
    *) echo "unknown flag: $arg (use --update and/or --force)" >&2; exit 2 ;;
  esac
done
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SRC="$ROOT/references/$REF_ID/attempts/$ATTEMPT"
DST="$ROOT/references/$REF_ID/reproduce"
REGISTRY="$ROOT/skills/fetch-reference/scripts/references_registry.py"
WARN_MB=10
LIMIT_MB=100

[ -d "$SRC" ] || { echo "no references/$REF_ID/attempts/$ATTEMPT to promote" >&2; exit 1; }
if [ -d "$DST" ] && [ -n "$(ls -A "$DST" 2>/dev/null)" ] && [ -z "$UPDATE" ]; then
  echo "references/$REF_ID/reproduce/ already holds a record; refusing to touch it." >&2
  echo "  -> rerun with --update to merge this attempt into it (review the git diff afterwards)." >&2
  exit 1
fi

# A missing result.json refuses rather than skips: an attempt with no result has nothing to promote.
if [ -z "$FORCE" ]; then
  [ -f "$SRC/result.json" ] || { echo "attempt has no result.json; run it first (run_attempt.sh)" >&2; exit 1; }
  grep -q '"status": *"success"' "$SRC/result.json" || {
    echo "result.json is not status=success; refusing" >&2; exit 1; }
  [ -f "$SRC/gate-state.yaml" ] || {
    echo "gate-state.yaml missing; the reproduction review gate is required" >&2; exit 1; }
  grep -qE '^rigor_recommendation: *(Accept|accept)' "$SRC/gate-state.yaml" || {
    echo "gate-state.yaml: rigor_recommendation is not Accept; complete VERIFY first" >&2; exit 1; }
  VERDICT=$(grep -o '"verdict": *"[^"]*"' "$SRC/result.json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
  case "$VERDICT" in
    reproduced|partial) ;;
    *) echo "result.json verdict is '${VERDICT:-missing}', not reproduced|partial; set it after Accept" >&2; exit 1 ;;
  esac
else
  VERDICT=$(grep -o '"verdict": *"[^"]*"' "$SRC/result.json" 2>/dev/null | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
fi

EXCLUDES=(--exclude='.venv' --exclude='venv' --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache')
huge=$(cd "$SRC" && find . -type f -size +${LIMIT_MB}M -not -path '*/.venv/*' -not -path '*/venv/*' -not -path '*/.git/*' 2>/dev/null)
if [ -n "$huge" ]; then
  echo "refusing: files over ${LIMIT_MB} MB cannot be tracked; leave weights in the attempt workspace or delete:" >&2
  echo "$huge" >&2
  exit 1
fi

mkdir -p "$DST"
( cd "$SRC" && tar cf - "${EXCLUDES[@]}" . ) | ( cd "$DST" && tar xf - )
[ -f "$DST/result.json" ] && mv -f "$DST/result.json" "$DST/RESULT.json"

if [ -x "$SRC/.venv/bin/python" ] && command -v uv >/dev/null 2>&1; then
  uv pip freeze --python "$SRC/.venv/bin/python" > "$DST/venv-freeze.txt" 2>/dev/null \
    && echo "froze venv deps -> reproduce/venv-freeze.txt" || echo "warn: venv freeze failed (run.sh is the recipe)" >&2
fi

big=$(find "$DST" -type f -size +${WARN_MB}M 2>/dev/null)
[ -n "$big" ] && { echo "WARNING: large files in the record (>${WARN_MB} MB); keep it lean:" >&2; echo "$big" >&2; }

python3 "$REGISTRY" sync "$REF_ID" >/dev/null || echo "warn: registry sync failed; run references_registry.py sync $REF_ID" >&2
case "$VERDICT" in
  reproduced|partial) python3 "$REGISTRY" set "$REF_ID" --status "$VERDICT" >/dev/null \
    || echo "warn: could not set status $VERDICT" >&2 ;;
esac

echo "promoted references/$REF_ID/attempts/$ATTEMPT -> references/$REF_ID/reproduce/ (status ${VERDICT:-unchanged})"
find "$DST" -type f | sed "s|$ROOT/||;s|^|  |" | head -50
echo "next: commit references/$REF_ID/reproduce/, references/$REF_ID/provenance.json and references/references.json"
