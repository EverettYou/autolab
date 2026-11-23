---
name: auto-research
description: Run the autonomous research loop as bounded ticks over `.auto-research/state.json`. A research tick advances the active deliverable or the best runnable task (references, labs, promotion, audits); a supervisor tick keeps the repository and the loop state honest, compiles results into the wiki, reorders and refills the task list, detects stalls, and escalates real decisions through research-threads.
usage: Use when asked to run, resume, pause, or supervise autonomous research; to add, reorder, block, or finish tasks; or to hand off a session so another agent can continue from files alone.
---

# Autonomous research loop

The program is open-ended: collect and reproduce what the literature offers, test our own questions
in labs, promote what holds up into `lib/` when enabled, and keep the package and wiki honest.
The loop never concludes on its own and never parks. It is a sequence of bounded ticks, and all of
its state lives in files, so any agent with any tool can run the next tick.

This skill is the procedure behind the loop / orientation / never-park rules in `AGENTS.md`.
It does not restate the rules it depends on; follow them where they live:

- orientation order, decisions, never parking, git, secrets, evidence: `AGENTS.md`;
- GPU eligibility, the training gate, time tiers, and the `gpu`/`time`/`blocked_on` fields:
  `wiki/project/spending-compute.md`;
- comparing and reporting numbers: `wiki/project/honest-comparison.md`;
- asking the researcher, recording their words, closing threads: `skills/research-threads`
  (one concern per thread; close when done; progress in the lab report, not the threads store).

## State

This repository tracks the **minimum** `.auto-research/` scaffold (format READMEs + empty `state.json`).
Consumer labs gitignore the whole folder after create (live checkout data). A missing
`state.json` is filled by `seed_local.py`. The file holds the loop: `status` (`running`,
`paused`, or `idle`), the `active_deliverable` (a lab, a summary, and acceptance criteria) or null,
a concrete `next_action`, `last_action`, the ordered `tasks` (scheduling meta only), and ordered
`threads` (Thread meta only — no messages). Each task has an `id`, `title`, `for`, `gpu`, `time`,
`blocked_on`, `related_labs`, `added`, and a body in `.auto-research/tasks/<id>.md`. Each Thread’s
messages are `.auto-research/threads/<id>.json` → `{"messages": [...]}`. Change the store only
through the scripts; they validate every write and replace files atomically under a shared lock.

```bash
L=".venv/bin/python skills/auto-research/scripts/loop_state.py"
$L status                                  # state, top of the task list, open threads, and warnings
$L start | pause | idle [--summary "..."]
$L set-next --text "..."
$L set-deliverable --lab <lab-id> --summary "..." --acceptance "..." [--acceptance "..."] | --clear
$L log-action --summary "research: ..." [--next "..."]
$L task list [--unblocked | --blocked] [--fits free|light|heavy] [--json]
$L task show <id>
$L task add --title "..." --for integrator --gpu free --time 5min [--lab <lab-id>] \
    [--top | --before <id> | --after <id>] (--content "..." | --content-file body.md)
# `--content` = ## Goal / ## Work / ## Done when only (see `.auto-research/tasks/README.md`)
$L task move <id> (--top | --bottom | --before <id> | --after <id>)
$L task set <id> [--title "..."] [--for ...] [--gpu ...] [--time ...] [--lab <lab-id>]
$L task done <id> [--summary "..."]     # deletes the item and its body
$L task block <id> --on "researcher decision in thread-042"
$L task unblock <id>
$L scheduler [--set session-cron|runner|external <job-id> --every-min N --owner <self> | --clear | --verify <listed job ids…>]
$L validate
.venv/bin/python skills/auto-research/scripts/auto_research_lint.py  # state + tasks + threads format
.venv/bin/python skills/auto-research/scripts/fs_health_lint.py    # repository layout patrol
```

`running` is a flag the loop wrote about itself. It is not evidence that anything fires ticks, and it
is never the answer to "is the loop running?" (see [Starting the loop](#starting-the-loop)).
`running` means ticks should proceed. `paused` means the researcher, or a task they authorized, stopped
the loop; run ticks only when asked, and `start` again when told to resume. `idle` means nothing can
proceed without the researcher; it should almost never happen, because work without a GPU and
without an answer always exists.

## Starting the loop

"Resume", "start", or "run the loop" usually means the researcher is leaving and expects ticks to
continue without them. The state file cannot tell you whether that is true, so do this before
saying anything about it.

**Ownership (encoded in `scheduler.json` + `loop_runner`):** any agent may start the loop when
asked. **Who starts owns it** (`--owner <self>`). That owner alone performs ticks in **its own**
session / CLI. No agent may start or wake another product's ticks (Cursor must not
`serve --owner codex`; Codex must not register `owner=claude` and expect Claude to tick).

**Same chat vs same-owner headless** (do not conflate them):

| Want | What actually does that |
| --- | --- |
| Ticks return to **this same chat** | Claude `CronCreate` (`session-cron`), Cursor product automations, or desktop Codex "schedule this chat" (`external`) — always `--owner <self>` |
| Same **owner**, headless wake | `loop_runner serve --owner <self>` only for `claude`/`codex`: wakes that same product's CLI. Not a sticky interactive chat; progress in `.auto-research/` and `.tmp/auto-research/scheduler.log` |

1. **Ask the scheduler, not the state.** List jobs with **this product's** scheduling tools (if any).
   `loop_state.py status` prints a `loop:` line (`live`, `UNSCHEDULED`, or `STALE`) including
   `owner=…`; treat anything but `live` as "not ticking". `running` is only a flag.
2. **Create a schedule this agent owns** (`--owner` = this product, never another):

   | Kind | When | What to do |
   | --- | --- | --- |
   | **`session-cron`** | This agent has in-session cron (e.g. Claude `CronCreate`) | Recurring one-tick job in **this** session. `$L scheduler --set session-cron <job-id> --every-min 12 --owner <self>`. |
   | **`runner`** | This is Claude/Codex CLI with no in-session cron | **This** agent starts `loop_runner.py serve --owner <self>`, then `$L scheduler --set runner <pid> --every-min 12 --owner <self>`, `$L start`. Runner refuses a mismatched registered owner. |
   | **`external`** | Sticky chat via desktop Scheduled (or similar) | See [Codex desktop Scheduled](#codex-desktop-scheduled). Register with `--owner <self>` only after the task exists. |

   If none apply, run ticks only when asked. Do not claim the loop is running. Do not start another
   owner's runner "as a favor."
3. **Register and verify.** `$L scheduler --set … --owner <self>`, then `$L start`. For `runner`,
   `loop_runner.py status` must show `alive` and the same `owner`. Session-cron: `--verify`.
4. **Limits.** Session cron dies with that session. `loop_runner` outlives the chat while the machine
   is up, but each tick is a new process of **the same owner**. Desktop Scheduled needs the app
   running. No system cron/systemd for the loop here.
5. **Report only what you verified.** "Running" needs registered scheduler (`owner=…`) plus advancing
   `last_action` — and say whether ticks are same-chat or same-owner headless.
6. **Pause.** `$L pause`; also cancel this owner's cron / stop `loop_runner` / pause Scheduled.

### Codex desktop Scheduled

([docs](https://learn.chatgpt.com/docs/automations?surface=app)) CLI/IDE have no Scheduled UI.
Use desktop only when the researcher wants ticks **back in one Codex chat**: desktop app → Codex →
**local** project (the checkout with `.auto-research/`, not a worktree) → schedule that chat every
~12 min → check **Scheduled**. Keep the machine on and the app running. Otherwise, from Codex CLI,
start **`loop_runner` in that CLI session** and accept headless ticks.

## Every tick

1. **Orient.** Run `$L status` and `research_threads.py list --status open`
   (`skills/research-threads`). Researcher messages awaiting an agent come before anything else.
   The active deliverable and next action are in `.auto-research/state.json`; what a lab is doing
   now is that lab's `lab.json`.
2. **Choose the kind.** Run a research tick by default. Run a supervisor tick when about an hour of
   research ticks has passed since the last one, when a lab or a reproduction finished, when a thread
   closed, when `status` reports a stall or an empty runnable task list, or when asked.
3. **Do the tick** (sections below) within about 30 minutes of agent time. A tick never waits on a
   long program: programs of 15 minutes or more run detached, and a tick only launches or harvests
   them.
4. **Record.** Update what the next reader opens (`AGENTS.md`: filesystem is the handoff), then
   `$L log-action --summary "<research|supervisor>: <what changed>" --next "<the next concrete step>"`.
5. **Land.** Run `$L validate` (and `research_threads.py validate` if the threads store changed), the
   `land` bundle of `skills/guards` when governed files changed, then land through
   `skills/git-workflow` with explicit paths and a subject such as
   `auto(research): <summary>` or `auto(supervisor): <summary>`. Exit 2 (committed, push skipped) and
   3 (nothing to commit) block nothing; retry the push on a later tick.
6. **Report** one line when the tick runs in a conversation:
   `[auto] <research|supervisor> | step=<what> | files=<paths> | next=<next_action>`.

Every tick produces a real artifact (`AGENTS.md`: never park). A tick that only monitors a GPU, re-reads a
blocked task list, or updates status is parking. Two consecutive ticks without a substantive commit is a
stall (see below).

## Research tick

Work in this order: open researcher instructions, then the active deliverable, then `next_action`
while it still holds, then the task list, then self-directed work.

1. **Resources.** `bash skills/runtime-env/scripts/snapshot.sh --bundle router --max-age 60`; map
   `AVAIL_TIER` to the GPU tier that can run now ([router](references/router.md#resources)).
2. **Pick one step.** For a deliverable, the next unmet acceptance criterion. For the task list, clear
   stale blockers, keep the items that fit the tier (`$L task list --unblocked --fits <tier>`),
   and score them ([router](references/router.md#choosing-an-item)). The task list order is the
   supervisor's priority, one signal among several.
3. **Plan.** If the step opens a **new** topic (not continuing the same lab/attempt), run
   `wiki-query` once. Name the files the step will touch. Skip files another writer changed in the
   last 30 minutes and pick other work instead; never end the tick over it
   ([overlap guard](references/router.md#overlap-guard)).
4. **Advance** via the Role card. Open **only** the entry in **Open**; do not load other skills
   this tick unless that entry links them. Read order: `$L status` + task body → this card → one
   entry file.

   | `for` | Open | Do this tick | Done when |
   |---|---|---|---|
   | `scout` | `discover-references`; on `pass`, `fetch-reference` | One discovery pass; archive at most 1–2 `pass` hits | Candidate table returned (or negative confirm recorded); fetched ids have `provenance.json` |
   | `reproducer` | `reproduce-reference` (+ `runtime-env` isolation) | Advance one attempt one phase (PLAN→…→PROMOTE) | `gate-state.yaml` moved, or attempt disposed / dead-ended |
   | `integrator` | `promote-to-lib` (bootstrap `lib/` first if needed) | Enable/scaffold `lib/` when off, then one promote-gate step; queue `audit` after a landed promote | `lib/` importable if this tick bootstrapped it; gate phase advanced (bootstrap-only is OK — not a promote failure) |
   | `auditor` | `audit` | Review promoted package code against its evidence | Audit record under `wiki/records/audits/` (or explicit N/A) |
   | `auto` | lab trio below | Exactly one lab step in the order given | `PLAN.md` / `REPORT.md` / `lab.json` (or catalog) changed for real |
   | `maintain` | [supervisor §Keep honest](references/supervisor.md#keep-the-repository-honest) **only** | Run guards, fix cheap failures or one hygiene track; harvest due runs. No synthesize/replan here | Guards green or fix tasks queued; `last_action` names what changed |
   | `all` | Whatever skills the goal needs (agent chooses) | Composite work: pick and sequence skills by judgment; no fixed road. Body states Goal / Done when and constraints — it need not pre-name roles | Task **Done when** holds; record which skills you used in `last_action` / the task body rewrite |

   **`auto` order (pick the first that applies):** no lab yet → `create-lab` (wiki search once);
   lab open, question unanswered → `research-workflow`; layout/catalog/complete → `organize-lab`.
   A tick that **continues** a lab already under way does not re-run a full wiki search.

   **Boundaries:** `scout` archives into `references/`; `reproducer` tests external claims;
   `auto` runs our experiments in `labs/`; `integrator` grows `lib/`; `auditor` checks what
   landed in `lib/`; `maintain` keeps the tree honest. Do not cross these in one step.

5. **Run programs within their tier** ([dispatch](references/router.md#dispatch)). Before any
   training launch, pass the gate in `wiki/project/spending-compute.md`; while a run is live, checking
   its pace against its ETA is a legitimate step, but a liveness check alone is not.
6. **Update the state.** A finished item: `$L task done <id>`. A partly finished item: rewrite
   its body to say what remains. New follow-ups: `$L task add` at the rank they deserve. Update the
   lab (`REPORT.md`, `lab.json`, then `skills/organize-lab` to rebuild `labs/labs.json`) and reply to
   or close the related thread.

With no GPU, take `gpu: free` items; most work never needs one: finding and reading sources,
reproduction and promotion coding, CPU smoke tests within the smoke cap, audits, lab drivers and CPU
evaluations, wiki pages and records, refactoring, classical benchmarks.

## Supervisor tick

Do the duties in order; the checklists are in [references/supervisor.md](references/supervisor.md).

1. **Threads**: act on threads awaiting an agent, close what is finished or stale, unblock task list
   items whose threads closed.
2. **Keep the repository honest**: follow [supervisor §Keep honest](references/supervisor.md#keep-the-repository-honest)
   (`run_guards.sh` + Threads/loop validates; fix cheap issues; one hygiene track); harvest due runs.
3. **Synthesize**: ingest finished labs and reproductions through `skills/wiki-ingest`; when the
   picture moved, file a dated synthesis record and choose a direction for each thread of work.
4. **Replan**: clean and reorder the task list, turn the direction and audit findings into concrete
   items, and refill the task list when it has no runnable work.
5. **Check for stalls** (below), and escalate real decisions through `skills/research-threads`.
6. **Set `next_action`** to a concrete research step and log the tick.

A supervisor tick is held to the same standard as a research tick: it lands an ingested page, a
record, a fixed inconsistency, or a task list that changed, not a status pass.

## Active deliverable

When the researcher names a concrete deliverable (a figure, a table, a report section, a trained
checkpoint), or a thread's decision sets one, record it with `set-deliverable`. Each acceptance
criterion is a checkable statement about an artifact, for example "`labs/<id>/figures/fig2.pdf`
exists and its numbers match `labs/<id>/results/fig2.json`". Research ticks advance the deliverable
first. It is done only when every criterion has been checked by opening the artifact itself, not by
trusting a log line, a registered name, or a previous claim. Then clear it, record the outcome in the
lab report and the thread, and move on. Never weaken a criterion to finish; if one proves
unreachable, ask through research-threads and work on the rest meanwhile.

## Task list

The task list is the agents' own queue of unfinished work. It ranks below open researcher instructions
and the active deliverable. Work an agent chooses for itself goes here, never into a researcher
instruction thread.

- **Unfinished work only.** It is not a log: no session narratives, loop-state dumps, or completed
  work. Finished, stale, or dropped items are deleted with `task done`; git history and the wiki's
  synthesis records carry the timeline.
- **Each item is an order.** The title names the job; the body is an imperative with its done
  criteria, and links to the lab, reference, record, or thread it depends on. Edit an existing item
  rather than adding a near-duplicate.
- **Routing fields.** `for` is one or more of `scout`, `reproducer`, `integrator`, `auditor`,
  `maintain`, `auto`, `all`. `gpu` and `time` follow `wiki/project/spending-compute.md`; `time` is the
  program's wall clock only, never agent time.
- **`blocked_on` blocks that item only**, and only for a researcher decision (cite its thread) or an
  external act that no retry can replace. GPU availability, runtime, time caps, credits, and outages
  are never blockers; the script refuses them.
- **Order is priority.** Insert new items where they belong (`--top`, `--before`), and let the
  supervisor reorder.
- **Rules win over items.** An item that conflicts with a working rule is not executed as written:
  fix the item, or, if the conflict is real, ask in a thread. (A researcher instruction is different:
  it overrides the standing rule via Threads / graduation.)

## Stalls

Signals, any one of which calls for a supervisor response:

- `status` warns that no action has been logged for more than two hours while running;
- two consecutive ticks without a substantive commit;
- the same `next_action` or the same top item for three ticks with no artifact;
- the same step failing twice with the same error;
- a detached run whose log has not advanced within its logging cadence;
- an item whose `time` was raised or which was split twice.

Response: stop repeating the step. Write what was tried and what failed into the item's body, then
change the approach: split the item, shrink the setting, take a different item, or, when the way
forward is a real decision, ask through research-threads and continue elsewhere. After two ticks in a
row lost to overlap with another writer, the third takes disjoint work (a reference to find, a
reproduction, a refactor).

## Running the loop

- **On request**: "run a research tick", "run the loop for an hour". Run ticks back to back and
  orient afresh at the start of each.
- **On a schedule**: any scheduler (cron, CI, an agent platform's automations) can start an agent
  with the instruction "Follow `skills/auto-research/SKILL.md` and run one tick." A research tick
  every 10 to 15 minutes and a supervisor tick about hourly is the reference cadence. Run one loop
  agent at a time, because only one agent writes git at a time (`AGENTS.md` / `git-workflow`).
- **In an interactive agent session**: asking the agent to "run the loop" means [Starting the loop](#starting-the-loop)
  **as this agent** (`--owner <self>`): schedule and tick only in this product's session/CLI. Never
  start another owner's runner. Dashboard = monitored status (`owner=…`), not the `running` flag.
- Detached programs continue between ticks, and the next tick harvests them. Record each one where
  the next agent will look (the lab's `REPORT.md` or `PLAN.md`, and `next_action`).

## Session / agent handoff

Use when a session ends, another agent takes over, or a long job will outlive the current worker.
Do **not** stop live research processes as part of a handoff. The next agent must be able to act
from files alone (no chat-only state).

1. Name the active deliverable and any open Threads that own human instructions
   (`$L status`, `research_threads.py list --status open`).
2. Summarize in the task body (or a short lab note): the question, the locked setting fields that
   move the number, what already ran, and provisional conclusions with paths to evidence.
3. List live or queued compute jobs without stopping them. Point at PIDs / logs only when useful.
4. Write the next concrete command set and acceptance criterion into `.auto-research/tasks/<id>.md`.
   Delete finished tasks (`$L task done`) instead of marking them done in prose.
5. If a human decision is required, open or update a Thread via `research-threads` — do not invent a
   priority.
6. When a Notes manuscript is in play, name `notes/<project>/` and whether a recompile is pending.
7. Leave `next_action` concrete (`$L set-next` / `log-action`), and land so the files match disk.

## Stops

Only the hard stops in `AGENTS.md` (never-park) and an explicit STOP from the researcher end work.
On a STOP, finish or cleanly abandon the current step, run `$L pause --summary "..."`, record the
STOP in its thread, and land. None of these is a stop: an empty or blocked task list, a pending
question, no GPU,
an unknown runtime, a failed push, an unmerged pull request, another writer's files, the researcher
being away. CONCLUDE closes one thread of work, never the loop; when the task list runs dry, the
supervisor refills it.

## Boundaries

The loop grants no permissions of its own: each step is bound by the skill it invokes and by
`AGENTS.md`. The loop writes `.auto-research/` through `loop_state.py` (state and tasks) and
`research_threads.py` (threads: questions, replies, and resolutions; researcher messages only as
their verbatim words), plus whatever the invoked skill writes. It never merges into `main`, creates
branches outside `land.sh`, runs reference code outside isolation, retries a dead end in
`wiki/dead-ends/` whose "Revisit if" condition is unmet, or edits `notes/` unless asked.

When a tool classifier denies `run_attempt.sh` (or attempt `run.sh`) as “external code”, that is a
**tool** stop on an already-sanctioned path, not a scientific stop: follow
`skills/reproduce-reference/references/tool-permission-denials.md` (reason + remedy; block only that
task; after outputs land, compare and clear the block).
