# Research Wiki

This folder is the repository's only knowledge layer: what is worth reusing, compiled from
references, labs, notes, and package work, plus the dated records those lessons came from. Raw
material stays where it lives (`references/`, `labs/`, `notes/`, `lib/`); the wiki cites it and does
not copy it.

This `README.md` is the **wiki contract**. Controlled vocabulary lives in `taxonomy.yml`. Start
browsing at [index.md](index.md).

## Navigation: classifier tree, not a hub

- **`index.md` (root)** is a **classifier**. It links only to category sub-indexes, `thesis.md`, and
  other hubs (for example `records/index.md`). It does **not** enumerate every leaf page.
- **Sub-indexes** are each folder's `index.md` (exempt from the compiled-page contract). A
  sub-index lists the compiled pages and nested subfolders **in that folder only**. Nesting under a
  category folder is unbounded (`concepts/…/…`); `page_type` still follows the **top-level** category
  in `taxonomy.yml`.
- **Leaf pages** form a network through `## Related pages` and citations. Do not force every leaf
  through the root index.
- **`thesis.md`** is the standing **scientific synthesis** (what we currently claim), not a second
  catalog. Keep it short; point at evidence pages, do not re-list the classifier tree.

## What lives where

Ledger folders below are **created when the first page is ingested**. Do not pre-create empty
domain trees in the template.

| Folder | Holds | `page_type` | Topic list |
|---|---|---|---|
| `concepts/` | cross-cutting ideas and definitions compiled from several sources | `concept` | `topics` |
| `methods/` | methods at the scientific level for this project | `method` | `topics` |
| `comparisons/` | regime-tagged head-to-head results | `comparison` | `topics` |
| `questions/` | research questions, open or closed, and what would settle them | `question` | `topics` |
| `implementations/` | maps of one code base, a package component, or an external repository | `implementation` | `topics` or `project_topics` |
| `papers/` | compact routers from one reference to its compiled pages and consuming labs | `paper` | none |
| `algorithms/` | one algorithm or routine: claims, parameters, package status | `algorithm` | `topics` |
| `models/` | one model family or model-side finding | `model` | `topics` |
| `techniques/` | reusable practices: evaluation procedures, operational gotchas | `technique` | `topics` or `project_topics` |
| `dead-ends/` | settled negatives: what was tried, why it failed, when to revisit | `dead-end` | `topics` |
| `project/` | researcher-facing manual: product story, principles, how to use the OS | `project` | `project_topics` |
| `package/` | manual of the shared code under repo `lib/` when `features.lib` is on | `package` | `project_topics` |
| `records/` | dated write-ups; also `records/log.md` (wiki operation log) | exempt | exempt |

Root files: `README.md` (this contract), `index.md` (classifier), `thesis.md` (synthesis),
`sources.yml` (provenance ledger), `taxonomy.yml` (controlled vocabulary). Folder `index.md`
files are sub-indexes / guides.

## Knowledge flow

- **References to wiki.** External material lives in `references/<id>/`. After reproduction,
  `references/<id>/reproduce/` is evidence. Ingest into ledger pages or `dead-ends/` as appropriate.
- **Labs to wiki.** Ingest a lab once `REPORT.md` has methods, findings, uncertainty, and a wiki handoff.
- **Notes to wiki.** Cite `notes/<project>/main.pdf` (or `main.tex`); do not paste manuscripts.
- **Decisions.** Researcher decisions go through Threads in `.auto-research/`, not into wiki pages.

## Compiled-page contract

Every Markdown page outside `records/` is a compiled page, except this root `README.md`,
root `index.md`, `records/log.md`, and folder `index.md` sub-indexes.

Frontmatter (YAML): `title`, `page_type`, `status`, `updated`, `source_refs`, `idea_ids`, and
`topics` / `project_topics` as required by `taxonomy.yml`.

Directly under the H1: **Summary**, **Sources**, **Last updated**. End with `## Related pages`.
When you add a leaf page, list it in that folder's `index.md` (create the sub-index if needed). When
you create a new top-level category folder, link its `index.md` from the root `index.md`.
