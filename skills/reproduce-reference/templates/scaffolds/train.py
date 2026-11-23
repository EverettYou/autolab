"""
Training loop — read configs/base.yaml; cite optimizer schedule in comments.

Training efficiency gate (mandatory for reproduction training; see AGENTS.md / spending-compute):
  1. Efficiency gate BEFORE the loop: benchmark a warmed one-step (loss forward + backprop, timed
     separately) on a single GPU. If >0.2 s/step, STOP and fix (vectorize Python loops / broken accel
     kernel CPU-fallback / model size / architecture) to <=0.2 s/step before training.
  2. Print a numeric ETA = one_step_time * total_steps (not a qualitative guess).
  3. Append loss (+ step) to a log in the attempt workspace at least every ~10 min, FLUSHED
     (python -u / flush=True). Whoever monitors the run compares loss decay with the ETA and stops
     on saturation.
  See wiki/models/gpu-training-protocol.md for the benchmark recipe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import yaml


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def train(
    model: torch.nn.Module,
    config_path: Path,
    device: torch.device,
    max_steps: int | None = None,
) -> dict[str, float]:
    """§… — training procedure from paper."""
    cfg = load_config(config_path)
    # [UNSPECIFIED] optimizer details must match REPRODUCTION-NOTES.md
    raise NotImplementedError
