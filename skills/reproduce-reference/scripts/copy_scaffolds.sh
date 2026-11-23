#!/usr/bin/env bash
# Seed an attempt workspace with the build-from-paper scaffolds (src/*.py) and configs/base.yaml.
# Refuses to overwrite files that already exist in the workspace.
#
# Usage: bash skills/reproduce-reference/scripts/copy_scaffolds.sh <id> <attempt>
set -euo pipefail
REF_ID="${1:?reference id required}"
ATTEMPT="${2:?attempt slug required}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$SKILL_DIR/../.." && pwd)"
WS="$ROOT/references/$REF_ID/attempts/$ATTEMPT"
[ -d "$WS" ] || { echo "no workspace references/$REF_ID/attempts/$ATTEMPT" >&2; exit 1; }

copy_new() {  # src dest
  if [ -e "$2" ]; then echo "keep existing ${2#"$ROOT"/}"; else cp "$1" "$2"; echo "seeded ${2#"$ROOT"/}"; fi
}
mkdir -p "$WS/src" "$WS/configs"
for f in model loss data train evaluate; do
  copy_new "$SKILL_DIR/templates/scaffolds/${f}.py" "$WS/src/${f}.py"
done
copy_new "$SKILL_DIR/templates/configs/base.yaml" "$WS/configs/base.yaml"
