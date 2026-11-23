# Machine profile — generic host with Docker

A machine where the agent runs **on the host** (not already in a container) and a container
runtime (`docker` or `podman`) is available. This is the environment the trust-zone rule was
originally written for: build a fresh image per reproduction attempt and run untrusted code
inside it.

## Fingerprint

- **Not** in a container (no `/.dockerenv`).
- `docker` (or `podman`) on PATH; ideally a working daemon (`docker info` succeeds).
- No curated preinstalled ML stack assumed.

## Isolation strategy

Each reproduction attempt gets its **own disposable container** — this is the strongest isolation
and the right call when the host is a shared/control plane.

Assets live with this profile:

```
skills/runtime-env/machines/assets/docker/
├── Dockerfile.base              # base image: python:3.11-slim + numpy/scipy
└── Dockerfile.attempt.template  # per-attempt template, FROM lab-base:latest
```

Flow:

```bash
# 1. Build the base image once (from repo root):
docker build -f skills/runtime-env/machines/assets/docker/Dockerfile.base \
  -t lab-base:latest .

# 2. Per attempt: references/<id>/attempts/<slug>/Dockerfile FROM lab-base:latest,
#    COPY the external code, pip-install its pinned deps (network available at BUILD only).

# 3. Build + run with the host-side cap and NO network at run time:
bash skills/reproduce-reference/scripts/run_attempt.sh <id> <slug>   # docker mode when a Dockerfile exists
#    -> docker run --rm --network none -v <attempt>/output:/workspace/output:rw <image>
```

- Network: available during `docker build` (for installs), **disabled at run** (`--network none`).
- Smoke wall-clock cap: 30 minutes, enforced host-side by `timeout` around `docker run`.
- Mount only the results dir; never bind-mount host source beyond designated output.

## Python environment

Inside each attempt image, install the repo's pinned deps fresh (no shared baseline to inherit).
For numerical smoke tests, `Dockerfile.base` preinstalls `numpy`/`scipy`.

## GPU notes

GPU passthrough needs the **NVIDIA Container Toolkit** and `docker run --gpus all`. If the
toolkit isn't installed, reproductions run CPU-only — fine for small-distance smokes, not for
training. Verify with `docker run --rm --gpus all <img> nvidia-smi`.

## Gotchas

- Don't mount the host Docker socket into a container to get DinD — that's host-root.
- `Dockerfile.base` is CPU-only `python:3.11-slim`; for GPU, base off an `nvidia/cuda` image and
  add the toolkit, then re-pin torch to a matching CUDA build.
