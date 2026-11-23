# References

**External sources** — papers, repositories, and datasets the lab builds on. Each source gets one
kebab-case id and one directory. References are **input**: a reproduction record says how a
source’s claims held up when rerun here; it does not make those claims ours. Durable project
knowledge still lives in the **wiki**; our own experiments live in **labs**.

**This README** is the human floor contract. **Enforcement:**
[`skills/fetch-reference`](../skills/fetch-reference/SKILL.md) (`references_registry.py validate`,
provenance schema) plus reproduce / attempts guards.

## Role vs the rest of the repo

| Place | Holds |
| --- | --- |
| `references/<id>/` | One external source: provenance, optional PDF / clones, optional reproduce record |
| `references/references.json` | Generated catalog from every `provenance.json` — not edited by hand |
| `references/<id>/attempts/` | Untrusted external reproduce sandboxes (`runtime-env`) |
| `labs/<id>/` | Our trusted experiments |
| `wiki/` | Cited project knowledge distilled from labs / reproductions |
| `notes/<Project>/` | Optional long-form manuscripts (not an archive of external PDFs) |
| `lib/` | Optional shared package (never copy from references) |

Pipeline:

```text
discover-references  →  candidates only (no files)
fetch-reference      →  references/<id>/ + references.json
reproduce-reference  →  attempts/<slug>/  →  (Accept) reproduce/
wiki-ingest          →  wiki pages citing provenance / reproduce/
promote-lib       →  optional re-implementation in lib/
```

## Layout of every reference

Name: `references/<kebab-id>/`. Ids are never renamed; older names go in `aliases`.

A directory with only `provenance.json` is valid. Do **not** invent top-level names; `validate`
rejects anything outside the table below.

### Required

| Path | Owns |
| --- | --- |
| `provenance.json` | Tracked source of truth (id, kind, title, checksums, repos, status, …) |

`references/references.json` at the tree root is the generated index (`rebuild` / `sync`). Do not
edit it by hand.

### Optional (create when you have cargo)

| Path | Tracked? | When |
| --- | --- | --- |
| `paper.pdf` | no | Archived PDF |
| `README.md` | yes | Optional **archive note** (why fetched, PDF quirks, links to reproduce/labs) — not a paper abstract and not a literature review (`wiki/literature/` owns cluster reviews) |
| `repos/<name>/` | no | One checkout / dataset tree per upstream |
| `attempts/<slug>/` | no | Untrusted reproduction workspace |
| `reproduce/` | yes | Accepted attempt (`promote_attempt.sh` only) |

```text
references/<id>/
  provenance.json     # required
  paper.pdf           # optional — local
  README.md           # optional
  repos/<name>/       # optional — local
  attempts/<slug>/    # optional — local
  reproduce/          # optional — tracked
```

Field definitions: [`provenance-schema.md`](../skills/fetch-reference/references/provenance-schema.md).

## Skills that own this tree

| Skill | Does |
| --- | --- |
| [`discover-references`](../skills/discover-references/SKILL.md) | Search candidates; writes nothing here |
| [`fetch-reference`](../skills/fetch-reference/SKILL.md) | Archive; write provenance; rebuild catalog |
| [`reproduce-reference`](../skills/reproduce-reference/SKILL.md) | Run claims in `attempts/`; promote → `reproduce/` |
| [`guards`](../skills/guards/SKILL.md) | `references` / `reproduce` / attempts GC |

```bash
S=skills/fetch-reference/scripts
python3 $S/references_registry.py resolve 2512.07057
python3 $S/fetch_reference.py paper --id <id> --arxiv … --note "…"
python3 $S/references_registry.py rebuild
python3 $S/references_registry.py validate
bash skills/reproduce-reference/scripts/run_attempt.sh <id> <slug>
bash skills/reproduce-reference/scripts/promote_attempt.sh <id> <slug>
```

## Catalog and git

`references.json` rows carry `id`, `kind`, `title`, `arxiv_id`, `aliases`, `has_pdf`, `repos`,
`reproduction`, `attempts`, `status`, and a path to provenance. Status: `pending`, `fetched`,
`attempted`, `reproduced`, `partial`, `failed`.

Tracked: `provenance.json`, optional per-id `README.md`, `reproduce/`.  
Local (gitignored under `references/*/*` with those exceptions): `paper.pdf`, `repos/`, `attempts/`.

## vs other floors

| | `references/<id>/` | `labs/<date-slug>/` | `notes/<Project>/` |
| --- | --- | --- | --- |
| Purpose | External archive + optional claim reproduction | Our experiment | Long-form manuscript |
| Trust | External / untrusted clones | Trusted lab code | Our TeX |
| Hard need | `provenance.json` | `lab.json`, `PLAN.md`, `REPORT.md` | `main.pdf` (+ `main.tex` to edit) |
