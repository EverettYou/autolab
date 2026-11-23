# Skills

Tool-agnostic lab procedures. Any agent opens `skills/<name>/SKILL.md` from a clone.

This tree is **sync zone** (see `autolab/scripts/sync_apply.py`): synced wholesale into consumer
labs. Do not put project-private procedures here. Pair with [`dashboard/`](../dashboard/README.md)
as the other system surface.

## Catalog

- [audit](audit/SKILL.md) — Review promoted package code against tests and evidence
- [auto-research](auto-research/SKILL.md) — Run the research loop over `.auto-research/`
- [research-threads](research-threads/SKILL.md) — Researcher–agent interaction over Threads
- [create-lab](create-lab/SKILL.md) — Scaffold a dated lab for one bounded question
- [discover-references](discover-references/SKILL.md) — Find literature worth fetching
- [fetch-reference](fetch-reference/SKILL.md) — Record provenance and add an authorized reference
- [git-workflow](git-workflow/SKILL.md) — Review and land scientific changes on a research branch
- [guards](guards/SKILL.md) — Mechanical repository invariant checks
- [organize-lab](organize-lab/SKILL.md) — Keep labs staged, laid out, and catalogued
- [promote-to-lib](promote-to-lib/SKILL.md) — Promote validated lab code into `lib/src/<package>/`
- [reproduce-reference](reproduce-reference/SKILL.md) — Reproduce a cited paper or upstream result
- [research-workflow](research-workflow/SKILL.md) — Plan and execute a bounded lab question
- [runtime-env](runtime-env/SKILL.md) — Fingerprint hosts and build the repository venv
- [wiki-ingest](wiki-ingest/SKILL.md) — Add durable findings to the wiki
- [wiki-lint](wiki-lint/SKILL.md) — Check wiki links and claim provenance
- [wiki-query](wiki-query/SKILL.md) — Look up internal knowledge before starting work
- [autolab](autolab/SKILL.md) — **template only**: scaffold a consumer lab and sync OS files (never present in consumers)
