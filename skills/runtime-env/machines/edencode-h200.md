# Machine profile — EdenCode H200 dev container

The EdenCode H200 server's containerized dev environment. **The agent runs *inside* the
launched dev container** (not on the host). This container **is** the isolation boundary — for
both development and reproductions/benchmarks.

## Fingerprint (how this profile is matched)

- `/.dockerenv` present (we are in a container).
- `/etc/os-release` → Ubuntu 22.04.
- `torch` is `2.6.0+cu124`; `/dev/nvidia0..1` mapped. `torch_geometric` may be present on the
  container image but is **not** a `lib/` dependency.
- **No `docker`/`podman` inside** (no nested runtime) and **no `edencode` CLI inside** (that's a
  host tool). Home is `/home/<user>` (e.g. `/home/yzyou`), `uv` at `/usr/local/bin/uv`.

## Isolation strategy

**This container is the isolation boundary.** Do NOT try to install Docker or use
docker-in-docker — the host Docker Engine is one layer up and intentionally unreachable; a
mounted host socket would be host-root and breaks the "host is control plane" rule.

- Run benchmarks and reproductions **here**, in a venv (see below).
- For **untrusted external code**, isolate within this container: the attempt workspace
  (`references/<id>/attempts/<slug>/`), a **per-attempt venv** (see "conflicting pins"),
  and the 30-minute smoke cap for a first pass (`run_attempt.sh` enforces it). Heavy GPU training
  runs detached (at most 2 days). Accepted tradeoff: blast radius is this disposable per-user
  container. Keep no secrets here; git uses a forwarded SSH agent so no keys live on the server.

## Python environment

The container ships a **known-good ML baseline** — do not rebuild it. Layer onto it.

Baseline (profile image, verified 2026-05-29): `torch 2.6.0+cu124`, `torchvision 0.21.0+cu124`,
`numpy 2.3.5`, `scipy 1.17.1`, `pandas 3.0.1`, `matplotlib 3.10.8`, `networkx 3.6.1`, `pytest`,
`ruff`. Packages not in the baseline are layered into `./.venv` by `setup_venv.sh` only when
`lib/pyproject.toml` needs them.

### Canonical project venv

**One venv at the repo root** (`repo/.venv`). Do not create a second venv inside `lib/`. The install
recipe is `lib/pyproject.toml` (core deps + the `[dev]` extra):

```bash
bash skills/runtime-env/scripts/setup_venv.sh   # rebuilds ./.venv
```

The venv inherits the baseline via `--system-site-packages`. Same standing rule as B300
(`skills/runtime-env/SKILL.md`): keep every container distribution that already satisfies
pyproject; install `--no-deps` only what is missing or unsatisfied. Do not float satisfied
baseline packages to newer PyPI wheels. The system `python3.11` here has no `Python.h` and the
image cannot be given `python3.11-dev` (no sudo). The editable install compiles the lab package,
so **before** that install the script runs `uv python install` for the same minor version and
exports `C_INCLUDE_PATH` / `CPLUS_INCLUDE_PATH`. A startup header shim still points later
`torch.compile` runs at those headers; the shim alone is too late for the build.

Do not hand-install individual packages into this venv unless you know why — change
`lib/pyproject.toml` and re-run the script.

### Conflicting pins (foreign reproductions) → still `--system-site-packages`, shadow the conflicts

A foreign repo will pin versions that clash with the baseline. **Default policy: still create a
`--system-site-packages` venv and SHADOW only the conflicting packages by installing the repo's
versions into the venv** (the venv's site-packages precede the baseline on `sys.path`, so they
win). This inherits the multi-GB CUDA torch from the baseline instead of reinstalling it — the
attempt venv stays ~hundreds of MB, not multi-GB. Use a **per-attempt** venv (not the shared root
`.venv`) so these overrides don't pollute the core env.

C-extension **ABI-locked to numpy 1.x** (numpy 2 → "dtype size changed, 96 vs 88"), and
isolation:

```bash
W=references/<id>/attempts/<slug>
uv venv --python /usr/bin/python3.11 --system-site-packages "$W/.venv"   # inherits baseline torch 2.6+cu124
PY="$W/.venv/bin/python"
uv pip install --python "$PY" numpy==1.26.4 scipy==1.11.1 retworkx==0.14.2   # shadow baseline numpy/scipy
```

Result: **198 MB** venv (vs 4.8 GB fully isolated), torch/CUDA inherited, full GNN fwd+bwd (fp16)
on the H200. torch 2.6 runs fine against the shadowed numpy 1.26.4. `.venv` and the attempt
workspaces under `references/*/attempts/` are gitignored.

**Last resort — fully isolated venv** (`uv venv` *without* `--system-site-packages`): only if a
repo genuinely needs an incompatible **torch/CUDA** build, or shadowing can't reconcile the stack.
This reinstalls everything (GB-scale); delete it after the run.

## GPU notes

- 2× **NVIDIA H200 NVL**, driver **590.48.01**, CUDA **12.4** runtime (matches `torch …+cu124`).
- **Mapped ≠ usable.** Seen 2026-05-29: right after some container starts, `/dev/nvidia*` and
  the driver libs (`libnvidia-ml.so.590.48.01`) were present but `torch.cuda.is_available()` was
  `False` with "Can't initialize NVML". **Rebuilding/relaunching the dev container fixed it**
  (CUDA then live on both H200s). So if CUDA looks down: relaunch the container first.
- GPU utilization for agents: run `snapshot.sh --bundle router` — probe script
  `machines/probes/edencode-h200-gpu.sh` reads **host H200s via container NVML** (`nvidia-smi` or
  pynvml). Do not use `ps` CPU% as GPU evidence.
- The `edencode`/`nvidia-smi` CLI diagnostics may also be run on the **host** by humans. If a relaunch
  doesn't fix GPU, the human runs `edencode doctor` / `nvidia-smi` on the host or pings admin
  (per section 10.6 of the EdenCode user guide).

### Probe thresholds (router `AVAIL_TIER`)

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `GPU_IDLE_UTIL_MAX` | 10 | `utilization.gpu` ≤ this → idle candidate |
| `GPU_MIN_FREE_GIB_HEAVY` | 20 | Min free VRAM per GPU for idle tier |
| `GPU_COUNT_EXPECTED` | 2 | Both must pass for `avail_heavy` |

Override via env when invoking the gpu probe (rare).

## Launch / git (for humans, context only)

- Launch from host home: `cd ~ && edencode run --profile dev` (dev ⊃ base ⊃ cuda).
- Git auth uses **SSH agent forwarding** from the laptop — no private keys on the server.

## Gotchas

- `nvidia-smi` may be absent *inside* the container even when CUDA works via torch — test with
  `torch.cuda.is_available()`, not only `nvidia-smi`.
- The baseline `numpy` is **2.x**; older repos pinned to numpy 1.x must use an isolated venv.
- Don't `pip install` into the system interpreter (mutates the shared baseline) — always a venv.
- **`--system-site-packages` only inherits the baseline if the venv is built on the system
  interpreter.** A bare `uv venv --system-site-packages` picks a *uv-managed* CPython
  (`~/.local/share/uv/python/...`) whose site-packages are empty, so numpy/torch are invisible.
Always pin the base explicitly: `uv venv --python /usr/bin/python3.11 --system-site-packages …`
(`setup_venv.sh` does this). Observed 2026-06-11 when standing up per-project venvs with
`--system-site-packages` without `--python /usr/bin/python3.11`.
