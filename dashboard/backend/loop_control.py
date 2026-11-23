"""Reorder the auto-research tasks for the status page.

The dashboard does not start or pause the loop. A person starts it in a Claude session.
Reordering is the one write: it goes through ``loop_state.py task move``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .repo import BadRequest

_REPO = Path(__file__).resolve().parents[2]
_STATE = _REPO / "skills" / "auto-research" / "scripts" / "loop_state.py"


def move(root: Path, item_id: str, *, before: str | None = None, after: str | None = None) -> None:
    """Place one task before or after another. The state script is the only writer."""
    if not _STATE.is_file():
        raise BadRequest("the auto-research state script is missing")
    if not (root / ".auto-research" / "state.json").is_file():
        raise BadRequest("there is no .auto-research/state.json to reorder")
    if bool(before) == bool(after):
        raise BadRequest("name the item to place this one before or after, not both")
    anchor = before or after
    if anchor == item_id:
        raise BadRequest("an item cannot be placed relative to itself")
    flag = "--before" if before else "--after"
    completed = subprocess.run(
        [sys.executable, str(_STATE), "--root", str(root), "task", "move", item_id, flag, anchor],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "could not reorder the tasks").strip()
        raise BadRequest(detail.splitlines()[-1][:500])
