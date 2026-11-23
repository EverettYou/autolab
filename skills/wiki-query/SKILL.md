---
name: wiki-query
description: Answer project research questions from the maintained wiki with traceable citations.
usage: Use when locating project knowledge, checking whether an algorithm, model, or approach was already tried, synthesizing across papers and labs, comparing hypotheses or methods, finding contradictions, generating research directions, selecting a high-information experiment, or gathering context for a lab.
---

# Wiki query

Use compiled knowledge before reaching back into raw sources. A query is read-only by default.

## Scope

The wiki is `wiki/` at the repository root; its rules are in `wiki/README.md`. If another directory holds
its own `wiki/README.md` and the question concerns it, query that wiki instead, and keep its evidence
visibly separate from the project wiki's synthesis.

## What to read

- `wiki/index.md` is the classifier (category hubs). Drill into folder `index.md` sub-indexes for leaves; use `wiki/thesis.md` for the standing synthesis, not as a catalog.
- Synthesized pages (`concepts/`, `methods/`, `comparisons/`, `questions/`, `implementations/`) hold the
  current cross-source view.
- Ledger pages (`algorithms/`, `models/`, `techniques/`, `dead-ends/`) hold what was learned about one
  algorithm, model/oracle family, or practice. Their Summary line often carries later results than the body, so read it
  first.
- `dead-ends/` lists settled negatives. Check it before proposing to scout, reproduce, or integrate a
  candidate, and say so when an idea was already tried and what would justify revisiting it.
- `project/` pages hold the project's constraints (compute budget, evaluation discipline, trust zones).
- `lib/` is the manual of the configured lab package (when `features.lib` is on). The API itself is
  rendered from docstrings in the dashboard API section; source lives under `lib/src/<package>/`.
- `records/` is dated history. Use it for when and why something was decided or measured; prefer the
  compiled pages for what is currently believed, and say when an answer rests on a record that later work
  may have superseded.
- `wiki/sources.yml` shows which sources were ingested and at which revision.

## Workflow

1. Read `wiki/README.md`, `wiki/index.md`, and `wiki/thesis.md`.
2. Turn the request into a few search concepts, code symbols and aliases, relevant page types, and evidence
   needs.
3. Search compiled pages first:

   ```bash
   .venv/bin/python skills/wiki-query/scripts/query_wiki.py "<term>" "<term>"
   ```

   The command matches title, Summary, and topics, skips `wiki/records/`, and lists matching dead ends
   (with their Revisit-if text) and open questions apart from the other pages. Read the highest-ranked
   pages and follow their links one hop. Treat hits as candidates, not evidence. Search `wiki/records/`
   only when the question is about when or why something was decided.
4. Synthesize across pages instead of concatenating excerpts. Separate established evidence, current wiki
   synthesis, unresolved contradiction, and your own new inference. Keep every number tied to its setting
   (code, noise model, parameters); never compare numbers across settings.
5. Cite wiki page paths near claims, and include the primary paper, code, or lab citation when the answer
   drives a scientific decision. When proposing text for a wiki page, use only standard Markdown citations,
   `[readable label](relative-path#locator)`, and name the page by the article-title rule in `wiki/README.md`:
   a noun phrase for the topic, or the research question itself on a `questions/` page. Distinguish wiki
   synthesis, static code inspection, repository-test evidence, and lab evidence.
6. For idea generation, propose several candidates before selecting one, and score them qualitatively by
   scientific value, information gain, tractability, discriminating power, and dependency risk.
7. For a next lab, return motivation, hypothesis and alternatives, required wiki context, a minimal
   discriminating design, observables, how to read a failure, and the likely wiki update. Do not fabricate
   findings or create the lab unless asked.

Read [references/query-output.md](references/query-output.md) when the answer will seed an idea or a lab.

## Write boundary

Do not edit the wiki, labs, or the task list during an ordinary query. If a synthesis is genuinely reusable,
offer to preserve it; after approval, hand it to **wiki-ingest** as a source of kind `query`. Creating an
idea, a task, or a lab is a separately authorized action. Log a query in `wiki/records/log.md` only when it
is saved.

## Answer quality

Say when the wiki lacks coverage. Prefer proposing a source to acquire or a lab to run over speculation. A
good answer makes the next decision cheaper, not just restates the thesis.
