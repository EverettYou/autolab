---
name: create-lab
description: Start a new dated lab under labs/ with `lab.json`, `PLAN.md`, `REPORT.md` and `.gitignore`, and register it in `labs/labs.json`.
usage: Use when a bounded research question needs its own runs, results and report. Use `reproduce-reference` instead when the goal is to reproduce a paper or repository.
---

# Create a lab

A lab answers one bounded question with its own code, results, and report. Labs are exploratory:
creating one does **not** claim useful knowledge yet. Project high-level knowledge lives in the
**wiki** (via `wiki-ingest` after a lab earns claims). Human-facing folder layout:
[`labs/README.md`](../../labs/README.md). Machine-checked contract:
`skills/organize-lab/references/report-contract.md`. Reproduction stays in **that lab’s** `PLAN.md` /
`REPORT.md` — there is no `labs/REPRODUCE.md`.

## Before creating

1. **Wiki first** — background knowledge and open questions:

   ```bash
   .venv/bin/python skills/wiki-query/scripts/query_wiki.py "<term>" "<term>"
   ```

   Record the pages, dead ends, and open questions that apply. The wiki is the high-level knowledge
   source; a new lab should know what the project already believes before it runs.

2. **`labs/labs.json` next** — operational index and **parent lineage**:

   - If an `active` or `inactive` lab already covers the same closed question, continue that lab
     (`organize-lab`) instead of forking a twin.
   - If one or more earlier labs are the work this question continues, name them as **parents**
     (`lab.json` `parents` / `--parent`). Labs often inherit: a later lab pushes forward from
     another lab's setting, code, or partial answer. Clear parents at create time; empty `parents`
     means a root exploration with no lab predecessor.
   - Do **not** look for a cross-lab results rollup file — there is none. Local evidence stays under
     each lab; only distilled claims go to the wiki later.

3. Make sure the question is closed: answerable with yes/no or a number, with a success criterion
   you can state before running.

## Steps

1. Scaffold the lab (the date defaults to today):

   ```bash
   python3 skills/create-lab/scripts/new_lab.py --slug <kebab-slug> --title "<title>" \
       --summary "<one sentence>" [--parent <lab-id> ...] [--reference <id> ...] \
       [--thread <thread-id> ...]
   ```

   The script creates **only the four root files** under `labs/<YYYY-MM-DD-slug>/`:

   - `lab.json` (stage `active`, `parents` as given)
   - `PLAN.md`, `REPORT.md` (templates with `<!-- fill: -->`)
   - `.gitignore`

   It does **not** pre-create empty `scripts/`, `results/`, etc. — that is intentional. It refuses
   to overwrite an existing lab, checks parent / reference / thread ids, validates the new
   `lab.json`, and rebuilds `labs/labs.json`.

### Required vs optional (do not invent other roots)

**Required** (layout/validate fails without them): `lab.json`, `PLAN.md`, `REPORT.md`.  
**Also scaffolded:** `.gitignore` (keep it; missing it does not fail layout validate).

Lab root may hold **only** those files (no per-lab `README.md`, no loose `.py` / `.md`).

**Optional** directories — create when you have cargo (mkdir or `paths.lab_output`); then file by type:

| Directory | Holds |
| --------- | ----- |
| `notes/` | Supporting Markdown |
| `scripts/` | All code and shell entry points |
| `configs/` | Experiment inputs |
| `tests/` | Lab-local tests |
| `results/` | Small cited machine-readable outputs (&lt; 1 MB each) |
| `figures/` | Plots |
| `data/` | Bulky generated data (repo-gitignored) |
| `checkpoints/` | Weights (manifests tracked; heavy blobs ignored) |
| `logs/` | Run logs / pids (repo-gitignored) |

A lab with only the required files is valid. Cited paths in `REPORT.md` must exist when claimed.

Full contract: `skills/organize-lab/references/report-contract.md`. Summary: [`labs/README.md`](../../labs/README.md).

2. Register the plan: replace every `<!-- fill: ... -->` marker in `PLAN.md`. Fill **Prior anchors**
   with wiki background and how this lab relates to each parent. The `run-lab` skill
   describes arms, shots, and stop rules. Once runs start, the registered sections do not change;
   add dated notes under Amendments.
3. Leave `REPORT.md` as the template skeleton until the first result. Then write Setting as it was
   actually run, with the exact commands, and Results with their artifacts; mark what is still
   pending. Never write expected results as findings.
4. Update `lab.json` (`current_focus`, `next_action`, `updated`), rebuild the catalog with
   `python3 skills/organize-lab/scripts/labs_catalog.py rebuild`, and commit the lab with explicit
   paths (`git-workflow`).

When the lab is the active deliverable of an autonomous loop, record its acceptance criteria in
the loop state as the `auto-research` skill describes.

## After the lab (knowledge, not rollup)

Not every lab produces project knowledge. When `REPORT.md` has real claims worth keeping, distill
them with `wiki-ingest` (lab as source) into the right wiki pages — possibly several entries from
one lab, or none. Do not append to any labs-wide results ledger. Before `stage: complete`, run
`lab_report_lint.py` (see `organize-lab` Enforcement).

## Rules while the lab runs

- Everything the lab writes stays inside its directory and the legal tree above: code in
  `scripts/`, other Markdown in `notes/`, cited outputs in `results/` and `figures/`, bulky
  outputs in `data/`, weights in `checkpoints/`, logs in `logs/`. Nothing else goes in the lab root.
- Start every entry point in `scripts/` with a docstring that says what it does and how to call it,
  and find the lab with `LAB = Path(__file__).resolve().parents[1]`.
- Import shared lab helpers from `labs/_tools/` (`paths`, `progress`; see `labs/_tools/README.md`) instead of
  copying them. Route outputs with `lab_output`, `lab_place`, and `lab_run_file`; open files with
  `truncate_for_run` or `require_absent` (see the lab file contract in `organize-lab`).
- Keep state in `lab.json`, open work in the `.auto-research` task list, and questions for the
  researcher in discussion threads; do not write status or to-do documents in the lab.
- Run Python with the repository venv (`.venv/bin/python`). Code that is not yet trusted runs in the
  isolated runtime described by `runtime-env`.
- Do not edit `lib/` or `references/` from a lab. Code that deserves to live in the package
  goes through `promote-lib`.
- Heavy GPU training follows the compute rules in `AGENTS.md`, `skills/auto-research/references/spending-compute.md`,
  and `wiki/models/gpu-training-protocol.md`: smoke test first, a measured step time and numeric
  ETA before any long run, flushed progress logs, and early stop on saturation.
- Put machine-readable outputs in `results/`, each file under 1 MB, and cite them from
  `REPORT.md`; the completion gate in `organize-lab` checks this. A JSON file keeps the numbers
  the report quotes. Per-shot arrays go in `data/` as `.npz`, and the JSON records that path.
