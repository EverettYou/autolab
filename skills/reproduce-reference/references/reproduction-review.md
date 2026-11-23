# Reproduction review checklist

The VERIFY gate: does the evidence support each major paper claim? Read and reason only: do not
execute code, rerun benchmarks, or fetch URLs. Apply it from a second agent session when possible;
when the implementer applies it, work only from the files on disk.

Inputs: `gate-state.yaml` claims, `result.json`, `ARCHITECTURE.md`, `REPRO-PLAN.md`, metrics in
`output/`, the paper summary or `PAPER-SPEC.md`, and `wiki/deadends/` for this reference.

Procedure:

1. Read in this order and record it: `gate-state.yaml`, `result.json`, `ARCHITECTURE.md`, metrics,
   paper summary, dead ends.
2. For each major claim: restate it falsifiably (code, distance, regime, metric, baseline), cite
   the evidence file and number, and mark it pass, fail, or inconclusive.
3. Score D1 to D6 (below) with a strength, a weakness, and a suggestion each.
4. List findings F01, F02, ... with severity (critical, major, minor) and a one-line fix.
5. Recommend:
   - Accept: every major claim passes, or passes partially with the cap honestly documented;
     suggest `verdict: reproduced` or `partial`.
   - Revise: a fixable gap (wrong regime wiring, under-training, a missing baseline row); give the
     improvement list for the next IMPLEMENT or RUN iteration.
   - Reject: the claim does not hold, or the gap is intrinsic.

| Dim | Name | Asks |
|-----|------|------|
| D1 | Evidence relevance | Does the result substantiate this specific claim? |
| D2 | Falsifiability | Could the claim have failed on our measurement? |
| D3 | Scope calibration | Does the claim match the regime actually run? |
| D4 | Baseline fairness | Paper-faithful comparison (same graph, noise, shots)? |
| D5 | Exploration honesty | Failures and caveats documented? |
| D6 | Methodological rigor | Logical error rates with shots and uncertainty; reproducible setup? |

Reject if any dimension scores 1, or D1, D3, or D4 score 2 or less. Accept only with no critical
or major findings and a mean of at least 4. Otherwise Revise.

Write `rigor-review.md` in the attempt workspace:

```markdown
# Reproduction review: <reference id> / <attempt>, <YYYY-MM-DD>

Regime demonstrated: ...
Suggested verdict: reproduced | partial | none
Read order: ...

## Claims
| ID | Claim | Evidence | Status | Notes |

## Dimension scores
| Dim | Score | Strength | Key weakness |

## Findings
| ID | Dim | Severity | Target | Suggested fix |

## Improvements for the next iteration (Revise only)
1. ...

## Recommendation
Accept | Revise | Reject: reason
```

Rules:

- Every major claim gets its own row.
- A regime mismatch fails the claim even when `status` is success.
- Reproduction compares against the paper, not against the platform roster; benchmarking is a
  separate evaluation.
