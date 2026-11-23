"""Compare a NumPy scaled-dot-product attention to the Attention Is All You Need formula.

Run from repo root:
  .venv/bin/python labs/2026-11-23-toy-scaled-dot-product/scripts/check_attention.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB.parents[1] / "labs" / "_tools"))
from paths import lab_output  # noqa: E402


def scaled_dot_product(q: np.ndarray, k: np.ndarray, v: np.ndarray) -> np.ndarray:
    d = q.shape[-1]
    scores = q @ k.swapaxes(-1, -2) / np.sqrt(d)
    weights = np.exp(scores - scores.max(axis=-1, keepdims=True))
    weights = weights / weights.sum(axis=-1, keepdims=True)
    return weights @ v


def reference(q: np.ndarray, k: np.ndarray, v: np.ndarray) -> np.ndarray:
    # Same math, different expression order — catches accidental scaling mistakes.
    scale = 1.0 / np.sqrt(q.shape[-1])
    logits = np.matmul(q, np.transpose(k, (0, 1, 3, 2))) * scale
    logits = logits - np.max(logits, axis=-1, keepdims=True)
    attn = np.exp(logits)
    attn = attn / np.sum(attn, axis=-1, keepdims=True)
    return np.matmul(attn, v)


def main() -> None:
    rng = np.random.default_rng(0)
    batch, heads, seq, dim = 2, 4, 8, 16
    q = rng.normal(size=(batch, heads, seq, dim))
    k = rng.normal(size=(batch, heads, seq, dim))
    v = rng.normal(size=(batch, heads, seq, dim))
    got = scaled_dot_product(q, k, v)
    want = reference(q, k, v)
    rel = float(np.max(np.abs(got - want) / (np.abs(want) + 1e-12)))
    out = {
        "relative_error_max": rel,
        "pass": rel < 1e-6,
        "shape": list(got.shape),
        "seed": 0,
    }
    path = lab_output(LAB, "attention_check", "json", seed=0)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out))
    if not out["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
