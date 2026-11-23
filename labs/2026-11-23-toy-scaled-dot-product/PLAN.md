# Plan: Toy scaled dot-product attention

Registered 2026-11-23. Add dated notes under Amendments; do not rewrite registered sections.

## Question

On fixed random Q/K/V tensors, does a two-line NumPy scaled-dot-product attention match the
Attention Is All You Need formula within `1e-6` relative error?

## Motivation

Sanity-check a small NumPy attention helper against the published formula before relying on it
in later labs.

## Prior anchors

Wiki query on "attention" returned only system pages (no domain ledger yet). Parent labs: none.
Formula source: [Vaswani et al. 2017](../../references/attention-is-all-you-need/provenance.json).

## Hypotheses and alternatives

- Working: identical algebra yields relative error ≈ 0.
- Rival: a missing `1/√d_k` scale would produce large, systematic error.

## Setting

- Batch × heads × seq × dim = 2 × 4 × 8 × 16
- Seed 0 (`numpy` Generator)
- CPU only

## Design

One deterministic check; no sweep. Compare `scaled_dot_product` against an independently written
`reference` using `matmul` + explicit transpose.

## Success criterion

`relative_error_max < 1e-6` in `results/attention_check_seed0.json`.

## Stop rules

Single smoke run; stop after one pass/fail.

## Completion

REPORT cites the JSON result. Wiki ingest: none — exploratory check only.

## Amendments

None.
