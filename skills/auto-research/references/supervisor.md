# Supervisor tick checklists

Detail for the supervisor tick in `skills/auto-research/SKILL.md`. Do the sections in order. Spend
the tick on whatever is most out of date; not every section changes something every time, but the
tick must land at least one real artifact.

## Threads

```bash
L=".venv/bin/python skills/auto-research/scripts/loop_state.py"
M=".venv/bin/python skills/research-threads/scripts/research_threads.py"
$M list --status open
$L status   # awaiting_human = open threads whose last message is an agent question
```

- A thread whose last message is from the researcher awaits an agent: carry it out or apply it now,
  or queue it at the top of the task list if it needs more than this tick.
- A thread whose work is finished, or which later work has overtaken, is closed with a resolution
  (`skills/research-threads`, "Closing").
- A standing rule in a thread is graduated (`skills/research-threads`, "Graduating standing rules").
- Every task that cites a closed thread is unblocked after its resolution is applied.

## Keep the repository honest

Mechanical checks live in `skills/guards` (`run_guards.sh`). This section is **when** to run them
and what to do with failures — not a second copy of the check table.

1. Run the full bundle, then the two writers the bundle does not cover:

   ```bash
   bash skills/guards/scripts/run_guards.sh          # includes labs/layout, fs, auto-research, …
   $L validate                                      # loop_state invariants
   $M validate                                      # Threads store
   ```

2. Fix cheap failures in-tick; queue the rest as `for: maintain` or `for: integrator` tasks.
3. Harvest live programs (below), then spend remaining time on **one** hygiene track.

When `fs` / layout findings need action:

| Finding | Action |
|---|---|
| empty forbidden directory whose content lives at its proper path | remove it after `diff -rq` confirms it holds nothing unique |
| forbidden directory with unique files | task `for: integrator` (package tree) or `maintain`, naming the files and their destination |
| loose root script | move it into `skills/<name>/scripts/` or the lab that uses it, or delete a duplicate |
| experiment files, data, weights, or reports inside `lib/src/<package>/` | task `for: integrator` |
| a retired top-level path reappeared | move its content to the new home named in the message, then delete it |

Live programs: for each detached run recorded in a lab or in `next_action`, check progress against
its ETA ([router](router.md#dispatch)), harvest finished runs into the lab's results and report, and
stop runs that are past their timeout or no longer progressing.

Then spend the remaining time on one hygiene track, choosing the one most out of date:

- **Codebase.** Look in `lib/src/<package>/` (when present) for structural duplication: wiring that a shared base
  should own, near-identical implementations that diverged, abstractions that eroded
  (`wiki/models/platform-abstraction-invariants.md`). A small safe fix (a typo, an obviously stale
  comment) lands directly with the package tests. A larger refactor becomes a design record,
  `wiki/records/design/<YYYY-MM-DD>-<slug>.md`, plus a task `for: integrator` that cites it.
- **Knowledge.** Check wiki pages against what references, labs, and the platform now show: fix
  inconsistencies, remove outdated facts, merge duplicates. Write through `skills/wiki-ingest` and
  check with `skills/wiki-lint`. Record durable, non-obvious facts only, never session history.
- **Documentation.** Compare `wiki/package/` with the code it describes: modules, solvers, and
  signatures that were renamed or removed. The dashboard's API section renders docstrings live, so a
  wrong API description is fixed in the docstring in `lib/src/<package>/`, with the package tests.

The commit message and `last_action` record what was fixed; there is no separate maintenance log.

## Synthesize

Inputs: labs whose stage became `complete` since the last synthesis (`labs/labs.json`), new
reproduction records (`references/<id>/reproduce/`), new lab results of record, new audit
and integration records (`wiki/records/audits/`, `wiki/records/integrations/`), `wiki/dead-ends/`,
`wiki/thesis.md`, and the latest record in `wiki/records/synthesis/`.

1. **Ingest** each finished lab and accepted reproduction through `skills/wiki-ingest` ("Lab
   handoff"), which updates the affected compiled pages, `wiki/thesis.md`, `wiki/sources.yml`, and
   `wiki/records/log.md`. The synthesis must reflect evidence, not task list state.
2. **Reconcile anomalies.** When a result conflicts with an earlier one, look for a single mechanism
   that explains both before filing either as an isolated failure. If none fits, say so, and make
   resolving the tension an open question.
3. **Write a synthesis record** when the understanding moved:
   `wiki/records/synthesis/<YYYY-MM-DD>-<slug>.md`, filed through `skills/wiki-ingest`, with these
   sections:

   | Section | What it gives the replan step |
   |---|---|
   | Current understanding | settled against provisional results, with citations to labs, records, and registry cells, so closed threads are not queued again |
   | Patterns and insights | the mechanisms behind the numbers, which become DEEPEN or BROADEN work |
   | Lessons and constraints | negatives and invariants (link `wiki/dead-ends/`) that new items must not contradict |
   | Open questions | one line each, concrete enough to become a search query, a reproduction, or a lab question |
   | Decision log | carried forward from the previous record, plus today's line |

4. **Choose a direction** for each thread of work that moved, and add a Decision log line naming
   the thread, the choice, the reason, and the next work type (`scout`, `reproducer`, `integrator`,
   `auditor`, `auto`, `maintain`):
   - DEEPEN a supported result: what would falsify or strengthen its mechanism?
   - BROADEN to an adjacent untested question: another code family, regime, or method.
   - PIVOT when an assumption broke: the noise model, the baseline, or the premise.
   - CONCLUDE when a contribution, or a coherent negative result, is solid: close that thread of
     work and name what comes next. The loop itself never concludes.

   Write each line concretely enough that the next step can queue it without reinterpretation
   ("DEEPEN pedagogical QOS statevector ridge vs classical baseline on fixed synthetic data", not
   "DEEPEN ML"). Describe a thread of work as paused while work continues elsewhere, never as parked.

## Replan

1. **Hygiene.** Delete finished, stale, and dropped items (`task done`). Merge duplicates. Rewrite
   vague bodies as an imperative with done criteria. Remove resource conditions written as
   blockers. Re-tier `time` from measured runtimes. Reorder by value (`task move`).
2. **Direction into items.** Search the wiki before turning a new Decision log line or open question
   into a task:

   ```bash
   .venv/bin/python skills/wiki-query/scripts/query_wiki.py "<term>" "<term>"
   ```

   Then write the item: search queries for `scout`, reference ids for `reproducer`, lab questions for
   `auto`. Start the body with the pages and dead ends that bear on it: the compiled-page paths, and
   whether a matching dead end's Revisit if condition is already met.
3. **Audit findings.** In `wiki/records/audits/index.yaml`, find ids whose `latest_verdict` is
   `REVISE` and that have no matching task. Read only the `## Actionable items` table of the
   latest report, `wiki/records/audits/<id>/<YYYY-MM-DD>-report.md`. For each critical or major row
   owned by `promote-to-lib`, add an item `for: integrator` whose body is the proposed action,
   the `File:line`, and the "done when" condition, with a link to the report. Queue the re-audit
   triggers as an item `for: auditor` after them. Never paste the report into the task list. A PASS
   needs no item; a FAIL, or a row owned by `human`, goes to the researcher (`skills/research-threads`).
4. **Audit seed.** When the task list lacks runnable work and a promoted algorithm has never been
   audited, add an item
   `for: auditor`.
5. **Refill with lenses** when the task list has no runnable work, using two to four of:
   - baseline gap: where the anchors leave performance on the table;
   - what changed: an old dismissal that is now feasible (faster simulation, a GPU, released weights);
   - cross-pollination: an adjacent technique with a structural fit;
   - boundary probe: where a solver or oracle sketch breaks;
   - tension: accuracy against latency, generality against specialization.

   Each hypothesis must be falsifiable in a setting we can run, or be marked understanding-only. Run
   the same search before adding an item, and use the pages it returns.
6. **Dead ends.** Before queueing a reproduction or a lab, read the Dead ends section of that search,
   and do not queue one whose Revisit if condition is unmet.

There is no quota: a tick that only cleans and reorders is fine when that is what the task list needs.
Prefer editing existing items to adding new ones.

## Escalate and hand off

- Anything that meets the "When to ask" test in `skills/research-threads` becomes a decision brief; the
  affected item is blocked on that thread, and the loop continues with other work.
- Set `next_action` to one concrete research step, the one the next research tick should take, and
  log the tick: `$L log-action --summary "supervisor: ..." --next "..."`.
