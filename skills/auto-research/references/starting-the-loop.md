# Starting and scheduling the loop

Detail for Starting the loop in `skills/auto-research/SKILL.md`.
`$L` is `.venv/bin/python skills/auto-research/scripts/loop_state.py`.

"Resume", "start", or "run the loop" usually means the researcher is leaving and expects ticks to
continue without them. The state file cannot tell you whether that is true, so do this before
saying anything about it.

## Ownership

Encoded in `scheduler.json` + `loop_runner`: any agent may start the loop when asked. **Who starts
owns it** (`--owner <self>`). That owner alone performs ticks in **its own** session / CLI. No agent
may start or wake another product's ticks (Cursor must not `serve --owner codex`; Codex must not
register `owner=claude` and expect Claude to tick).  <!-- rules-lint: allow -->

## Same chat vs same-owner headless

Do not conflate them:

| Want | What actually does that |
| --- | --- |
| Ticks return to **this same chat** | Claude `CronCreate` (`session-cron`), Cursor product automations, or desktop Codex "schedule this chat" (`external`) — always `--owner <self>` |  <!-- rules-lint: allow -->
| Same **owner**, headless wake | `loop_runner serve --owner <self>` only for `claude`/`codex`: wakes that same product's CLI. Not a sticky interactive chat; progress in `.auto-research/` and `.tmp/auto-research/scheduler.log` |  <!-- rules-lint: allow -->

## Procedure

1. **Ask the scheduler, not the state.** List jobs with **this product's** scheduling tools (if any).
   `loop_state.py status` prints a `loop:` line (`live`, `UNSCHEDULED`, or `STALE`) including
   `owner=…`; treat anything but `live` as "not ticking". `running` is only a flag.
2. **Create a schedule this agent owns** (`--owner` = this product, never another):

   | Kind | When | What to do |
   | --- | --- | --- |
   | **`session-cron`** | This agent has in-session cron (e.g. Claude `CronCreate`) | Recurring one-tick job in **this** session. `$L scheduler --set session-cron <job-id> --every-min 12 --owner <self>`. |  <!-- rules-lint: allow -->
   | **`runner`** | This is Claude/Codex CLI with no in-session cron | **This** agent starts `loop_runner.py serve --owner <self>`, then `$L scheduler --set runner <pid> --every-min 12 --owner <self>`, `$L start`. Runner refuses a mismatched registered owner. |  <!-- rules-lint: allow -->
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

## Codex desktop Scheduled

([docs](https://learn.chatgpt.com/docs/automations?surface=app)) CLI/IDE have no Scheduled UI.
Use desktop only when the researcher wants ticks **back in one Codex chat**: desktop app → Codex →
**local** project (the checkout with `.auto-research/`, not a worktree) → schedule that chat every
~12 min → check **Scheduled**. Keep the machine on and the app running. Otherwise, from Codex CLI,
start **`loop_runner` in that CLI session** and accept headless ticks.

## How ticks get fired (was “Running the loop”)

- **On request**: "run a research tick", "run the loop for an hour". Run ticks back to back and
  orient afresh at the start of each.
- **On a schedule**: any scheduler (cron, CI, an agent platform's automations) can start an agent
  with the instruction "Follow `skills/auto-research/SKILL.md` and run one tick." Wakes every
  ~12 min; `suggested_kind` (status / `loop_runner` prompt) forces a supervisor tick when
  `last_supervisor_at` is ≥~60 min old (or never), the runnable queue is empty, or the loop
  stalled — otherwise research. Run one loop agent at a time, because only one agent writes git at
  a time (`AGENTS.md` / `git-workflow`).
- **In an interactive agent session**: asking the agent to "run the loop" means this document
  **as this agent** (`--owner <self>`): schedule and tick only in this product's session/CLI. Never
  start another owner's runner. Dashboard = monitored status (`owner=…`), not the `running` flag.
- Detached programs continue between ticks, and the next tick harvests them. Record each one where
  the next agent will look (the lab's `REPORT.md` or `PLAN.md`, and `next_action`).
