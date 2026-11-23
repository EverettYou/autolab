---
title: Distillation tower
page_type: system
status: active
updated: 2026-11-20
source_refs:
  - README.md
  - lib/README.md
  - references/README.md
  - labs/README.md
  - notes/README.md
idea_ids: []
topics:
  - Lab OS Architecture
  - Research Pipeline
  - Knowledge Systems
---

# Distillation tower

**Summary**: The tower is not bureaucracy — it is the same path you already take when research
works: gather material, try ideas, keep only what you would defend, write it up, and reuse what
earned a tool. Floors match those stages so agents (and future you) do not mix “someone else’s PDF”
with “our claim” or “a one-off script” with “the package.”

**Sources**: [README](../../README.md) · [lib README](../../lib/README.md) · [notes README](../../notes/README.md) ·
`skills/promote-lib` · `skills/wiki-ingest`

**Last updated**: 2026-11-20

## Why bother — a research week, not a metaphor

Suppose you have an idea and want to do real work on it. You already do something like this by
hand:

1. **Brainstorm / aim** — what question is worth a week? (Threads + deliverable; not a floor.)
2. **Collect material** — papers, repos, datasets that might matter.
3. **Check the claims** — did that paper’s figure actually reproduce, or are you building on air?
4. **Explore** — dated experiments, dead ends, the bet that might become the result.
5. **Keep the lesson** — a short, cited note you would send a collaborator (“here is what we think
   is true”).
6. **Ship a product** — research notes (not necessarily a paper), and/or a small tool others in the
   lab can call next month.

The tower is that habit with **named folders and gates**, so an agent can help without turning the
repo into a junk drawer. You are not inventing a new scientific method — you are refusing to let
raw PDFs, scratch scripts, and defended claims live in the same pile.

| Everyday move | Floor | Why it is separate |
| --- | --- | --- |
| “I found this paper / repo” | `references/` (dirty) | Still **theirs**. Useful, untrusted until checked. |
| “I tried to reproduce / run it” | `references/<id>/reproduce/` | Evidence that the claim is or is not real. |
| “I’m testing *our* idea” | `labs/` (fuzzy) | Dated bets. Messy is fine; it is not the library. |
| “This we would defend in a meeting” | `wiki/` (clean) | Knowledge distillation — cited, reusable, searchable. |
| “This API we will keep calling” | `lib/` (clean, optional) | Code distillation — rewritten + tested, not copied from a lab. |
| “Write it up for humans” | `notes/` (narrative, optional) | Research notes / manuscript that **cite** the tower; they do not replace it. |
| “We tried X; it fails under Y” | `wiki/deadends/` | Settled “no” so you do not pay for it again. |

Most candidates should **stop early**. That is success: you searched widely and refused to promote
noise.

## Scenarios (when the tower earns its keep)

**Starting from an idea.** You sketch a question in a Thread, set a deliverable, then scout
literature into `references/`. You do **not** paste arXiv abstracts into the wiki. After a
reproduction (or an honest dead-end), a lab explores the twist that is actually yours. When the lab
`REPORT.md` has a finding, `wiki-ingest` keeps the claim; months later `wiki-query` finds it instead
of re-deriving from chat history.

**“Can we trust this baseline?”** A hot repo lands in `references/`. Reproduce before you compare
against it in a lab. If VERIFY fails, file `deadends/` and move on — you just saved a week of
building on a mirage. If it passes, the lab may extend it; only then might code graduate into
`lib/`.

**Exploration without polluting the toolkit.** Mid-project you try three decoder variants in three
labs. Two die; one works. Scratch code stays in those labs. The surviving idea becomes a wiki page
and, if the lab will call it repeatedly, a promoted package module — not `from labs/2026-… import
hack`.

**Writing without a paper mandate.** Notes are a **research product**: a note, a tech report, a
chapter draft. They cite references, wiki pages, and labs. You are not required to publish; you are
required not to treat the PDF as the only store of truth. Knowledge stays in `wiki/`; the note is
the narrative face.

**Building tools that accelerate the next lab.** After the third time you need the same constructor,
`promote-lib` re-implements it under `lib/`. Later labs import the package. That feedback loop —
lab → lib → faster lab — is why code distillation exists. See [[system/shared-package|Shared
package]].

**Handing the project to another agent (or future you).** Chat scrollback is gone. The tower still
has: what you fetched, what you verified, what you tried, what you believe, what you wrote, and
which APIs are safe to call. That is the point of floors.

## Floors (compact)

| Floor | Done looks like |
| --- | --- |
| `references/` | Provenance + (ideally) a reproduction record |
| `labs/` | `REPORT.md`: tried / held / still shaky |
| `wiki/` | Cited pages you would defend |
| `lib/` | Small installable package with tests |
| `notes/` | Human-facing write-up that cites the tower |

**Knowledge distillation** (`wiki-ingest`): from reproduction + lab reports, keep claims that deserve
a home; leave blobs where they were made.

**Code distillation** (`promote-lib`): rewrite under `lib/src/<package>/`, test, verify against
evidence. Never import production code from `labs/` or `references/`.

Same spine as process: discover sparingly → reproduce → lab → ingest / promote. Gates catch weak
evidence early — compute discipline lives in
`skills/auto-research/references/spending-compute.md` (agent procedure, not a wiki page).

## Related pages

- [[system/what-autolab-is|AutoLab]]
- [[system/shared-package|Shared package]]
- [[system/dashboard-and-threads|Dashboard and Threads]]
