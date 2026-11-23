# Reference records

Each reference lives in `references/<id>/`. The directory has one layout. Every row except
`provenance.json` is optional: a paper need not have a repository, a repository need not have a
PDF, and attempts and a reproduction appear only after that work starts.

| Path | Required | Tracked | Contents |
|------|----------|---------|----------|
| `provenance.json` | yes | yes | This record. |
| `paper.pdf` | no | no | The PDF, when there is one. |
| `README.md` | no | yes | A note about the reference, not a paper or a reproduction. |
| `repos/<name>/` | no | no | One subdirectory per repository or dataset. No loose files in `repos/`. |
| `attempts/<slug>/` | no | no | One subdirectory per attempt workspace. No loose files in `attempts/`. |
| `reproduce/` | no | yes | Files of the accepted reproduction (`RESULT.json`, notes, scripts). |

No other name is allowed at the top of the directory. `validate` reports one. Local pieces are
restored from the URLs and checksums in `provenance.json`.

## provenance.json (source of truth, tracked)

```json
{
  "id": "quantum-oracle-sketching",
  "kind": "paper",
  "title": "Exponential quantum advantage in processing massive classical data",
  "arxiv_id": "2604.07639",
  "authors": ["..."],
  "abstract": "...",
  "categories": ["quant-ph", "cs.LG"],
  "published": "2025-12-08T00:16:57Z",
  "upstream_updated": "2025-12-17T17:25:05Z",
  "entry_url": "https://arxiv.org/abs/2604.07639v2",
  "pdf_url": "https://arxiv.org/pdf/2604.07639v2",
  "pdf": "paper.pdf",
  "pdf_sha256": "d504687a...",
  "pages": 11,
  "fetched_at": "2026-06-22T06:10:44+00:00",
  "fetch_status": "pdf:ok",
  "metadata_source": "arxiv_api",
  "title_match_score": 1.0,
  "aliases": ["quantum-oracle-sketching"],
  "repos": [
    {"name": "quantum-oracle-sketching", "path": "repos/quantum-oracle-sketching",
     "url": "https://github.com/haimengzhao/quantum-oracle-sketching.git",
     "commit": "084a475b...", "retrieved_at": "2026-09-26T10:00:00+00:00"}
  ],
  "reproduction": null,
  "attempts": [],
  "status": "fetched",
  "legacy_paths": ["inbox/papers/quantum-oracle-sketching[2604.07639]"],
  "note": "optional: why it was fetched",
  "dispositions": {"attempt-slug": {"decision": "dropped", "note": "...", "date": "2026-09-26"}}
}
```

| Field | Meaning |
|-------|---------|
| `id` | Directory name; lowercase kebab-case; never renamed. Old names go in `aliases`. |
| `kind` | One label or a list: `paper`, `repository`, `dataset`. A paper and its code or dataset from the same work share one reference and list every label that applies. |
| `arxiv_id` | Bare id without version; the version is kept in `entry_url` and `pdf_url`. |
| `pdf`, `pdf_sha256`, `pages` | The archived PDF and its checksum; `null` when there is no PDF. |
| `fetch_status` | `pdf:ok`, `pdf:ok:pdf_only` (metadata unavailable), `pdf:ok:title_mismatch` (accepted by hand), `pdf:ok:adopted` (hand-placed file recorded as is), or legacy variants. |
| `metadata_source` | `arxiv_api`, `abs_html`, `pdf_only`, `url`, `local`, or legacy variants. |
| `repos` | Clones and dataset folders under `repos/<name>/`: git `url` and `commit`, or `tree_sha256` and `files` for non-git folders. |
| `reproduction` | `"reproduce/"` when the verified record exists, else `null` (mirrors disk). |
| `attempts` | Every attempt workspace ever created under `attempts/` (kept after cleanup). |
| `status` | `pending`, `fetched`, `attempted`, `reproduced`, `partial`, `failed`. |
| `dispositions` | Optional fate of attempt workspaces: `promoted`, `superseded`, `dead-end`, `dropped`, or `keep`, with a one-line note. Read by `skills/guards/scripts/gc_attempts.sh`, which never reclaims a dispositioned workspace. Older dispositions are rows in `wiki/implementations/attempt-dispositions.md`, which the guard also reads. |

Readers must tolerate extra keys. Writers preserve keys they do not own.

## references/references.json (generated, tracked)

`{"references": [...]}` sorted by id, one entry per provenance file:

`id`, `kind`, `title`, `arxiv_id`, `aliases`, `has_pdf` (a PDF is recorded), `repos` (names),
`reproduction`, `attempts`, `status`, `provenance` (`references/<id>/provenance.json`).

Rebuild it with `python3 skills/fetch-reference/scripts/references_registry.py rebuild`; never
edit it by hand. `references_registry.py validate` checks every provenance file against disk
and the index; `--local` also verifies the local PDF checksums and repository commits.
