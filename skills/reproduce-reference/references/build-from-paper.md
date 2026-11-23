# Build from paper

The IMPLEMENT path for a learned EM method (neural, GNN, transformer, diffusion) that has a paper
but no usable code. Classical algorithmic solvers use packages through run-the-repo, or become
study-only; they do not come here.

Goal: a runnable attempt workspace (`run.sh`, `src/`, `configs/base.yaml`,
`REPRODUCTION-NOTES.md`, passing self-test). Claim verification happens later in VERIFY.

Read [guardrails.md](guardrails.md) and [ambiguity-checklist.md](ambiguity-checklist.md)
before REFINE and BUILD.

```text
TEXT -> STRUCTURE -> CODE-LINKS -> EXTRACT -> CONTRIBUTION -> AUDIT -> FIGURES -> PLAN -> REFINE -> BUILD -> REVIEW -> ASSEMBLE -> SELF-TEST -> HANDOFF
```

In the commands below, `S=skills/reproduce-reference/scripts`, `R=references/<id>`, and
`W=references/<id>/attempts/<attempt>`.

| Stage | How | Artifacts in `W` |
|-------|-----|------------------|
| TEXT | `python3 $S/extract_paper_text.py $R/paper.pdf $W/paper.md` | `paper.md` |
| STRUCTURE | `python3 $S/extract_structure.py $W/paper.md $W/paper_struct` | `paper_struct/` |
| CODE-LINKS | `python3 $S/find_official_code.py $W/paper.md $W/official_code.json --reference-dir $R` | `official_code.json` |
| EXTRACT | [paper-spec.md](paper-spec.md), extract part | `PAPER-SPEC.md` |
| CONTRIBUTION | [paper-spec.md](paper-spec.md), contribution part | `CONTRIBUTION.md` |
| AUDIT | [ambiguity-audit.md](ambiguity-audit.md) | `REPRODUCTION-NOTES.md` |
| FIGURES | `python3 $S/render_figures.py $R/paper.pdf $W/figures --pages <from PAPER-SPEC>` | `figures/`, `FIGURES.md` |
| PLAN | [implementation-plan.md](implementation-plan.md), draft | `IMPLEMENTATION-PLAN.md`, `configs/base.yaml` |
| REFINE | [implementation-plan.md](implementation-plan.md), refine | updated plan, frozen module list |
| BUILD | `bash $S/copy_scaffolds.sh <id> <attempt>` (optional), then [module-build.md](module-build.md) per module | `src/`, `tests/` |
| REVIEW | [module-review.md](module-review.md) per module | `reviews/` |
| ASSEMBLE | write `run.sh` (`--smoke` from `smoke.*`, `--eval` for the paper regime) and `ARCHITECTURE.md` (modules, regime, claim map) | `run.sh`, `ARCHITECTURE.md` |
| SELF-TEST | pytest plus a smoke forward pass | `output/self_test.json`, `SELF-TEST.md`, `self_test: pass` |

Notes:

- `extract_paper_text.py` uses PyMuPDF with a pypdf fallback; agents read `paper_struct/`
  (algorithms, equations, tables, footnotes) instead of all of `paper.md` where possible.
- CODE-LINKS is a pivot check. If `official_code.json` reports `pivot_run_the_repo: true`, verify
  the link belongs to this paper, archive it with `fetch-reference repo`, set
  `implementation_mode: run-the-repo`, and stop this pipeline. Broken or placeholder links are
  noted in `CONTRIBUTION.md` and the pipeline continues.
- Resolve figure-against-text conflicts in `REPRODUCTION-NOTES.md` before PLAN.
- Do not resolve the runtime environment during this pipeline; that happens at RUN.

Handoff checklist (then set `phase: run`):

- [ ] `paper_struct/`, `CONTRIBUTION.md`, `REPRODUCTION-NOTES.md`, `IMPLEMENTATION-PLAN.md`
- [ ] `configs/base.yaml`, `run.sh`, `ARCHITECTURE.md`
- [ ] `self_test: pass` in `gate-state.yaml`
- [ ] no `result.json` yet

Dead end: two failed refinements, two failed reviews on the same gap, or an audit that cannot
specify the core solver. Set `phase: rejected` and write the dead-end page (see the skill).
