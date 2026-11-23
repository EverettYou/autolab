# Machine profile — EdenCode B300 dev container

The EdenCode B300 server's containerized dev environment. **The agent runs *inside* the
launched dev container** (not on the host). This container **is** the isolation boundary — for
both development and reproductions/benchmarks.

## Fingerprint (how this profile is matched)

- `/.dockerenv` present (we are in a container).
- `/etc/os-release` → Ubuntu 24.04.
- `nvidia-smi` reports **NVIDIA B300 SXM6 AC** and `/dev/nvidia0..7` are mapped. `torch` is
  `2.10.0+cu130`.
- **No `docker`/`podman` inside** (no nested runtime) and **no `edencode` CLI inside** (that's a
  host tool). The container user is `root` with `HOME=/home/<user>` (for example `/home/yzyou`).
  Hostname `edencode-b300`. `uv` at `/usr/local/bin/uv`. `gh` at `/usr/local/bin/gh`.
- There is no `python` on `PATH`. The system interpreter is `/usr/bin/python3` (3.12).

`whoami` is `root` inside this container. That does not mean the shell is on the host: `/.dockerenv`
is present and `nvidia-smi` initializes. The host-root warning in the runtime-env skill applies when
`nvidia-smi` fails NVML init.

## Isolation strategy

**This container is the isolation boundary.** Do NOT try to install Docker or use
docker-in-docker — the host Docker Engine is one layer up and intentionally unreachable; a
mounted host socket would be host-root and breaks the "host is control plane" rule.

- Run benchmarks and reproductions **here**, in a venv (see below).
- For **untrusted external code**, isolate within this container: the attempt workspace
  (`references/<id>/attempts/<slug>/`), a **per-attempt venv** (see "conflicting pins"),
  and the 30-minute smoke cap for a first pass (`run_attempt.sh` enforces it). Heavy GPU training
  runs detached (at most 2 days). Accepted tradeoff: blast radius is this disposable per-user
  container. Keep no secrets here. Git auth is the IDE HTTPS credential, not a key on disk
  (`skills/git-workflow`).

## Python environment

The container ships a **known-good ML baseline** — do not rebuild it. Layer onto it.

Baseline (profile image, verified 2026-10-09; jax checked 2026-11-12): `torch 2.10.0+cu130`,
`torchvision 0.25.0+cu130`, `numpy 2.3.5`, `scipy 1.17.1`, `jax`/`jaxlib` `0.9.0.1` + matching
`jax_cuda13` plugins, `pandas 3.0.1`, `matplotlib 3.10.8`, `networkx 3.6.1`, `pytest 8.3.4`,
`ruff 0.9.7`, `scikit-learn` 1.8.x. Packages **not** in the baseline (e.g. `pyqsp`, `qiskit`) are
layered into `./.venv` by `setup_venv.sh` only when `lib/pyproject.toml` needs them.

### Canonical project venv

**One venv at the repo root** (`repo/.venv`). Do not create a second venv inside `lib/`. The install
recipe is `lib/pyproject.toml` (core deps + the `[dev]` extra):

```bash
bash skills/runtime-env/scripts/setup_venv.sh   # rebuilds ./.venv
```

The venv inherits the baseline via `--system-site-packages`. `setup_venv.sh` does **not** resolve
`platform[dev]` against PyPI and reinstall everything: it keeps every container distribution that
already satisfies the corresponding specifier, and `uv pip install --no-deps` only what is missing
or unsatisfied (standing rule in `skills/runtime-env/SKILL.md`; incident thread-006: a bare
`jax>=0.8.1` resolve floated jax to 0.12 over the image's 0.9 CUDA plugins and broke GPU). Treat
the image torch/JAX/CUDA stack as fragile matched infrastructure — never hand-upgrade it in
`.venv`. Avoid `platform[gpu]` (`jax[cuda12]`) on this B300 image (CUDA 13 baseline); inherit the
image plugin instead.

The image ships without `Python.h`. Install `python3.12-dev` before the first `setup_venv.sh`.

Do not hand-install individual packages into this venv unless you know why — change
`lib/pyproject.toml` and re-run the script.

### Conflicting pins (foreign reproductions) → still `--system-site-packages`, shadow the conflicts

A foreign repo will pin versions that clash with the baseline. **Default policy: still create a
`--system-site-packages` venv and SHADOW only the conflicting packages by installing the repo's
versions into the venv** (the venv's site-packages precede the baseline on `sys.path`, so they
win). This inherits the multi-GB CUDA torch from the baseline instead of reinstalling it — the
attempt venv stays ~hundreds of MB, not multi-GB. Use a **per-attempt** venv (not the shared root
`.venv`) so these overrides don't pollute the core env.

`machines/edencode-h200.md`. The same shadowing recipe applies here; pin the base interpreter to
this image's Python 3.12:

```bash
W=references/<id>/attempts/<slug>
uv venv --python /usr/bin/python3 --system-site-packages "$W/.venv"
PY="$W/.venv/bin/python"
uv pip install --python "$PY" numpy==1.26.4 scipy==1.11.1 retworkx==0.14.2
```

**Last resort — fully isolated venv** (`uv venv` *without* `--system-site-packages`): only if a
repo genuinely needs an incompatible **torch/CUDA** build, or shadowing can't reconcile the stack.
This reinstalls everything (GB-scale); delete it after the run.

## GPU notes

- 8× **NVIDIA B300 SXM6 AC**, driver **595.71.05**, `nvidia-smi` CUDA **13.2**. `torch` is built
  `+cu130` (`torch.version.cuda` is 13.0). Each GPU reports **275040 MiB**.
- `nvidia-smi` is present inside this container and CUDA was live on all 8 devices at fingerprint
  (2026-10-09). If `torch.cuda.is_available()` is `False` with "Can't initialize NVML" while
  `/dev/nvidia*` exists, relaunch the dev container before debugging the stack.
- GPU utilization for agents: run `snapshot.sh --bundle router` — probe script
  `machines/probes/edencode-b300-gpu.sh` reads **host B300s via container NVML** (`nvidia-smi` or
  pynvml). Do not use `ps` CPU% as GPU evidence.
- The `edencode` CLI diagnostics may also be run on the **host** by humans. If a relaunch
  doesn't fix GPU, the human runs `edencode doctor` / `nvidia-smi` on the host or pings admin.

### Probe thresholds (router `AVAIL_TIER`)

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `GPU_IDLE_UTIL_MAX` | 10 | `utilization.gpu` ≤ this → idle candidate |
| `GPU_MIN_FREE_GIB_HEAVY` | 20 | Min free VRAM per GPU for idle tier |
| `GPU_COUNT_EXPECTED` | 8 | All eight must pass for `avail_heavy` |

Override via env when invoking the gpu probe (rare).

## Launch / git (for humans, context only)

- Launch from host home: `cd ~ && edencode run --profile dev`.
- `gh` 2.102.0 is on `PATH`. It is not logged in. Git over HTTPS uses the IDE askpass. Procedure:
  `skills/git-workflow`.

## Gotchas

- Test CUDA with `torch.cuda.is_available()` as well as `nvidia-smi`. Both worked at fingerprint;
  a later container start can still map `/dev/nvidia*` before NVML is ready.
- The baseline `numpy` is **2.x**; older repos pinned to numpy 1.x must shadow it in a per-attempt venv.
- Don't `pip install` into the system interpreter (mutates the shared baseline) — always a venv.
- **`--system-site-packages` only inherits the baseline if the venv is built on the system
  interpreter.** A bare `uv venv --system-site-packages` picks a *uv-managed* CPython
  (`~/.local/share/uv/python/...`) whose site-packages are empty, so numpy/torch are invisible.
  Always pin the base explicitly: `uv venv --python /usr/bin/python3 --system-site-packages …`
  (`setup_venv.sh` does this; this image has `/usr/bin/python3` 3.12 and no `/usr/bin/python3.11`).
- `python` is not on `PATH`. Call `python3` or the venv's `bin/python`.
- The image has no `Python.h`. `apt-get install python3.12-dev` (the container user is root) before
  `setup_venv.sh`. Verified needed on 2026-10-09: the build died on
  `lib/src/<package>/`.
  (`test_canonical_names_resolve` fails with `No module named 'relay_bp'` without it); install it with the baseline pins:
  beliefmatching 0.1.1).
  install it with `--no-deps` as its pyproject comment says: `uv pip install --python .venv/bin/python --no-deps "optional-extra>=0.1"`
  (done 2026-10-09: 0.1.1.dev20260910235247). With both extras the full suite on 2026-10-09 leaves one failure,
  `test_graphqec.py::test_graphqec_bb72_weight_store_key_count`: registered GraphQEC weights did not
  migrate from the H200 machine (FileNotFoundError on `model.safetensors`), not an environment defect.
- `notes/*/compile.sh` needs `~/.local/bin/tectonic`, which the image lacks. Installed 2026-10-10 with the researcher's approval:
  the official static release `tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz` from github.com/tectonic-typesetting/tectonic
  (archive sha256 `dfb82876f2986862996e564fa507a9e576e0c1e3bee63c2c1bd677c2543e6407`), `install -m 755 tectonic ~/.local/bin/`.
  The first compile downloads the TeX bundle (about a minute).
- `compile.sh` for the factory paper also needs `bibtex` (separate main / appendix reference lists, `bu1` / `bu2`), which the image
  lacks; tectonic's built-in BibTeX does not cover them. The script honours `BIBTEX=<path>`. Workaround used 2026-10-25, with no
  system or `~/.local` change: `apt-get download texlive-binaries libkpathsea6` (Ubuntu noble, 2023.20230311.66589-9build3; sha256
  `18cc916f…6d86` and `9a1fd09a…5021`) into a
  scratch directory, `dpkg -x <deb> root` for both, and a wrapper that sets
  `LD_LIBRARY_PATH=<root>/usr/lib/x86_64-linux-gnu` and runs `<root>/usr/bin/bibtex.original` (the Debian name of the binary). It
  warns that `texmf.cnf` is missing and works, because `unsrturl.bst` and `refs.bib` sit in the paper directory. A permanent install
  under `~/.local` needs the researcher's approval, as tectonic did.
