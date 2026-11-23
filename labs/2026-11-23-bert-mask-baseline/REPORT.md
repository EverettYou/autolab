# BERT MLM toy baseline shape

## Question

Does a one-layer bag-of-embeddings MLM head beat chance NLL on a 32-token toy corpus?
Plan: [PLAN.md](PLAN.md).

## Setting

```bash
.venv/bin/python labs/2026-11-23-bert-mask-baseline/scripts/toy_mlm.py
```

Vocab 50, seq 32, dim 16, 200 steps, seed 2.

## Results

[`results/toy_mlm_seed2.json`](results/toy_mlm_seed2.json):
`chance_nll ≈ 3.912`, `final_nll ≈ 3.205`, `pass = true`.

## Interpretation

The toy head overfits its own masked tokens enough to beat uniform chance; not a BERT reproduction.

## Verdict

Yes — final masked NLL is below `log V`.

## Next steps

None yet. A real BERT claim would need `reproduce-reference` on `bert-pretraining`.
