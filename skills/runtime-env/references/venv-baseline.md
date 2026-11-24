# Venv baseline — inherit with `setup_venv.sh`

Canonical script: `bash skills/runtime-env/scripts/setup_venv.sh` (rebuilds `./.venv`).

## Where to run setup

Policy `repo_venv` (from `resolve_policy`) gates the script:

- `here` — bare host without Docker/Podman, or already inside a container: build `./.venv` here.
- `require-container` — host has Docker/Podman: **refuse** and tell the operator to enter a
  container (curated baseline lives there). Do not pollute the host control plane.
  Escape hatch: `SETUP_VENV_ALLOW_HOST=1`.

## Prefer the baseline

Default: create `./.venv` with `--system-site-packages` and install only what the host or
container baseline does not already satisfy.

1. Editable lab package (`config.yml` `package`) with `--no-deps` when `features.lib` is on.
2. Walk `lib/pyproject.toml` deps (including `[dev]`).
3. **Keep** any importable distribution whose version meets the specifier.
4. **Install `--no-deps`** only missing or unsatisfied packages (they may shadow the baseline).

Torch / jax / CUDA wheels are the researcher’s baseline on the machine. Agents must not
reinstall them into `.venv` when the baseline already satisfies `lib/pyproject.toml`.

Escape hatch: `SETUP_VENV_ISOLATED=1` builds a clean isolated venv and does a full
`pip install -e "lib[dev]"`.

Dry-run: `SETUP_VENV_DIR=/tmp/... bash skills/runtime-env/scripts/setup_venv.sh`.

## Pin the host interpreter (uv)

`--system-site-packages` only inherits packages from the interpreter you pass to `uv venv`.
A bare `uv venv --python python3` may pick a uv-managed CPython whose site-packages are empty,
so numpy/torch disappear. Always pin the real host/framework interpreter (as `setup_venv.sh`
does via `resolve_host_python`). For a hand-built attempt venv:

```bash
uv venv --python /usr/bin/python3 --system-site-packages "$W/.venv"   # adjust path to the baseline python
```

## Conflicting pins (foreign reproductions)

Still prefer `--system-site-packages`. Shadow only the conflicting packages into a
**per-attempt** venv under `references/<id>/attempts/<slug>/` (not the shared root `.venv`).

Example when an upstream needs numpy 1.x (baseline is numpy 2 → “dtype size changed”):

```bash
W=references/<id>/attempts/<slug>
uv venv --python "$(command -v python3)" --system-site-packages "$W/.venv"
PY="$W/.venv/bin/python"
uv pip install --python "$PY" numpy==1.26.4 scipy==1.11.1   # shadow; keep baseline torch
```

Fully isolated venv (no `--system-site-packages`) only when torch/CUDA itself must differ —
expensive; delete after the run.

## Do not

- `pip install` into the system interpreter (mutates the shared baseline).
- Float satisfied baseline packages to newer PyPI wheels “just because”.
- Reinstall multi-GB CUDA torch into `.venv` when inherit already sees it.
