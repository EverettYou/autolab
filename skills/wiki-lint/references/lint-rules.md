# Wiki lint rules

The authoritative contract is `wiki/README.md`; the controlled values live in `wiki/taxonomy.yml`.
This file lists what the linter reports and how severe each finding is.

## Which files are checked how

| Files | Treatment |
| --- | --- |
| `index.md` at the wiki root; `records/log.md` | special files: required, links checked, no page contract |
| `README.md` (root contract); folder `index.md` (sub-index) | guide: links checked, no page contract |
| `records/**` (folders listed in `record_folders`) | immutable history: no page contract, link problems are warnings |
| every other `.md` file, including `thesis.md` and `package/**` | compiled page: full contract |

## Structural errors

- missing `README.md`, `index.md`, `thesis.md`, `records/log.md`, `sources.yml`, or `taxonomy.yml`;
- a compiled page in a folder that `taxonomy.yml` does not declare, or whose `page_type` does not match its folder;
- a compiled page filename that is not lowercase kebab-case;
- compiled page lacking required frontmatter (`title`, `page_type`, `status`, `updated`, `source_refs`, `idea_ids`) or a unique title;
- a compiled page outside `questions/` whose title is a question or an instruction: it starts with What, Why, How, When, Where, Which, Who, Does, Do, Is, Are, Can, Should, Did, Will, Must, or You, or it ends with `?` or other punctuation. A `questions/` page may keep a question title. Records are exempt;
- status outside the controlled list; missing or invalid `topics` on a compiled page (1–3 values
  from `taxonomy.yml`; extend the list with `skills/wiki-ingest/scripts/ensure_topics.py` when
  ingest introduces a new subject; records and folder `index.md` guides are exempt);
- compiled page lacking visible Summary, Sources, or Last updated fields, or a final `## Related pages` section;
- a relative Markdown link or path-qualified Obsidian wikilink in a compiled or special page whose target does not exist, including targets outside `wiki/` (`labs/`, `references/`, `lib/`, `skills/`);
- an ambiguous bare wikilink that matches several pages;
- a `source_refs` entry that does not resolve, is absolute or climbs out of the repository, or cites a compiled synthesis page; records and the ledger folders listed under `citable_wiki_prefixes` may be cited;
- resolver-style source IDs such as `` `global:paper-id` `` or `source:record-id` in a compiled page; citations must remain readable and resolvable as standard Markdown;
- MyST or Sphinx syntax outside code: roles such as `` {doc}`...` ``, directive fences such as ```` ```{note} ````, colon fences, and `(label)=` targets;
- malformed, duplicate, unresolved, or unsafe `sources.yml` provenance entries;
- malformed chronological log heading (`## [YYYY-MM-DD] ingest|query|lint|reorganize | title`).

Text inside inline code and fenced code is never parsed for links, so documentation examples are safe.
Bare parameter tuples such as `[[n,d]]` or `[[64,8]]` are text, not wikilinks: a double-bracket
body that contains a comma or no letter is ignored.

## Structural warnings

- a broken link inside a record (point it at the content's new home if it moved, otherwise unlink it and keep the words);
- a bare-name wikilink that resolves to exactly one page; write it path-qualified;
- a labelled wikilink inside a table row, escaped (`\|`) or not; its `|` breaks the cell in GitHub and in the dashboard's link index, so use a relative Markdown link there;
- a missing link or source target that git ignores (reference PDFs, cloned repositories, attempt workspaces), reported as local-only;
- an empty `source_refs` list, or a missing or malformed `updated` date;
- a visible Last updated date that differs from the frontmatter `updated` date;
- a compiled page whose title starts with *a*, *an*, or *the* (name the topic directly, unless that word is part of a name);
- `thesis.md` not linked from the root `wiki/index.md`;
- root `wiki/index.md` linking a compiled leaf other than `thesis.md` (it is a classifier: link
  folder `index.md` sub-indexes and hubs, not every page);
- a compiled page (other than `thesis.md`) whose folder has no `index.md` sub-index, or that is
  not listed in that folder's `index.md`;
- a lab report under `labs/` not referenced anywhere in the wiki;
- raw material missing from `sources.yml`, or a registry entry whose affected pages no longer exist;
- with `--check-paths`: repository paths in inline code that do not exist or point into a retired location. A trailing `#anchor`, `:line`, or `::symbol` is ignored when checking existence.

## Semantic review

- claims without scope, evidence, or calibrated uncertainty;
- new evidence that contradicts another page without an explicit tension;
- thesis claims no longer matching underlying pages;
- duplicate pages that silently use different terminology;
- important recurring concepts without pages;
- registered sources not integrated into durable synthesis pages;
- questions that remain open despite available evidence;
- gaps worth filling with another source or lab.

The optional LLM pass is conservative and evidence-bounded. It reads compiled pages only (records and
folder guides are skipped) and may emit only `unsupported_claim`, `possible_contradiction`,
`stale_thesis`, `duplicate_terminology`, `missing_recurring_concept`, `source_not_integrated`, or
`scope_boundary`. Findings below 0.75 confidence are discarded. A contradiction requires
incompatible supplied passages under compatible scope; a recorded tension is healthy wiki
state, not a lint problem. Semantic output is advisory and must not automatically rewrite
scientific claims, confidence, or thesis state.

Scientific disagreement is not a lint error. Unrecorded disagreement is.
