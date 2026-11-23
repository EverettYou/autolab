---
name: wiki-lint
description: Audit the project wiki for structural integrity and knowledge health.
usage: Use after wiki ingest, before wiki-based design or research, or when checking broken links (inside wiki/ and into labs/, references/, lib/), missing frontmatter or provenance, category and folder mismatches, leftover MyST syntax in the package manual, stale or contradictory claims, index drift, source coverage, and unresolved knowledge gaps.
---

# Wiki lint

Check both what can be validated mechanically and what requires scientific judgment. Lint reports problems; it does not erase disagreements to make the wiki look consistent.

## Workflow

1. Read `wiki/README.md`, `wiki/taxonomy.yml`, and [references/lint-rules.md](references/lint-rules.md).
2. Run the structural linter from the repository root:

   ```bash
   .venv/bin/python skills/wiki-lint/scripts/lint_wiki.py
   ```

   The script finds the repository root from its own location, so it works from any working
   directory; pass a directory that holds `wiki/README.md` to lint a different wiki. Add
   `--check-paths` for the migration audit: it also checks repository paths written in inline
   code (for example `` `labs/<id>/REPORT.md` ``) and flags retired locations listed under
   `retired_path_prefixes` in `wiki/taxonomy.yml`. Those findings are warnings.

   Add `--semantic` for the optional OpenAI-backed knowledge-health review. This mode requires
   `OPENAI_API_KEY`, uses `OPENAI_SEMANTIC_LINT_MODEL` (falling back to `OPENAI_MODEL` and then
   `gpt-4o`), and caches strict structured results under `.tmp/`. Use `--semantic-limit N` for a
   bounded smoke test and `--semantic-refresh` only when the same evidence should be reviewed again
   intentionally.

3. Review structural findings. Compiled pages (every category folder, `thesis.md`, and the lib
   package manual) must satisfy the page contract: frontmatter, a `page_type` matching their folder,
   controlled status and topic values, visible Summary, Sources, and Last updated fields, and a
   final `## Related pages` section. Outside `questions/`, the title names the topic: a question or
   an instruction (it starts with What, Why, How, When, Where, Which, Who, Does, Do, Is, Are, Can,
   Should, Did, Will, Must, or You, or it ends in punctuation) is an error. A `questions/` page may
   keep a question title. A title that starts with *a*, *an*, or *the* is a warning. Every relative
   Markdown link and every Obsidian wikilink must
   resolve, including links that leave `wiki/` for `labs/`, `references/`, or `lib/`.
   Dated records under `wiki/records/` are immutable history: they are exempt from the
   contract, and their broken links are reported as warnings: repoint a link whose content moved,
   unlink one whose target is gone, and leave the record's words alone. Missing targets that git ignores (reference PDFs, cloned repositories, attempt
   workspaces) are local-only warnings, not errors.
4. Audit semantic health: unsupported claims, contradictions hidden by overwrites, stale thesis statements, concepts mentioned repeatedly without pages, missing inverse links where useful, registered sources that did not change durable synthesis, and high-value gaps. The semantic mode supplies bounded page, neighbor-summary, and provenance packets to the model and skips records and folder guides. Treat every finding as a review candidate rather than established fact.
5. Classify each finding as error, warning, or research opportunity. Cite exact paths. Findings that
   need scientific judgment, an ambiguous merge, or a priority call go to the researcher as a
   discussion thread:

   ```bash
   .venv/bin/python skills/research-threads/scripts/research_threads.py open \
     --category decision --title "Wiki lint: <short question>" --content "<finding, paths, options>"
   ```

## Fix boundary

Automatically fix only clearly mechanical problems when the user asks: index omissions, link spelling or a moved target whose new location is unambiguous, formatting, or missing reciprocal navigation. Do not automatically resolve scientific contradictions, merge concept pages with distinct meanings, change confidence, rewrite the thesis, or edit a record. Route substantive corrections through **wiki-ingest** with source evidence.

## Completion

Report structural status, knowledge-health findings, source coverage, and the highest-value maintenance or research actions as a numbered list with suggested fixes. A zero-error structural result does not imply that the wiki is scientifically complete.

The command exits non-zero when structural errors remain. Semantic findings do not change the exit status and never modify the wiki. API or configuration failures do return a distinct failure because an explicitly requested review did not complete. Token usage is appended to `.tmp/llm-usage.jsonl` without credentials or source text.

## Tests

```bash
.venv/bin/python -m pytest skills/wiki-lint/tests -q
```
