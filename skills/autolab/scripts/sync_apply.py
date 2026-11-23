#!/usr/bin/env python3
"""Apply template sync-zone paths into a consumer lab worktree.

Ownership model for paths in Autolab:

* **Sync zone** — OS conventions and procedures. Upserted on every sync.
* **Bootstrap-once** — ``.auto-research/`` scaffold only if the consumer has no folder yet.
* **Project payloads** — never synced (dated labs, reference bodies, notes manuscripts, lib
  package code, domain wiki ledgers, consumer ``config.yml`` / root README).
* **Demo / fake examples** (future) — may exist in Autolab so the dashboard can run locally;
  they must **not** be listed below. Keep sync off for those paths.

Usage (from the Autolab checkout):
  python skills/autolab/scripts/sync_apply.py --from /path/to/autolab --to /path/to/consumer
  python skills/autolab/scripts/sync_apply.py --from . --to ../my-lab --dry-run
"""
from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Sync registry — everything Autolab owns as OS today goes here.
# Do not add fake labs / fake notes / fake lib demos here.
# ---------------------------------------------------------------------------

# Wholesale directory trees (relative to template root).
SYNC_TREES = (
    "skills",
    "dashboard",
    "wiki/project",  # Lab OS architecture manual (not domain science)
    "labs/_tools",
)

# Single files upserted every sync.
SYNC_FILES = (
    "run.sh",
    # Floor contracts (READMEs) — OS prose, not project payloads
    "labs/README.md",
    "references/README.md",
    "notes/README.md",
    "lib/README.md",
    "wiki/README.md",
    "wiki/taxonomy.yml",
)
# Never sync a root VERSION file. OS release is config.yml → os_version only
# (see template_os_version / --bump-pin; fs_health_lint retires VERSION).
assert "VERSION" not in SYNC_FILES

# Scaffold files copied only when consumer lacks .auto-research/ entirely.
BOOTSTRAP_AUTO_RESEARCH = (
    "README.md",
    "state.json",
    "tasks/README.md",
    "threads/README.md",
)

# Explicit non-sync (documentation + future demos). Not copied by this script.
# - skills/autolab/ (template-only; stripped)
# - config.yml, root README.md, AGENTS.md, tool bootstrap pointer (consumer identity)  # rules-lint: allow
# - labs/labs.json, references/references.json (live catalogs)
# - dated labs/<YYYY-*>/, references/<id>/, notes/<manuscript>/, lib/src/, lib/tests/
# - wiki domain ledgers (concepts/, methods/, …), wiki/thesis.md, wiki/sources.yml, wiki/records/
# - .auto-research/ after first bootstrap (live loop + Threads)
# - Future: any Autolab-only demo fixtures under labs/, notes/, lib/ used to populate the dashboard

# Never touch these names anywhere under a synced tree
SKIP_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "site.json",
    "state.json",
    "threads.json",
    "tasks",
    "scheduler.json",
}

# Never sync template-only admin skill into consumers (include legacy folder name).
TEMPLATE_ONLY_SKILL_PARTS = {"autolab", "manage-projects"}


def should_skip(rel: Path) -> bool:
    """Skip using paths *relative to the sync tree root* (never absolute paths — the
    template checkout may be named ``autolab`` and must not trip template-only filters)."""
    parts = set(rel.parts)
    if parts & SKIP_NAMES:
        return True
    if parts & TEMPLATE_ONLY_SKILL_PARTS:
        return True
    return False


def copy_tree(src: Path, dst: Path, *, dry_run: bool) -> list[str]:
    changes: list[str] = []
    if not src.is_dir():
        raise SystemExit(f"missing sync tree: {src}")
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if should_skip(rel):
            continue
        target = dst / rel
        if path.is_dir():
            if dry_run:
                if not target.exists():
                    changes.append(f"mkdir {target}")
            else:
                target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists() and filecmp.cmp(path, target, shallow=False):
            continue
        changes.append(f"copy {rel.as_posix()}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return changes


def copy_file(src: Path, dst: Path, *, dry_run: bool, label: str | None = None) -> list[str]:
    if not src.is_file():
        return []
    if dst.exists() and filecmp.cmp(src, dst, shallow=False):
        return []
    name = label or dst.name
    if dry_run:
        return [f"copy {name}"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return [f"copy {name}"]


def bootstrap_auto_research(source: Path, dest: Path, *, dry_run: bool) -> list[str]:
    """Copy the .auto-research scaffold once; no-op if the consumer already has the folder."""
    auto_src = source / ".auto-research"
    auto_dst = dest / ".auto-research"
    if not auto_src.is_dir():
        return []
    if auto_dst.exists():
        return []  # already initialized — never re-sync
    changes: list[str] = ["bootstrap .auto-research/ (init-once scaffold)"]
    if dry_run:
        return changes
    auto_dst.mkdir(parents=True, exist_ok=True)
    (auto_dst / "tasks").mkdir(exist_ok=True)
    (auto_dst / "threads").mkdir(exist_ok=True)
    for rel in BOOTSTRAP_AUTO_RESEARCH:
        src = auto_src / rel
        if src.is_file():
            target = auto_dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            changes.append(f"copy .auto-research/{rel}")
    return changes


def ensure_consumer_auto_research_gitignore(dest: Path, *, dry_run: bool) -> list[str]:
    """Ignore the whole `.auto-research/` folder on consumers (live checkout data)."""
    gitignore = dest / ".gitignore"
    block = (
        "# Local loop + Threads store: scaffold copied once, then never tracked / re-synced.\n"
        ".auto-research/\n"
    )
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s*\.auto-research/\s*$", text):
            return []
        changes = ["gitignore: ignore .auto-research/ (consumer live data)"]
        if dry_run:
            return changes
        if text and not text.endswith("\n"):
            text += "\n"
        gitignore.write_text(text + "\n" + block, encoding="utf-8")
        return changes
    changes = ["gitignore: create with .auto-research/ ignore"]
    if not dry_run:
        gitignore.write_text(block, encoding="utf-8")
    return changes


def apply(source: Path, dest: Path, *, dry_run: bool) -> list[str]:
    changes: list[str] = []
    for name in SYNC_TREES:
        src = source / name
        if not src.is_dir():
            continue
        changes.extend(copy_tree(src, dest / name, dry_run=dry_run))
    for name in SYNC_FILES:
        src = source / name
        if not src.is_file():
            continue
        changes.extend(copy_file(src, dest / name, dry_run=dry_run, label=name))
    changes.extend(bootstrap_auto_research(source, dest, dry_run=dry_run))
    changes.extend(ensure_consumer_auto_research_gitignore(dest, dry_run=dry_run))
    # Consumers must not keep template-only skills
    for name in TEMPLATE_ONLY_SKILL_PARTS:
        stray = dest / "skills" / name
        if stray.exists():
            changes.append(f"remove skills/{name} (template-only)")
            if not dry_run:
                shutil.rmtree(stray) if stray.is_dir() else stray.unlink()
    return changes


def template_os_version(source: Path) -> str:
    """OS release from the template ``config.yml`` → ``os_version`` (single source of truth)."""
    path = source / "config.yml"
    if not path.is_file():
        return ""
    match = re.search(r'(?m)^\s*os_version:\s*["\']?([^"\'\n]+)["\']?\s*$', path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else ""


def bump_pin(dest: Path, version: str, *, dry_run: bool) -> None:
    path = dest / "config.yml"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    updated, n = re.subn(
        r"(?m)^(os_version:\s*)([\"']?)[^\"'\n]+([\"']?)\s*$",
        rf'\1"{version}"',
        text,
        count=1,
    )
    if n and updated != text and not dry_run:
        path.write_text(updated, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", type=Path, required=True)
    parser.add_argument("--to", dest="dest", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--bump-pin",
        action="store_true",
        help="set consumer os_version from the template config.yml os_version",
    )
    args = parser.parse_args(argv)
    source = args.source.resolve()
    dest = args.dest.resolve()
    if not source.is_dir() or not dest.is_dir():
        raise SystemExit("both --from and --to must be directories")
    changes = apply(source, dest, dry_run=args.dry_run)
    version = template_os_version(source)
    if args.bump_pin and version:
        bump_pin(dest, version, dry_run=args.dry_run)
        changes.append(f"pin os_version={version}")
    if not changes:
        print("already up to date")
        return 0
    print(f"{len(changes)} change(s){' (dry-run)' if args.dry_run else ''}:")
    for line in changes[:50]:
        print(f"  {line}")
    if len(changes) > 50:
        print(f"  … {len(changes) - 50} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
