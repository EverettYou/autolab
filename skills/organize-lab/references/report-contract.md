# Lab file contract

A lab is one bounded question under `labs/<YYYY-MM-DD-slug>/`. **This file is the canonical,
machine-checked definition** of what a lab contains: `create-lab` scaffolds it, `organize-lab`
validates / tidies / report-lints it, and the dashboard renders it. Human summary:
[labs/README.md](../../../labs/README.md). Tool when-to-run table: `skills/organize-lab/SKILL.md`
(Enforcement). `labs/labs.json` is generated from the `lab.json` files and is never edited by hand.

## Layout

**Required** (layout validate errors if missing; dashboard / catalog need them):

```
labs/<YYYY-MM-DD-slug>/
  lab.json
  PLAN.md
  REPORT.md
```

**Scaffold also writes** `.gitignore` (recommended; not a layout-validate hard miss).

**Optional directories** — create only when you have that kind of content; then place files by type
(`CONTENT_RULES` / `lab_layout.py tidy`). An empty shell with only the required files is valid.

```
  notes/        supporting documents that REPORT.md or PLAN.md link to
  scripts/      all code, including shell launchers
  configs/      experiment inputs
  tests/        lab-local tests
  results/      small machine-readable outputs that REPORT.md cites (tracked)
  figures/      plots generated from results/ (tracked)
  data/         bulky generated data: samples, predictions, buffers (ignored)
  checkpoints/  model weights: manifests tracked, blobs ignored
  logs/         run logs and pid files (ignored)
```

The lab root holds exactly `lab.json`, `PLAN.md`, `REPORT.md`, and optionally `.gitignore`. Each
required file has one job:

| File | Owns |
|------|------|
| `lab.json` | Machine-readable state and catalog fields (schema below). One-line values only, no prose. `stage` is the only lab state; do not repeat it as a status line in Markdown. |
| `PLAN.md` | The registered plan: question, motivation, prior anchors, hypotheses, setting, design, success criterion, stop rules. Written before running; once runs start, only dated notes under Amendments are added. |
| `REPORT.md` | What was actually run and what it established, readable without the plan: the question in one or two sentences linking `PLAN.md`, the setting as run with the exact commands, results with their artifacts, interpretation, verdict, next steps. |
| `.gitignore` | Lab-local transient ignores (see Git policy). |

There is no per-lab README. What the lab is lives in `lab.json` (`title`, `summary`); how to run it
lives in the REPORT Setting and each entry point's docstring. The folder layout for humans is also
summarized in [labs/README.md](../../../labs/README.md); this contract remains the machine-checked
definition.

When optional dirs exist, everything else has one place:

- Other Markdown goes in `notes/`: sub-experiment write-ups, audits, reviews, run books for long
  runs, and material transcribed from outside the repository. New note names are lowercase
  kebab-case.
- Code goes in `scripts/`. Each entry point starts with a docstring that says what it does and how
  to call it. Scripts find the lab with `LAB = Path(__file__).resolve().parents[1]` and are run from
  the repository root. How to reproduce a lab lives in **that lab’s** `PLAN.md` / `REPORT.md`
  (Setting commands), not in a `labs/`-wide file — see [labs/README.md](../../../labs/README.md).
- No status, to-do, or loop-state documents: state is `lab.json`, open work is the `.auto-research`
  task list, and decisions for the researcher are discussion threads.
- A directory that fits none of the above goes under `data/<name>/` (generated), `configs/<name>/`
  (inputs), or `notes/` (documents). An old sub-experiment folder that holds its own code moves
  whole to `scripts/<name>/`, so its relative paths keep working.
- Shared helpers live in `labs/_tools/` (`paths`, `progress`; see `labs/_tools/README.md`). Import them
  instead of copying or hand-building output directories (`from paths import lab_output, …`).

## Git policy

This repository tracks slim numerical evidence. `create-lab` writes a lab-local `.gitignore` that ignores
only transient files (`__pycache__/`, `.cache/`, `*.pid`, `*.lock`). The repository `.gitignore`
drops bulky lab trees (`labs/**/data/`, `labs/**/logs/`, heavy weight blobs, archives). Keep
provenance of ignored outputs in the report.

Keep each file in `results/` and `figures/` under 1 MB. Larger outputs belong in `data/`, and the
report cites a small summary instead.

**Repo size budget:** `data/` and `logs/` are gitignored. Git tracks REPORT/notes/scripts/figures and
slim `results/*.json` summaries (full tables may live locally under `data/`). Prefer a PNG in git
when a figure also has an SVG.

A JSON file in `results/` keeps the numbers the report quotes (parameters, metrics, seeds, config).
Large arrays go in `data/` and the JSON records a lab-relative path, for example
`"plot_data": "data/spectrum.npz"`.

Labs may need their own ignore exceptions; write them in the lab's `.gitignore`. Do not add
per-lab lines to the repository `.gitignore`. Optional consumer-only grandfather lists (if a
checkout introduces `labs/layout-exceptions.json`) are local — new labs from this template get no exceptions;
let `tidy` place misplaced files.

## lab.json

```json
{
  "id": "2026-11-16-delta-phase-boundary",
  "title": "Bond-staggering phase boundary",
  "stage": "active",
  "summary": "One sentence a reader can scan in the catalog.",
  "current_focus": "What the lab is doing now.",
  "next_action": "The next concrete step, or empty when complete.",
  "created": "2026-11-16",
  "updated": "2026-11-18",
  "references": ["main"],
  "discussion": ["thread-001"],
  "parents": ["2026-11-01-prior-lab"]
}
```

- `id` equals the directory name; `created` is the id's date.
- `stage` is one of `active`, `blocked`, `complete`, `inactive`. A `blocked` lab also has
  `blocked_reason`: one sentence saying why it is blocked. `next_action` then says how to clear it.
- `references` are ids under `references/`; `discussion` are thread ids in `.auto-research/state.json`.
- `parents` are other lab ids this work continues (lineage). Empty means a root exploration. Parents
  are not a cross-lab results ledger — project knowledge is distilled into the wiki via
  `wiki-ingest`, not rolled up under `labs/`.
- `updated` changes whenever the lab's state, focus, next action, or findings change.
- File names are fixed by this contract; `lab.json` does not list them.

`labs/labs.json` holds `{"labs": [...]}` with `id`, `title`, `stage`, `summary`, `current_focus`,
`next_action`, `created`, `updated`, `parents` per lab, sorted newest first by creation date.

## PLAN.md

`PLAN.md` follows the `create-lab` template: Question, Motivation, Prior anchors, Hypotheses and
alternatives, Setting, Design, Success criterion, Stop rules, Completion, Amendments. Prior anchors
tie wiki background to `lab.json` `parents`. A later revision of the plan is a dated entry under
Amendments, not a second plan file.

## REPORT.md

Required second-level sections, in this order (extra sections may sit between them):

1. `## Question` - the closed question and the success criterion in one or two sentences, linking
   `PLAN.md` for the motivation and design.
2. `## Setting` - the setting as run: data/protocol regime, parameters that move the number,
   solver or training config, samples/shots, seeds, package/commit if relevant, deviations from
   `PLAN.md`, and the exact commands (from the repository root) that produced each result.
3. `## Results` - tables and figures with uncertainty. Every quantitative claim links the
   machine-readable artifact it came from (`results/*.json` or similar).
4. `## Interpretation` - mechanism, agreement or conflict with prior results, alternatives that
   were ruled out, limitations.
5. `## Verdict` - the answer at the strength the evidence supports: supported, not supported, or
   inconclusive (name the underpowered rows).
6. `## Next steps` - follow-ups with owners: tasks, promotion candidates, wiki pages to
   update, discussion threads to open. Write "None" when there are none.

Writing rules:

- Absolute dates (`2026-09-25`), never "today" or "last week".
- Compare results only within one setting (same regime and fair controls). A cross-setting number
  is context, not a ranking.
- Record failed branches and negative results; they are findings.
- Each figure has an italic caption line directly below it that names the data it plots.
- Until the first result, `REPORT.md` is the template skeleton. Afterwards it records what has run
  and marks what is still pending; it never presents expected results as findings.

## Sources and reconstructed documents

Link material that is in the repository and summarize it; do not copy it. Material outside the
repository, or only in git history, cannot be linked: transcribe the relevant part into `notes/`
with a header naming its source, then summarize and link the transcription. A `PLAN.md` or
`REPORT.md` written after the fact starts with a provenance note;
[reconstruct.md](reconstruct.md) describes the procedure.

## Deterministic checks

- `scripts/labs_catalog.py validate` checks every `lab.json` against the schema and every lab
  against the layout: root files, the two documents, directory names, each tracked file's
  directory against its type (`CONTENT_RULES`), and file sizes in `results/` and `figures/`.
- `scripts/lab_report_lint.py` enforces the mechanical part of the document contract: section
  presence and order, resolvable relative links (including `notes/`), at least one
  machine-readable artifact cited in Results, a non-empty Verdict, a `PLAN.md` with Question and
  Success criterion headings, and no leftover `<!-- fill: ... -->` markers. Figures without
  captions, reports over the line budget, and a Setting that names no `scripts/` command are
  warnings.
- `scripts/lab_layout.py tidy <lab-id>` moves stray files of a lab into this layout and rewrites
  the links that pointed at them.
