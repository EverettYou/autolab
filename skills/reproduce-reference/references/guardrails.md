# Reproduction guardrails

Anti-hallucination rules for attempt workspaces. Read before generating code from a paper.

## Never invent

- Equations, Hamiltonians, bond dimensions, or metrics that the paper does not state.
- A control the paper did not run, unless the attempt is explicitly labeled as an extension and
  the lab report says so.
- Continuum CFT claims from a single small-L data point.

## Always record

- Every UNSPECIFIED choice and the default taken (`REPRODUCTION-NOTES.md`).
- Seeds, library versions, and the exact command lines.
- Which claims from `gate-state.yaml` were tested, partial, or blocked.

## EM-specific traps

| Phrase in paper | Ambiguity | What to do |
|-----------------|-----------|------------|
| "δ = 0 line" | Which microscopic parametrization; tip vs bulk | Quote coefficients and BC |
| "critical" | Gap closing, correlator power, central charge | Name the observable |
| "PBC / OBC" | Physical vs dual lattice; even/odd L | Match the figure caption |
| "DMRG converged" | Energy, gap, or discard weight | Record χ and tolerance |
| "same as KW" | Exact duality map vs approximate | Cite the mapping used |

## Scope discipline

- **Implement:** core model + measurement needed for `gate-state.yaml` claims.
- **Do not implement:** unrelated figure polish or platform promotion inside the attempt.
  Promotion is `promote-lib` after `reproduce/` exists.
