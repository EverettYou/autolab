"""One-layer bag-of-embeddings MLM head on a tiny corpus.

Run from repo root:
  .venv/bin/python labs/2026-11-23-bert-mask-baseline/scripts/toy_mlm.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB.parents[1] / "labs" / "_tools"))
from paths import lab_output  # noqa: E402


def main() -> None:
    rng = np.random.default_rng(2)
    vocab, seq, dim, steps = 50, 32, 16, 200
    tokens = rng.integers(0, vocab, size=seq)
    mask = np.zeros(seq, dtype=bool)
    mask[::4] = True
    emb = rng.normal(scale=0.1, size=(vocab, dim))
    W = rng.normal(scale=0.1, size=(dim, vocab))
    lr = 0.05
    chance = float(np.log(vocab))
    losses = []
    for _ in range(steps):
        x = emb[tokens]
        logits = x @ W
        # softmax CE on masked positions only
        logits = logits - logits.max(axis=-1, keepdims=True)
        probs = np.exp(logits)
        probs = probs / probs.sum(axis=-1, keepdims=True)
        y = tokens
        nll = -np.log(probs[np.arange(seq), y] + 1e-12)
        loss = float(nll[mask].mean())
        losses.append(loss)
        grad_logits = probs
        grad_logits[np.arange(seq), y] -= 1.0
        grad_logits[~mask] = 0.0
        grad_logits /= max(mask.sum(), 1)
        dW = x.T @ grad_logits
        dx = grad_logits @ W.T
        W -= lr * dW
        emb[tokens] -= lr * dx
    final = losses[-1]
    out = {
        "chance_nll": chance,
        "final_nll": final,
        "pass": final < chance,
        "steps": steps,
        "seed": 2,
    }
    path = lab_output(LAB, "toy_mlm", "json", seed=2)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if not out["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
