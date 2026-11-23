# Dashboard

Convention-driven web UI over this repository. It is **sync zone** (with `skills/`): the same
tree ships into every consumer lab. Domain content lives in the data floors; this folder only
serves and presents them.

## Run

From the repository root (Python 3.11+):

```bash
./run.sh start          # background; prints host/port
./run.sh status
./run.sh logs -f
./run.sh restart        # after server edits
./run.sh stop
./run.sh check
```

Port defaults to `hash(config.yml name)` in **1024–65535**, then linear-probes (+1) until free or
reclaimable by the **same project name** (any checkout). Override with
`dashboard.port` or `<NAME>_DASHBOARD_PORT` / `LAB_DASHBOARD_PORT` (prefix from `name`). Display
`title` / `intro` live in root `config.yml` (project identity — never synced). Local UI settings
(search key, page sizes) live under `.cache/dashboard/site.json`.
The server binds loopback and serves local frontend libraries under `frontend/vendor/`
(no CDN at runtime). The first `./run.sh` may create `.venv` and download pinned vendor
packages via `frontend/vendor/install_vendor.py` (needs network once; offline after that).

## What it shows

The home view summarizes the lab timeline, wiki graph, Threads, and the research queue. Nav opens
the data floors and control surfaces:

| Nav | Backing floor / store |
| --- | --- |
| References | `references/` |
| Labs | `labs/` |
| Wiki | `wiki/` |
| Notes | `notes/` (when `features.notes`) |
| API | `lib/` (when `features.lib`) |
| Threads | `.auto-research/` (Threads + loop) |

The System menu opens Files, Skills, and Settings. Optional floors appear only when enabled in
`config.yml`. Layout contracts for each floor live in that floor’s README — not here.

## Tree

| Path | Holds |
| --- | --- |
| `server.py` | HTTP entry |
| `backend/` | Catalog, search, Markdown, Threads writes, Notes compile adapter |
| `frontend/js/` | App shell and research views |
| `frontend/css/` | Styles |
| `frontend/vendor/` | Local Markdown, math, diagram, and PDF libraries (pins in `manifest.json`; large trees installed on demand) |

Local-only (not synced as content): `.cache/dashboard/site.json`, `data/` search index. Heavy lab
blobs and checkpoints stay on disk per floor git policy; the browser lists what the catalog exposes.

Day-to-day operation (Threads, queue, loop) is documented in `wiki/system/dashboard-and-threads.md`.
