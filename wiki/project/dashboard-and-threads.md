---
title: Dashboard and Threads
page_type: project
status: active
updated: 2026-11-20
source_refs:
  - README.md
  - .auto-research/README.md
  - skills/research-threads/SKILL.md
  - skills/auto-research/SKILL.md
idea_ids: []
project_topics:
  - Research Pipeline
  - Lab OS Architecture
  - Lab Practice
---

# Dashboard and Threads

**Summary**: How to run the control surface day to day — open the dashboard, steer with Threads,
manage the task queue, start/pause the auto-research loop, and monitor what is happening. The
filesystem under `.auto-research/` is the truth; the UI is a view over those files.

**Sources**: [README](../../README.md) · [.auto-research README](../../.auto-research/README.md) ·
`skills/research-threads` · `skills/auto-research`

**Last updated**: 2026-11-20

## Open the dashboard

```bash
./run.sh start          # background; prints host/port
./run.sh status         # is it up?
./run.sh logs -f        # follow server log
./run.sh stop
```

Port is derived from `config.yml` `name` (hash in 1024–65535, then probe). Override with
`dashboard.port` or `<NAME>_DASHBOARD_PORT` (from `name`). Same `name` across checkouts is the same project and may
reclaim its port. Display title is `dashboard/frontend/site.json`.
First time on a checkout, seed the store if missing:

```bash
.venv/bin/python skills/auto-research/scripts/seed_local.py
```

**Nav:** References · Labs · Wiki · Threads (Notes / API when enabled). **Home** (`/`) shows loop
state and the task queue. **Auto Research** (`/auto-research`) is the full queue page — open it from
Home → “Open details”. System menu → Files / Skills / Settings.

What the dashboard **writes**: Thread open / reply / close / reopen (as you), and **task reorder**.
It does **not** start or pause the loop, add tasks, or mark tasks done — those go through the
scripts (or you tell an agent to run them).

## Threads — open, reply, close

Threads are the researcher↔agent channel. Meta in `.auto-research/state.json`; messages in
`.auto-research/threads/<id>.json`. Always use the script (or the dashboard, which calls it).

```bash
M=".venv/bin/python skills/research-threads/scripts/research_threads.py"
```

### On the dashboard (Threads)

1. Open **Threads** (`/threads`). Open threads sort first; badge **awaiting reply** means the last
   message is an agent `question` and a task is blocked on that thread.
2. **Open a thread:** New thread → title, instruction, optional lab, category (`direction` default
   for you), priority → **Open thread**. Posted as `author=user` (an instruction the loop treats as
   first-class input).
3. **Reply:** open the thread → choose Kind (`decision` to answer a question, `instruction` for a
   new directive, `reply` otherwise) → **Post reply**.
4. **Close:** write the closing note in the message box first → **Close thread** (red). Empty notes
   are refused. Closed threads stay readable; **Reopen** needs a reason.
5. Each thread page also shows the equivalent terminal commands under “Or from a terminal”.

### From a terminal (or ask an agent to scribe)

| Action | Command |
| --- | --- |
| List | `$M list --status open` |
| Open (your instruction) | `$M open --author user --title "…" --content "…"` |
| Open (agent question) | `$M open --title "…" --content-file brief.md` |
| Answer | `$M reply thread-042 --author user --type decision --content "…"` |
| Further instruction | `$M reply thread-042 --author user --type instruction --content "…"` |
| Close | `$M close thread-042 --author user --content "…"` |
| Reopen | `$M reopen thread-042 --author user --content "…"` |

You can also say the instruction in chat and ask the agent to record it — same script, professional
English, no hand-edits of the JSON.

## Auto-research loop — start, pause, aim

```bash
L=".venv/bin/python skills/auto-research/scripts/loop_state.py"
$L status                 # flag + liveness + top tasks + awaiting_human
```

`status` in `state.json` is only a **flag** (`running` / `paused` / `idle`). It is not proof that
ticks are firing. Live ticks need a **scheduler this agent owns** — see
`skills/auto-research/SKILL.md` §Starting the loop.

| Want | Do |
| --- | --- |
| **Start / resume** | Ask the agent to start the loop, or: register a schedule (`$L scheduler --set … --owner <self>`), then `$L start`. Same-chat ticks use session cron / product automations; headless same-owner ticks use `loop_runner.py serve --owner <self>`. |
| **Pause** | `$L pause [--summary "…"]`, and cancel that owner's cron / stop `loop_runner` / pause Scheduled. |
| **Set the aim** | `$L set-deliverable --lab <lab-id> --summary "…" --acceptance "…"` (or `--clear`). `$L set-next --text "…"`. |
| **Idle** | `$L idle` — almost never; means nothing can proceed without you. |

Do not expect a Start/Pause button on the dashboard — by design the loop is owned by the agent
session that registered the scheduler.

## Tasks — add, assign, reorder, finish

Tasks are the ordered queue the loop drains. List order **is** priority (index 0 first among
items that fit the GPU tier and are unblocked).

| Action | How |
| --- | --- |
| **Add** | `$L task add --title "…" --for integrator --gpu free --time 5min [--lab <id>] [--top \| --before <id> \| --after <id>] --content-file body.md` Body must have `## Goal` / `## Work` / `## Done when` (see `.auto-research/tasks/README.md`). |
| **Assign (`for`)** | Role string on the task: `scout`, `reproducer`, `integrator`, `auditor`, `maintain`, `auto`, or `all` (comma-separated). Change later with `$L task set <id> --for …`. The router picks work that matches the tick; `for` is the assignment signal. |
| **Reorder** | **Dashboard:** Auto Research → drag the grip (or ↑/↓ with the grip focused). Clear any filter first. **CLI:** `$L task move <id> --top \| --bottom \| --before <id> \| --after <id>`. |
| **Block / unblock** | `$L task block <id> --on "researcher decision in thread-042"` · `$L task unblock <id>`. |
| **Finish (close)** | `$L task done <id> [--summary "…"]` — **deletes** the meta row and `tasks/<id>.md`. There is no “done” checkbox on the dashboard. |

## Monitor on the dashboard

| Look here | What you see |
| --- | --- |
| **Home** | Loop status, next/last action skim, task list, open-thread counts → jump to Threads / Auto Research |
| **Auto Research** (`/auto-research`) | Status badge + **Monitor** / liveness line, deliverable, **Waiting** (threads awaiting your reply), next/last action, full task table (For / GPU / Time / blocked). Click a task to read its body and linked labs. |
| **Threads** | Open vs closed, **awaiting reply**, full message history |
| **Labs** | Side panel of related threads and tasks for that lab |
| **`$L status` / `$M list`** | Same facts from the terminal when the UI is down |

Refresh after file changes — the dashboard reads the repo; it does not invent a second database.
If Monitor says `UNSCHEDULED` or `STALE` while the flag is `running`, ticks are not actually live.

## Related pages

- [[project/what-autolab-is|Autolab]]
- [[project/distillation-tower|Distillation tower]]
- [[project/spending-compute|Spending compute]]
