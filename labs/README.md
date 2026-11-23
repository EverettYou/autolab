# Labs

**Experiments** — dated, exploratory, allowed to fail. Each lab answers one bounded question with
its own code, local outputs, and write-up. Labs are **not** the project knowledge graph: durable
claims are distilled into the **wiki** with `wiki-ingest` when (and only when) they are worth
keeping.

**This README** is the human floor contract. **Enforcement:**
[`skills/organize-lab`](../skills/organize-lab/SKILL.md) (`labs_catalog.py validate`,
`lab_layout.py tidy`, report contract) and `create-lab` scaffolding. Landing runs guards `labs` /
`layout`. **Per-lab `README.md` is forbidden** — root may hold only `lab.json`, `PLAN.md`,
`REPORT.md`, `.gitignore`.

Canonical layout detail:
[`skills/organize-lab/references/report-contract.md`](../skills/organize-lab/references/report-contract.md).

## Role vs the rest of the repo

| Place | Holds |
| --- | --- |
| `labs/<id>/` | One experiment: plan, runs, local evidence, report |
| `labs/labs.json` | Generated operational catalog — not a results ledger |
| `labs/_tools/` | Shared path/progress helpers ([`_tools/README.md`](_tools/README.md)) |
| `references/<id>/attempts/` | Untrusted **external** reproduce sandboxes — different trust zone |
| `wiki/` | High-level project knowledge |
| `lib/` | Optional maintained package (when `features.lib` is on) |
| `notes/<Project>/` | Optional long-form manuscripts |

A lab may pin to `lib/` APIs at experiment time; later refactors can break old scripts. The durable
record is `REPORT.md` (and any finding graduated to the wiki), not eternal runnability of every
script.

## Layout of every dated lab

Name: `labs/<YYYY-MM-DD>-<kebab-slug>/`.

An empty shell with only the required files is valid. Do **not** pre-create every directory. Create
a subdirectory only when you have that kind of content; once created, files must sit in the
matching folder.

### Required

```text
labs/<YYYY-MM-DD-slug>/
  lab.json     state + catalog fields (incl. parents)
  PLAN.md      plan before running
  REPORT.md    what ran, commands, results, verdict
```

| Path | Owns |
| --- | --- |
| `lab.json` | `stage`, focus, `next_action`, `references`, `discussion`, `parents` |
| `PLAN.md` | Question, motivation, prior anchors, design, success/stop rules |
| `REPORT.md` | Setting as run, exact commands, results + artifact links, interpretation, verdict |

`create-lab` also writes `.gitignore` (scaffold convention). Missing `.gitignore` does not fail
layout validate. Root may hold **only** those required files plus `.gitignore` — no per-lab
`README.md`, no loose `.py` / extra `.md`, no unknown directories.

### Optional (create when you have cargo)

| Directory | When |
| --- | --- |
| `scripts/` | Code / shell entry points (run from repo root) |
| `notes/` | Supporting Markdown for this experiment (not `notes/<Project>/`) |
| `configs/` | Experiment inputs |
| `tests/` | Lab-local tests |
| `results/` | Small cited machine-readable outputs (&lt; 1 MB each) |
| `figures/` | Plots (prefer PNG in git) |
| `data/` | Bulky generated data (repo-gitignored) |
| `checkpoints/` | Weights (manifests tracked; heavy blobs ignored) |
| `logs/` | Run logs / pids (repo-gitignored) |

### `parents` and catalog

`lab.json` → `parents` lists earlier lab ids this work continues (empty = root exploration). Lineage
is operational context for the next PLAN — not a cross-lab results rollup.

`labs/labs.json` is rebuilt from every `lab.json` (`labs_catalog.py rebuild`). Do not edit by hand.

## How to run / reproduce a lab

Reproduction is **per lab**. Prefer re-running a cited command over inventing a new sweep.
(External papers use `reproduce-reference`, not this section.)

1. Open that lab’s `PLAN.md` and `REPORT.md` → Setting: take the **exact** command, cwd, inputs,
   and acceptance check from the report.
2. Prefer the repository `.venv`. Record GPU/CPU scope the researcher authorized
   (`wiki/system/spending-compute.md`). Do not stop unrelated live jobs.
3. From the **repository root**:

   ```bash
   .venv/bin/python labs/<YYYY-MM-DD-slug>/scripts/<entry>.py …
   ```

4. Write only into that lab’s contracted directories. Prefer fresh output names beside originals
   unless the report says an in-place refresh is safe.
5. Compare numerics with the stated tolerance. Escalate scientific interpretation through
   `research-threads`.
6. If the artifact feeds a Notes figure, keep TeX edits under `notes/<project>/` and recompile
   there.

Shared helpers: put `labs/_tools` on `sys.path`, then `from paths import …` /
`from progress import Progress`.

## Where findings go

- Durable truth → **wiki** (`wiki-ingest` from the lab report when there are real claims)
- Reusable library code → `lib/` via `promote-to-lib`
- Everything else stays in the lab and may go stale

There is **no** `labs/RESULTS.md` or `labs/REPRODUCE.md`. Do not grow labs-root ledgers.

## vs other floors

| | `labs/<date-slug>/` | `references/<id>/` | `notes/<Project>/` |
| --- | --- | --- | --- |
| Purpose | Our experiment | External archive + optional reproduction | Long-form manuscript |
| Trust | Trusted lab code | External / untrusted clones | Our TeX |
| Hard need | `lab.json`, `PLAN.md`, `REPORT.md` | `provenance.json` | `main.pdf` (+ `main.tex` to edit) |
