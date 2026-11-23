#!/usr/bin/env python3
"""Repository layout patrol: retired paths stay gone, and the package tree holds source code only.

Run from the repository root (read-only):

    .venv/bin/python skills/auto-research/scripts/fs_health_lint.py [--json]

Exit codes: 0 pass (warnings allowed), 1 layout violations, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3]

RETIRED = {
    "STEERING.md": "researcher instructions and questions are Threads under .auto-research/threads/",
    "FEEDBACK.md": "researcher instructions and questions are Threads under .auto-research/threads/",
    "TODO.md": "unfinished work is the task list in .auto-research/state.json",
    "inbox": "external sources live in references/<id>/",
    "sandbox": "reproduction workspaces live in references/<id>/attempts/<slug>/",
    "archive": "measurements stay in labs/; knowledge in wiki/; reproductions in references/<id>/reproduce/",
    "projects": "the package lives in lib/",
    "lab": "experiments live in labs/<YYYY-MM-DD-slug>/",
    "knowledge": "compiled knowledge lives in wiki/",
    ".logs": "loop activity is last_action in .auto-research/state.json plus git history",
    "run_dashboard.sh": "the dashboard launcher is ./run.sh",
    "project.json": "home-page title and intro are dashboard/frontend/site.json; the loop's next action is .auto-research/state.json; a lab's focus is its lab.json",
    "discussion": "Threads meta in .auto-research/state.json; messages in threads/<id>.json",
    "library": "no top-level measurement/model store; keep numbers and checkpoints in labs/",
    # OS release pin is config.yml → os_version only (never a root VERSION file).
    "VERSION": "OS release is config.yml → os_version; do not add a root VERSION file "
               "(sync_apply --bump-pin reads that field)",
}
TOOL_LOCAL = (".claude", ".cursor")
TOP_LEVEL = {
    "README.md", "AGENTS.md", "CLAUDE.md", "run.sh", "config.yml", ".gitignore", ".gitattributes",
    "LICENSE", "references", "labs", "wiki", ".auto-research", "skills", "lib",
    "dashboard", "documents", "notes", ".tmp", ".venv", ".git", ".cache", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".runtime", ".github", "__pycache__", *TOOL_LOCAL,
}
PACKAGE_ZONES = {
    "lab": "experiments belong in labs/<YYYY-MM-DD-slug>/",
    "labs": "experiments belong in labs/<YYYY-MM-DD-slug>/",
    "experiments": "experiments belong in labs/<YYYY-MM-DD-slug>/",
    "scripts": "experiment and maintenance scripts belong in labs/ or skills/<name>/scripts/",
    "data": "data belongs in the lab that produced it",
    "results": "results belong in the lab that produced them",
    "figures": "figures belong in the lab that produced them",
    "weights": "model weights belong in the lab that produced them (checkpoints/)",
    "docs": "package documentation lives in wiki/",
}
PACKAGE_ENTRIES = {"src", "tests", "build", "dist", ".pytest_cache", ".ruff_cache", "__pycache__", ".venv",
                   "pyproject.toml", "uv.lock", "README.md", "hatch_build.py"}
WEIGHT_SUFFIXES = {".pt", ".pth", ".ckpt", ".safetensors"}
BUNDLED_DATA = ("algorithms", "_data")
# Source and build files the package may hold; any other file outside algorithms/_data is data (fitted
# parameters, tables, results) and belongs in a lab.
SOURCE_SUFFIXES = {".py", ".pyi", ".pyx", ".pxd", ".c", ".cpp", ".h", ".so"}
SOURCE_NAMES = {".gitkeep", "py.typed"}


def tracked(root: Path, names: tuple[str, ...]) -> dict[str, int]:
    """Count git-tracked files under each directory; empty when git or the work tree is unavailable."""
    counts: dict[str, int] = {}
    for name in names:
        try:
            done = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", name],
                                  capture_output=True, text=True, check=False)
        except OSError:
            return {}
        if done.returncode != 0:
            return {}
        files = [f for f in done.stdout.split("\0") if f]
        if files:
            counts[name] = len(files)
    return counts


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() + ("/" if path.is_dir() else "")


def patrol(root: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (sections of OK lines, violations, warnings)."""
    ok: list[str] = []
    fail: list[str] = []
    warn: list[str] = []

    retired = [name for name in RETIRED if (root / name).exists()]
    for name in retired:
        fail.append(f"{name}{'/' if (root / name).is_dir() else ''} is retired: {RETIRED[name]}")
    if not retired:
        ok.append("no retired top-level paths")
    for name, count in tracked(root, TOOL_LOCAL).items():
        fail.append(f"{name}/ has {count} tracked file(s): rules belong in README.md and wiki/system/, "
                    "procedures in skills/; tool-local state stays untracked")
    scripts = root / "scripts"
    loose = sorted(p.name for p in scripts.glob("*") if p.suffix in {".sh", ".py"}) if scripts.is_dir() else []
    if loose:
        fail.append(f"root scripts/ holds {', '.join(loose)}: move each into skills/<name>/scripts/")
    else:
        ok.append("no loose root scripts/")
    for entry in sorted(root.iterdir()):
        if entry.name not in TOP_LEVEL and entry.name not in RETIRED and entry.name != "scripts":
            warn.append(f"non-standard top-level entry: {rel(root, entry)}")

    package = root / "lib"
    if not package.is_dir():
        warn.append("lib/ is absent (optional shared package layer)")
        return ok, fail, warn
    zones = [name for name in PACKAGE_ZONES if (package / name).exists()]
    for name in zones:
        fail.append(f"lib/{name}/ exists: {PACKAGE_ZONES[name]}")
    if not zones:
        ok.append("no experiment, data, or docs zones under lib/")
    stray = sorted(p.name for p in package.glob("*.py") if p.name != "hatch_build.py")
    if stray:
        fail.append(f"stray .py under lib/ ({', '.join(stray)}): only hatch_build.py belongs there")
    else:
        ok.append("lib/ root .py: hatch_build.py only")
    for entry in sorted(package.iterdir()):
        if (entry.name not in PACKAGE_ENTRIES and entry.name not in PACKAGE_ZONES
                and entry.suffix != ".py" and not entry.name.endswith(".egg-info")):
            warn.append(f"non-standard entry under lib/: {entry.name}")

    src_root = package / "src"
    if not src_root.is_dir():
        ok.append("lib/src/ absent (optional; add when enabling features.lib)")
        return ok, fail, warn
    packages = sorted(
        p for p in src_root.iterdir()
        if p.is_dir() and p.name != "__pycache__" and not p.name.startswith(".")
    )
    if not packages:
        ok.append("lib/src/ is empty (no shared package yet)")
        return ok, fail, warn
    for source in packages:
        before = len(fail)
        for path in sorted(source.rglob("*")):
            parts = path.relative_to(source).parts
            if "__pycache__" in parts:
                continue
            where = rel(root, path)
            if path.is_file() and path.name == "run.py":
                fail.append(f"experiment script inside the package: {where}")
            elif path.is_file() and path.name.lower() == "report.md":
                fail.append(f"report inside the package: {where}")
            elif path.is_file() and path.suffix in WEIGHT_SUFFIXES:
                fail.append(f"model weights inside the package: {where} (keep under labs/<id>/checkpoints/)")
            elif path.is_dir() and path.name in {"results", "figures"}:
                fail.append(f"experiment output directory inside the package: {where}")
            elif path.is_dir() and path.name == "data" and parts[:2] != BUNDLED_DATA:
                fail.append(f"data/ directory inside the package (only algorithms/_data/ is allowed): {where}")
            elif (path.is_file() and parts[:2] != BUNDLED_DATA and path.suffix not in SOURCE_SUFFIXES
                  and path.name not in SOURCE_NAMES):
                fail.append(f"non-source file inside the package (only algorithms/_data/ may hold data): {where}")
        if len(fail) == before:
            ok.append(f"lib/src/{source.name}/ holds code only")
    return ok, fail, warn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repository layout patrol (read-only).")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository root (default: this repository)")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    ok, fail, warn = patrol(root)
    if args.json:
        print(json.dumps({"pass": not fail, "violations": fail, "warnings": warn, "ok": ok}, indent=2))
    else:
        for line in ok:
            print(f"OK: {line}")
        for line in warn:
            print(f"WARN: {line}")
        for line in fail:
            print(f"FAIL: {line}")
        print(f"fs_health_lint: {'PASS' if not fail else f'FAIL ({len(fail)} violation(s))'}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
