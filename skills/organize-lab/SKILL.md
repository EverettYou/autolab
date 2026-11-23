---
name: organize-lab
description: Keep `labs/` consistent - move a lab between stages, validate every `lab.json` and lab layout, tidy stray files into place, rebuild the `labs/labs.json` catalog, and gate completion on the report contract.
usage: Use after any lab state change, when finishing a lab, when files land in the wrong place, or when the catalog looks stale.
---

# Organize labs

A lab is one bounded question under `labs/<YYYY-MM-DD-slug>/`. Its root holds exactly `lab.json`,
`PLAN.md`, `REPORT.md`, and `.gitignore`; code, notes, and outputs have fixed directories. The
**canonical** layout is [references/report-contract.md](references/report-contract.md); human
summary: [labs/README.md](../../labs/README.md). Create labs with the `create-lab` skill; this
skill maintains them afterwards.

## Enforcement

README does not enforce structure. Use these tools:

| Command | When | Checks / does |
| ------- | ---- | ------------- |
| `python3 skills/organize-lab/scripts/labs_catalog.py validate [-q] [LAB …]` | After lab edits; land guard `layout` | `lab.json` schema + directory layout (four root files, known dirs, file types, size caps) |
| `python3 skills/organize-lab/scripts/labs_catalog.py rebuild` / `check` | After `lab.json` changes; land guard `labs` | Rewrite / freshness of `labs/labs.json` |
| `python3 skills/organize-lab/scripts/lab_layout.py tidy <lab-id> [--apply]` | When validate reports misplaced files | Move strays, fix `__file__` paths and repo links |
| `python3 skills/organize-lab/scripts/lab_layout.py check --links --imports` | After tidy / audits | Broken lab links and import regressions |
| `python3 skills/organize-lab/scripts/lab_report_lint.py <lab-id>` | **Before** setting `stage` to `complete` | REPORT/PLAN mechanical contract + layout/schema |

Landing runs guards `labs` and `layout` only — **not** `lab_report_lint`. Incomplete labs may still
have template `REPORT.md`; a lab must pass report lint before `complete`.

## Stages

| Stage | Meaning | Leaves when |
|-------|---------|-------------|
| `active` | Work is in progress. | The question is answered (`complete`), a named dependency stalls it (`blocked`), or it sits unused (`inactive`). |
| `blocked` | Waiting on a named dependency: a human decision, a GPU window, another lab, or a platform fix. | The dependency clears (`active`). |
| `complete` | The report passed the completion gate. | Never. A follow-up question is a new lab that links this one. |
| `inactive` | Sitting unused, with nothing scheduled. | Someone resumes it (`active`). |

- `lab.json.stage` is the only lab state. Do not repeat it as a status line in Markdown.
- A `blocked` lab names why in `blocked_reason` and how to clear it in `next_action`. When the
  blocker is a human decision, open a thread with `research-threads` and add the thread id to `discussion`.
- Bump `updated` whenever stage, focus, next action, or findings change.
- Never rename or delete a lab directory. Lab ids are cited by reports, wiki pages, threads, and
  registry entries.
- `labs/_tools/` holds shared helpers (`paths`, `progress`; see `labs/_tools/README.md`), not a lab. Directories
  starting with `_` are skipped by the catalog.

## After any lab change

1. Edit the lab's `lab.json` (`stage`, `current_focus`, `next_action`, `updated`, `references`,
   `discussion`, `parents`).
2. Rebuild the catalog:

   ```bash
   python3 skills/organize-lab/scripts/labs_catalog.py rebuild
   ```

   `rebuild` validates every `lab.json` first and refuses to write while any is invalid; fix the
   reported errors (or pass `--force` to write the valid entries only, and fix the rest next).
3. Commit the lab files and `labs/labs.json` together with explicit paths (`git-workflow`).

`labs_catalog.py validate [LAB_ID ...]` checks without writing (`--json` for machine output,
`-q` for errors only); `labs_catalog.py check` exits 1 when `labs/labs.json` is stale.

## Layout

`labs_catalog.py validate` also checks each lab against the layout: only the four root files, both
documents present, known directory names, every tracked file in the directory its type belongs to
(figures in `figures/`, other Markdown in `notes/`, logs in `logs/`, arrays in `data/`, code in
`scripts/`; a TeX document in `notes/` may keep its build files beside it, and a folder under
`scripts/` is an old sub-experiment with its own layout), and no file over 1 MB in a tracked
`results/` or `figures/`. The `land` guard bundle runs it, so a misplaced file blocks a landing. When files sit in the wrong place, let the tidy tool move them:

```bash
python3 skills/organize-lab/scripts/lab_layout.py tidy <lab-id>           # show the moves
python3 skills/organize-lab/scripts/lab_layout.py tidy <lab-id> --apply   # perform them
python3 skills/organize-lab/scripts/lab_layout.py check --links --imports # layout, broken lab links, imports
```

`tidy` moves stray code to `scripts/` (a folder that holds code moves whole, to `scripts/<name>/`),
stray Markdown to `notes/`, logs, figures, and outputs to their directories, adjusts `__file__`-based
paths in moved scripts, and rewrites every link in the repository that pointed at a moved file.
Code elsewhere follows too: a `sys.path` entry that names the lab's root now names its `scripts/`,
and a path joined onto the lab's root (`DEMO / "common.py"`) gets the new place. Records of past
runs (a lab's `results/`, `data/`, `logs/`, `checkpoints/`, and log and table files anywhere) and
verbatim transcriptions keep their paths as written. It refuses a lab that is running (a live
process, or a file written in the last 30 minutes) and skips any file that changed after the
preview. Lines it cannot adjust safely are printed for review; fix them by hand. Compare
`check --imports` before and after a tidy: an import that stopped resolving is a regression.

## Missing PLAN or REPORT

A lab without a `PLAN.md` or `REPORT.md` gets one reconstructed from its own materials and the
records that mention it, following [references/reconstruct.md](references/reconstruct.md). A
reconstructed document says so in its first lines and never invents what the materials do not
show.

## Completion gate

Run this before setting `stage` to `complete`.

1. Bring `REPORT.md` to the contract: Question, Setting, Results, Interpretation, Verdict, Next
   steps.
2. Run the deterministic lint and fix every error:

   ```bash
   python3 skills/organize-lab/scripts/lab_report_lint.py <lab-id>
   ```

3. Review what the lint cannot check. Reread the report as a skeptical reader:
   - every number in the report matches the artifact it links;
   - the Verdict answers the `PLAN.md` question at the strength the counts support, and any
     ratio or comparison claim matches the evidence strength the counts support;
   - rankings stay within one setting; cross-setting numbers are labeled as context;
   - the claim matches the evaluation kind (a claim verification is not a benchmark, a port
     alignment is not a reproduction);
   - failed branches and deviations from the plan are recorded, with dates.
4. Set `stage` to `complete`, update `current_focus` to the one-line result, set `next_action` to
   the follow-up lab or empty, bump `updated`, and rebuild the catalog.
5. Route what the lab produced:
   - reusable knowledge: `wiki-ingest` (algorithms, models, techniques, dead ends);
   - code worth keeping: `promote-to-lib`;
   - checkpoints and measurement tables of record: keep under the lab (`checkpoints/`, `results/`)
     and cite them from `REPORT.md` / the wiki — do not invent a parallel top-level store;
   - follow-up work: the `.auto-research` task list (`auto-research`);
   - decisions that need a human: `research-threads`.

## Periodic tidy

When the catalog looks stale, or as part of a maintenance pass:

1. `labs_catalog.py validate -q` and fix every error; `lab_layout.py tidy` the labs with layout
   findings.
2. For each `active` lab with no change for 14 days, check whether anything still runs for it
   (`runtime-env` snapshot, GPU process list). If nothing does, set `inactive`, or `blocked` with
   the blocker named.
3. For each `blocked` lab, check whether the blocker cleared (thread resolved, GPU free, platform
   fix merged) and move it back to `active` if so.
4. Rebuild the catalog and commit.
