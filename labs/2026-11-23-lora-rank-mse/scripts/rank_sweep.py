"""Sweep truncated-SVD ranks as a LoRA-style low-rank adapter on a fixed matrix.

Run from repo root:
  .venv/bin/python labs/2026-11-23-lora-rank-mse/scripts/rank_sweep.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB.parents[1] / "labs" / "_tools"))
from paths import lab_output  # noqa: E402


def low_rank_mse(W: np.ndarray, rank: int) -> float:
    u, s, vt = np.linalg.svd(W, full_matrices=False)
    approx = (u[:, :rank] * s[:rank]) @ vt[:rank, :]
    resid = W - approx
    return float(np.mean(resid**2))


def main() -> None:
    rng = np.random.default_rng(1)
    W = rng.normal(size=(32, 24))
    ranks = [1, 2, 4, 8]
    rows = [{"rank": r, "mse": low_rank_mse(W, r)} for r in ranks]
    mono = all(rows[i]["mse"] >= rows[i + 1]["mse"] - 1e-12 for i in range(len(rows) - 1))
    out = {"rows": rows, "monotone_nonincreasing": mono, "pass": mono, "seed": 1}
    path = lab_output(LAB, "rank_sweep", "json", seed=1)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if not out["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
