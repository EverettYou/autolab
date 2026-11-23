#!/usr/bin/env bash
# gc_attempts.sh: report (and optionally reclaim) attempt workspaces references/<id>/attempts/<slug>/ whose
# work is safely captured in the tracked record references/<id>/reproduce/.
#
# Attempts are gitignored, so deleting one whose recipe is not in the record loses the only copy. An attempt
# is RECLAIMABLE only when all of these hold:
#   - references/<id>/reproduce/ is recipe-complete (RESULT.json plus a recipe driver or a marker, the same
#     test as reproduce_lint.sh), and
#   - the record names this attempt: RESULT.json "attempt" (or the legacy "slug") equals the attempt slug,
#     or one extends the other by "-suffix" and that match is unambiguous among the reference's attempts, and
#   - the attempt holds no training checkpoints and no .gc-keep sentinel, no running process has its cwd
#     inside it, and no source file in it is newer than RESULT.json.
# Everything else is reported, never deleted:
#   PROTECTED     checkpoints, sentinel, live process, newer sources, or not captured and still being touched
#   DISPOSITIONED a recorded decision: provenance.json "dispositions", else a row in the ledger
#                 wiki/implementations/attempt-dispositions.md, else a local DISPOSITION.md (untracked)
#   ORPHANED      not captured by the record and no source touched in GC_ORPHAN_DAYS (default 14); record
#                 a disposition (references_registry.py dispose) or promote it.
#
# Dry run by default. --reclaim (alias --apply) deletes RECLAIMABLE attempts, re-checking just before deletion.
# Attempt checkpoints stay protected; reclaiming never deletes a workspace that still holds them.
#
# Usage: bash skills/guards/scripts/gc_attempts.sh [--reclaim|--apply]
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
RECLAIM=0
case "${1:-}" in
  --reclaim|--apply) RECLAIM=1 ;;
  "") ;;
  *) echo "usage: gc_attempts.sh [--reclaim|--apply]" >&2; exit 2 ;;
esac
[ -d "$ROOT/references" ] || { echo "gc_attempts: no references/ directory"; exit 0; }
PY="$(command -v python3 || command -v python)"
LEDGER="$ROOT/wiki/implementations/attempt-dispositions.md"
ORPHAN_DAYS="${GC_ORPHAN_DAYS:-14}"

is_recipe_complete() {  # record dir
  local d="$1" f m
  [ -f "$d/RESULT.json" ] || return 1
  for f in "$d"/run.sh "$d"/run.py "$d"/run_*.py "$d"/repro*.py "$d"/arena*.py "$d"/*.sh "$d"/*.py; do
    [ -e "$f" ] && return 0
  done
  for m in RECIPE-STATUS.md SUPERSEDED.md; do [ -f "$d/$m" ] && return 0; done
  return 1
}

# Prints the attempt slug the record names, resolved against the reference's attempt directories.
record_attempt() {  # ref_dir
  [ -n "$PY" ] || return 0
  "$PY" - "$1" <<'PYEOF'
import json, sys
from pathlib import Path
ref = Path(sys.argv[1])
try:
    data = json.loads((ref / "reproduce" / "RESULT.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(0)
named = [str(v) for v in (data.get("attempt"), data.get("slug")) if v]
attempts = sorted(p.name for p in (ref / "attempts").iterdir() if p.is_dir()) if (ref / "attempts").is_dir() else []
for name in named:
    if name in attempts:
        print(name)
        sys.exit(0)
for name in named:
    hits = [a for a in attempts if a.startswith(name + "-") or name.startswith(a + "-")]
    if len(hits) == 1:
        print(hits[0])
        sys.exit(0)
PYEOF
}

DISPO=""
has_disposition() {  # ref_dir slug
  local ref_dir="$1" slug="$2" row
  DISPO=""
  if [ -n "$PY" ] && [ -f "$ref_dir/provenance.json" ]; then
    DISPO="$("$PY" -c 'import json,sys
d = json.load(open(sys.argv[1])).get("dispositions") or {}
e = d.get(sys.argv[2])
if e: print("%s: %s [provenance.json]" % (e.get("decision", "?"), e.get("note", "")))' "$ref_dir/provenance.json" "$slug" 2>/dev/null)"
    [ -n "$DISPO" ] && return 0
  fi
  if [ -f "$LEDGER" ]; then
    row="$(grep -m1 -F "| \`$slug\` |" "$LEDGER" 2>/dev/null || grep -m1 -F "| $slug |" "$LEDGER" 2>/dev/null || true)"
    if [ -n "$row" ]; then
      DISPO="$(printf '%s' "$row" | awk -F'|' '{gsub(/^ +| +$/,"",$3); r=$4; gsub(/^ +| +$/,"",r); print $3": "substr(r,1,90)}') [ledger]"
      return 0
    fi
  fi
  if [ -f "$ref_dir/attempts/$slug/DISPOSITION.md" ]; then
    DISPO="$(head -1 "$ref_dir/attempts/$slug/DISPOSITION.md" | sed 's/^#* *//') [local DISPOSITION.md only; record it with references_registry.py dispose]"
    return 0
  fi
  return 1
}

holds_checkpoints() {  # attempt dir
  local s="$1"
  [ -f "$s/.gc-keep" ] && return 0
  find "$s" -maxdepth 3 -type d -name 'checkpoints*' -not -path '*/.venv/*' 2>/dev/null | grep -q . && \
    find "$s" -maxdepth 4 \( -name '*.pt' -o -name '*.ckpt' -o -name '*.safetensors' \) -not -path '*/.venv/*' 2>/dev/null | grep -q . && return 0
  return 1
}

has_inflight_process() {  # attempt dir
  local abs pid cwd
  abs="$(readlink -f "$1" 2>/dev/null)" || return 1
  for pid in /proc/[0-9]*; do
    cwd="$(readlink -f "$pid/cwd" 2>/dev/null)" || continue
    case "$cwd" in "$abs"|"$abs"/*) return 0 ;; esac
  done
  return 1
}

sources_newer_than_record() {  # attempt dir, record dir
  [ -f "$2/RESULT.json" ] || return 1
  find "$1" -type f \( -name '*.py' -o -name '*.md' -o -name '*.sh' \) \
    -not -path '*/results/*' -not -path '*/logs/*' -not -path '*/output/*' -not -path '*/__pycache__/*' \
    -not -path '*/.venv/*' -newer "$2/RESULT.json" 2>/dev/null | grep -q . && return 0
  return 1
}

is_stale() {  # attempt dir
  find "$1" -type f \( -name '*.py' -o -name '*.md' -o -name '*.sh' -o -name '*.ipynb' \) \
    -not -path '*/__pycache__/*' -not -path '*/.venv/*' -mtime "-$ORPHAN_DAYS" 2>/dev/null | grep -q . && return 1
  return 0
}

reclaimable=0 protected=0 orphaned=0 dispositioned=0
for ref_dir in "$ROOT"/references/*/; do
  [ -d "$ref_dir/attempts" ] || continue
  ref_dir="${ref_dir%/}"
  id="$(basename "$ref_dir")"
  record="$ref_dir/reproduce"
  captured=""
  if is_recipe_complete "$record"; then captured="$(record_attempt "$ref_dir")"; fi
  for s in "$ref_dir"/attempts/*/; do
    [ -d "$s" ] || continue
    s="${s%/}"
    slug="$(basename "$s")"
    case "$slug" in _*|.*) continue ;; esac
    label="$id/$slug ($(du -sh "$s" 2>/dev/null | cut -f1))"
    if holds_checkpoints "$s"; then
      echo "PROTECTED     $label: holds training checkpoints or .gc-keep (untracked; only copy)"
      protected=$((protected+1))
    elif has_inflight_process "$s"; then
      echo "PROTECTED     $label: a running process has its cwd here (in-flight job)"
      protected=$((protected+1))
    elif [ "$captured" = "$slug" ] && sources_newer_than_record "$s" "$record"; then
      echo "PROTECTED     $label: sources newer than reproduce/RESULT.json (change not copied forward)"
      protected=$((protected+1))
    elif [ "$captured" = "$slug" ]; then
      echo "RECLAIMABLE   $label: captured by recipe-complete references/$id/reproduce/"
      reclaimable=$((reclaimable+1))
      if [ "$RECLAIM" = 1 ]; then
        if is_recipe_complete "$record" && ! has_inflight_process "$s" && ! sources_newer_than_record "$s" "$record" && ! holds_checkpoints "$s"; then
          rm -rf "$s" && echo "              -> reclaimed"
        else
          echo "              -> SKIPPED (state changed between check and delete)"
        fi
      fi
    elif has_disposition "$ref_dir" "$slug"; then
      echo "DISPOSITIONED $label: $DISPO"
      dispositioned=$((dispositioned+1))
    elif is_stale "$s"; then
      if [ -d "$record" ]; then why="record names a different attempt"; else why="no reproduce/ record"; fi
      echo "ORPHANED      $label: $why and no source touched in ${ORPHAN_DAYS}d; record a disposition"
      echo "                            (references_registry.py dispose $id $slug --decision ... --note ...) or promote it."
      orphaned=$((orphaned+1))
    else
      if [ -d "$record" ]; then why="record does not name this attempt"; else why="not promoted yet"; fi
      echo "PROTECTED     $label: $why (active work)"
      protected=$((protected+1))
    fi
  done
done

echo "gc_attempts: $reclaimable reclaimable, $protected protected, $orphaned orphaned, $dispositioned dispositioned"
[ "$orphaned" -gt 0 ] && echo "gc_attempts: orphaned workspaces need a disposition; --reclaim never touches them."
if [ "$RECLAIM" = 0 ] && [ "$reclaimable" -gt 0 ]; then
  echo "gc_attempts: dry run. Pass --reclaim to delete the reclaimable workspaces (their recipes are in reproduce/)."
fi
exit 0
