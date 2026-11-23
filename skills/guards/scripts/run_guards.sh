#!/usr/bin/env bash
# Run a bundle of repository guards and summarize pass/fail per check.
#
# Usage: bash skills/guards/scripts/run_guards.sh [BUNDLE] [--fail-fast] [--reclaim|--apply]
#   BUNDLE: all (default) | land | rules | labs | layout | references | reproduce | cited |
#           attempts | runtime | bench | fs | auto-research
#   --reclaim/--apply is passed to gc_attempts.sh (attempts bundle only); every other check is read-only.
# Exit: 0 all passed, 1 at least one check failed, 2 unknown bundle or flag.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
S="skills/guards/scripts"
PY="$(command -v python3 || command -v python)"
VPY="$ROOT/.venv/bin/python"; [ -x "$VPY" ] || VPY="$PY"   # checks that import the lab package

BUNDLE="all"; FAIL_FAST=0; RECLAIM=""
for arg in "$@"; do
  case "$arg" in
    --fail-fast) FAIL_FAST=1 ;;
    --reclaim|--apply) RECLAIM="--reclaim" ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    -*) echo "run_guards: unknown flag $arg" >&2; exit 2 ;;
    *) BUNDLE="$arg" ;;
  esac
done
if [ -n "$RECLAIM" ] && [ "$BUNDLE" != "attempts" ]; then
  echo "run_guards: --reclaim is only accepted with the attempts bundle" >&2; exit 2
fi

check_cmd() {  # name -> command line
  case "$1" in
    rules)      echo "$PY $S/rules_lint.py -q" ;;
    labs)       echo "$PY skills/organize-lab/scripts/labs_catalog.py check -q" ;;
    layout)     echo "$PY skills/organize-lab/scripts/labs_catalog.py validate -q" ;;
    references) echo "$PY skills/fetch-reference/scripts/references_registry.py validate" ;;
    reproduce)  echo "bash $S/reproduce_lint.sh" ;;
    # cited runs the full census: its existing failures were cleared 2026-09-29 (thread-130).
    cited)      echo "$PY $S/cited_results_lint.py -q" ;;
    attempts)   echo "bash $S/gc_attempts.sh $RECLAIM" ;;
    runtime)    echo "bash $S/runtime_claim_lint.sh" ;;
    bench)      echo "$PY $S/bench_selftest.py" ;;
    fs)            echo "$PY skills/auto-research/scripts/fs_health_lint.py" ;;
    auto-research) echo "$PY skills/auto-research/scripts/auto_research_lint.py" ;;
  esac
}

case "$BUNDLE" in
  all)        CHECKS=(rules labs layout references reproduce cited attempts runtime bench fs auto-research) ;;
  land)       CHECKS=(rules labs layout references reproduce cited auto-research) ;;
  rules|labs|layout|references|reproduce|cited|attempts|runtime|bench|fs|auto-research) CHECKS=("$BUNDLE") ;;
  *) echo "run_guards: unknown bundle '$BUNDLE'" >&2; sed -n '4,5p' "$0" >&2; exit 2 ;;
esac

declare -a SUMMARY=()
failed=0
for name in "${CHECKS[@]}"; do
  cmd="$(check_cmd "$name")"
  script="$(echo "$cmd" | awk '{print $2}')"
  if [ ! -f "$script" ]; then
    SUMMARY+=("SKIP  $name ($script not present)")
    continue
  fi
  echo "== $name: $cmd"
  $cmd
  rc=$?
  if [ "$rc" -eq 0 ]; then
    SUMMARY+=("PASS  $name")
  else
    SUMMARY+=("FAIL  $name (exit $rc)")
    failed=$((failed+1))
    [ "$FAIL_FAST" = 1 ] && break
  fi
  echo
done

echo "== run_guards $BUNDLE summary"
printf '%s\n' "${SUMMARY[@]}"
[ "$failed" -eq 0 ] || exit 1
exit 0
