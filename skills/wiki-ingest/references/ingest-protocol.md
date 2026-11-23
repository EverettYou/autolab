# Ingest protocol

## Provenance

Internal sources are paths relative to the repository root. Every claim citation uses standard Markdown:
`[readable label](relative-path#locator)` for internal material and
`[readable label](https://canonical-source-url#locator)` for external material. The target is stored in the
page and must resolve without a project-specific resolver; never mirror an external page merely to cite it.

Typical internal sources: `references/<id>/paper.pdf`, `references/<id>/repos/<name>/src/module.py`,
`references/<id>/reproduce/`, `labs/<id>/REPORT.md` and its `results/`, `lib/src/<package>/...`,
`labs/<id>/results/...`, `wiki/records/<folder>/<file>.md`, and `skills/<skill>/SKILL.md`. Add a page,
section, figure, table, commit, result key, symbol, test, heading, or line locator whenever possible. Do not
cite a compiled wiki page as though it were the primary source; records and the ledger folders are the only
citable wiki paths. Mark unsupported claims `(needs verification)`.

## Integration units

Create pages around durable concepts, methods, algorithms, models, techniques, comparisons, and questions.
Record source-level provenance only in `wiki/sources.yml`; do not create source-summary pages or mirror a
paper's section structure. A paper page may exist as a routing node for its reference folder, compiled
topics, implementations, and lab uses, but it stays compact and does not duplicate topic synthesis. The
registry entry lists the pages an ingest changed without duplicating their content.

If a reference folder holds both a paper and a repository, treat it as a bundle, and the paper and the code
snapshot as separate sources with separate revisions and `updated_pages`. Static code inspection supports
statements about architecture and interfaces, not runtime correctness or reproduction of paper results.
Create a paper-to-code comparison when the implemented objective, level of description, or algorithm
differs materially from the paper method a reader might otherwise assume it realizes.

Operational detail stays with the resource that owns it: the package manual in `wiki/package/`, skill
files, lab reports, and reference folders. Compiled pages summarize relationships and link out.

## Claims

For consequential claims, preserve:

- the claim and calibrated confidence;
- supporting and challenging raw sources;
- scope and assumptions, including the setting (code, noise model, parameters) a number belongs to;
- whether it is source-reported, lab-observed, or wiki synthesis;
- related concepts, methods, comparisons, questions, and task list ideas.

## Contradictions

Never overwrite an older claim just because a new source disagrees. Record both scoped claims, identify
possible reasons for the disagreement, update the thesis only as far as justified, and open a question page
when the conflict is unresolved.

## Idempotence

Before ingesting, inspect the matching `sources.yml` entry and the log. Re-ingesting the same revision
should not duplicate pages, links, or log claims. If a source changed, update its revision and affected-page
list and say which compiled conclusions changed.

## Ingest preview

Before editing, show the extracted takeaways, possible contradictions, planned page changes, and proposed
thesis effect. Ambiguous ontology, conflicting interpretations, and consequential scope changes go to the
researcher as a question in `.auto-research/state.json` (procedure: `skills/research-threads`). A routine ingest
continues after a visible preview when the operation was already authorized and no material decision
remains.
