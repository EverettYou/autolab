# Wiki log

Append-only operation log for wiki maintenance (ingest, renames, contract bumps). Newest first.
Kind in each heading must be `ingest`, `query`, `lint`, or `reorganize`.

## [2026-11-20] reorganize | folder sub-indexes are index.md

- Category hubs are `wiki/<folder>/index.md` (was folder `README.md`).
- Root `wiki/README.md` remains the contract; root `wiki/index.md` remains the classifier.

## [2026-11-20] reorganize | classifier index and README contract

- Root index is a classifier; folder sub-indexes list leaves.
- Wiki contract lives in `wiki/README.md` (no `SCHEMA.md`).
- Operation log lives here (was `wiki/log.md`).
