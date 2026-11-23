# Loop state and CLI

Detail for the State section of `skills/auto-research/SKILL.md`.
`$L` is `.venv/bin/python skills/auto-research/scripts/loop_state.py`.

## Scaffold

This repository tracks the **minimum** `.auto-research/` scaffold (format READMEs + empty
`state.json`). Consumer labs gitignore the whole folder after create (live checkout data). A
missing `state.json` is filled by `seed_local.py`.

Change the store only through the scripts; they validate every write and replace files atomically
under a shared lock.

## Fields

| Field | Meaning |
|---|---|
| `status` | `running`, `paused`, or `idle` |
| `active_deliverable` | lab + summary + acceptance criteria, or null |
| `next_action` | concrete next step string |
| `last_action` | last logged tick summary |
| `last_supervisor_at` | ISO-8601 UTC of last supervisor `log-action`, or null |
| `idle` | null unless status is idle — reason, lift condition, fingerprint |
| `tasks` | ordered scheduling meta only; body in `.auto-research/tasks/<id>.md` |
| `threads` | ordered Thread meta only; messages in `.auto-research/threads/<id>.json` → `{"messages":[…]}` |

`status` prints `suggested_kind` (`kind`, `forced`, `reason`). The runner embeds the same signal in
its wake prompt. When `forced` is true, the agent must run that kind. Forces: idle status →
`idle-probe`; ≥60 min since `last_supervisor_at` (or never); empty unblocked queue with no
deliverable; stall (>2 h without `last_action` while running). Research-step choice inside a
research tick stays heuristic.

Each task has `id`, `title`, `for`, `gpu`, `time`, `blocked_on`, `related_labs`, `added`.

`running` is a flag the loop wrote about itself. It is not evidence that anything fires ticks, and
it is never the answer to "is the loop running?" (see `starting-the-loop.md`). `running` means ticks
should proceed. `paused` means the researcher, or a task they authorized, stopped the loop; run
ticks only when asked, and `start` again when told to resume.

## Commands

```bash
L=".venv/bin/python skills/auto-research/scripts/loop_state.py"
$L status                                  # state, top of the task list, open threads, and warnings
$L start | pause [--summary "..."]
$L idle --reason router-empty|repeated-tick|supervisor-refill-failed|other \
    --lift-when "…" --detail "…" [--summary "…"] [--same-tick-streak N]
$L idle-check                              # cheap probe while status is idle
$L set-next --text "..."
$L set-deliverable --lab <lab-id> --summary "..." --acceptance "..." [--acceptance "..."] | --clear
$L log-action --summary "research: ..." [--next "..."] [--kind research|supervisor]
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
