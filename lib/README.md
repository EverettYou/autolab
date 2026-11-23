# Library

**Optional shared package** — installable Python core for a consumer lab. Turn on with
`features.lib: true` and `package: <name>` in `config.yml`. The first promotion may enable this
via [`skills/promote-to-lib`](../skills/promote-to-lib/SKILL.md) when an integrator task needs the
package.

**This README** is the human floor contract. Code enters only through `promote-to-lib` (never copy
from `labs/` or `references/`).

## Role vs the rest of the repo

| Place | Holds |
| --- | --- |
| `lib/src/<package>/` | Reusable APIs (import `<package>`) |
| `lib/tests/` | Flat unit tests for that package |
| `labs/<id>/` | Experiments, drivers, one-off scripts |
| `references/<id>/` | Cited papers / upstream clones |
| `wiki/package/` | Narrative / API tutorial pages when lib is on |
| `notes/<Project>/` | Optional manuscripts |

The dashboard API view reads docstrings live from the installed package. Package narrative lives
in the wiki, not as a second docs tree under `lib/`.

## Layout (when enabled)

```text
lib/
├── README.md
├── pyproject.toml          # project name = import name; editable install into repo .venv
├── hatch_build.py          # optional build hook
├── src/
│   └── <package>/          # the only importable package
│       ├── __init__.py
│       └── …               # domain subpackages for that project
└── tests/                  # flat modules — does not mirror src/
    └── test_<topic>.py
```

| Path | Holds |
| --- | --- |
| `src/<package>/` | Source only: reusable APIs. No data dumps, result trees, weights, lab drivers, notebooks |
| `tests/` | Flat `test_*.py`; `pytest lib/tests` runs them |
| `pyproject.toml` | Metadata, deps, extras; Hatch `packages = ["src/<package>"]` |

`lib/` itself must **not** get an `__init__.py` (plain directory).

## What goes in `src/<package>/`

One import root whose name matches `config.yml` → `package`. Subpackages are stable domain nouns
for that project — not experiment folders.

**In:** library-grade modules via `promote-to-lib`; thin wrappers that expose a stable API over
mature third-party libs when that is the project’s design.

**Out:** `data/`, `apps/`, `viz/`, `scripts/`, `results/`, `figures/`; collected matrices,
checkpoints, or measurement dumps; lab drivers and one-off notebooks.

Bundled analytic constants may live only under an explicit in-package `_data/` when the
construction is defined in code. No legacy aliases: renames are hard (update call sites, delete
the old name).

## What goes in `tests/`

| Do | Don't |
| --- | --- |
| Add flat `test_<topic>.py` | Mirror `src/` as nested test packages |
| Cover public APIs needed for promotion | Import from `labs/` or `references/` |

```bash
uv pip install --python .venv/bin/python -e "lib[dev]"
.venv/bin/pytest lib/tests -q
```

## Template state

`src/` and `tests/` stay empty (`features.lib: false`, `package: null`). Add `src/<package>/`
when a consumer enables the shared core.

## vs other floors

| | `lib/` | `labs/<id>/` | `wiki/package/` |
| --- | --- | --- | --- |
| Purpose | Installable reusable APIs | One experiment | Narrative of the package |
| Entry | `promote-to-lib` | `create-lab` / organize-lab | `wiki-ingest` |
| Feature flag | `features.lib` | always on | follows lib |
