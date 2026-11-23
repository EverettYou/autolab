# Code map

Map an upstream repository or paper artifact onto the pieces a reproduction or promotion needs.

## What to extract

| Piece | Look for |
|------|----------|
| Entry scripts | README quickstart, notebooks that run the claim |
| Hamiltonian construction | δ/ε family, coefficients, BC, sector projectors |
| Solver core | ED, DMRG/MPS, sweeps, bond growth |
| Observables | gaps, correlators, entanglement / central charge |
| Evaluation | finite-size protocol, seeds, checkpoint I/O |
| Dependencies | pinned versions, CPU/GPU requirements |

## Integration hooks for the lab package

When promoting later, prefer:

- pure functions or small classes with explicit arrays / MPS handles
- no hidden global RNG; seed at the boundary
- ED baseline beside DMRG on the same small-L instances

Record the map under the attempt as `CODE-MAP.md` before rewriting anything.
