#!/usr/bin/env bash
# reproduce_lint.sh: guard the verified reproduction records references/<id>/reproduce/.
#
# Recipe tier. Attempt workspaces (references/<id>/attempts/) are gitignored, so a record that holds only
# a RESULT.json loses its recipe when the workspace is cleaned. A reproduce/ record is OK iff it has
#   (a) RESULT.json (a lowercase result.json means it bypassed promote_attempt.sh), and
#   (b) a recipe (run.sh, run.py, run_*.py, repro*.py, arena*.py, or any *.sh), or an explicit marker
#       (RECIPE-STATUS.md for recipe-lost/restoration-pending, SUPERSEDED.md).
#
# Reference-resolution tier. "Recipe present" never checks the paths a record cites. Each cited path
# is reported RESOLVES / DANGLING-RENAMED (a same-named file exists inside the record, or archived_as
# maps it) / DANGLING-GONE. Only one class hard-fails: a cited recipe or code file under
# references/<id>/attempts/ with no counterpart in the record and not declared in missing_artifacts,
# because that is the file lost when the workspace goes. Cites that resolve only because an untracked
# attempt still exists on this machine are counted as local-only; --strict fails those too.
#
# Usage: bash skills/guards/scripts/reproduce_lint.sh [--strict]
# Exit 0 = clean (warnings allowed); 1 = thin or undocumented record, or unrecoverable dangling cite.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STRICT=0
case "${1:-}" in
  --strict) STRICT=1 ;;
  "") ;;
  *) echo "usage: reproduce_lint.sh [--strict]" >&2; exit 2 ;;
esac
[ -d "$ROOT/references" ] || { echo "reproduce_lint: no references/ directory"; exit 0; }

fail=0 pending=0 ok=0 empty=0
for d in "$ROOT"/references/*/reproduce/; do
  [ -d "$d" ] || continue
  id="$(basename "$(dirname "$d")")"
  if [ -z "$(ls -A "$d" 2>/dev/null)" ]; then
    echo "WARN     $id: empty reproduce/ (treated as no record; remove it)"; empty=$((empty+1)); continue
  fi
  if [ ! -f "$d/RESULT.json" ]; then
    if [ -f "$d/result.json" ]; then
      echo "FAIL     $id: lowercase result.json but no RESULT.json; the record bypassed promote_attempt.sh."
      echo "                 Rename it to RESULT.json."
    else
      echo "FAIL     $id: no RESULT.json; a record without a result is an ungated promotion."
    fi
    fail=$((fail+1)); continue
  fi
  recipe=""
  for f in "$d"run.sh "$d"run.py "$d"run_*.py "$d"repro*.py "$d"arena*.py "$d"*.sh; do
    [ -e "$f" ] && { recipe="$(basename "$f")"; break; }
  done
  marker=""
  for m in RECIPE-STATUS.md SUPERSEDED.md; do [ -f "$d$m" ] && marker="$m"; done
  if [ -n "$recipe" ]; then
    ok=$((ok+1))
  elif [ -n "$marker" ]; then
    echo "PENDING  $id: RESULT.json only, $marker present (restoration pending)"; pending=$((pending+1))
  else
    echo "FAIL     $id: RESULT.json only, no recipe and no RECIPE-STATUS.md or SUPERSEDED.md marker"; fail=$((fail+1))
  fi
done
echo "reproduce_lint: $ok recipe-complete, $pending pending (marked), $fail failing, $empty empty"

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "reproduce_lint: WARN no python; skipping the reference-resolution tier"
else
  "$PY" - "$ROOT" "$STRICT" <<'PYEOF'
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
strict = sys.argv[2] == "1"
CURRENT = ("references", "labs", "lib", "wiki", "skills", "documents", "dashboard", "notes")
LEGACY = ("sandbox", "archive", "lab", "projects", "notes", "inbox")
PATH_RE = re.compile(r"(?:^|[\s\"'`=,(])((?:%s)/[A-Za-z0-9_./\-]+)" % "|".join(CURRENT + LEGACY))
HARD_SUFFIXES = {".py", ".sh", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".rst"}
SOFT_DIR_HINTS = ("/results/", "/checkpoints/", "/output/", "/logs/", "/__pycache__/", "/.venv/")
WEIGHT_SUFFIXES = {".pt", ".ckpt", ".safetensors", ".npy", ".npz", ".h5"}
ATTEMPT_RE = re.compile(r"^references/[^/]+/attempts/")

counts = dict(resolves=0, local_only=0, renamed=0, legacy=0, warn=0, declared=0, fail=0, cites=0)
records_citing = 0


def walk_strings(obj, out):
    if isinstance(obj, dict):
        for value in obj.values():
            walk_strings(value, out)
    elif isinstance(obj, list):
        for value in obj:
            walk_strings(value, out)
    elif isinstance(obj, str):
        for match in PATH_RE.finditer(obj):
            out.append(match.group(1).rstrip(".,;:)'\""))


def record_basenames(record: Path) -> dict:
    found = {}
    for path in record.rglob("*"):
        if path.is_file() and path.name != "RESULT.json":
            found.setdefault(path.name, str(path.relative_to(record)))
    return found


for result in sorted(root.glob("references/*/reproduce/RESULT.json")):
    record = result.parent
    ref_id = record.parent.name
    try:
        data = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FAIL     {ref_id}: RESULT.json unreadable: {exc}")
        counts["fail"] += 1
        continue
    cited = []
    walk_strings(data, cited)
    archived_as = data.get("archived_as") or {}
    declared = data.get("missing_artifacts") or []
    declared_names = {Path(str(m)).name for m in declared}
    if not cited and not declared:
        continue
    records_citing += 1
    names = record_basenames(record)
    seen = set()
    for rel in cited:
        if rel in seen:
            continue
        seen.add(rel)
        counts["cites"] += 1
        in_attempt = bool(ATTEMPT_RE.match(rel))
        base = Path(rel).name
        suffix = Path(rel).suffix.lower()
        soft = any(h in rel for h in SOFT_DIR_HINTS) or suffix in WEIGHT_SUFFIXES
        hard = not soft and suffix in HARD_SUFFIXES and not rel.endswith("/")
        remap = archived_as.get(rel)
        if remap and (record / remap).exists():
            print(f"DANGLING-RENAMED  {ref_id}: {rel} -> archived_as:{remap}")
            counts["renamed"] += 1
            continue
        if (root / rel).exists():
            if in_attempt and hard and base not in names:
                counts["local_only"] += 1
                if strict:
                    print(f"LOCAL-ONLY(FAIL)  {ref_id}: {rel} resolves only in the untracked attempt; copy it into the record")
                    counts["fail"] += 1
            else:
                counts["resolves"] += 1
            continue
        if base in names:
            print(f"DANGLING-RENAMED  {ref_id}: {rel} -> references/{ref_id}/reproduce/{names[base]}")
            counts["renamed"] += 1
            continue
        if rel.split("/", 1)[0] in LEGACY:
            print(f"LEGACY-PATH(warn)  {ref_id}: {rel} (retired layout; rewrite to the current path)")
            counts["legacy"] += 1
            continue
        if not hard:
            print(f"DANGLING-GONE(warn)  {ref_id}: {rel}")
            counts["warn"] += 1
            continue
        if rel in declared or base in declared_names:
            print(f"DANGLING-GONE(declared)  {ref_id}: {rel} (named in missing_artifacts)")
            counts["declared"] += 1
            continue
        if not in_attempt:
            print(f"DANGLING-GONE(warn)  {ref_id}: {rel} (tracked path moved or removed; fix the cite)")
            counts["warn"] += 1
            continue
        print(f"DANGLING-GONE(FAIL)  {ref_id}: {rel} (no copy in the record; add archived_as or missing_artifacts)")
        counts["fail"] += 1
    for missing in declared:
        print(f"MISSING-DECLARED  {ref_id}: {missing}")

print(
    f"reproduce_lint refs: {records_citing} records cite paths; {counts['resolves']} RESOLVES, "
    f"{counts['local_only']} local-only (untracked attempt), {counts['renamed']} DANGLING-RENAMED, "
    f"{counts['legacy']} LEGACY-PATH, {counts['warn'] + counts['declared']} DANGLING-GONE(warn/declared), "
    f"{counts['fail']} FAIL over {counts['cites']} unique cites"
)
sys.exit(1 if counts["fail"] else 0)
PYEOF
  [ $? -eq 0 ] || fail=$((fail+1))
fi

if [ "$fail" -ne 0 ]; then
  echo "reproduce_lint: FAIL. Add a recipe (promote_attempt.sh copies it), a RECIPE-STATUS.md marker, fix the"
  echo "RESULT.json casing, or declare (missing_artifacts) or remap (archived_as) unrecoverable cites."
  exit 1
fi
echo "reproduce_lint: OK"
