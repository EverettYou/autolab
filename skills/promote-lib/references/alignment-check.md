# Port alignment checklist

The VERIFY gate for promoting an algorithm: does the lib package port track the reproduced source on
the matched setting? It is judged relatively (curve and direction), not against the state of the
art. The same agent or a second session can apply it; it may run the package but must not edit
`lib/src/` while checking.

Inputs: the reference id (`references/<id>/reproduce/` must exist), `lib_target` from the
gate, an optional tolerance on the agreed metric ratio (default depends on the metric; for error
metrics a geometric-mean ratio in `[0.5, 2]` is a starting point), and optionally a live source run
from a rehydrated attempt.

Procedure:

1. Anchor: read `RESULT.json` for setting, data regime, metric anchors, source numbers, seeds.
2. Rebuild the setting in the package: the same data factory, feature map, regularization, and
   qubit budget when relevant.
3. Run the lib target at each anchor, with enough samples for a meaningful comparison where a
   ratio is quoted.
4. Optionally run the rehydrated source on identical inputs
   (`skills/reproduce-reference/scripts/rehydrate.sh`, then `run_attempt.sh`).
5. Compute the per-anchor ratio `metric_package / metric_source` (define orientation so that 1.0
   means match) and a summary statistic (geometric mean when ratios are positive).
6. Verdict:
   - PASS: within tolerance and not worse at every anchor in the agreed sense. For directional
     sources (for example faster but weaker), PASS requires the same direction on the package, not
     an identical number.
   - REVISE: a fixable port gap (wiring, numerics, streaming contract), with an improvement list.
   - FAIL: unexplained divergence, or not alignable (missing record: queue a reproduction).

Output (the promoter saves the JSON under `wiki/records/integrations/` or the source lab, and
copies the verdict into the gate):

```markdown
## Port alignment: <id>

Lib target: ...
Evidence: references/<id>/reproduce/
Setting: ...
Tolerance: ...

### Checks
| ID | Check | Status | Notes |
| A1 | metric ratio at ... | pass/fail | ... |

### Per anchor
| factor | source | package | ratio | notes |

Summary ratio: ...
Verdict: PASS | REVISE | FAIL | not alignable

### Improvements for BUILD (REVISE or FAIL)
1. ...

### JSON
{"reference": "<id>", "lib_target": "...", "setting": {...}, "anchors": [...],
 "summary_ratio": ..., "verdict": "PASS"}
```

Rules:

- Alignment is not benchmarking: do not compare against the roster or a baseline registry here.
- Alignment is not a source audit: code fidelity to the paper is the `audit-lib` skill's job.
- Record the configuration fields that move the number; tag the setting and cite the artifact.
