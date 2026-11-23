#!/usr/bin/env python3
"""Create a new consumer lab from this template tree (full copy, then empty project zone).

Usage (AutoLab template only):
  python skills/autolab/scripts/create_project.py --name mylab --dest ../mylab
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from sync_apply import (  # shared empty loop seed + consumer gitignore + workflow contract
    CONSUMER_AUTO_RESEARCH_GITIGNORE,
    EMPTY_AUTO_RESEARCH_STATE,
    install_lab_os_sync_workflow,
    rewrite_consumer_auto_research_gitignore,
)

SKIP = {".git", ".venv", ".cache", ".pytest_cache", "__pycache__", ".runtime", ".tmp", "tools"}
# Template-only: never ship this skill into consumer labs.
TEMPLATE_ONLY_SKILLS = {"autolab"}
# Downloadable vendor trees — consumers install via ./run.sh (install_vendor.py).
VENDOR_DOWNLOAD_DIRS = ("mermaid", "katex", "pdfjs", "marked", "dompurify", "highlight")


def _dashboard_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {n for n in names if n in SKIP or n == ".git"}
    # When copying dashboard/frontend/vendor/, skip downloadable package dirs + stamp.
    parts = Path(directory).parts
    if len(parts) >= 2 and parts[-2:] == ("frontend", "vendor"):
        ignored.update(n for n in names if n in VENDOR_DOWNLOAD_DIRS or n == ".installed")
    return ignored


def copy_template(source: Path, dest: Path) -> None:
    if dest.exists():
        raise SystemExit(f"destination exists: {dest}")
    dest.mkdir(parents=True)
    for item in source.iterdir():
        if item.name in SKIP:
            continue
        target = dest / item.name
        if item.is_dir():
            if item.name == "skills":
                shutil.copytree(
                    item,
                    target,
                    ignore=shutil.ignore_patterns(*SKIP, ".git", *TEMPLATE_ONLY_SKILLS),
                )
            elif item.name == "dashboard":
                shutil.copytree(item, target, ignore=_dashboard_ignore)
            else:
                shutil.copytree(item, target, ignore=shutil.ignore_patterns(*SKIP, ".git"))
        else:
            shutil.copy2(item, target)
    # Belt-and-suspenders: remove if an ignore pattern failed
    for name in TEMPLATE_ONLY_SKILLS:
        stray = dest / "skills" / name
        if stray.exists():
            shutil.rmtree(stray) if stray.is_dir() else stray.unlink()


def empty_project_zone(root: Path) -> None:
    """Clear science floors so the new lab starts with empty catalogs and optional layers."""
    labs = root / "labs"
    for path in list(labs.iterdir()):
        if path.name.startswith("20") and path.is_dir():
            shutil.rmtree(path)
    (labs / "labs.json").write_text('{\n  "labs": []\n}\n', encoding="utf-8")

    refs = root / "references"
    for path in list(refs.iterdir()):
        if path.name not in {"README.md", "references.json"}:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    (refs / "references.json").write_text('{\n  "references": []\n}\n', encoding="utf-8")

    # Optional floors: keep contracts (READMEs); clear any manuscripts / package bodies.
    notes = root / "notes"
    if notes.is_dir():
        for path in list(notes.iterdir()):
            if path.name != "README.md":
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()

    # Shared package starts empty unless --package enables features.lib.
    lib = root / "lib"
    if lib.is_dir():
        for sub in ("src", "tests"):
            folder = lib / sub
            if folder.is_dir():
                shutil.rmtree(folder)
                folder.mkdir(parents=True, exist_ok=True)
        pyproject = lib / "pyproject.toml"
        pyproject.write_text(
            '[build-system]\n'
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n'
            '\n'
            '# Placeholder until a consumer enables features.lib and adds src/<package>/.\n'
            '[project]\n'
            'name = "lab-lib"\n'
            'version = "0.0.0"\n'
            'description = "Optional shared package for this lab (empty until enabled)"\n'
            'requires-python = ">=3.11"\n'
            'dependencies = []\n'
            '\n'
            '[project.optional-dependencies]\n'
            'dev = ["pytest"]\n'
            '\n'
            '[tool.pytest.ini_options]\n'
            'testpaths = ["tests"]\n'
            'pythonpath = ["src"]\n',
            encoding="utf-8",
        )


def localize_auto_research(root: Path) -> None:
    """After scaffold: keep README contracts tracked; gitignore live loop data.

    READMEs stay on the consumer and continue to OS-sync. ``state.json``, task bodies, and
    thread message files are local-only (same selective rules as ``sync_apply``).
    """
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        # Also drop template-tracked state.json rule — consumers keep state local.
        lines = []
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped == ".auto-research/state.json":
                continue
            lines.append(line)
        gitignore.write_text(
            rewrite_consumer_auto_research_gitignore("".join(lines)),
            encoding="utf-8",
        )
    else:
        gitignore.write_text(CONSUMER_AUTO_RESEARCH_GITIGNORE, encoding="utf-8")

    # Keep only the minimum scaffold (strip any live template loop debris from the copy).
    auto = root / ".auto-research"
    (auto / "tasks").mkdir(parents=True, exist_ok=True)
    (auto / "threads").mkdir(parents=True, exist_ok=True)
    for folder in (auto / "tasks", auto / "threads"):
        for path in list(folder.iterdir()):
            if path.name == "README.md":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    for name in ("scheduler.json", "threads.json"):
        stray = auto / name
        if stray.is_file():
            stray.unlink()
    for lock in auto.glob("*.lock"):
        lock.unlink()
    # Empty seed on disk (gitignored on consumers; never the template's live queue).
    (auto / "state.json").write_text(EMPTY_AUTO_RESEARCH_STATE, encoding="utf-8")


def slugify_name(raw: str) -> str:
    """Stable project identity slug for config.yml ``name``."""
    slug = re.sub(r"[^a-z0-9]+", "-", raw.strip().lower()).strip("-")
    if not slug or not re.match(r"^[a-z]", slug):
        raise SystemExit(
            f"invalid project name {raw!r}: need a slug starting with a letter "
            "(lowercase letters, digits, hyphens)"
        )
    return slug[:63]


def write_config(root: Path, *, name: str, package: str | None) -> None:
    package_line = f"package: {package}" if package else "package: null"
    lib_flag = "true" if package else "false"
    version = "0.1.0"
    # Prefer the template checkout's config.yml os_version (copied into dest already).
    cfg = root / "config.yml"
    if cfg.is_file():
        match = re.search(r'(?m)^\s*os_version:\s*["\']?([^"\'\n]+)["\']?\s*$', cfg.read_text(encoding="utf-8"))
        if match and match.group(1).strip():
            version = match.group(1).strip()
    slug = slugify_name(name)
    display = name.strip() or slug
    intro = (
        "Shared lab OS: references, labs, and wiki are the default triad; notes and lib are optional. "
        "Threads under .auto-research drive the agent loop."
    )
    intro_yaml = intro.replace("\\", "\\\\").replace('"', '\\"')
    title_yaml = display.replace("\\", "\\\\").replace('"', '\\"')
    (root / "config.yml").write_text(
        f"""# Lab repository config (project zone — not named after any template).
# Identity: ``name`` is the stable slug; ``title`` / ``intro`` are display chrome (never synced).
os_version: "{version}"
name: {slug}
title: "{title_yaml}"
intro: "{intro_yaml}"
features:
  notes: false
  lib: {lib_flag}
{package_line}
loop_schema: auto-research-1
""",
        encoding="utf-8",
    )
    # Human README only (project identity). AGENTS.md / CLAUDE.md come from the template copy  # rules-lint: allow
    # and keep OS-syncing via sync_apply — do not rewrite them here.
    (root / "README.md").write_text(
        f"""# {display}

Management toolkit for this agentic research project: literature, experiments, knowledge, notes,
code, and progress live as files; the agent does routine work; you steer and decide.

Agents read [`AGENTS.md`](AGENTS.md). This page is for you: what the lab covers and how to use it.

## How you work

The only command you need to run yourself:

```bash
./run.sh    # prints host/port — open the dashboard
```

The first run may create `.venv` and download pinned frontend vendor libraries (needs network
once). From there, **dashboard + agent chat** cover the research loop. In your coding assistant
opened on this repo:

1. **Steer in plain language** — topic choice, literature, experiments, coding, analysis, write-ups.
2. **Watch the dashboard** — References, Labs, Wiki, Threads, and the task queue.
3. **Answer when asked** — decisions land in Threads; reply there or in chat.

You do not need skill names or scripts. Say what you want; the agent routes via `AGENTS.md`.

## What this lab helps you do

| Capability | Examples |
|---|---|
| Topic & progress | Aim the research loop; see what’s next / blocked; pause or resume |
| Literature | Discover, archive, and reproduce papers under `references/` |
| Experiments | Open dated labs; run sweeps; analyze results |
| Coding & tools | Implement in labs; promote proven code into `lib/` |
| Knowledge | Query what you already know; ingest findings into the wiki |
| Notes & manuscripts | Long-form write-ups under `notes/` when enabled |
| Decisions | Threads for scope, compute, and judgment calls |
| Landing work | Commit/push on the research branch (you merge `main` when ready) |

In chat, say it in plain language — for example:

| You might say | What happens |
|---|---|
| “Find papers on … and archive the best ones” | Literature discovery + fetch |
| “Reproduce the claims in reference …” | Isolated reproduce attempt |
| “Open a lab on whether …” | Dated experiment with a closed question |
| “Run / resume the research loop” | Autonomous ticks over the task queue |
| “Pause the loop” / “What’s blocked?” | Loop control and status |
| “What do we already know about …?” | Wiki lookup |
| “Ingest this into the wiki” | Compile durable, cited claims |
| “Promote validated code into the package” | Grow `lib/` when enabled |
| “Land my changes” | Commit/push on the research branch (not `main`) |

Decision-shaped asks → Thread (chat or dashboard).

## Where science lives

| Folder | Meaning |
|---|---|
| `references/` | External papers and provenance |
| `labs/` | Dated experiments |
| `wiki/` | Compiled, cited knowledge |
| `notes/` | Optional manuscripts |
| `lib/` | Optional shared package |
| `.auto-research/` | Loop + Threads |
| `skills/` | Procedures the agent follows |
| `dashboard/` | The UI you browse |

Optional `notes/` / `lib/`: enable when you need them (say so in chat).
Dashboard title / intro: `config.yml` (`title`, `intro`).
""",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="project identity slug (also seeds display title)")
    parser.add_argument("--dest", type=Path, required=True, help="new lab directory")
    parser.add_argument("--package", default=None, help="optional lib package import name")
    parser.add_argument("--from", dest="source", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--git-init", action="store_true")
    args = parser.parse_args(argv)
    source = args.source.resolve()
    dest = args.dest.resolve()
    copy_template(source, dest)
    # Remove template-named config if the copy still had a legacy filename.
    legacy = dest / "autolab.yml"
    if legacy.is_file():
        legacy.unlink()
    # Template-only CI must not ship into consumers.
    for name in ("release-tag.yml", "autolab-sync.example.yml", "lab-os-sync.example.yml"):
        wf = dest / ".github" / "workflows" / name
        if wf.is_file():
            wf.unlink()
    # Belt-and-suspenders if an old checkout still had the previous skill name.
    legacy_skill = dest / "skills" / "manage-projects"
    if legacy_skill.exists():
        shutil.rmtree(legacy_skill) if legacy_skill.is_dir() else legacy_skill.unlink()
    empty_project_zone(dest)
    write_config(dest, name=args.name, package=args.package)
    localize_auto_research(dest)
    # Consumer sync workflow lives in this skill; template .github/workflows/ stays template-only.
    # Same helper as sync_apply — upserts on every later Lab OS sync too.
    install_lab_os_sync_workflow(source, dest, dry_run=False)
    if args.git_init:
        subprocess.run(["git", "init", "-b", "main"], cwd=dest, check=True)
        subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
        subprocess.run(
            [
                "git",
                "-c", "user.email=lab@local",
                "-c", "user.name=Lab Scaffold",
                "commit",
                "-m",
                f"Initialize {args.name}",
            ],
            cwd=dest,
            check=True,
        )
    print(f"created {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
