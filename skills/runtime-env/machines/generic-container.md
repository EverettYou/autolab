# Machine profile — generic container (no nested Docker)

The agent runs inside a container, there's no nested container runtime, and it doesn't match
the EdenCode H200 fingerprint. Treat **this container as the isolation boundary** (same principle
as EdenCode), but make no assumptions about a preinstalled ML stack.

## Fingerprint

- `/.dockerenv` (or cgroup container markers) present.
- No `docker`/`podman` inside; no `/var/run/docker.sock`.
- Not the EdenCode profile (no `*+cu124` torch baseline, or different layout).

## Isolation strategy

- This container is the isolation boundary; run reproductions here.
- Untrusted external code: the attempt workspace `references/<id>/attempts/<slug>/` + a per-attempt
  venv + the 30-minute smoke cap (`run_attempt.sh` enforces it). Don't attempt docker-in-docker.

## Python environment

First probe what's already present:

```bash
python --version; command -v uv pip
python - <<'PY'
import importlib.metadata as m
for p in ["torch","numpy","scipy"]:
    try: print(p, m.version(p))
    except Exception: print(p, "MISSING")
PY
```

- **If a curated stack exists** (torch/numpy/scipy preinstalled): inherit it —
  `uv venv --system-site-packages .venv` and layer extras with `--no-deps` (see edencode-h200
  for why `--no-deps` matters: avoids a numpy ABI break).
- **If the container is bare**: a normal isolated venv is fine —
  `uv venv .venv && uv pip install --python .venv/bin/python -e "platform[dev]"`. Install a CUDA
  torch matching the driver only if GPU work is needed.

## GPU notes

Check `/dev/nvidia*` and `python -c "import torch; torch.cuda.is_available()"`. Mapped devices
don't guarantee a working NVML — if CUDA is down and you can relaunch the container, try that
first; otherwise escalate to whoever provisions the host.

## Gotchas

- Don't `pip install` into a shared/system interpreter if the container image is shared across
  tenants — use a venv.
