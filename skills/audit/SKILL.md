---
name: audit
description: Source audit of promoted platform code - read each platform file against its paper and the quality bar (math alignment, bugs, readability, platform invariants), one file per review, then aggregate a report whose actionable items feed the task list. CPU-only; not a promotion gate.
usage: Use after promote-to-lib, or when a task asks for an audit of a reference id or platform module.
---

# Source audit

Port alignment checks numbers; an audit reads code. It runs after promotion, does not block
landing, and never edits `lib/src/`. Its findings become tasks in the replan step of the
`auto-research` supervisor tick.

Target: a reference id (for example a boundary-model paper slug) or a platform module / class
(for example `<package>.models.core`); resolve one to the other with `wiki/algorithms/` or
`wiki/models/` pages and `wiki/records/integrations/`.

Records live in `wiki/records/audits/<id>/`:

| File | Content |
|------|---------|
| `gate.yaml` | loop state for the current iteration |
| `workspace/<basename>.md` | one file review per platform file |
| `<YYYY-MM-DD>-report.md` | the aggregated report |
| `audit-index.yaml` | one entry per audit iteration |

`wiki/records/audits/index.yaml` is the master index that the `auto-research` supervisor tick scans when it replans.

## Gate state

```yaml
slug: <id>
phase: plan                  # plan | review | aggregate | done | failed
lib_target: <module or class>
paper_available: true        # references/<id>/paper.pdf present locally
iteration: 1                 # matches the latest audit-index.yaml entry; increment on re-audit
files:
  - path: lib/src/<package>/...
    status: pending          # pending | pass | revise | fail
    workspace_file: null
verdict: null
verdict_date: null
```

## PLAN

1. Query the wiki for the target, then resolve id and lib classes from the hit pages and
   `wiki/records/integrations/`:

   ```bash
   .venv/bin/python skills/wiki-query/scripts/query_wiki.py "<id or lib target>"
   ```

2. List the files: each primary `.py` under `lib/src/<package>/` for this target, with its tests in
   `lib/tests/` merged into the matching module's review. Skip bare `__init__.py` files.
3. Note what exists: `references/<id>/` (paper, provenance, `reproduce/`), earlier audits in
   `wiki/records/audits/<id>/`, and older faithfulness reviews.
4. For a first audit create `wiki/records/audits/<id>/` and an `audit-index.yaml` with `slug`,
   `lib_target`, and `audits: []`. Write `gate.yaml` and set `phase: review`.

Do not pre-package paper excerpts for the reviews; each review finds its own context.

Example file set:
`lib/src/<package>/models/core.py`, `lib/src/<package>/solvers/runner.py`,
and `lib/tests/test_*.py` merged into the matching module reviews.

## REVIEW

1. Apply [references/file-review.md](references/file-review.md) to each `pending` file, one file
   per review, at most 6 per session. Separate agent sessions may take files in parallel; the same
   agent may take them in turn.
2. Save each review as `workspace/<basename>.md` and set `files[].status` and `workspace_file`.
3. When no file is pending, set `phase: aggregate`.

## AGGREGATE

1. Merge the reviews into `wiki/records/audits/<id>/<YYYY-MM-DD>-report.md`:

   ```markdown
   # Audit: <id>, <date>

   Verdict: PASS | REVISE | FAIL
   Platform: ...

   ## Summary
   ## Algorithm brief
   ## Paper, reproduction, and platform
   ## Findings by severity

   ## Actionable items
   | ID | Priority | Owner | File:line | Gap | Proposed action | Done when |

   ### Re-audit triggers
   ## File index
   ```

   Owner is `promote-to-lib`, `audit`, or `human`. The worst file verdict wins. A REVISE or
   FAIL report without at least one actionable item row is incomplete: redo AGGREGATE.
2. Append to `audit-index.yaml`: iteration, date, verdict, report path, files audited, actionable
   counts by severity, and whether a re-audit is triggered.
3. Update `wiki/records/audits/index.yaml` for this id: `latest_verdict`, `latest_audit_date`,
   `iteration_count`, `open_critical_major` (add the entry on a first audit, bump `updated`).
4. Update the related `wiki/algorithms/` or `wiki/models/` page with the audit date, verdict, and
   a link to the report.
5. Set `phase: done` (or `failed` on FAIL), with `verdict` and `verdict_date`.

## FOLLOW-UP

| Verdict | Action |
|---------|--------|
| PASS | Remove the audit item from the `.auto-research/state.json` task list. |
| REVISE | Report and gate only; the `auto-research` supervisor tick turns the actionable items into tasks. |
| FAIL | Also open a discussion thread for the human (`research-threads`). |

Land the records with explicit paths (`git-workflow`): `wiki/records/audits/` and the related
algorithm or model pages.

## Rules

- CPU only; no GPU benchmarks. Short file-specific pytest runs are fine.
- Never edit `lib/src/` or `lib/tests/` during an audit.
- Every gap row carries a proposed action and a "done when" condition.
