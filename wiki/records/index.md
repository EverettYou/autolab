# Records

Dated, append-only write-ups that compiled pages may cite. They are **not** the knowledge layer —
settled claims belong on ledger pages (`concepts/`, `algorithms/`, …) via `wiki-ingest`. The root
[wiki index](../index.md) links here as a hub; it does not list every record.
Operation log: [log.md](log.md).

Create a subfolder only when you file the first record of that kind. Typical folders:

| Folder | When to file |
| ------ | ------------ |
| `discoveries/` | Literature scout / discovery runs (`discover-references` handoff) |
| `synthesis/` | Supervisor synthesis after understanding moved |
| `design/` | Design notes before a non-trivial implementation |
| `integrations/` | Promotion plans, gates, and landed integration notes (`promote-to-lib`) |
| `audits/` | Package audits (`audit`); often `audits/<id>/` with dated reports |

Naming: `wiki/records/<folder>/<YYYY-MM-DD>-<slug>.md` (audits may nest under a reference or
module id). Start with an H1 that names the kind and the date. Procedure: `skills/wiki-ingest`.

Do not put decisions for the researcher here — use Threads (`.auto-research/`).
