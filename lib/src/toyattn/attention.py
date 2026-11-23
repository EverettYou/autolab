"""Scaled dot-product attention (NumPy)."""

from __future__ import annotations

import numpy as np


def scaled_dot_product(q: np.ndarray, k: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Attention(Q,K,V) = softmax(QK^T / sqrt(d_k)) V for leading batch dims."""
    d = q.shape[-1]
    scores = q @ np.swapaxes(k, -1, -2) / np.sqrt(d)
    weights = np.exp(scores - scores.max(axis=-1, keepdims=True))
    weights = weights / weights.sum(axis=-1, keepdims=True)
    return weights @ v
