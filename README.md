# Autolab

Autolab is a **lab operating system** for agent-friendly research: literature in `references/`, dated experiments in `labs/`, cited knowledge in `wiki/`, procedures in `skills/`, and a dashboard that keeps you in the loop with the agent via Threads.

This repository is the **template**. Domain science does not live here — you scaffold a consumer lab, then fill it with your papers, experiments, and claims.

Agent operating instructions live in [`AGENTS.md`](AGENTS.md). Deeper design notes live in [`wiki/project/`](wiki/project/).

## Quick start (this checkout)

```bash
# Seed local loop + Threads state when missing
.venv/bin/python skills/auto-research/scripts/seed_local.py

# Dashboard
./run.sh check
./run.sh start    # prints host/port
./run.sh status
./run.sh stop
```

Port comes from `config.yml` `name` (hash in 1024–65535). Override with `dashboard.port` or `<NAME>_DASHBOARD_PORT`.

## Create a new lab from this template

From the Autolab repo root:

```bash
python skills/autolab/scripts/create_project.py \
  --name my-lab \
  --dest ../my-lab \
  --git-init
```

Optional: `--package mypkg` enables `features.lib` and sets the import name.

What you get: a consumer checkout with empty `references/` / `labs/` / wiki scaffolds, `skills/` + `dashboard/`, Threads under `.auto-research/`, and **no** `skills/autolab/` (template-admin only).

Then in the new lab:

```bash
cd ../my-lab
.venv/bin/python skills/auto-research/scripts/seed_local.py   # if needed
./run.sh start
```

Full procedure: [`skills/autolab/SKILL.md`](skills/autolab/SKILL.md).

## Sync the OS into an existing lab

When Autolab ships skills or dashboard updates:

```bash
python skills/autolab/scripts/sync_apply.py \
  --from . \
  --to ../my-lab \
  --bump-pin
```

Use `--dry-run` first. Sync upserts the OS floor (`skills/` except `autolab`, `dashboard/`, floor READMEs, …); it never overwrites your papers, dated labs, domain wiki, or consumer `README.md` / `config.yml` body. Details and the sync registry live in `skills/autolab`.

## What you can do day to day

| Goal | Where |
|---|---|
| Browse papers, labs, wiki, Threads | Dashboard (`./run.sh start`) |
| Steer the agent / answer decisions | Threads (dashboard or `skills/research-threads`) |
| Run or resume autonomous work | Ask the agent, or `skills/auto-research` |
| Add a dated experiment | `skills/create-lab` |
| Fetch / reproduce literature | `skills/discover-references`, `fetch-reference`, `reproduce-reference` |
| Compile findings | `skills/wiki-ingest` |
| Promote proven code into a package | `skills/promote-to-lib` (when `features.lib`) |
| Skill catalog | [`skills/README.md`](skills/README.md) |

Default lab shape: `references` + `labs` + `wiki` plus skills, dashboard, and Threads. Enable `notes` / `lib` via directories and `config.yml` `features`.

## Layout (human map)

| Path | What it is |
|---|---|
| `references/` | External papers and provenance |
| `labs/` | Dated experiments |
| `wiki/` | Compiled, cited knowledge (`wiki/project/` = OS manual) |
| `notes/` | Optional long-form manuscripts |
| `lib/` | Optional installable package |
| `.auto-research/` | Loop state + Threads (local after scaffold) |
| `skills/` | Procedures any agent can follow |
| `dashboard/` | Web UI over the filesystem |
| `config.yml` | Project `name`, features, OS version pin |
| `AGENTS.md` | Instructions for coding agents |
| `skills/autolab/` | Template only: create + sync (absent in consumers) |

How knowledge moves: papers → reproduce / labs → wiki (and optionally `lib/` / `notes/`). See [`wiki/project/what-autolab-is.md`](wiki/project/what-autolab-is.md).
