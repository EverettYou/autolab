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

## Python headers (`Python.h`) — native builds during editable install

### What fails, and why

When `features.lib` is on, `setup_venv.sh` runs `pip install -e lib`. If that package’s
build compiles a **native** extension (Cython, C, pybind, …), the C compiler needs
`Python.h` from the **same minor** as the interpreter that will load the `.so`.

Many curated images ship a usable *runtime* Python (imports work) but omit the matching
development package (`pythonX.Y-dev` on Debian/Ubuntu). Then
`sysconfig.get_path("include")` has **no** `Python.h`, and the editable install fails in
the build backend. That is an **interpreter-packaging** gap: runtime present, headers
absent. It is not caused by the host GPU, hostname, or any particular lab’s domain logic.
Lab-specific extensions and bootstraps (which module is Cythonized, CPU-thread guards,
…) belong in `lib/`; this skill only ensures headers exist when a native build may run.

Remediation: restore headers for that interpreter, or point the build at ABI-compatible
headers of the same `X.Y`.

### How `setup_venv.sh` branches (before `pip install -e lib`)

The script asks what is true on *this* machine, in order—not which lab or accelerator.

1. **Interpreter already has `Python.h`** — nothing to do.
2. **`C_INCLUDE_PATH` / `CPLUS_INCLUDE_PATH` already names a dir with `Python.h`** — reuse
   it (operator or prior process already fixed the path).
3. **Same-minor uv-managed CPython headers already on disk** — export that include dir
   (no redundant download).
4. **OS can install `pythonX.Y-dev` non-interactively** — Debian/Ubuntu `apt-get`, and the
   process is root or has passwordless `sudo`. Prefer this: fixes packaging on the
   interpreter we actually build against, so later `sysconfig` lookups also see headers.
5. **`uv` is on `PATH`** — `uv python install <same-minor>` and export that include dir.
   Used when step 4 is unavailable. The venv still runs on the baseline interpreter; only
   the *headers* come from the uv-managed tree (same minor → ABI-compatible).
6. **Otherwise fail** — name what was missing (`pythonX.Y-dev`, uv, or a manual
   `C_INCLUDE_PATH`) instead of a generic “build failed”.

### After install: generic header shim

If the build succeeded only via exported/uv headers, the venv interpreter’s own include
dir may still lack `Python.h`. Later processes that shell out to gcc (rebuilds,
`torch.compile` / inductor helpers, …) need the same path. When that gap remains,
`setup_venv.sh` writes `_venv_python_header_shim` (a `.pth` import). The shim **cannot**
replace the pre-install step: the editable native compile runs inside the install
process, before any later-session `.pth` can help.

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
