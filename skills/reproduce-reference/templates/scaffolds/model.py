"""Model / solver module — cite every non-trivial choice: §X.Y or [UNSPECIFIED]."""

from __future__ import annotations


class Model:
    """Mirror configs/base.yaml solver + data sections."""

    def __init__(self, config: dict):
        self.config = config

    def forward(self, batch):
        raise NotImplementedError
