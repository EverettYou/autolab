# EM ambiguity checklist — for AMBIGUITY-AUDIT stage

Classify each row **SPECIFIED | PARTIALLY_SPECIFIED | UNSPECIFIED**. Search method,
experiments, appendix, captions, footnotes. Record exact quote + section.

## Hamiltonian & duality

| Item | Look for |
|------|----------|
| Family | δ-staggered, ε-density, KW dual, other |
| Microscopic coefficients | J, μ, δ/ε, boundary terms |
| Physical vs logical frame | EM boundary vs KW dual mapping |
| Boundary conditions | OBC, PBC, mixed |
| Sector / projection | Charge, momentum, duality projector |

## Numerics

| Item | Look for |
|------|----------|
| Solver | Exact diagonalization, DMRG/MPS, other |
| System sizes | L list; finite-size protocol |
| Bond / cutoff | χ, truncation, ED cutoff |
| Sweeps / convergence | Sweep schedule, energy/gap tolerance |
| Seeds / warm starts | Initial MPS, checkpoint provenance |

## Observables

| Item | Look for |
|------|----------|
| Spectrum | Gaps, level crossings, tip location |
| Correlators | Operators, distances, BC |
| Entanglement | Cut, central charge fit |
| Transition locator | Metric and uncertainty |

## Evaluation (claim-critical)

| Item | Look for |
|------|----------|
| Metric | Gap, correlator, fit residual, tip μ … |
| Uncertainty | Fit error, bond doubling, seed spread |
| Controls | Alternate BC, neighboring cut, ED vs DMRG |
| Regime tag | Family + BC + sector + L + bond |

## Provenance

| Item | Look for |
|------|----------|
| Code / notebook path | Lab script, platform module, upstream repo |
| Checkpoint path | `*.mps.pkl.gz` and companion JSON |
| Figure inputs | notes/figures or lab results cited by REPORT |
