---
name: guards
description: Mechanical repository invariant checks - governing-doc rules, lab and reference catalogs, reproduction records, attempt workspace cleanup, runtime claims, and the microbenchmark instrument - run as bundles before committing or during maintenance.
usage: Use before landing changes to governed files, after reproduction changes, and for periodic cleanup.
---

# Guards

Mechanical checks that invariants hold. Every check is read-only except `gc_attempts.sh --reclaim`.
Run from the repository root, either one script or a bundle:

```bash
bash skills/guards/scripts/run_guards.sh            # all read-only checks
bash skills/guards/scripts/run_guards.sh land       # before committing governed files
bash skills/guards/scripts/run_guards.sh attempts   # attempt cleanup report (dry run)
```

## Checks

| Check | Script | Invariant | Run when |
|-------|--------|-----------|----------|
| rules | `scripts/rules_lint.py` | README.md, AGENTS.md, and `skills/` are tool-agnostic, use the current layout, carry no emojis, and every skill has valid frontmatter and a catalog row in `skills/README.md` (lint scripts may name what they forbid; a line containing `rules-lint: allow` is skipped) | after editing README.md or any skill |
| labs | `skills/organize-lab/scripts/labs_catalog.py check` | every `labs/*/lab.json` is valid and `labs/labs.json` is current | after lab changes |
| layout | `skills/organize-lab/scripts/labs_catalog.py validate` | every lab matches the layout: only the four root files, known directories, and each file in the directory its type belongs to (figures in `figures/`, documents in `notes/`, logs in `logs/`, arrays in `data/`); fix with `lab_layout.py tidy` | after lab changes |
| references | `skills/fetch-reference/scripts/references_registry.py validate` | every `references/*/provenance.json` agrees with disk and `references/references.json` is current | after fetching, reproducing, or promoting |
| reproduce | `scripts/reproduce_lint.sh` | every `references/*/reproduce/` has `RESULT.json` and a recipe or marker; cited attempt files survive in the record (attempt files only) | after `promote_attempt.sh`, before committing records |
| cited | `scripts/cited_results_lint.py` | every `results/...json` path quoted in the wiki, labs, reproduction records, task bodies, tasks, and threads resolves (literal, doc-relative, relocated, or pinned as `<commit>:<path>`); a missing result is counted, never a failure (results are gitignored by design; thread-009, 2026-10-13), and only a pin to a commit that lacks the file FAILs. `reproduce_lint` covers attempt-file cites only; this covers result-file cites | after editing prose that cites results |
| attempts | `scripts/gc_attempts.sh` | attempt workspaces are deleted only when captured by a recipe-complete record | periodic cleanup |
| runtime | `scripts/runtime_claim_lint.sh` | GPU utilization claims in `wiki/records/synthesis/` cite a runtime snapshot (warn-only) | before landing synthesis records |
| bench | `scripts/bench_selftest.py` | the timing instrument itself (fixture self-test); labs import it to time the same work two ways | before publishing a microbenchmark ratio |
| fs | `skills/auto-research/scripts/fs_health_lint.py` | the top-level paths retired by the 2026-09-26 layout (listed in the script) stay gone, tool folders hold no tracked files, and `lib/` holds source code only | during a supervisor tick, and after moving directories |
| auto-research | `skills/auto-research/scripts/auto_research_lint.py` | `.auto-research/state.json`, `tasks/`, and `threads/` match `.auto-research/README.md` (missing/unexpected keys, enums, ids, orphans); prints path + reason per finding | before landing loop/Threads changes; during a supervisor tick |
| time tiers | `scripts/parse_time.sh <tier>` | task list time tier to seconds, for the `min(2 * tier, cap)` run cap | before setting a reproduction timeout |

## Bundles

| Bundle | Checks |
|--------|--------|
| `all` (default) | rules, labs, layout, references, reproduce, cited, attempts (dry run), runtime, bench, fs, auto-research |
| `land` | rules, labs, layout, references, reproduce, cited, auto-research |
| any single check name | that check |

`--fail-fast` stops at the first failure. Checks whose script is absent are reported as SKIP.

`cited` runs in full in the bundles. It first ran changed-only (`--changed`, still available) until
the failures that predated it were cleared on 2026-09-29 (discussion thread-130): a file deleted on
purpose is cited as `<commit>:<path>` from a commit that still holds it, and a file that was never
preserved keeps its citation with `<!-- lost-citation -->` on the same line.

## Attempt cleanup

`gc_attempts.sh` reports each `references/<id>/attempts/<slug>/`:

- RECLAIMABLE: `references/<id>/reproduce/` is recipe-complete and its `RESULT.json` names this
  attempt (`attempt`, or the legacy `slug`, exactly or by an unambiguous `-suffix` match), with no
  checkpoints, `.gc-keep`, running process, or newer sources;
- PROTECTED: checkpoints or `.gc-keep`, a live process, sources newer than the record, or active
  work not captured by the record;
- DISPOSITIONED: a recorded decision in `provenance.json` (`references_registry.py dispose`) or a
  row in `wiki/implementations/attempt-dispositions.md`; never reclaimed;
- ORPHANED: not captured and untouched for `GC_ORPHAN_DAYS` (default 14); needs a disposition.

It deletes nothing unless given `--reclaim` (alias `--apply`), and re-checks each workspace just
before deleting it.

## Exit codes

`0` pass (warnings allowed), `1` hard failure (fix before committing), `2` usage or tool error.

After changing a guard, run its tests (temporary repositories only, including a real `--reclaim`):
`python3 -m unittest discover -s skills/guards/tests`.

## Related skills

- `git-workflow`: run the `land` bundle before `land.sh` when governed files changed.
- `reproduce-reference`: `reproduce_lint.sh` after promotion; `gc_attempts.sh` for cleanup.
- `auto-research`: the supervisor tick runs the `all` bundle.
