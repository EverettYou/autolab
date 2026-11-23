# Research Wiki

**Compiled knowledge layer** — what is worth reusing, built from references, labs, notes, and
package work, plus the dated records those lessons came from. Raw material stays where it lives
(`references/`, `labs/`, `notes/`, `lib/`); the wiki cites it and does not copy it.

**This README** is the human floor contract (the wiki contract). Controlled vocabulary lives in
`taxonomy.yml`. **Enforcement:** [`skills/wiki-lint`](../skills/wiki-lint/SKILL.md). Ingest via
[`skills/wiki-ingest`](../skills/wiki-ingest/SKILL.md); look up via
[`skills/wiki-query`](../skills/wiki-query/SKILL.md). Start browsing at [index.md](index.md).

## Role vs the rest of the repo

| Place | Holds |
| --- | --- |
| `wiki/` ledger pages | Durable, cited claims and routers |
| `wiki/project/` | Researcher-facing Lab OS manual (sync zone) |
| `wiki/package/` | Manual of `lib/` when `features.lib` is on |
| `wiki/records/` | Dated write-ups + `records/log.md` |
| `references/<id>/` | External sources (cite; don’t copy) |
| `labs/<id>/` | Experiments (ingest from `REPORT.md` when claims hold) |
| `notes/<Project>/` | Manuscripts (cite `main.pdf`; don’t paste TeX) |
| `.auto-research/` | Threads / loop decisions — not wiki pages |

## Navigation: classifier tree, not a hub

- **`index.md` (root)** is a **classifier**. It links only to category sub-indexes, `thesis.md`,
  and other hubs (for example `records/index.md`). It does **not** enumerate every leaf page.
- **Sub-indexes** are each folder's `index.md` (exempt from the compiled-page contract). A
  sub-index lists pages and nested subfolders **in that folder only**. Nesting under a category
  is unbounded; `page_type` still follows the **top-level** category in `taxonomy.yml`.
- **Leaf pages** form a network through `## Related pages` and citations.
- **`thesis.md`** is the standing scientific synthesis (what we currently claim), not a second
  catalog. Keep it short; point at evidence pages.

## What lives where

Ledger folders below are **created when the first page is ingested**. Do not pre-create empty
domain trees in the template.

| Folder | Holds | `page_type` | Topic list |
| --- | --- | --- | --- |
| `concepts/` | Cross-cutting ideas compiled from several sources | `concept` | `topics` |
| `methods/` | Methods at the scientific level for this project | `method` | `topics` |
| `comparisons/` | Regime-tagged head-to-head results | `comparison` | `topics` |
| `questions/` | Research questions and what would settle them | `question` | `topics` |
| `implementations/` | Maps of a code base, package component, or external repo | `implementation` | `topics` or `project_topics` |
| `papers/` | Routers from one reference to compiled pages and labs | `paper` | none |
| `algorithms/` | One algorithm or routine | `algorithm` | `topics` |
| `models/` | One model family or model-side finding | `model` | `topics` |
| `techniques/` | Reusable practices and operational gotchas | `technique` | `topics` or `project_topics` |
| `dead-ends/` | Settled negatives | `dead-end` | `topics` |
| `project/` | Lab OS / product manual | `project` | `project_topics` |
| `package/` | Shared-code manual under `lib/` | `package` | `project_topics` |
| `records/` | Dated write-ups; also `records/log.md` | exempt | exempt |

Root files: `README.md` (this contract), `index.md` (classifier), `thesis.md` (synthesis),
`sources.yml` (provenance ledger), `taxonomy.yml` (controlled vocabulary).

## Knowledge flow

- **References → wiki.** After reproduction, `references/<id>/reproduce/` is evidence. Ingest into
  ledger pages or `dead-ends/` as appropriate.
- **Labs → wiki.** Ingest once `REPORT.md` has methods, findings, uncertainty, and a wiki handoff.
- **Notes → wiki.** Cite `notes/<project>/main.pdf`; do not paste manuscripts.
- **Decisions.** Researcher decisions go through Threads in `.auto-research/`, not into wiki pages.

## Compiled-page contract

Every Markdown page outside `records/` is a compiled page, except this root `README.md`, root
`index.md`, `records/log.md`, and folder `index.md` sub-indexes.

Frontmatter (YAML): `title`, `page_type`, `status`, `updated`, `source_refs`, `idea_ids`, and
`topics` / `project_topics` as required by `taxonomy.yml`.

Directly under the H1: **Summary**, **Sources**, **Last updated**. End with `## Related pages`.
When you add a leaf page, list it in that folder's `index.md`. When you create a new top-level
category folder, link its `index.md` from the root `index.md`.

## vs other floors

| | `wiki/` | `labs/` | `references/` |
| --- | --- | --- | --- |
| Purpose | Cited, reusable knowledge | One experiment | External archive |
| Writes | `wiki-ingest` / hand edit under lint | organize-lab | fetch / reproduce |
| Copies raw material? | No — cites only | Owns its outputs | Owns provenance + optional PDF |
