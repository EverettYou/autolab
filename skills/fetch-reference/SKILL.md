---
name: fetch-reference
description: Archive a selected paper, repository, or dataset under `references/<id>/` with a checksummed `provenance.json`, and register it in `references/references.json`.
usage: Use after discover-references picks a candidate, when a lab or reproduction needs a source that is not yet archived, or to restore or verify local copies.
---

# Fetch a reference

References are the external sources the lab builds on. Each one is a directory `references/<id>/`
with one layout. Pieces are optional — a paper may have no repository, a repository may have no
PDF, and most references have no attempt or reproduction yet — but a new file only goes in one of
these places:

| Path | Required | What it is |
|------|----------|------------|
| `provenance.json` | yes | Tracked record. Source of truth for the reference. |
| `paper.pdf` | no | The archived PDF, when this reference has a paper. Local. |
| `README.md` | no | A short tracked note about the reference itself. |
| `repos/<name>/` | no | One checkout per code repository or dataset. Local. |
| `attempts/<slug>/` | no | An untrusted reproduction workspace. Local. Created by `reproduce-reference`, not by this skill. |
| `reproduce/` | no | The tracked record of an accepted attempt. Written only by `promote_attempt.sh`. |

Nothing else belongs at the top of `references/<id>/`. `references_registry.py validate` rejects
any other name there. `paper.pdf`, `repos/`, and `attempts/` stay local (gitignored);
`provenance.json`, `README.md`, and `reproduce/` are tracked. `references/references.json` is
generated from the provenance files. Field definitions:
[references/provenance-schema.md](references/provenance-schema.md).

Dependencies: the repository venv already has `pypdf`; elsewhere install
`skills/fetch-reference/requirements.txt`. arXiv access uses the export and abs HTTP endpoints
directly with a shared 3-second rate limit.

## Before fetching

1. Check whether it is already archived. `references_registry.py resolve <name>` matches ids,
   aliases, attempt slugs, repo names, and arXiv ids (with or without version):

   ```bash
   python3 skills/fetch-reference/scripts/references_registry.py resolve 2512.07057
   ```

2. Choose the id: short lowercase kebab-case naming the method or artifact (`quantum-oracle-sketching`,
   `relay-bp`). Ids are never renamed; record older names with `--alias`.

## Commands

All commands run from the repository root; `S=skills/fetch-reference/scripts`.

```bash
# arXiv paper -> references/<id>/paper.pdf + provenance.json, registered
python3 $S/fetch_reference.py paper --id quantum-oracle-sketching --arxiv 2512.07057 --note "BB144 beam search baseline"

# non-arXiv paper: direct PDF URL, or a local file
python3 $S/fetch_reference.py paper --id some-paper --url https://example.org/paper.pdf --title "Title"
python3 $S/fetch_reference.py paper --id some-paper --pdf /tmp/paper.pdf --title "Title"

# companion repository -> references/<id>/repos/<name>/ (records URL and commit)
python3 $S/fetch_reference.py repo --id quantum-oracle-sketching --url https://github.com/org/Repo.git --name quantum-oracle-sketching

# dataset or other files placed by hand under references/<id>/repos/<name>/ (records a tree checksum)
python3 $S/fetch_reference.py register --id some-dataset --kind dataset --title "Title" --url https://zenodo.org/records/N

# verify local copies against provenance.json; restore missing PDFs (checksum-verified)
python3 $S/fetch_reference.py status --all
python3 $S/fetch_reference.py refetch --all
# Dashboard Open PDF also calls refetch when paper.pdf is missing locally (same checksum rules).
# Dashboard View Repo calls `repo` when repos/<name>/ is missing locally.

# discovery search (JSONL; --text for reading)
python3 $S/fetch_reference.py search "quantum oracle sketching" --max-papers 15
python3 $S/fetch_reference.py search "quantum oracle sketching" --since-days 30 --max-papers 20   # newest first, inside the window
```

## Rules

- Never overwrite an archived copy silently. `paper` refuses when `paper.pdf` exists but is not
  the recorded copy, and `refetch` installs a download only when its sha256 matches the record.
  Use `--force` only after inspecting both files; it records the new checksum.
- A first-page title that does not match the arXiv title stops the fetch (exit 3). Open the PDF,
  confirm it is the right paper, then rerun with `--allow-title-mismatch`.
- A hand-placed PDF is recorded with `paper --id <id> --adopt` (validates it and records its
  checksum without touching the file).
- Duplicates are refused: the same arXiv id or a name already used as an id or alias. Two
  references to one paper are allowed only with `--allow-duplicate` and a reason in `--note`.
- Repository clones are read-only sources. Never run their code outside an attempt workspace; see
  `reproduce-reference` and the isolation rules in `runtime-env`.
- Record why the reference was fetched with `--note`; discovery candidates carry that reason.
- After any manual change inside `references/<id>/`, run
  `python3 $S/references_registry.py sync <id>` and commit `provenance.json` and
  `references/references.json` together with explicit paths (`git-workflow`).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | OK |
| 1 | Download or network failure, or a local copy is missing |
| 2 | Invalid input: not a usable PDF, checksum mismatch, usage error |
| 3 | Title mismatch between the first page and the arXiv metadata |
| 4 | Refused: would overwrite an archived copy, or the name or arXiv id is already registered |

## Registry maintenance

`references_registry.py` owns the index:

| Command | Effect |
|---------|--------|
| `rebuild` | Regenerate `references.json` from every `provenance.json`. |
| `check` | Exit 1 when `references.json` is stale. |
| `validate [--local]` | Schema, disk consistency, unique names; `--local` also verifies PDF checksums and repo commits. |
| `sync <id>... \| --all` | Mirror `reproduce/`, `attempts/`, and unrecorded `repos/` into provenance, then rebuild. |
| `set <id> --status S` | Change curated fields (status, kind, title, aliases), then rebuild. |
| `dispose <id> <attempt> --decision D --note N` | Record the fate of an attempt workspace. |
| `resolve <name>` | Print the reference id for an id, alias, attempt, repo, or arXiv id. |

Tests: `.venv/bin/python -m unittest discover -s skills/fetch-reference/tests`;
title normalization self-test: `python3 $S/selftest_normalize_title.py`.
