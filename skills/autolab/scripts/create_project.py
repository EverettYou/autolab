#!/usr/bin/env python3
"""Create a new consumer lab from this template tree (full copy, then empty project zone).

Usage (Autolab template only):
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

SKIP = {".git", ".venv", ".cache", ".pytest_cache", "__pycache__", ".runtime", ".tmp", "tools"}
# Template-only: never ship this skill into consumer labs.
TEMPLATE_ONLY_SKILLS = {"autolab"}


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

    # Optional layers off by default: keep empty notes README; leave lib stub or remove content
    notes = root / "notes"
    if notes.is_dir():
        for path in list(notes.iterdir()):
            if path.name != "README.md":
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()


def localize_auto_research(root: Path) -> None:
    """After scaffold: keep minimum .auto-research/ on disk; stop tracking/syncing it.

    The template tracks the whole minimum scaffold. A consumer treats the folder as live local
    data (gitignore the whole tree) — later sync_apply skips it when present.
    """
    gitignore = root / ".gitignore"
    block = (
        "# Local loop + Threads store: scaffold copied once, then never tracked / re-synced.\n"
        ".auto-research/\n"
    )
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        # Drop template .auto-research rules; replace with whole-folder ignore.
        lines = []
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith(".auto-research/") or stripped.startswith("!.auto-research/"):
                continue
            if stripped.startswith("#") and ".auto-research" in stripped:
                continue
            if "research queue" in stripped.lower() or "Threads (state" in stripped:
                continue
            lines.append(line)
        text = "".join(lines)
        if ".auto-research/" not in text:
            if text and not text.endswith("\n"):
                text += "\n"
            text += "\n" + block
        gitignore.write_text(text, encoding="utf-8")
    else:
        gitignore.write_text(block, encoding="utf-8")

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
    # Always ship the empty tracked seed (never the template's live queue).
    (auto / "state.json").write_text(
        '{\n'
        '  "schema": "auto-research-1",\n'
        '  "status": "paused",\n'
        '  "updated": "1970-01-01T00:00:00Z",\n'
        '  "active_deliverable": null,\n'
        '  "next_action": "Start the loop only on your own branch after the researcher '
        'sets an active deliverable.",\n'
        '  "last_action": null,\n'
        '  "tasks": [],\n'
        '  "threads": []\n'
        '}\n',
        encoding="utf-8",
    )


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
    (root / "config.yml").write_text(
        f"""# Lab repository config (project zone — not named after any template).
# Identity: ``name`` is required and stable. Display title lives in dashboard site.json only.
os_version: "{version}"
name: {slug}
features:
  notes: false
  lib: {lib_flag}
{package_line}
loop_schema: auto-research-1
""",
        encoding="utf-8",
    )
    # Human README + agent AGENTS.md (split audiences; see Autolab root docs).
    (root / "README.md").write_text(
        f"""# {display}

Lab repository built on Autolab: archive literature in `references/`, run dated experiments
in `labs/`, compile cited knowledge in `wiki/`, and steer work through `skills/` and the
dashboard (Threads).

Agent operating instructions: [`AGENTS.md`](AGENTS.md). Skill catalog: [`skills/README.md`](skills/README.md).

## Quick start

```bash
.venv/bin/python skills/auto-research/scripts/seed_local.py   # if state is missing
./run.sh check
./run.sh start    # prints host/port
./run.sh status
./run.sh stop
```

## Day to day

| Goal | Where |
|---|---|
| Browse papers, labs, wiki, Threads | Dashboard (`./run.sh start`) |
| Steer the agent / answer decisions | Threads (dashboard or `skills/research-threads`) |
| Run or resume autonomous work | Ask the agent, or `skills/auto-research` |
| New dated experiment | `skills/create-lab` |
| Literature → reproduce → lab → wiki | see `skills/README.md` |

## Layout

| Path | Role |
|---|---|
| `config.yml` | Project ``name``, features, OS version pin |
| `references/` | External papers and provenance |
| `labs/` | Dated experiments |
| `wiki/` | Compiled, cited knowledge |
| `notes/` | Optional long-form manuscripts |
| `lib/` | Optional installable package |
| `.auto-research/` | Loop + Threads (local; gitignored after scaffold) |
| `skills/` | Procedures |
| `dashboard/` | Web UI |
| `AGENTS.md` | Instructions for coding agents |

Enable `notes` / `lib` via directories and `config.yml` `features`.
Dashboard display title is `dashboard/frontend/site.json` (not config).
""",
        encoding="utf-8",
    )
    site = root / "dashboard" / "frontend" / "site.json"
    site.parent.mkdir(parents=True, exist_ok=True)
    defaults = root / "dashboard" / "frontend" / "site.defaults.json"
    if defaults.is_file():
        data = json.loads(defaults.read_text(encoding="utf-8"))
    else:
        data = {}
    data["title"] = display
    site.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        f"""# {display} — agent instructions

You help the **researcher** run and manage research in this lab: literature, experiments,
wiki claims, and the auto-research loop. Work with them through chat and Threads; keep the
filesystem honest so another agent can continue from files alone.

Human project map: [`README.md`](README.md). Do not treat the README as your operating manual.

## Role

- Partner on **research work**. Do not redesign the lab OS, sync model, or folder architecture
  unless the researcher explicitly asks.
- Prefer skills over improvising. Open `skills/<name>/SKILL.md` and follow it.
- Decide routine choices yourself; escalate irreversible or judgment calls through Threads
  (`skills/research-threads`).
- Never park the whole loop on one blocker. A pending question or long run blocks one task,
  not everything.

## Commands

```bash
.venv/bin/python skills/auto-research/scripts/loop_state.py status
.venv/bin/python skills/research-threads/scripts/research_threads.py list --status open
.venv/bin/python skills/auto-research/scripts/seed_local.py
./run.sh check && ./run.sh start
.venv/bin/python skills/wiki-query/scripts/query_wiki.py "<topic keywords>"
bash skills/git-workflow/scripts/land.sh <paths...>
```

Skill catalog: [`skills/README.md`](skills/README.md).

## Orient every session

1. Open Threads and `.auto-research/state.json` (status, deliverable, next action, tasks).
2. Carry out researcher instructions / decisions before self-directed work.
3. Search the wiki (`skills/wiki-query`) before a new line of inquiry.
4. Then pick the next runnable task or deliverable step.

Order: researcher instructions → active deliverable / next action → task list → self-directed work.

## Where work lives

| Zone | Path |
|---|---|
| External material | `references/` |
| Experiments | `labs/<YYYY-*>/` |
| Cited knowledge | `wiki/` (`wiki-query` then `wiki-ingest`) |
| Manuscripts | `notes/` (when enabled) |
| Shared package | `lib/` only via `promote-to-lib` |
| Control plane | `.auto-research/` (scripts only) |
| Procedures | `skills/<name>/SKILL.md` |

## Workflows

| Intent | Skill |
|---|---|
| Loop / tasks | `auto-research` |
| Decisions | `research-threads` |
| New lab | `create-lab` |
| Lab question | `research-workflow` |
| Literature | `discover-references`, `fetch-reference`, `reproduce-reference` |
| Wiki lookup / compile | `wiki-query`, then `wiki-ingest` |
| Git | `git-workflow` only |
| Host / venv | `runtime-env` |

## Boundaries

**Always:** follow the skill; write Threads/loop state through scripts; land on
`research/auto-<YYYY-MM-DD>` via `git-workflow`; isolate untrusted code per `runtime-env`;
verify the layer you changed.

**Ask first:** scope changes, large compute beyond the task tier, deleting expensive results,
acts only the researcher can perform.

**Never:** redesign the OS unprompted; merge/PR to `main` or ask whether to land; commit
secrets; put progress in Threads (use lab `REPORT.md` / loop state); edit `lib/` except through
`promote-to-lib`.

## Graduating standing rules

When a Thread decision is lasting policy, codify it here, in the owning skill, or in
`wiki/project/`, then close the Thread with a pointer.
""",
        encoding="utf-8",
    )
    # Consumer tool bootstrap pointer (not template skill prose).  # rules-lint: allow
    (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")  # rules-lint: allow


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
