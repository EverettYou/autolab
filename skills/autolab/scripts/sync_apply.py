#!/usr/bin/env python3
"""Apply template sync-zone paths into a consumer lab worktree.

Ownership model for paths in AutoLab:

* **Sync zone** — OS conventions and procedures. Upserted on every sync (includes
  ``.auto-research`` README contracts).
* **Bootstrap-once** — empty ``.auto-research/state.json`` only when missing; never overwrite
  a live loop. ``wiki/taxonomy.yml`` once when missing.
* **Local live data** — never synced (``state.json``, task bodies, thread message files,
  dated labs, reference bodies, notes, lib code, domain wiki ledgers, consumer identity).

Usage (from the AutoLab checkout):
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
# Sync registry — everything AutoLab owns as OS today goes here.
# Do not add project payloads here (dated labs, reference bodies, notes, lib code stay local).
# ---------------------------------------------------------------------------

# Wholesale directory trees (relative to template root).
SYNC_TREES = (
    "skills",
    "dashboard",
    "wiki/system",  # Lab OS architecture manual (not domain science)
    "labs/_tools",
)

# Removed from consumers on sync (renames / retired OS paths only).
# Never list wiki/project or scaffold/project here — research-program ledger + its ingest templates.
RETIRED_TREES: tuple[str, ...] = (
    "skills/research-threads",  # renamed to skills/thread-interaction
    "skills/runtime-env/machines",  # dossiers retired; docker assets under skills/runtime-env/assets/
    "skills/runtime-env/probes",  # moved to skills/runtime-env/scripts/probes/
)

# Retired single files (copy_tree does not delete orphans).
RETIRED_FILES: tuple[str, ...] = (
    "skills/runtime-env/scripts/lib/match_profile.sh",
    "skills/runtime-env/scripts/lib/profile_signals.sh",
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
    # Auto-research format contracts (live state / task bodies / thread files stay local)
    ".auto-research/README.md",
    ".auto-research/tasks/README.md",
    ".auto-research/threads/README.md",
    # wiki/taxonomy.yml is bootstrap-once (consumer extends topics/; never overwrite on sync)
)
# Never sync a root VERSION file. OS release is config.yml → os_version only
# (see template_os_version / --bump-pin; fs_health_lint retires VERSION).
assert "VERSION" not in SYNC_FILES
assert "wiki/taxonomy.yml" not in SYNC_FILES
assert ".auto-research/state.json" not in SYNC_FILES

# Same empty seed create_project writes. Never ship the template's live loop.
EMPTY_AUTO_RESEARCH_STATE = (
    "{\n"
    '  "schema": "auto-research-1",\n'
    '  "status": "paused",\n'
    '  "updated": "1970-01-01T00:00:00Z",\n'
    '  "active_deliverable": null,\n'
    '  "next_action": "Start the loop only on your own branch after the researcher '
    'sets an active deliverable.",\n'
    '  "last_action": null,\n'
    '  "last_supervisor_at": null,\n'
    '  "idle": null,\n'
    '  "tasks": [],\n'
    '  "threads": []\n'
    "}\n"
)

# Consumer gitignore: track/sync README contracts; keep live loop data local.
CONSUMER_AUTO_RESEARCH_GITIGNORE = (
    "# .auto-research/: README contracts stay tracked and OS-synced; live loop data stays local.\n"
    ".auto-research/state.json\n"
    ".auto-research/scheduler.json\n"
    ".auto-research/threads.json\n"
    ".auto-research/*.lock\n"
    ".auto-research/tasks/*\n"
    "!.auto-research/tasks/README.md\n"
    ".auto-research/threads/*\n"
    "!.auto-research/threads/README.md\n"
)

# Explicit non-sync. Not copied by this script.
# - skills/autolab/ (template-only; stripped)
# - config.yml, root README.md, AGENTS.md, tool bootstrap pointer (consumer identity)  # rules-lint: allow
# - labs/labs.json, references/references.json (live catalogs)
# - dated labs/<YYYY-*>/, references/<id>/, notes/<manuscript>/, lib/src/, lib/tests/
# - wiki domain ledgers (project/, concepts/, methods/, …), wiki/thesis.md, wiki/sources.yml,
#   wiki/records/, wiki/taxonomy.yml after first copy (living topics list)
# - .auto-research/state.json, task bodies, thread message files (live loop)

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

# Downloadable dashboard vendor trees (local install via install_vendor.py; not OS source).
VENDOR_DOWNLOAD_DIRS = frozenset(
    {"mermaid", "katex", "pdfjs", "marked", "dompurify", "highlight"}
)

# Never sync template-only admin skill into consumers (include legacy folder name).
TEMPLATE_ONLY_SKILL_PARTS = {"autolab", "manage-projects"}


def should_skip(rel: Path) -> bool:
    """Skip using paths *relative to the sync tree root* (never absolute paths — the
    template checkout may be named ``autolab`` and must not trip template-only filters)."""
    parts = set(rel.parts)
    if parts & SKIP_NAMES:
        return True
    # dashboard/frontend/vendor/<downloadable>/… — installed on the consumer by ./run.sh
    if (
        len(rel.parts) >= 3
        and rel.parts[0] == "frontend"
        and rel.parts[1] == "vendor"
        and rel.parts[2] in VENDOR_DOWNLOAD_DIRS
    ):
        return True
    if len(rel.parts) >= 3 and rel.parts[0] == "frontend" and rel.parts[1] == "vendor" and rel.parts[2] == ".installed":
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


def ensure_auto_research_state(dest: Path, *, dry_run: bool) -> list[str]:
    """Create dirs + empty ``state.json`` only when missing — never overwrite a live loop."""
    auto_dst = dest / ".auto-research"
    state = auto_dst / "state.json"
    changes: list[str] = []
    if not auto_dst.exists():
        changes.append("mkdir .auto-research/ (tasks + threads)")
        if not dry_run:
            auto_dst.mkdir(parents=True, exist_ok=True)
            (auto_dst / "tasks").mkdir(exist_ok=True)
            (auto_dst / "threads").mkdir(exist_ok=True)
    elif not dry_run:
        (auto_dst / "tasks").mkdir(exist_ok=True)
        (auto_dst / "threads").mkdir(exist_ok=True)
    if state.is_file():
        return changes
    changes.append("write .auto-research/state.json (empty seed)")
    if not dry_run:
        auto_dst.mkdir(parents=True, exist_ok=True)
        (auto_dst / "tasks").mkdir(exist_ok=True)
        (auto_dst / "threads").mkdir(exist_ok=True)
        state.write_text(EMPTY_AUTO_RESEARCH_STATE, encoding="utf-8")
    return changes


def bootstrap_taxonomy(source: Path, dest: Path, *, dry_run: bool) -> list[str]:
    """Copy wiki/taxonomy.yml once when the consumer has none (never overwrite living topics)."""
    src = source / "wiki" / "taxonomy.yml"
    dst = dest / "wiki" / "taxonomy.yml"
    if not src.is_file():
        return []
    if dst.is_file():
        return []
    changes = ["bootstrap wiki/taxonomy.yml (init-once; consumer owns topics thereafter)"]
    if dry_run:
        return changes
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return changes


def rewrite_consumer_auto_research_gitignore(text: str) -> str:
    """Drop whole-folder or stale .auto-research rules; append the selective consumer block."""
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(".auto-research/") or stripped.startswith("!.auto-research/"):
            continue
        if stripped.startswith("#") and ".auto-research" in stripped:
            continue
        if "research queue" in stripped.lower() or "threads (state" in stripped.lower():
            continue
        if "scaffold copied once" in stripped.lower():
            continue
        if "readme contracts stay tracked" in stripped.lower():
            continue
        lines.append(line)
    body = "".join(lines).rstrip() + "\n\n"
    return body + CONSUMER_AUTO_RESEARCH_GITIGNORE


def ensure_consumer_auto_research_gitignore(dest: Path, *, dry_run: bool) -> list[str]:
    """Track/sync README contracts; gitignore live state, task bodies, and thread files."""
    gitignore = dest / ".gitignore"
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        updated = rewrite_consumer_auto_research_gitignore(text)
        if updated == text:
            return []
        changes = ["gitignore: .auto-research README tracked; live loop data local"]
        if not dry_run:
            gitignore.write_text(updated, encoding="utf-8")
        return changes
    changes = ["gitignore: create with selective .auto-research rules"]
    if not dry_run:
        gitignore.write_text(CONSUMER_AUTO_RESEARCH_GITIGNORE, encoding="utf-8")
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
    changes.extend(ensure_auto_research_state(dest, dry_run=dry_run))
    changes.extend(bootstrap_taxonomy(source, dest, dry_run=dry_run))
    changes.extend(ensure_consumer_auto_research_gitignore(dest, dry_run=dry_run))
    # Consumers must not keep template-only skills
    for name in TEMPLATE_ONLY_SKILL_PARTS:
        stray = dest / "skills" / name
        if stray.exists():
            changes.append(f"remove skills/{name} (template-only)")
            if not dry_run:
                shutil.rmtree(stray) if stray.is_dir() else stray.unlink()
    for name in RETIRED_TREES:
        stray = dest / name
        if stray.exists():
            changes.append(f"remove {name} (retired)")
            if not dry_run:
                shutil.rmtree(stray) if stray.is_dir() else stray.unlink()
    for name in RETIRED_FILES:
        stray = dest / name
        if stray.is_file():
            changes.append(f"remove {name} (retired)")
            if not dry_run:
                stray.unlink()
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


def assert_consumer_dest(dest: Path) -> None:
    """Refuse to sync into an AutoLab template checkout.

    ``apply`` deletes ``skills/autolab`` on purpose for consumers. Running the same
    path against this template would strip the admin skill from AutoLab itself.
    """
    for name in TEMPLATE_ONLY_SKILL_PARTS:
        if (dest / "skills" / name).exists():
            raise SystemExit(
                f"refusing to sync into {dest}: skills/{name} is present "
                "(AutoLab template only). Lab OS sync targets consumer labs, not this repo."
            )


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
    assert_consumer_dest(dest)
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
