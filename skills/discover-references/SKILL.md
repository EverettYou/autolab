---
name: discover-references
description: Search arXiv, GitHub, and data repositories for papers, code, and datasets worth studying, and return a deduplicated, topic-grouped candidate list with a disposition and one-line relevance note per item. An explicit subject guides the search. With no subject, the topic is the overlap of the collected references and the compiled wiki. Produces candidates only; it never downloads or creates files.
usage: Use when someone asks for references about a subject, a question needs literature, a roster gap needs candidates, or someone asks what is new.
---

# Discover references

Discovery curates; it does not hoard. Search widely, read metadata and abstracts, and hand back
a short list. Archiving a chosen candidate is `fetch-reference`; reproducing it is
`reproduce-reference`.

## 1. Resolve the scope and pick one mode

Take the scope from the first source that applies:

1. An explicit request from the human, in chat or in an open `.auto-research/state.json` thread.
   When it names a subject, that subject is the search topic.
2. The active deliverable or a task in `.auto-research/state.json` that asks for literature.
3. The latest synthesis record in `wiki/records/synthesis/` (its BROADEN, DEEPEN, PIVOT, or
   CONCLUDE direction).
4. The standing topic from `scripts/topic_alignment.py topic`, below. If it reports no standing
   topic, stop and say so. Do not substitute a field the command did not print.

Pick exactly one mode (details in [references/selection-lenses.md](references/selection-lenses.md)):
`directed`, `freshness`, `coverage-gap`, `released-assets`, `theory-codes`, or `negative-confirm`.

Churn guard: read the last few records in `wiki/records/discoveries/`. If the same gap was
confirmed empty within about a week and nothing new triggered this run, switch mode or report
that the scope is withheld instead of repeating the sweep.

## 2. Search topic

An explicit subject and the standing collection are different. The subject guides the search
when the scope names one. The standing collection is the references and the compiled wiki.

When the scope names a subject, use that subject's own words as the query axes. A request such
as "look for references about neutral-atom rearrangement", a task that names a subject, or a
synthesis direction that names one, is such a scope. Do not replace those words with the
standing term list.

Score every candidate against that subject:

```bash
.venv/bin/python skills/discover-references/scripts/topic_alignment.py score --topic "<subject>" --title "<title>" --abstract "<abstract>"
```

Prefer `request`. It is the fraction of the subject's terms the candidate uses, and, when the
dashboard search key is configured, seventy percent the cosine between the subject and the
candidate. `alignment` is the standing score. Report it. Do not reject a hit that matches the
subject because its standing alignment is low.

When the scope names no subject, the search topic is the standing overlap:

```bash
.venv/bin/python skills/discover-references/scripts/topic_alignment.py topic
```

The terms it prints are the overlap of reference titles and abstracts in `references/references.json`
and the compiled wiki under `wiki/`. `wiki/records/` is the session log and is not part of the
topic. A term counts when at least five of those documents contain it, or every document does
when fewer than five are collected. Search queries come from the highest-ranked terms. If the
command reports no standing topic, stop and say so.

Score without `--topic`:

```bash
.venv/bin/python skills/discover-references/scripts/topic_alignment.py score --title "<title>" --abstract "<abstract>"
```

Prefer `alignment`. `words` is the fraction of the candidate's terms already in the overlap.
`embedding` is the cosine between the candidate and the centroid of the references and the
compiled wiki, using the search embedding model. `alignment` is seventy percent embedding and
thirty percent words. With no key, or when the embedding call fails, `alignment` is the word
fraction and `embedding` says why. `novel` is what no collected reference and no compiled wiki
page says.

Then search the wiki for this scope:

```bash
.venv/bin/python skills/wiki-query/scripts/query_wiki.py "<term>" "<term>"
```

Read the dead ends that command lists, and do not resurface one unless its Revisit if condition
is now met. A wiki roster or coverage page is a map of gaps when the project has one; it does
not replace the overlap. `wiki/literature/` holds cluster literature reviews (what this lab has
already synthesized across groups of papers); it is not a per-paper abstract dump.

## 3. Search (metadata only)

```bash
python3 skills/fetch-reference/scripts/fetch_reference.py search "<query>" --max-papers 15 --text
```

Use queries derived from the scope and mode, plus GitHub and data-repository searches when code
or data is the target. Stay on titles, abstracts, author lists, repository descriptions, and
activity. Read a full paper only when the abstract cannot settle the disposition; then follow
[references/paper-summary.md](references/paper-summary.md) and read it online without saving it.

## 4. Deduplicate and disposition

1. For each hit, run `python3 skills/fetch-reference/scripts/references_registry.py resolve <arxiv-id-or-name>`;
   an existing reference is noted, not re-proposed. Drop hits already dispositioned in recent
   discovery records.
2. Score each new hit with `topic_alignment.py score`, passing `--topic` when the scope names a
   subject. Apply the three lenses (topic relevance, research quality, author credibility) and
   assign `pass`, `study-only`, or `reject`. Put `request` in the relevance line when the scope
   names a subject, and `alignment` otherwise.
3. Verify sources: the title matches the claimed thesis; a paper that uses an algorithm without
   defining it is cited alongside the defining paper; record the setting, the measure, and whether
   code, data, or weights are released.
4. Respect the budget: at most 1 to 2 papers and 0 to 1 repositories marked `pass` per run,
   unless the request names specific targets. A third needs a stated reason.

## 5. Return the candidate list

Return this in the response (no files):

```markdown
## Candidates: <YYYY-MM-DD>, <scope in a few words>

Scope: <source>; mode: <mode>; searched: <query axes>; stop condition: <what counted as done>.

### <topic group>
| Candidate | Link | Kind | Disposition | Relevance | Assets | Suggested id |
|-----------|------|------|-------------|-----------|--------|--------------|
| <title> (<first author>, <year>) | arXiv:<id> or URL | paper, repository, dataset | pass, study-only | <one line> | code / weights / data / none | <kebab-id> |

### Examined and not pursued
| Candidate | Link | Disposition | Reason |
|-----------|------|-------------|--------|
```

An empty candidate table is a valid result for `negative-confirm`; the scope line and the
examined table still record what was searched.

## Handoff

- `pass`: archive with `fetch-reference`, passing the suggested id and the relevance line as
  `--note`; then `reproduce-reference` or a lab (`create-lab`) as the scope requires.
- `study-only`: worth remembering but not fetching; `wiki-ingest` can add a paper page.
- When the run belongs to an autonomous loop or a directed hunt, including a negative
  confirmation, the caller records it in `wiki/records/discoveries/<YYYY-MM-DD>-<slug>.md`
  through `wiki-ingest`, so the next run's churn guard can see it.
