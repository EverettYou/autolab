# Implementation plan checklist

Build-from-paper stages PLAN (draft) and REFINE (critique). Plan only; no code.

Inputs: `PAPER-SPEC.md`, `CONTRIBUTION.md`, `REPRODUCTION-NOTES.md`, `FIGURES.md`,
`REPRO-PLAN.md`, the claims in `gate-state.yaml`; on refine also the draft plan,
`configs/base.yaml`, and [guardrails.md](guardrails.md).

## Draft: write `IMPLEMENTATION-PLAN.md` and `configs/base.yaml`

```markdown
# Implementation plan: <reference id> / <attempt>

## Goal
one paragraph: a runnable smoke path plus the claim metrics

## Modules
| ID | Name | Responsibility | Depends on | Tests |

## Interfaces
### <module-id>
- Public API: ...
- Files to create: ...

## Execution paths
### Smoke (at most 30 minutes)
### Eval (claim metrics)

## Assumptions
- ASSUMPTION: paper gap -> choice

## Risks
| Risk | Mitigation |

## Build order
1. Layer 0: utils
2. Layer 1: data and syndrome sampling
3. Layer 2: model, loss
4. Layer 3: train, evaluate

## Config
every key in configs/base.yaml cites a section or is marked [UNSPECIFIED] in a comment

## Implementation checklist
- [ ] Module A
```

Start `configs/base.yaml` from `templates/configs/base.yaml`. Set `implementation_mode:
build-from-paper` and list the modules in `gate-state.yaml`.

## Refine: append to the plan

```markdown
## Refine checklist
- [ ] claim C1 -> metric artifact: ...
## Changes from draft
## Blockers
```

Rules:

- Use the smallest module count that still allows independent work (usually 3 to 8).
- Every claim in `gate-state.yaml` maps to an evaluation artifact.
- If the paper releases weights, the smoke path must not require full training; name the path.
- The module list is frozen after REFINE. Two failed refinements on the same gap is a dead end.
