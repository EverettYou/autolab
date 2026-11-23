---
name: auto-research
description: Run the autonomous research loop as bounded ticks over `.auto-research/state.json`. A research tick advances the active deliverable or the best runnable task (references, labs, promotion, audits); a supervisor tick runs follow-up → scan → ingest → replan → reroute → set-next (Threads, health-scan, wiki ingest, task queue, course-change, next_action) and escalates real decisions through thread-interaction.
usage: Use when asked to run, resume, pause, or supervise autonomous research; to add, reorder, block, or finish tasks; or to hand off a session so another agent can continue from files alone.
---

# Autonomous research loop

Open-ended program of bounded ticks; all loop state lives in files. Never concludes on its own and
never parks. Procedure behind the loop / orientation / never-park rules in `AGENTS.md` — follow
dependencies where they live:

- orientation, decisions, never parking, git, secrets, evidence: `AGENTS.md`;
- GPU / training gate / time tiers / `gpu`/`time`/`blocked_on`:
  `skills/auto-research/references/spending-compute.md`;
- ask / record / close: `skills/thread-interaction`.

`$L` = `.venv/bin/python skills/auto-research/scripts/loop_state.py` (shorthand used below).

## State

Fields in `.auto-research/state.json`: `status` (`running`|`paused`|`idle`), `active_deliverable`,
`next_action`, `last_action`, `last_supervisor_at`, `idle`, ordered `tasks`, ordered `threads`. Task
bodies: `.auto-research/tasks/<id>.md`. Thread messages: `.auto-research/threads/<id>.json`. Scripts
only — full CLI and scaffold notes: [references/state-and-cli.md](references/state-and-cli.md).
`running` ≠ scheduler live (see Starting).

## Starting the loop

Ownership: **who starts owns it** (`--owner <self>`); never start another product's ticks. Situations:

| Kind | When |
|---|---|
| `session-cron` | This product has in-session cron |
| `runner` | This product's CLI supports `loop_runner serve --owner <self>` |
| `external` | Desktop Scheduled sticky chat for this product |
| none | Run ticks only when asked; do not claim the loop is running |

Register → `$L start` → verify (`loop:` must be `live`). Pause: `$L pause` + cancel this owner's
schedule. Full procedure (same-chat vs headless, Codex desktop, cadence):
[references/starting-the-loop.md](references/starting-the-loop.md).

## Every tick

1. **Orient.** `$L status` (reads `suggested_kind`). If `idle`: `$L idle-check` then
   [references/idle.md](references/idle.md) (lift → `$L start`; unchanged → end; do not load full
   research context). Else list open Threads; researcher replies first.
2. **Kind** — honor `suggested_kind` from status / runner prompt (table below). When
   `forced: true`, that kind is mandatory. Then **Do** within ~30 min agent time (programs ≥15 min:
   launch or harvest only).
3. **Record.** Filesystem handoff (`AGENTS.md`), then
   `$L log-action --summary "<research|supervisor>: …" --next "…" [--kind research|supervisor]`.
   Supervisor summaries (prefix `supervisor:` or `--kind supervisor`) update `last_supervisor_at`.
4. **Land.** `$L validate` (+ `thread_interaction.py validate` if threads changed); guards `land`
   bundle if governed files changed; `skills/git-workflow` with
   `auto(research|supervisor): …`. Exit 2/3 do not block.
5. **Report** (in conversation):
   `[auto] <research|supervisor> | step=… | files=… | next=…`.

Every tick lands a real artifact (never park). Two consecutive ticks without a substantive commit =
stall → supervisor.

| Kind | When |
|---|---|
| **idle-probe** | `status` is `idle` (`suggested_kind` forced) |
| **supervisor** | **forced** when ≥~60 min since `last_supervisor_at` (or never), empty runnable task list + no deliverable, or stall; also when a lab or a reproduction finished, thread closed, or asked |
| **research** | default when `suggested_kind` is research (not forced); research-*step* choice stays heuristic via router |

## Research tick

Open [references/router.md](references/router.md) → **Resources → Pick** → **only** Open the Role-card
skill below (do not load other skills this tick unless that entry links them). `run-lab` is the lab
method under `auto`, **not** this tick.

1. Resources / pick / overlap / dispatch — follow the router.
2. Advance via the Role card (read order: `$L status` + task body → this table → one Open entry).
3. Update state: `$L task done` / rewrite body / `$L task add`; update lab + thread as needed.

| `for` | Open | Do this tick | Done when |
|---|---|---|---|
| `scout` | `discover-references`; on `pass`, `fetch-reference` | One discovery pass; archive at most 1–2 `pass` hits | Candidate table returned (or negative confirm recorded); fetched ids have `provenance.json` |
| `reproducer` | `reproduce-reference` (+ `runtime-env` isolation) | Advance one attempt one phase (PLAN→…→PROMOTE) | `gate-state.yaml` moved, or attempt disposed / dead-ended |
| `integrator` | `promote-lib` (bootstrap `lib/` first if needed) | Enable/scaffold `lib/` when off, then one promote-gate step; queue `audit-lib` after a landed promote | `lib/` importable if this tick bootstrapped it; gate phase advanced (bootstrap-only is OK — not a promote failure) |
| `auditor` | `audit-lib` | Review promoted package code against its evidence | Audit record under `wiki/records/audits/` (or explicit N/A) |
| `auto` | lab trio: `create-lab` → `run-lab` → `organize-lab` (first that applies) | Exactly one lab step | `PLAN.md` / `REPORT.md` / `lab.json` (or catalog) changed for real |
| `maintain` | [supervisor §Scan](references/supervisor.md#scan) **only** | Guards / cheap fixes / one hygiene track; harvest due runs; no ingest/replan | Guards green or fix tasks queued; `last_action` names what changed |
| `all` | Skills the Goal needs (agent chooses) | Composite; body states Goal / Done when | Task **Done when** holds; record skills used in `last_action` / body |

Role boundaries and GPU-free defaults: [router.md](references/router.md#role-boundaries).

## Supervisor tick

Duty order: **follow-up → scan → ingest → replan → reroute → set-next**. Execute
[references/supervisor.md](references/supervisor.md) (checklists live only there). Same artifact
standard as a research tick.

## Active deliverable

Record with `set-deliverable`; each acceptance criterion names a checkable artifact. Research ticks
advance it first. Done only when every criterion is verified by opening the artifact (not a log
line). Never weaken a criterion; if unreachable, ask via `thread-interaction` and continue the rest.

## Task list

Agents' unfinished work — below researcher instructions and the deliverable; never a log.

- Imperative body + done criteria; edit duplicates; delete finished with `task done`.
- `for`: `scout`|`reproducer`|`integrator`|`auditor`|`maintain`|`auto`|`all`. `gpu`/`time` per
  spending-compute; `time` = program wall clock only.
- `blocked_on`: researcher decision (cite thread) or irreplaceable external act only — not GPU/time/credits.
- Order is priority; supervisor reorders. Rules win over items (unless a researcher instruction overrides via Threads).

## Reroute

Signals and response: [supervisor.md §Reroute](references/supervisor.md#reroute). Any stall signal →
supervisor tick; stop repeating the failing step and change course.

## Session / agent handoff

Do not stop live research processes. Next agent must act from files alone:

1. Name deliverable + open Threads (`$L status`, `thread_interaction.py list --status open`).
2. Summarize in the task body / lab note: question, locked setting fields, what ran, evidence paths.
3. List live/queued jobs (PIDs/logs if useful) without stopping them.
4. Write next commands + acceptance into `.auto-research/tasks/<id>.md`; `$L task done` for finished.
5. Human decision → `thread-interaction` Thread. Notes in play → name `notes/<project>/`.
6. Concrete `next_action`; land so disk matches.

## Stops

Only AGENTS hard stops (never-park) or an explicit researcher STOP end work. On STOP: finish or
abandon cleanly → `$L pause --summary "…"` → record in thread → land. Everything that is **not** a
stop or light idle: [references/idle.md](references/idle.md#not-a-stop-and-not-light-idle).

## Boundaries

No extra permissions: each step bound by the skill it opens and `AGENTS.md`. Writers:
`loop_state.py`, `thread_interaction.py`, plus the invoked skill. Never merge to `main`, branch
outside `land.sh`, run reference code outside isolation, retry an unmet `wiki/deadends/` “Revisit
if”, or edit `notes/` unless asked. Tool classifier denial of sanctioned
`run_attempt.sh` / attempt `run.sh`: follow
[tool-permission-denials.md](../reproduce-reference/references/tool-permission-denials.md).
