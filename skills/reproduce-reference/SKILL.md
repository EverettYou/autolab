---
name: reproduce-reference
description: Reproduce the claims of an archived reference (paper, repository, or dataset) in an isolated attempt workspace under `references/<id>/attempts/<slug>/`, verify them claim by claim, and promote an accepted attempt to the tracked record `references/<id>/reproduce/`.
usage: Use when a fetched reference should be tested before anything builds on it.
---

# Reproduce a reference

Reproduction asks one question: do the paper's own claims hold in the paper's own regime? It
compares against the paper, not against later lab arenas or package peers, and it does
not port code into the package (that is `promote-to-lib`).

Workspaces and records:

- `references/<id>/attempts/<slug>/` is an untrusted, gitignored workspace: code, `run.sh`,
  `output/`, `result.json`, `gate-state.yaml`, plans, reviews. Name the first attempt after the
  reference id and later ones `<id>-<purpose>`.
- `references/<id>/reproduce/` is the tracked verified record, written only by
  `scripts/promote_attempt.sh` after an accepted review.

Before starting, query the wiki for this reference (dead ends, prior claims, related pages):

```bash
.venv/bin/python skills/wiki-query/scripts/query_wiki.py "<reference-id or topic>"
```

Do not retry a dead end unless its "Revisit if" condition is now met.

## Loop

PLAN, IMPLEMENT, RUN, VERIFY, then loop back or PROMOTE. Keep the state in
`references/<id>/attempts/<slug>/gate-state.yaml`, created at PLAN and updated at every transition:

```yaml
reference: <id>
attempt: <slug>
iteration: 1
phase: plan                  # plan | implement | run | verify | promote | rejected
implementation_mode: null    # run-the-repo | build-from-paper
self_test: null              # pass | fail (build-from-paper only)
claims:
  - id: C1
    text: "<falsifiable claim: code, distance, regime, metric, baseline>"
    status: pending          # pending | pass | fail | inconclusive
rigor_recommendation: null   # Accept | Revise | Reject, set by VERIFY
verdict: null                # reproduced | partial, set on Accept
last_improvements: []        # from a Revise review
```

### PLAN

1. Create the workspace and record it:
   `mkdir -p references/<id>/attempts/<slug>` then
   `python3 skills/fetch-reference/scripts/references_registry.py sync <id>`.
2. Choose `implementation_mode`:
   - `run-the-repo` when `references/<id>/repos/` has usable code (map large repositories with
     [references/code-map.md](references/code-map.md));
   - `build-from-paper` when only the paper exists and the method must be rebuilt from the text.
3. Extract the major falsifiable claims (paper summary, `PAPER-SPEC.md`, or the repository
   README) into `claims`.
4. Write `REPRO-PLAN.md`: mode, regime, metrics, and a claim-to-experiment map. Set `phase: implement`.

### IMPLEMENT

The goal is a runnable workspace, not yet claim verification.

- run-the-repo: copy or symlink the needed upstream files from `references/<id>/repos/<name>/`
  into the workspace, follow the upstream README, add thin wrappers only where needed (`run.sh`,
  pinned dependencies), and document entry points, regime, and the claim-to-script map in
  `ARCHITECTURE.md`.
- build-from-paper: follow [references/build-from-paper.md](references/build-from-paper.md)
  end to end, including its self-test and handoff checklist.

`run.sh` receives the output directory as its first argument. When the workspace is ready, set
`phase: run`. Blocked by the dead-end criteria, set `phase: rejected` (see Reject below).

### RUN

1. Resolve the runtime now, not earlier: follow `runtime-env` for this machine. Untrusted code
   runs only in the isolated runtime it describes.
2. Execute under the wall-clock cap:

   ```bash
   bash skills/reproduce-reference/scripts/run_attempt.sh <id> <slug> [timeout_seconds]
   ```

   The default cap is the 30-minute smoke limit. For a queued time tier use
   `min(2 * $(bash skills/guards/scripts/parse_time.sh <tier>), cap)`. GPU training runs
   detached for at most 2 days, and only on a GPU.

   **This command is the sanctioned path.** If a tool permission classifier rejects it as
   `code_from_external` (or similar), follow
   [references/tool-permission-denials.md](references/tool-permission-denials.md): record why,
   point at this path, do not bypass isolation, do not re-ask whether external code may run in
   isolation, and unblock via the allow-rule / human `!` remedy there. After `output/` exists,
   continue VERIFY or the lab compare step.
3. Before any real training, pass the efficiency gate: a warmed training step takes at most 0.2 s
   on one GPU, a numeric ETA is recorded, training writes a flushed loss log at least every 10
   minutes, and loss decay is checked against the ETA with an early stop on saturation (`AGENTS.md`,
   `wiki/models/gpu-training-protocol.md`). Prefer released weights plus
   evaluation over training from scratch.
4. `result.json` records the mechanical `status` only; `verdict` stays `unevaluated`.
   - failed from the environment: fix it and stay in RUN;
   - failed from the implementation: increment `iteration`, set `phase: implement`;
   - timeout: record it in `REPRO-PLAN.md` and split the step or raise the tier;
   - success: set `phase: verify`.

### VERIFY

Apply [references/reproduction-review.md](references/reproduction-review.md), preferably from a
second agent session, and save the result as `rigor-review.md` in the workspace. Copy the
recommendation and per-claim status into `gate-state.yaml`.

- Revise: copy the improvements into `last_improvements`, increment `iteration`, and return to
  IMPLEMENT (code fixes) or RUN (scale or rerun only).
- Reject: set `phase: rejected`, write `wiki/dead-ends/<id>.md` through `wiki-ingest` (what was
  tried, why it failed, "Revisit if"), set the reference status with
  `references_registry.py set <id> --status failed`, and record the attempt with
  `references_registry.py dispose <id> <slug> --decision dead-end --note "<reason>"`.
- Accept: set `verdict` in `result.json` to `reproduced` or `partial` as the review suggests,
  set `phase: promote`.

### PROMOTE

```bash
bash skills/reproduce-reference/scripts/promote_attempt.sh <id> <slug>
```

The script refuses unless `result.json` is `status: success` with verdict `reproduced` or
`partial` and `gate-state.yaml` says `rigor_recommendation: Accept`. It copies the workspace
without virtualenvs, git metadata, or bytecode into `references/<id>/reproduce/`, renames
`result.json` to `RESULT.json`, refuses files over 100 MB, and updates `provenance.json`
(`reproduction`, `status`) and `references/references.json`. An existing record is only merged
with `--update`.

Then:

1. Add a short `references/<id>/reproduce/README.md` if the attempt lacks one: what was run, the
   regime, the verdict, and how to rerun (`rehydrate.sh`, then `run_attempt.sh`).
2. Write or update the model page (`wiki/models/`) or algorithm page (`wiki/algorithms/`) for the
   reference through `wiki-ingest`, citing `references/<id>/reproduce/`. A discovery alone never
   creates such a page; an accepted reproduction does.
3. Commit the record, `provenance.json`, and `references/references.json` with explicit paths.
4. If the method deserves a place in the package, queue `promote-to-lib` in the task list.

To rerun a promoted reproduction, unfold it into a new workspace:
`bash skills/reproduce-reference/scripts/rehydrate.sh <id> <new-slug>`.

## Rules

- Trust zones are in `wiki/project/distillation-tower.md`. Reproduction never writes
  `lib/`; the package re-implements from the evidence through `promote-to-lib`.
- Keep expensive artifacts: rescue weights and configs, never delete them mid-loop. Weights worth
  keeping stay in the attempt workspace (or a cited lab `checkpoints/` path) until promoted
  evidence no longer needs them.
- `partial` is a valid verdict when the direction of the claim holds under the compute cap and the
  gap is documented.
- Attempt workspaces are cleaned only by `skills/guards/scripts/gc_attempts.sh`, which protects
  anything not captured in the record.
- No secrets in workspaces, logs, or records.

## References

| File | Use |
|------|-----|
| [references/build-from-paper.md](references/build-from-paper.md) | IMPLEMENT pipeline when there is no code |
| [references/paper-spec.md](references/paper-spec.md) | EXTRACT and CONTRIBUTION |
| [references/ambiguity-audit.md](references/ambiguity-audit.md) | AUDIT before any code |
| [references/implementation-plan.md](references/implementation-plan.md) | PLAN and REFINE |
| [references/module-build.md](references/module-build.md) | BUILD one module |
| [references/module-review.md](references/module-review.md) | REVIEW one module |
| [references/code-map.md](references/code-map.md) | Map a foreign repository |
| [references/reproduction-review.md](references/reproduction-review.md) | VERIFY claims |
| [references/guardrails.md](references/guardrails.md), [references/ambiguity-checklist.md](references/ambiguity-checklist.md) | Anti-hallucination rules and EM traps |
| [references/tool-permission-denials.md](references/tool-permission-denials.md) | When auto mode blocks `run_attempt.sh`: reason + sanctioned remedy |
