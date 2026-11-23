# Router: choosing and dispatching a research step

Detail for steps 1 to 5 of a research tick in `skills/auto-research/SKILL.md`. The rules on GPUs,
training, and time tiers are in `wiki/project/spending-compute.md`; this page only applies them.
`$L` is `.venv/bin/python skills/auto-research/scripts/loop_state.py`.

## Resources

Take a live snapshot at the start of the tick:

```bash
bash skills/runtime-env/scripts/snapshot.sh --bundle router --max-age 60
```

Read `OVERALL` and `AVAIL_TIER`, and map the tier to what can run now:

| `AVAIL_TIER` | Items that fit |
|---|---|
| `avail_heavy` | `gpu: free`, `light`, `heavy` |
| `avail_light` | `gpu: free`, `light` |
| `avail_none` | `gpu: free` only |

`$L task list --unblocked --fits <free|light|heavy>` applies the mapping. Never infer GPU load from
`ps` CPU percentages. The snapshot has two known blind spots: an instantaneous utilization sample
can call a busy card available (`thread-124` in `.auto-research/state.json`), and it cannot tell CUDA
being down from CUDA being contended (`thread-122`). Before a GPU launch, confirm with
`torch.cuda.is_available()` on the machine and the card's current power draw.

An unknown runtime is not a blocker: plan and build with `time: 0`, or fingerprint the machine with
`snapshot.sh --bundle fingerprint` (`1min`), and defer running external code until the runtime
profile is known.

## Clearing stale blockers

Before collecting candidates, try to clear every `blocked_on` instead of skipping the item.
`$L validate` already reports items that cite a closed thread.

| `blocked_on` names | Clear when | Then |
|---|---|---|
| a thread (`thread-NNN`) | the thread is closed | apply its resolution to the item, `$L task unblock <id>` |
| another task ("after `<id>`") | that item no longer exists | unblock |
| credits, spend limits, an API or service being down | always: a running tick disproves it, and it should never have been written | unblock |
| a researcher decision with no thread | now: open the thread (`skills/research-threads`) and cite it in `blocked_on` | keep blocked |
| an external act (an upstream release, data access) | the act happened; check at most once per supervisor tick | unblock |

A newly unblocked item is a full candidate in the same tick.

## Choosing an item

Candidates are, in order of precedence: open researcher instructions, the active deliverable's next
unmet criterion, then every unblocked task that fits the GPU tier. Score all of them rather
than taking the first:

| Signal | Prefer |
|---|---|
| Task list rank | earlier items: the supervisor's priority |
| Resource fit | `gpu` within the tier; `time: 0` is always runnable |
| Dispatch fit | a step that completes, or launches, within this tick's remaining agent time |
| Harvest due | a detached run that has finished or passed its ETA |
| Pipeline value | reproduction, promotion, and audit steps that are actionable now |
| Unblocking value | a cheap step that unblocks several other items |
| Anti-stall | never a GPU-monitoring-only step; never waiting for the top item to become runnable |

Break ties by role: `reproducer`, then `integrator`, then `auditor`, then `scout`, then `maintain`;
`auto` items take the rank of the lab step their body implies; `all` items are composite — score
them by the Goal / Done when, not by a pre-assigned role. When nothing in the task list is
runnable, do the repository duties of a supervisor tick (`maintain`) and refill the task list.

## Dispatch

| `time` | How it runs |
|---|---|
| `0` | agent work only: reading, coding, writing, reviewing |
| `1min`, `5min` | inline, under a timeout |
| `15min` and above | detached; a tick only launches or harvests it |

The timeout for any tier above `0` is min(2 x tier, cap); `bash skills/guards/scripts/parse_time.sh
<tier>` prints the tier in seconds, and the caps are in `wiki/project/spending-compute.md`. When a
program exceeds its estimate, raise the item's tier (`$L task set <id> --time <tier>`) or split
the item, and note the measured runtime in its body.

Launch a detached program from the repository root with repository-relative paths, its own timeout,
and a flushed log, for example:

```bash
setsid nohup timeout <seconds> .venv/bin/python -u labs/<lab-id>/scripts/<driver>.py ... \
    > labs/<lab-id>/logs/<run>.log 2>&1 < /dev/null &
echo $!    # the process id
```

Record the command, process id, log path, start time, and numeric ETA in the lab's `REPORT.md` or
`PLAN.md`, and put the harvest in `next_action`, so any later agent can find the run. Reproduction
runs use the runner in `skills/reproduce-reference` inside the attempt workspace instead.

Monitoring a live run means checking progress, not liveness: the log's latest step against the ETA,
drift in step time, steady loss decay, and early stopping when it saturates. A process being listed
is not progress; check its CPU-time delta, its open `/dev/nvidia*` handles, and fresh output.

## Overlap guard

Other agents and people write concurrently. For each file the step plans to touch:

```bash
find <planned paths> -type f -mmin -30 2>/dev/null
```

Any hit is another writer's active file: choose different work for this tick, and leave the file out
of the commit. Never end the tick or stop the loop over it. A file idle for 30 minutes or more may be
committed. After two ticks in a row lost to overlap, the third takes disjoint work.

Run everything from the repository root: a relative lab path issued from inside `lib/` once
created an experiment directory inside the package tree (2026-06-20).
