---
name: research-threads
description: Researcher–agent interaction over Threads — ask for decisions, record instructions and answers, and close, retract, or graduate threads under `.auto-research/threads/`.
usage: Use when a choice is irreversible, externally consequential, a scope or resource commitment, or a true judgment call; when the researcher gives an instruction or answers a question in conversation; and when work tied to a thread is finished.
---

# Research threads

Thread meta lives in `.auto-research/state.json` → `threads` (ordered; no messages). Message lists
live in `.auto-research/threads/<id>.json` as `{"messages": [...]}` only. A missing store is created by
`skills/auto-research/scripts/seed_local.py`. The format is in `.auto-research/README.md`. This skill
is the procedure behind the decision / Threads rules in `AGENTS.md`.

Write the store only through the script, from the repository root. It validates every change, assigns
the next ids, never edits or deletes an existing message, and replaces message files + `state.threads`
atomically under a lock. Never hand-edit those files.

```bash
M=".venv/bin/python skills/research-threads/scripts/research_threads.py"
$M list [--status open|closed] [--json]           # most recently updated first, with who it awaits
$M show thread-042 [--json]
$M open --title "..." [--category decision|scope|checkpoint|direction] [--priority high|normal|low] \
    [--lab <lab-id> ...] [--author agent|user] (--content "..." | --content-file brief.md)
$M reply thread-042 --author agent|user [--type reply|decision|instruction|question] [--lab <lab-id>] \
    [--continue-thread] (--content "..." | --content-file -)
$M close thread-042 [--author agent|user] (--content "..." | --content-file resolution.md)
$M reopen thread-042 --author agent|user [--type reply|decision|instruction] --content "..."
$M validate
```

`open` defaults to an agent `question` in a `decision` thread; with `--author user` it records an
`instruction` in a `direction` thread. `--content-file -` reads standard input.

## Thread hygiene (required)

These rules keep the dashboard readable and "awaiting reply" honest, without forcing a new thread
for every clarification. The threads store script enforces a **narrow** subset for **agent** posts;
researcher posts are never blocked. Pass `reply --continue-thread` only for the **same** open
concern—never to dump progress or start a clearly new decision.

1. **New concern → new thread.** After a researcher `decision` that an agent has already taken up
   (an agent `reply` after that decision), do not open another `question` on the same thread—`$M
   open` a new one. Clarifying questions *before* that acknowledgment stay on the same thread.
2. **Close when done.** Once the decision is applied, `$M close` with a resolution that links the
   durable record. Prefer closing over leaving a finished thread as a chat log.
3. **Progress stays out of the threads store.** Intermediate results, GPU status, and loop narratives go
   in the lab `REPORT.md` / `results/`, or `.auto-research/state.json`—not in `reply --type reply`.
4. **Do not reply on top of your own unanswered question.** An agent `reply` after your own
   `question` clears the awaiting-reply badge. Put the update in the lab; if a threads store note is
   essential, end with `reply --type question` restating the open question in one line.

Enforced by the script: (4) always; (1) only after a decision has been acknowledged. There is no
message-count cap—length is handled by closing finished threads and by the dashboard collapse.
Judgment still matters: if the next ask is a different decision, open a new thread even when the
script would allow a reply.

## Start of every work session

1. Run `$M list --status open`. A thread whose last message is from the researcher awaits an agent:
   carry out the instruction or apply the decision before other work (`AGENTS.md` orientation), reply with
   what you did, and close the thread when it is finished.
2. Before opening a thread, search the threads store, closed threads included (`$M list --json`, then
   `$M show`). The answer may already be recorded: thread-125 asked the researcher about a push
   failure whose self-recovery a closed thread had predicted three weeks earlier.

## When to ask

Decide routine choices yourself and continue: a configuration value, which candidate to try next,
naming, how to structure code, a small change of scope. Record the reasoning where the work lives (the
lab's `PLAN.md` or `REPORT.md`, the commit message), not in a thread.

**Do not ask about landing — land.** Dirty or huge trees still go through `land.sh` onto
`research/auto-<date>` (see `skills/git-workflow`, "When the tree is dirty or huge: land boldly").
Opening a thread that offers "you commit vs the loop lands" is a skill miss: the answer is to land.

**Do not ask about PRs or merging to `main`.** Land and push on `research/auto-*` only. The
researcher merges when they choose; never escalate or remind.

Ask the researcher when the choice is one of these:

- **Scientific scope**: changing a research question or a lab's accepted claim, redefining what
  counts as done for a program, dropping or replacing a line of work the researcher asked for.
- **Resources**: committing GPU-days beyond what a task's tier already implies, holding both
  GPUs for a long run, spending money or external credits.
- **Safety and irreversibility**: deleting data, checkpoints, or results that cannot be regenerated
  cheaply; an exception to the package boundaries; any action on systems outside the repository.
- **An act only the researcher can perform**: relaunching the container to restore CUDA, restoring
  credentials or the SSH agent, or adding a tool-permission allow rule when the auto-mode
  classifier blocks a command that is already the sanctioned isolation path
  (`skills/reproduce-reference/references/tool-permission-denials.md`). The loop keeps working
  meanwhile; the thread records the need. Do **not** re-ask whether reference code may run in
  isolation — that is already project policy; ask only for the tool allow / a human `!`
  `run_attempt.sh` invocation, and always state why it was blocked and what to run next.
- **A true judgment call**: the evidence does not decide, and the options lead to different
  programs of work.

Test before asking: if the choice is wrong, can the next agent undo it cheaply, and would the
researcher be unsurprised to read about it afterwards? If both, decide.

A thread is never a status report (hygiene rule 3). Progress notes, "still waiting" updates, GPU
monitoring, and loop narratives belong in the lab report or `.auto-research/state.json`, or nowhere.

After asking, skip that task and do other work (`AGENTS.md`: never park the whole loop). Block only the task the
answer gates: `.venv/bin/python skills/auto-research/scripts/loop_state.py task block <item-id>
--on "researcher decision in thread-042"`. Open threads whose last message is an agent question show
up in `$L status` as `awaiting_human` (same rule as the dashboard badge); do not park the whole loop on them.

## Writing the question

The researcher reads the thread cold, on the dashboard or in the file, possibly days later. Write a
decision brief that stands alone:

```markdown
**What this is about:** the task, the lab (`labs/<id>/`), and what the decision gates.

**What we know:** evidence so far (run `wiki-query` once for the topic; link results and pages;
do not restate).

**What is unclear:** the specific uncertainty the researcher can resolve and the agent cannot.

**Options:**
1. **<option A>**: consequence, cost (GPU-hours, calendar days), reversibility.
2. **<option B>**: consequence, cost, reversibility.

**Suggested:** the option you recommend, and why, in one or two sentences.

**Default if silent:** what the loop does in the meantime; it never waits.

**Blocks:** the tasks held by this question, or "nothing; the loop continues".
```

- A thread reads "awaiting user" (threads store `list`, dashboard badge "awaiting reply") only while its
  latest message is a `question` and a task's `blocked_on` cites its id. Block each task named under
  **Blocks:** with `loop_state.py task block`, and unblock it once answered. A progress report
  blocks nothing and waits on nobody; the thread stays open with no extra badge.
- A progress note added to a question thread (`reply --type reply`) becomes the latest message, so the thread stops reading
  "awaiting user" while the question is still open (2026-10-12, threads 008 and 010). Put progress in the lab or the
  question's links instead; if a note is needed, end with `reply --type question` restating the open question in one line.
- The title names the decision in one line, not the topic: "Spend two H200-days on the window
  solver now, or after the classical baseline re-measurement?" rather than "Oracle sketch".
- One concern per thread (hygiene rule 1). Absolute dates only. No shorthand invented during the
  session; link to files instead of pasting them.
- Category: `decision` by default; `scope` for a change to the research question, budget, or
  deliverable; `checkpoint` for a planned review of results. Priority `high` only when the answer
  gates the active deliverable or something is at risk; otherwise `normal`.
- Add the thread id to the `discussion` field of each related lab's `lab.json`, and pass the lab with
  `--lab` so the thread lists it in `related_labs`.

## Recording the researcher's words

The researcher may run the commands, or tell an agent in conversation. The agent is then a scribe:

- a new directive: `$M open --author user --title "<short line naming it>" --content "<their words>"`;
- an answer to an existing question: `$M reply thread-042 --author user --type decision --content "<their words>"`;
- a further directive on an open thread: `$M reply thread-042 --author user --type instruction --content "<their words>"`;
- closing a thread: `$M close thread-042 --author user --content "<their words>"`.

Record the researcher's **intent** in **professional English**. Do not paste Chinese (or other
non-English) speech verbatim into the threads store, and do not paste casual dictation unchanged: translate
and lightly edit for clarity while preserving meaning, decisions, and constraints. Do not invent
substance, drop conditions, or add routing the researcher did not give; put your own reading in a
separate agent reply. Never write a user message for something the researcher did not say, and never
open a user instruction on your own initiative: work the agents choose for themselves goes into the
task list (`skills/auto-research`). If the words are ambiguous, ask in an agent reply. When the
researcher asks only to record an instruction, record it (in professional English) and stop; the
research loop picks it up as its highest-priority input.

If a user message was already stored incorrectly (wrong language or unedited dump), do not append a
"correction" reply that leaves the bad text in place: with the researcher's explicit say-so, edit that
message's `content` in `.auto-research/threads/<id>.json` in place, then run `$M validate`.

## Replying

Use an agent `reply` for evidence that changes the picture or a clarification the researcher needs
before deciding—not for routine progress (hygiene rule 3). Keep it to what changes their decision;
do not narrate ticks. After you have applied a decision, close the thread (hygiene rule 2) instead of
leaving it open as a log.

## Closing

Either side can close a thread. The last message of a closed thread is always a resolution.

The researcher closes from the dashboard (the red Close thread button on an open thread) or from
the terminal. The note is their words, recorded as `author=user`:

```bash
$M close thread-042 --author user --content "..."
```

An empty note is refused. An agent closes only after applying the outcome (update the task list,
the deliverable, or the rule). `--author` defaults to `agent`:

```bash
$M close thread-042 --content-file resolution.md
```

An agent's resolution starts with one of these words and an em dash, then says what happened:

| Opening | When |
|---|---|
| `Done —` | the instruction was carried out |
| `Resolved —` | the question was answered and the answer applied |
| `Graduated —` | the instruction became a standing rule (see below) |
| `Stale —` | superseded by later work or a newer instruction (say which) |
| `Infeasible —` | cannot be done here (give the evidence) |
| `Withdrawn —` | the researcher withdrew it |

Include durable links (lab report, result files, commit, wiki page, task id) so the next
reader never needs the conversation, and end with a one-line summary of the outcome. Never write a
user resolution the researcher did not say, and never record a decision they did not make.

After closing: unblock the tasks that cited the thread (`loop_state.py task unblock
<item-id>`), and update the related lab's `REPORT.md` or `lab.json` when the outcome changes them.

When new evidence overturns a resolution, or the researcher returns to a closed topic, reopen the
thread with a message that says why (`$M reopen`) instead of opening a duplicate.

## Retracting an instruction

When a newer researcher instruction supersedes an older open one, close the older thread with
`Stale — superseded by thread-NNN`, plus what changed. Only the researcher's words can retract their
instruction; an agent never retires one because it is inconvenient or slow.

## Graduating standing rules

When an instruction or decision is policy beyond one task ("always", "never", "from now on"), it must
not live only in a thread (`AGENTS.md` graduating rules):

1. Write the rule where it belongs: `AGENTS.md` when it binds every agent session, the owning
   `skills/<name>/SKILL.md` when it is a procedure, or a `wiki/project/` page when it is a domain
   constraint with its reason and the incident behind it.
2. Update or remove any conflicting or stale copy elsewhere, and link instead of restating.
3. Close the thread: `Graduated — codified in <path>, section "<heading>"`, with the one-line summary.

## Before landing

Run `$M validate`, then land through `skills/git-workflow` with explicit paths
(`.auto-research/threads/`, `state.json` `threads` meta, and any `lab.json` you changed).

## Dashboard

The dashboard's Threads section (`./run.sh start`, port 8020) reads Threads from
`.auto-research/threads/` and lists open threads first. The researcher can open a thread, reply,
close an open thread, or reopen a closed one on that page; those posts are recorded as
`author=user` through this script. An agent close still uses `$M close` with the default author.
The same commands work from a terminal, and by telling an agent. Write every question so that it
reads well there on its own.
