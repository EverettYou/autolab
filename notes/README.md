# Notes

**Long-form manuscripts** (LaTeX → PDF), edited in the dashboard Notes workbench when
`features.notes: true`. This is **not** `labs/<id>/notes/` (lab-local Markdown supporting a
report).

**This README** is the human floor contract. Soft conventions only — there is no lab-style lint
gate. The dashboard lists folders that look like Notes projects (reading PDF and/or editable
main source). Project layout detail for the UI is here; dashboard mechanics are in
[`dashboard/README.md`](../dashboard/README.md).

## Role vs the rest of the repo

| Place | Holds |
| --- | --- |
| `notes/<Project>/` | One manuscript: source, reading PDF, optional figures / scripts / data |
| `labs/<id>/notes/` | Supporting Markdown for one experiment |
| `references/<id>/` | External papers (archive PDFs there, not here) |
| `wiki/` | Cited knowledge; link to `main.pdf`, do not paste large TeX |
| `lib/` | Optional shared package |

Enable with `features.notes: true` in `config.yml`, then add projects under this folder.

## Layout of every project

Name: `notes/<Project Title>/` (human-readable title is OK). One project = one folder = one main
PDF.

### Required (minimum readable project)

| Path | Role |
| --- | --- |
| `notes/<Project>/` | Project root |
| `main.pdf` | Reading copy the dashboard / wiki can open |

Without `main.pdf` there is nothing to present. A PDF-only project is valid and **read-only** in
Notes (no source to edit or recompile).

### Required for an editable project

| Path | Role |
| --- | --- |
| `main.tex` (or legacy `main.txt`) | Main LaTeX source the workbench edits and compiles |

Keep the **entry** file as `main.tex`. Supporting `.tex` inputs may sit beside it or in
subfolders via `\input` / `\include`. Editable projects normally keep both `main.tex` and
`main.pdf` (compile refreshes the PDF).

### Optional (create when you have cargo)

| Path | Role |
| --- | --- |
| `figures/` | Assets included by TeX |
| `data/` | Sparse snapshots used to redraw figures (not full lab dumps) |
| `scripts/` | Figure-generation scripts that write into `figures/` |
| `*.bib` | Bibliography |
| `.build/` | Compile / plot cache — gitignored (`notes/**/.build/`) |

```text
notes/<Project Title>/
  main.tex          # required to edit / compile
  main.pdf          # required to read
  figures/          # optional
  scripts/          # optional
  data/             # optional
  references.bib    # optional
  .build/           # local cache (not tracked)
```

## Conventions

- **One project = one folder = one main PDF.** Do not pile unrelated papers in one folder.
- **Main source name:** `main.tex` (dashboard default). Other `.tex` files are includes.
- **Figures:** prefer vector PDF in `figures/`; regenerate via `scripts/` when a script owns them.
- **Data in notes is thin:** plot tables for figures. Full experiment records stay in `labs/`.
- **Build intermediates** under `.build/` or TeX aux names already ignored by `.gitignore`.
- **Wiki cites Notes** (link to `main.pdf`); do not paste large TeX into wiki pages.

## Compile (outside the dashboard)

```bash
cd "notes/<Project Title>"
mkdir -p .build
xelatex -interaction=nonstopmode -halt-on-error -output-directory=.build -jobname=main main.tex
xelatex -interaction=nonstopmode -halt-on-error -output-directory=.build -jobname=main main.tex
cp .build/main.pdf main.pdf
```

Or use **Compile** in the dashboard Notes tab after editing `main.tex`.

## vs other floors

| | `notes/<Project>/` | `labs/<id>/notes/` | `references/<id>/` |
| --- | --- | --- | --- |
| Purpose | Manuscript / long-form paper | Supporting Markdown for one experiment | External archive |
| Hard need | `main.pdf` (+ `main.tex` to edit) | Lab’s `lab.json` / PLAN / REPORT | `provenance.json` |
| Feature flag | `features.notes` | Always part of lab layout (optional dir) | always on |
