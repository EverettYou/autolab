# Research Wiki

**Compiled knowledge layer** — what is worth reusing, built from references, labs, notes, and
package work, plus the dated records those lessons came from. Raw material stays where it lives
(`references/`, `labs/`, `notes/`, `lib/`); the wiki cites it and does not copy it.

**This README** is the human floor contract (the wiki contract). Controlled vocabulary lives in
`taxonomy.yml`. **Enforcement:** [`skills/wiki-lint`](../skills/wiki-lint/SKILL.md). Ingest via
[`skills/wiki-ingest`](../skills/wiki-ingest/SKILL.md); look up via
[`skills/wiki-query`](../skills/wiki-query/SKILL.md). Start browsing at [index.md](index.md).

## Role

| Place | Holds |
| --- | --- |
| `wiki/` ledger pages | Durable, cited claims and routers |
| `wiki/system/` | Lab OS manual (sync zone) |
| `wiki/project/` | This lab's research-program pages (not synced) |
| `taxonomy.yml` → `topics` | Living vocabulary (bootstrap-once; ingest may add) |
| `wiki/package/` | Manual of `lib/` when `features.lib` is on |
| `wiki/records/` | Dated write-ups + `records/log.md` |

Other floors (`references/`, `labs/`, `notes/`, Threads): see **vs other floors** below.

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
domain trees in the template. **Naming:** folder `concepts/` → `page_type: concept`;
`literature/`, `project/`, `system/`, `package/` keep the same stem; `deadends/` → `deadend`.
Types are defined in `taxonomy.yml`.

| Folder | Holds |
| --- | --- |
| `concepts/` | Cross-cutting ideas compiled from several sources |
| `methods/` | Methods at the scientific level for this project |
| `comparisons/` | Regime-tagged head-to-head results |
| `questions/` | Research questions and what would settle them |
| `implementations/` | Maps of a code base, package component, or external repo |
| `literature/` | Literature reviews over a **cluster** of references |
| `algorithms/` | One algorithm or routine |
| `models/` | One model family or model-side finding |
| `techniques/` | Reusable practices and operational gotchas |
| `deadends/` | Settled negatives |
| `project/` | Research-program pages for this lab |
| `system/` | Lab OS manual (sync zone) |
| `package/` | Shared-code manual under `lib/` |
| `records/` | Dated write-ups; also `records/log.md` (exempt from compiled-page / topics) |

Root files: `README.md` (this contract), `index.md` (classifier), `thesis.md` (synthesis),
`sources.yml` (provenance ledger), `taxonomy.yml` (controlled vocabulary).

## Knowledge flow

- **References → wiki.** After reproduction, `references/<id>/reproduce/` is evidence. Ingest into
  ledger pages, `literature/` reviews (clusters of papers), or `deadends/` as appropriate. Do not
  mirror a single paper as a wiki page; use optional `references/<id>/README.md` only for archive notes.
- **Labs → wiki.** Ingest once `REPORT.md` has methods, findings, uncertainty, and a wiki handoff.
- **Notes → wiki.** Cite `notes/<project>/main.pdf`; do not paste manuscripts.
- **Decisions.** Researcher decisions go through Threads in `.auto-research/`, not into wiki pages.

## Compiled-page contract

Every Markdown page outside `records/` is a compiled page, except this root `README.md`, root
`index.md`, `records/log.md`, and folder `index.md` sub-indexes.

Frontmatter (YAML): `title`, `page_type`, `status`, `updated`, `source_refs`, `idea_ids`, and
`topics` (required on every compiled page, including `thesis.md`). Topics must be listed under
`taxonomy.yml` → `topics`; that list **grows** — when ingest needs a new subject, add it with
`skills/wiki-ingest/scripts/ensure_topics.py` before tagging the page. Records and folder
`index.md` guides are exempt.

Directly under the H1: **Summary**, **Sources**, **Last updated**. End with `## Related pages`.
When you add a leaf page, list it in that folder's `index.md`. When you create a new top-level
category folder, link its `index.md` from the root `index.md`.

## vs other floors

| | `wiki/` | `labs/` | `references/` |
| --- | --- | --- | --- |
| Purpose | Cited, reusable knowledge | One experiment | External archive |
| Writes | `wiki-ingest` / hand edit under lint | organize-lab | fetch / reproduce |
| Copies raw material? | No — cites only | Owns its outputs | Owns provenance + optional PDF |
