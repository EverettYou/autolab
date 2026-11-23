---
name: promote-lib
description: Enable the shared package under lib/ when needed, then re-implement a validated approach in lib/src/<package>/ with tests and fidelity evidence - from an accepted reproduction, a published construction, or a lab capability - and record the promotion.
usage: Use when references/<id>/reproduce/ or a lab result justifies a place in the package, including the first time the repository needs lib/ turned on.
---

# Promote lib

The shared package under `lib/src/<package>/` is the trusted core once enabled. Code enters it only
through this gate: re-implemented from the evidence, tested, verified, and recorded. Never import
or copy from `references/` or `labs/`. Rules: `wiki/system/distillation-tower.md` and
`wiki/system/shared-package.md`. Layout: `lib/README.md`.

Entering this skill (or `for: integrator`) means the project needs that package. If `lib/` is not
enabled yet, **bootstrap it in this skill** before PLAN/BUILD — that is success for the tick, not a
failed promote. Only `promote-lib` / `integrator` turns `features.lib` on.

| Kind | Source of evidence | VERIFY gate |
|------|--------------------|-------------|
| `algorithm` | `references/<id>/reproduce/` (accepted reproduction) | port alignment: package code against the reproduced source, same setting, by the agreed metric |
| `solver-family` | the published construction named in the plan | construction fidelity: bit-exact or numerically matched primitives against an independent source; alignment may be N/A |
| `lab-capability` | a lab's recorded outputs (`labs/<id>/`) | behavior equivalence: the package code reproduces the lab's recorded numbers on the same inputs and seeds |

Reproduction review is not a gate here (claims were settled in `reproduce-reference`).
Comparable arena numbers, when needed, stay in the lab that produced them and cite from
`REPORT.md` / the wiki — they do not gate VERIFY.

Preconditions: for an algorithm, `references/<id>/reproduce/` exists. If it does not, queue
`reproduce-reference` instead of declaring the promotion blocked. Before PLAN, query the wiki for
the target and dead ends:

```bash
.venv/bin/python skills/wiki-query/scripts/query_wiki.py "<id or package target>"
```

## Bootstrap `lib/` (when off or empty)

Skip this section when `config.yml` already has `features.lib: true`, a `package: <name>`, and
`lib/src/<name>/` imports cleanly.

1. **Choose `package`.** A legal Python identifier (short, lowercase, no hyphens). Prefer a name
   already implied by the task, lab, or project title. If several fit or none is obvious, ask once
   through `thread-interaction` and wait — do not invent a contested name.
2. **Enable in `config.yml`:** set `features.lib: true` and `package: <name>`.
3. **Scaffold:**
   - `lib/src/<name>/__init__.py` (empty or a one-line docstring);
   - set `[project] name` in `lib/pyproject.toml` to the import name (and Hatch package discovery
     for `src/<name>` when the file requires it — see `lib/README.md`);
   - keep `lib/tests/` as the flat pytest root.
4. **Install and smoke:** run `skills/runtime-env` / `setup_venv.sh` so the editable `lib/` install
   matches config; confirm `.venv/bin/python -c "import <name>"`.
5. **Stop or continue.** If this tick only bootstrapped, log that, leave the integrator task open
   for PLAN next tick, and land `config.yml` + `lib/`. Bootstrap incomplete ≠ promote failure.

## Gate state

Track the loop in `wiki/records/integrations/<id>-gate.yaml` (stable across iterations):

```yaml
reference: <id>              # or the lab id for a lab-capability
kind: algorithm              # algorithm | solver-family | lab-capability
iteration: 1
phase: plan                  # plan | build | verify | promote | done | failed
package_target: <module or class>
align_verdict: null          # PASS | REVISE | FAIL | N/A
checks: []                   # named fidelity checks: {id, name, status}
last_improvements: []
```

## PLAN

1. Read the evidence: `references/<id>/reproduce/` (`RESULT.json`, README, recipe, regime), the
   construction sources, or the lab report and its result files.
2. Map the source with `skills/reproduce-reference/references/code-map.md`; rehydrate a runnable
   copy with `skills/reproduce-reference/scripts/rehydrate.sh <id> <slug>` when you need live
   outputs.
3. Survey the package: sibling modules under `lib/src/<package>/`, base helpers to reuse, and any
   `wiki/models/` or `wiki/algorithms/` pages.
4. Write `wiki/records/integrations/<id>-INTEGRATION-PLAN.md`: source to package mapping;
   interface and data compatibility; honesty label (`sota`, `diversity`, or `reproduced`).
5. Set `phase: build`.

## BUILD

1. Implement under `lib/src/<package>/` with tests in `lib/tests/` (flat `test_<topic>.py`).
   Consolidate shared bases instead of duplicating them. No compatibility aliases; renames are hard.
2. Run `.venv/bin/pytest lib/tests -q`. It must pass before VERIFY. On failure, fix,
   increment `iteration`, and rerun.
3. Set `phase: verify`.

## VERIFY

- algorithm: apply [references/alignment-check.md](references/alignment-check.md). Save its JSON
  under the lab or `wiki/records/integrations/`, and copy the verdict and checks into the gate.
- solver-family: do not invent end-to-end task rows. Set `align_verdict: N/A` with the reason when
  appropriate, and prove construction fidelity against an independent source (published matrices
  or a second derivation), never expectations produced only by the code under test.
- lab-capability: rerun the lab's recorded measurement through the package on the same inputs and
  seeds, and compare outcomes or recorded numbers; any difference must be explained.

On REVISE or FAIL, list the fixes in `last_improvements`, increment `iteration`, set
`phase: build`, and return to BUILD. Do not land on an unexplained FAIL. On PASS, set
`phase: promote`.

## PROMOTE

1. Document: update or create the relevant `wiki/algorithms/` or `wiki/models/` page, an
   `implementations/` map if useful, and wiki manual pages for new public APIs.
2. Record the promotion in `wiki/records/integrations/` and set `phase: done`.
3. Land through `skills/git-workflow` with explicit paths under `lib/`, `wiki/`, `config.yml` when
   bootstrap changed it, and any lab evidence cited by the gate.
4. Queue a follow-up task `for: auditor` citing the integration record.

## See also

- [references/alignment-check.md](references/alignment-check.md)
- `lib/README.md`
- `skills/audit-lib/SKILL.md`
- `skills/runtime-env/SKILL.md`
