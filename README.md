# Autolab

Autolab is a **management toolkit for agentic research**: literature, experiments, knowledge, notes, code, and project progress live as ordinary files you can see; an agent does the routine work; you steer and decide. Built for researchers who want to run an agentic research project without turning the repo into a black box.

This repository is the **template**. Your domain science lives in a lab you create from it — not here.

Agents read [`AGENTS.md`](AGENTS.md) (how to execute). This page is for you: what the platform covers and how to use it. Design notes: [`wiki/system/`](wiki/system/).

## How you work with it

The only command you need to run yourself:

```bash
./run.sh    # prints host/port — open the dashboard
```

The first run may create `.venv` and download pinned frontend vendor libraries (needs network once; then offline). From there, **dashboard + agent chat** cover the research loop. In your coding assistant (Cursor, Claude Code, Codex, …) opened on the lab:

1. **Steer in plain language** — topic choice, literature, experiments, coding, analysis, write-ups.
2. **Watch the dashboard** — References, Labs, Wiki, Threads, and the task queue.
3. **Answer when asked** — irreversible or judgment calls show up as Threads; reply there or in chat.

You do not need to memorize scripts or skill names. Say what you want; the agent follows `AGENTS.md` into the right workflow.

## What this platform helps you do

End-to-end research work, managed in one place:

| Capability | Examples |
|---|---|
| Project setup | Scaffold a new lab from this template; sync OS updates into an existing lab |
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
| “Scaffold a new lab called X next to this repo” | New consumer project from this template |
| “Sync Autolab OS into ../my-lab” | Push skills + dashboard updates into that lab |
| “Find papers on … and archive the best ones” | Literature discovery + fetch |
| “Reproduce the claims in reference …” | Isolated reproduce attempt |
| “Open a lab on whether …” | Dated experiment with a closed question |
| “Run / resume the research loop” | Autonomous ticks over the task queue |
| “Pause the loop” / “What’s blocked?” | Loop control and status |
| “What do we already know about …?” | Wiki lookup before more work |
| “Ingest this lab / paper into the wiki” | Compile durable, cited claims |
| “Promote the validated code into the package” | Grow `lib/` when that feature is on |
| “Land my changes” / “Commit and push the research branch” | Safe git workflow (no merge to `main`) |

Decision-shaped asks (“should we drop this line of work?”, “OK to burn a GPU-day?”) belong in a Thread — say so in chat, or open one in the dashboard.

## This template vs your lab

| | Autolab (this repo) | Your lab (created from it) |
|---|---|---|
| Purpose | Ship the OS; create & sync labs | Hold *your* papers, labs, wiki |
| Day to day | Create a lab, sync OS, try the loop | Full research management |
| `skills/autolab/` | Present (create + sync) | Absent |

A new lab starts with empty science floors and owns its own content. Later OS sync updates skills and the dashboard; it does not copy or overwrite your papers, labs, wiki, notes, or lib.

Default lab shape: `references` + `labs` + `wiki`, plus skills, dashboard, and Threads. Optional `notes/` (manuscripts) and `lib/` (shared package) — enable when you need them (say so in chat).

## Where your science lives

| Folder | Meaning |
|---|---|
| `references/` | External papers and provenance |
| `labs/` | Dated experiments |
| `wiki/` | Compiled, cited knowledge |
| `notes/` | Optional long-form manuscripts |
| `lib/` | Optional installable package |
| `.auto-research/` | Loop + Threads (local control plane) |
| `skills/` | Procedures the agent follows |
| `dashboard/` | The UI you browse |

Flow: papers → reproduce / labs → wiki (and optionally `lib/` / `notes/`). More: [`wiki/system/what-autolab-is.md`](wiki/system/what-autolab-is.md).
