# Paper spec checklist

Build-from-paper stages EXTRACT and CONTRIBUTION. Deeper than the discovery paper summary: mine
the appendix, footnotes, and captions, and flag every unknown.

Inputs: `references/<id>/paper.pdf`, `paper.md` and `paper_struct/` in the attempt workspace,
the claims in `gate-state.yaml`, and `REPRO-PLAN.md`.

## EXTRACT: write `PAPER-SPEC.md`

```markdown
# Paper spec: <reference id>

## Metadata
Title: ...  Pages: N

## Algorithms
### <name> (section, page, Algorithm N)
Inputs: ...  Outputs: ...
Steps: ...
Equations: (eq N) ...

## Architecture
| Block | Role | Shapes or hints | Ref |
Data flow: ...

## Loss, metrics, training, evaluation
- Objective and hyperparameters (with refs), code family, distance, noise model, shots, baselines

## Figures and tables
| ID | Page | Type | Describes |

## Appendix and footnote findings
- ...

## Unknowns (do not invent)
- ...
```

## CONTRIBUTION: write `CONTRIBUTION.md`

```markdown
# Contribution: <reference id>

## One-sentence summary
## Paper type
architecture | training | inference | benchmark | theory+experiment, with justification
## Core contribution to implement
section refs
## Algorithm specification
the primary Algorithm box or equation set; discrepancies against the prose
## Official code
URL or none; framework; what it covers (verify the link belongs to this paper, see official_code.json)
## Scope
### Will implement
### Will reference (Stim, PyMatching, standard BP)
### Out of scope (baselines, ablations, infrastructure)
## Key sections
1. section: why it matters
```

Rules:

- Search the appendix, footnotes, and captions, not only the methods section.
- An unreadable or missing PDF stops the stage; never substitute the abstract.
- Record unknowns as unknowns; the ambiguity audit classifies them next.
