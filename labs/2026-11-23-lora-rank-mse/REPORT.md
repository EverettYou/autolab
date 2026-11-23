# LoRA rank vs toy adapter MSE

## Question

Does raising truncated-SVD rank from 1 to 8 monotonically reduce reconstruction MSE on a fixed
matrix (LoRA-style low-rank geometry)? Plan: [PLAN.md](PLAN.md).

## Setting

```bash
.venv/bin/python labs/2026-11-23-lora-rank-mse/scripts/rank_sweep.py
```

Seed `1`, matrix `32×24`, ranks `1,2,4,8`.

## Results

[`results/rank_sweep_seed1.json`](results/rank_sweep_seed1.json): MSE sequence
`0.812 → 0.697 → 0.528 → 0.285`, `monotone_nonincreasing = true`.

## Interpretation

Residuals fall with rank as expected from truncated SVD; this is a geometry check, not a PEFT train.

## Verdict

Yes — MSE is monotone nonincreasing over the swept ranks.

## Next steps

None.
