"""Which files, and which added lines, a pending commit touches. Shared by the `--changed` guards.

"Pending" is the working tree and index against a base revision (default `HEAD`), plus untracked
files. Another writer's uncommitted edits count too, because a guard cannot know which paths the
commit will list; a failure it reports in someone else's file is still a real failure.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def changed_files(root: Path, pathspecs: "list[str]", base: str = "HEAD") -> "dict[str, str]":
    """``{repo-relative path: status}`` for files changed since ``base`` under ``pathspecs``.

    Status is ``"added"`` (new against ``base``, including untracked) or ``"modified"``. Deleted
    files are left out: there is nothing left to check.
    """
    result: dict[str, str] = {}
    for line in _git(root, "diff", "--name-status", "--no-renames", base, "--", *pathspecs).splitlines():
        status, _, path = line.partition("\t")
        if status.startswith("D") or not path:
            continue
        result[path] = "added" if status.startswith("A") else "modified"
    for path in _git(root, "ls-files", "--others", "--exclude-standard", "--", *pathspecs).splitlines():
        if path:
            result[path] = "added"
    return result


def added_lines(root: Path, path: str, status: str, base: str = "HEAD") -> "list[str]":
    """The lines ``path`` adds against ``base`` (every line of a new file)."""
    if status == "added":
        try:
            return (root / path).read_text(errors="replace").splitlines()
        except OSError:
            return []
    diff = _git(root, "diff", "-U0", "--no-color", base, "--", path)
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
