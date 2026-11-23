# Toy scaled dot-product attention

## Question

Does a NumPy scaled-dot-product attention match the Attention Is All You Need formula within
`1e-6` relative error on a fixed random Q/K/V draw? Plan: [PLAN.md](PLAN.md).

## Setting

- Shape `(2, 4, 8, 16)`, seed `0`
- Command from repository root:

```bash
.venv/bin/python labs/2026-11-23-toy-scaled-dot-product/scripts/check_attention.py
```

## Results

[`results/attention_check_seed0.json`](results/attention_check_seed0.json):
`relative_error_max = 0.0`, `pass = true`.

## Interpretation

The two implementations agree to machine precision on this draw; the scale factor is present.

## Verdict

Yes — relative error is below `1e-6`.

## Next steps

None for this question. Follow-on toy MLM lab: `2026-11-23-bert-mask-baseline`.
