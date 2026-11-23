# Plan: LoRA rank vs toy adapter MSE

Registered 2026-11-23. Add dated notes under Amendments; do not rewrite registered sections.

## Question

On a fixed random matrix, does increasing truncated-SVD rank from 1 → 8 monotonically reduce
reconstruction MSE (LoRA-style low-rank adapter geometry)?

## Motivation

Tied to `references/lora-low-rank-adaptation`: show a sweep lab with a monotone
success criterion the dashboard can render.

## Prior anchors

No domain wiki pages yet. Reference: [Hu et al. 2021](../../references/lora-low-rank-adaptation/provenance.json).
This lab does **not** reimplement PEFT training — only the low-rank reconstruction geometry LoRA uses.

## Hypotheses and alternatives

- Working: Eckart–Young — higher rank never increases Frobenius residual.
- Rival: a buggy truncation axis would break monotonicity.

## Setting

- Matrix `32 × 24`, seed `1`
- Ranks `{1, 2, 4, 8}`
- CPU SVD

## Design

For each rank `r`, form the rank-`r` SVD truncation and record mean squared residual.

## Success criterion

`mse(rank)` is nonincreasing across the listed ranks (`monotone_nonincreasing = true`).

## Stop rules

One sweep; no early stop.

## Completion

REPORT cites `results/rank_sweep_seed1.json`. Wiki: none for this exploratory sweep.

## Amendments

None.
