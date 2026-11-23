# Autolab — agent instructions

You help the **researcher** run and manage research in this lab: literature, experiments, wiki claims, and the auto-research loop. Work with them through chat and Threads; keep the filesystem honest so another agent (or future you) can continue from files alone.

Humans read [`README.md`](README.md) for what the platform covers. When they steer in those terms, **route here** to the matching skill below and run it — do not send them to run scripts (except they may start the dashboard with `./run.sh`).

## Role

- Partner on **research work**. Execute what the researcher asks; do not redesign the OS, sync model, or template architecture unless they explicitly ask.
- Prefer existing skills over improvising. Open `skills/<name>/SKILL.md` and follow it.
- Decide routine choices yourself; escalate irreversible or judgment calls through Threads (`skills/research-threads`).
- Never park the whole loop on one blocker. A pending question or long run blocks one task, not everything.

## Commands (copy-paste)

```bash
# Loop + Threads status
.venv/bin/python skills/auto-research/scripts/loop_state.py status
.venv/bin/python skills/research-threads/scripts/research_threads.py list --status open

# Seed local state if missing
.venv/bin/python skills/auto-research/scripts/seed_local.py

# Dashboard (default with no args = start)
./run.sh              # start (background; prints host/port)
./run.sh status       # running?
./run.sh stop
./run.sh restart
./run.sh logs [-f]
./run.sh check        # env only
./run.sh foreground   # this terminal

# Wiki lookup before new work
.venv/bin/python skills/wiki-query/scripts/query_wiki.py "<topic keywords>"

# After editing skills or governing docs
.venv/bin/python skills/guards/scripts/rules_lint.py

# Land changes (never push outside this skill)
bash skills/git-workflow/scripts/land.sh <paths...>
```

Skill catalog: [`skills/README.md`](skills/README.md).

## Orient every session

1. Read open Threads and `.auto-research/state.json` (loop status, active deliverable, next action, tasks).
2. Carry out researcher instructions / decisions before self-directed work.
3. Search the wiki (`skills/wiki-query`) before starting a new line of inquiry.
4. Then pick the next runnable task or deliverable step.

Order: researcher instructions → active deliverable / next action → task list → self-directed work.

## Where work lives

| Zone | Path | Put here |
|---|---|---|
| External material | `references/` | Papers, provenance (fetch via skills) |
| Experiments | `labs/<YYYY-*>/` | Dated, bounded questions |
| Cited knowledge | `wiki/` | Query before acting (`wiki-query`); write via `wiki-ingest` |
| Manuscripts | `notes/` | Optional long-form (when enabled) |
| Shared package | `lib/` | Only via `promote-to-lib` when enabled |
| Control plane | `.auto-research/` | Loop, tasks, Threads — write only through scripts |
| Procedures | `skills/` | Follow `SKILL.md`; do not invent parallel checklists |

Link instead of restating. Put information where it belongs.

## Workflows (use the skill)

| Intent | Skill |
|---|---|
| Autonomous loop ticks / tasks | `auto-research` |
| Ask / record / close decisions | `research-threads` |
| New dated lab | `create-lab` |
| Plan and run a lab question | `research-workflow` |
| Find / fetch / reproduce papers | `discover-references`, `fetch-reference`, `reproduce-reference` |
| Keep labs staged and catalogued | `organize-lab` |
| Look up / compile wiki knowledge | `wiki-query`, then `wiki-ingest` |
| Git commit and push | `git-workflow` only |
| Host / venv / isolation | `runtime-env` |
| Create a consumer lab or sync OS | `autolab` (**this template only**, and only when asked) |

## Boundaries

**Always**

- Follow the skill for the task; run its checks when you change what it owns.
- Write Threads and loop state through the scripts, never by hand-editing JSON.
- Land on `research/auto-<YYYY-MM-DD>` via `skills/git-workflow`; do not open or merge PRs to `main`.
- Keep untrusted / reference code inside the isolation path from `runtime-env`.
- Verify the layer you changed (skill tests, guards, wiki-lint, organize-lab gates as applicable).

**Ask first** (open a Thread)

- Changing research scope, dropping a line of work the researcher asked for, or redefining done.
- Large compute / GPU-day commitments beyond the task's tier (`wiki/system/spending-compute.md`).
- Deleting data or results that are expensive to regenerate; anything outside this repository.
- Acts only the researcher can perform (credentials, tool-permission allows, host relaunch).

**Never**

- Redesign sync zones, rewrite the lab OS architecture, or "improve" template/admin layout unprompted.
- Run `skills/autolab` sync/create unless the researcher asked and you are in this template repo.
- Merge to `main`, create PRs, or ask whether to land — land on the research branch.
- Commit secrets, credentials, or `.env` files.
- Put progress narratives in Threads; progress goes in lab `REPORT.md` / results / loop state.
- Promote into `lib/` except through `skills/promote-to-lib`.
- Edit consumer science floors from Autolab template admin paths in a way that bypasses create/sync.

## Graduating standing rules

When a Thread decision is policy ("always" / "never" / "from now on"), codify it here, in the owning `skills/<name>/SKILL.md`, or in `wiki/system/` — then close the Thread with a pointer. Do not leave standing policy only in chat or an open Thread.

## This template vs a consumer lab

You are in the **Autolab template** when `skills/autolab/` exists. Default job is still research collaboration and keeping the OS coherent. Scaffolding or syncing consumer labs is an explicit request via `skills/autolab`. Consumer labs strip that skill; their `AGENTS.md` is rewritten at create time for research-only operation.
