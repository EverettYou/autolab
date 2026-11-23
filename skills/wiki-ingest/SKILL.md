---
name: wiki-ingest
description: Compile sources into the project wiki and keep it current.
usage: Use when a reference (paper, repository, dataset) or its reproduction, a finished lab report, platform code, or a saved query synthesis should become cited wiki knowledge; when filing a dated record (discovery, design, audit, integration, synthesis); when adding an algorithm, model, technique, or dead-end page; or when initializing a wiki.
---

# Wiki ingest

Compile a source once and keep the wiki current. One source may revise many existing pages; do not write a
standalone summary and stop. The rules every page follows are in `wiki/README.md`; this skill is the
procedure that applies them.

## Scope and sources

The wiki is `wiki/` at the repository root. The script below finds the root from its own location, so it
runs from any working directory; give a directory after the command (`list <dir>`, `register <dir> ...`)
only for a different directory with its own `wiki/README.md`.

Sources are repository-relative paths outside `wiki/`:

- `references/<id>/`: external papers, repositories, and datasets (`provenance.json`, `paper.pdf`,
  `repos/<name>/`), with the verified reproduction record in `references/<id>/reproduce/`. The catalog is
  `references/references.json`. PDFs, cloned repositories, and `attempts/` are gitignored: cite them, but
  expect them to be missing on another machine.
- `labs/<YYYY-MM-DD-slug>/`: experiments, through their `REPORT.md` and the `results/` or `figures/` files
  it cites.
- `lib/`: optional Python package source and tests (when `features.lib` + `package` are set).
- Measurements of record stay in labs and are cited from `REPORT.md` / the wiki.
- `skills/<name>/` and `README.md`: procedures and project rules, for `project/` pages.

Dated records under `wiki/records/` may be cited as wiki sources when
`citable_wiki_prefixes` in `wiki/taxonomy.yml` allows them (template default: records only).
Compiled ledger and package pages are synthesis, not evidence — cite the lab, reference, or
record underneath. Cite external material by canonical URL; do not mirror it locally unless asked.

Never modify a source while ingesting it: references, labs, lib package code, and records stay as
they are.

If `wiki/` is missing, initialize it from [assets/scaffold/](assets/scaffold/) before the first ingest.
Never start a second, parallel knowledge tree.

## Before editing

Read `wiki/README.md`, `wiki/taxonomy.yml`, `wiki/index.md`, `wiki/thesis.md`, `wiki/sources.yml`, and
the newest entries at the top of `wiki/records/log.md`. Read [references/ingest-protocol.md](references/ingest-protocol.md)
for provenance, claims, and contradictions. Then classify the input:

- Paper or other text: [references/text-ingest.md](references/text-ingest.md).
- Repository or code: [references/code-ingest.md](references/code-ingest.md), with
  [assets/implementation-template.md](assets/implementation-template.md) for implementation pages.
- Lab report: both. Ingest the narrative as text and inspect the cited scripts and results as code or data
  evidence.
- Reproduction record (`references/<id>/reproduce/`): the evidence for what was and was not reproduced.
  Compile it into the reference's algorithm or model page, or into a dead-end page if it was rejected.
- Work write-up (discovery, design, audit, integration, synthesis): file it as a record (see Records
  below), then fold what it established into the compiled pages.

A paper and its companion repository are one bundle but two provenance records. Ingest them separately,
connect what they share, and record mismatches. Never infer that a repository implements every method or
result in its paper because the two share a folder.

## Where knowledge goes

Follow the folder table in `wiki/README.md`. A finding about one model goes on that model's page in
`models/`; about one algorithm in `algorithms/`; a practice that transfers across work goes in
`techniques/`; a settled negative is a `dead-ends/` page in the format of `wiki/dead-ends/index.md`; an
idea that spans several algorithms or models is a concept; a method as such is a method; a measured
head-to-head is a comparison; an unresolved problem is a question; how the project runs is a `project/`
page; the manual of the lab package (when present) is `wiki/package/` and `lib/`. Query first, then
revise an existing page before creating a new one:

```bash
.venv/bin/python skills/wiki-query/scripts/query_wiki.py "<topic or source id>"
```

Also walk the classifier (`wiki/index.md` → folder `index.md` sub-indexes) when the hit list is thin.

## Two-pass workflow

Keep analysis and wiki edits apart.

- **Pass 1, analysis (no edits).** Read the source and the pages it affects, then write a short ingest
  brief: source identity and revision, supported claims with locators, implementation facts, evidence and
  limitations, contradictions with current pages, planned page operations, proposed links, topics, and the
  expected effect on the thesis.
- **Pass 2, integration.** Use the brief as the plan, re-check each claim against the source, then edit.

1. Resolve the source: its path, its revision (commit, sha256, or date), and whether `wiki/sources.yml`
   already registers it.
2. Pass 1: produce the brief and show it before writing. When a choice would materially change the wiki
   (categorization, the scope of a claim, how to settle a conflict), ask the researcher through the
   threads store and leave that part until it is answered:

   ```bash
   .venv/bin/python skills/research-threads/scripts/research_threads.py open --category decision \
     --title "wiki: <the question>" --content "<the brief and the choice to make>"
   ```

   A routine ingest with no material choice continues after the brief.
3. Pass 2: integrate across every affected page (algorithm, model, technique, concept, method,
   implementation, comparison, question, thesis). Keep competing claims side by side; never overwrite a
   disagreement silently. Connect paper methods to implementations and both to lab evidence. Do not copy a
   paper, repository file, lab report, or record into the wiki. A `papers/<id>.md` page is allowed only as
   a compact router to the reference, its compiled pages, implementations, and consuming labs.
4. Every page you create or revise meets the compiled-page contract in `wiki/README.md`: frontmatter, the
   three visible fields under the H1, and a final `## Related pages`. Start new pages from
   [assets/page-template.md](assets/page-template.md). Name the page by the article-title rule there: outside
   `questions/`, the title is a noun or noun phrase a reader would use as the subject of the first sentence
   (sentence case, no leading article, no trailing punctuation, not a question or an instruction). A
   `questions/` page keeps the research question as its title. The filename stays lowercase kebab-case and
   need not equal the title. On a content change, set `updated` and `**Last updated**` to today and add the
   new sources to `source_refs`. A title-only correction does not change `updated`.
5. Cite claims with standard Markdown links that carry a locator, such as
   `[Liu et al. (2025), §II](../../references/<id>/paper.pdf#page=4)` or
   `[lab report, Results](../../labs/<id>/REPORT.md)`, or with the canonical URL. Link wiki pages with
   path-qualified links such as `[[models/qos|Quantum Oracle Sketching]]`. Mark synthesis, inference, and
   uncertainty, and mark unsupported claims `(needs verification)`.
6. Re-evaluate `wiki/thesis.md`: strengthen, narrow, or challenge it, or leave it unchanged with a stated
   reason.
7. Update the **classifier tree**, not a flat root catalog: list the new leaf in its folder
   `index.md` (create that sub-index if needed). If this is the first page in a **new top-level**
   category, link that folder's `index.md` from `wiki/index.md`. Nested subfolders get their own
   `index.md`; do not dump every leaf onto the root index. Revise one-liners that no longer match.
8. Register the source in `wiki/sources.yml` with the script below; a re-ingest updates the existing entry.
9. Add a log entry at the top of `wiki/records/log.md`, directly below the preamble:
   `## [YYYY-MM-DD] ingest | <title>`, followed by bullets naming what changed. Never rewrite older
   entries.
10. Run wiki-lint (`.venv/bin/python skills/wiki-lint/scripts/lint_wiki.py`) and fix what it reports in
    the pages you touched. Route substantive contradictions and uncertain merges to the threads store.

Register provenance once the page edits are known:

```bash
.venv/bin/python skills/wiki-ingest/scripts/source_registry.py register \
  --source-id paper:<reference-id> \
  --title "<paper title>" \
  --kind paper \
  --path references/<reference-id>/paper.pdf \
  --revision sha256:<digest> \
  --updated-page wiki/models/<page>.md \
  --updated-page wiki/thesis.md
```

Kinds are `paper`, `repository`, `dataset`, `reproduction`, `lab`, `record`, `knowledge`, `query`,
`project`, `skill`, and `other`; `list` prints the ledger. The script refuses paths that do not exist,
compiled wiki pages, and retired locations.

## Records

A discovery, design, audit, integration, or synthesis write-up is filed as a dated record,
`wiki/records/<folder>/<YYYY-MM-DD>-<slug>.md` (audits may use `wiki/records/audits/<reference-id>/`),
starting with an H1 that names the kind and the date; `wiki/records/index.md` describes the folders. A
record is written once and not edited afterwards: a correction is a new record that names the one it
corrects. After filing, fold what the record established into the compiled pages and cite it in their
`source_refs`. The index summarizes records by folder, so a new record needs no index line.

## Lab handoff

Ingest a lab only after its `REPORT.md` records methods, findings, uncertainty, limitations, result
provenance, and a wiki handoff. Treat the lab's motivation and design as hypotheses, not findings. Cite the
specific `results/` or `figures/` files a claim depends on, and register the report with kind `lab`.

Labs are exploratory: **do not** ingest every lab, and **do not** maintain a `labs/`-level results
rollup. Distill only claims worth keeping into the wiki (one lab may yield several pages, or none).
Parent lineage stays in `lab.json` `parents`; the wiki holds the project's high-level knowledge.

## Completion

Report the source ingested, the pages created and updated, the thesis change, contradictions introduced or
resolved, and the lint result. Stop rather than invent missing provenance or experimental conclusions.
