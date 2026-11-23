# Idle (backstop, not a parking lot)

Detail for idle probes in `skills/auto-research/SKILL.md`.
`$L` is `.venv/bin/python skills/auto-research/scripts/loop_state.py`.

## Prefer seeking work

Prefer staying `running` and **finding work**: unblocked tasks, maintain / side tracks, supervisor
refill. Work without a GPU and without a researcher answer almost always exists — do not enter idle
lightly.

## Not a stop and not light idle

None of these alone is a stop or an idle entry: an empty or blocked task list, a pending question,
no GPU, an unknown runtime, a failed push, an unmerged pull request, another writer's files, the
researcher being away. First seek side work and have the supervisor refill. CONCLUDE closes one
thread of work, never the loop. Idle is allowed only as this backstop after those paths fail, with
`reason` + `lift_when`.

## When to enter

Enter idle only after seeking work has also failed, with an explicit record the **next** tick can
probe without reloading the full research context:

| `reason` | When |
| --- | --- |
| `router-empty` | Router cannot pick any next step after side work + supervisor refill failed |
| `repeated-tick` | About **5** consecutive ticks returned the same substance (same fingerprint / no new artifact) |
| `supervisor-refill-failed` | Supervisor tried to refill and still produced nothing runnable |
| `other` | Rare; `detail` must still justify why seeking work failed |

Required on entry (`$L idle --reason … --lift-when … --detail …`):

- **why** (`reason` + `detail`) — not a dump-and-ignore;
- **`lift_when`** — concrete exit condition (e.g. “thread-042 gets a researcher reply”, “an
  unblocked task appears”, “deliverable is set”);
- **fingerprint** — auto-captured (tasks / threads / `next_action`); optional
  `--same-tick-streak N` for `repeated-tick`.

`$L start` clears `idle`. `$L pause` clears `idle` and deregisters the scheduler. Idle **keeps** the
scheduler so cheap probes still fire.

## Idle probe

While `status` is `idle`, a tick is an **idle probe**, not a research tick: run `$L idle-check`
first. If the fingerprint is unchanged and `lift_when` is unmet, end the tick without loading the
full wiki / lab / task context. If something changed or `lift_when` looks met, `$L start` and resume
the main loop.
