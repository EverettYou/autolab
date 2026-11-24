---
name: runtime-env
description: Detect the current machine and runtime, run read-only environment probes (GPU, network, host resources, git and SSH), resolve isolation and venv policy from live facts, and build the canonical `.venv` with setup_venv.sh.
usage: Use before running code, classifying GPU capacity, fetching external sources, or executing a reproduction attempt, especially on a machine not yet fingerprinted in this session.
---

# Runtime environment

This repository syncs to GitHub and may run on very different machines (a GPU cloud
container, a bare host with Docker, a plain container, a laptop). The boundaries in `AGENTS.md`,
`wiki/system/distillation-tower.md` (human OS manual) and
`skills/auto-research/references/spending-compute.md` (agent compute policy) state the
machine-agnostic invariants; this skill resolves them into concrete facts and policy for the
machine you are on:

- External (untrusted) code runs only inside an isolated runtime, never on a host control plane.
- Do not rebuild a known-good preinstalled stack; layer onto it with `setup_venv.sh`.
- Time limits: smoke runs 30 minutes; detached GPU jobs at most 2 days; heavy GPU work only when
  a usable GPU is present.

## When to use

| Trigger | Command |
|---------|---------|
| Machine not fingerprinted this session | `snapshot.sh --bundle fingerprint` |
| Choosing work by GPU capacity (research loop routing) | `snapshot.sh --bundle router --max-age 60` |
| Before fetching from arXiv or GitHub (`fetch-reference`) | `snapshot.sh --bundle scout` |
| Before the first execution of an attempt (`reproduce-reference` RUN) | `snapshot.sh --bundle repro-run` |
| Launching detached GPU work | `snapshot.sh --bundle train-launch` |
| Creating the venv, or unsure of the Python stack | `setup_venv.sh` after a fingerprint |

All scripts live in `skills/runtime-env/scripts/`. Full probe catalog: [probes.md](probes.md).

## Forbidden inferences

See [references/gpu-reading.md](references/gpu-reading.md). Summary:

- `ps` or `top` %CPU is not GPU utilization.
- A live process (`kill -0`) is not GPU saturation.
- Call a job foreign only when the snapshot shows `tag=foreign` on a GPU PID.
- Do not claim a GPU utilization percentage when `GPU_PROBE_SOURCE=torch_mem_only`.

Quote `SNAPSHOT_TIME` and `AVAIL_TIER` from the snapshot output in maintenance and synthesis records.

## Procedure

### 1. Fingerprint facts

```bash
bash skills/runtime-env/scripts/detect.sh
# or:
bash skills/runtime-env/scripts/snapshot.sh --bundle fingerprint
```

Read live facts (`FACT_*` / detect lines) and resolved policy (`POLICY_*`, `RUNTIME_CAPABILITY`).
Hostname in detect output is human context only — **not** an input to policy.

### 2. Snapshot when routing, fetching, or recording GPU state

```bash
bash skills/runtime-env/scripts/snapshot.sh --bundle router --max-age 60
bash skills/runtime-env/scripts/snapshot.sh --bundle router --json
```

Classify capacity from `AVAIL_TIER` only (`avail_heavy`, `avail_light`, `avail_none`).

### 3. Apply resolved policy

Policy is a pure function of facts (plus optional local override). Do **not** look up branded
machine dossiers. See [references/isolation-boundaries.md](references/isolation-boundaries.md).

| Condition | isolation | untrusted_code | venv.mode | repo_venv |
|-----------|-----------|----------------|-----------|-----------|
| default / bare host (no docker) | host-control-plane | forbid | inherit-baseline | here |
| in container | this-container | allow-in-attempt-workspace | inherit-baseline | here |
| host + docker/podman | docker-attempt | only-in-container | inherit-baseline | require-container |

`RUNTIME_CAPABILITY` examples: `container+H200`, `container+B300`, `container`, `host+docker`,
`host+Darwin`, `host` — product/OS capability tags only (no vendor brand, no personal hostname).

`repo_venv=require-container` means `setup_venv.sh` **refuses** to build `./.venv` on that host
control plane (so the host is not polluted). Enter a lab/research container and run setup there.
Bare hosts without Docker/Podman keep `repo_venv=here` and may install on the host. Escape hatch:
`SETUP_VENV_ALLOW_HOST=1`.

Optional local override (never commit real machine ids): `$AUTOLAB_RUNTIME_POLICY` or
`~/.config/autolab/runtime-policy.json` with keys `isolation`, `untrusted_code`, `venv.mode`,
`repo_venv`.

If policy conflicts with a human instruction, record the conflict in a discussion thread
(`thread-interaction`) and continue with work that does not depend on it.

### 4. Do not add per-machine Markdown dossiers

Learned operational knowledge goes in [references/](references/) (vendor-free how-tos). Machine
exceptions stay in a **local** override file. Do not add `machines/<name>.md` profiles to the
public tree.

## Canonical venv

`bash skills/runtime-env/scripts/setup_venv.sh` rebuilds `./.venv` (it wipes the old one). Full
doctrine: [references/venv-baseline.md](references/venv-baseline.md).

When `features.lib` and `package` are set it installs `lib/` editable and smoke-imports that
package; otherwise it only ensures a working interpreter/venv. Prefer `uv` when on PATH;
otherwise `python3 -m venv` + `pip`. Override interpreter with `SETUP_VENV_PYTHON`.
Run only when the venv is missing or broken. `./run.sh` invokes this script when `.venv` is
absent.

If policy resolves to `repo_venv=require-container` (host with Docker/Podman), setup exits with
a clear refuse message instead of installing on the host — use the container baseline.

### Prefer the baseline

**Default:** inherit host/container site-packages and install only what is missing. Heavy stacks
(torch / jax / CUDA) are the researcher's baseline; agents must not reinstall them into `.venv`
when already satisfied.

1. Creates `./.venv` with `--system-site-packages` (unless `SETUP_VENV_ISOLATED=1` or policy
   `venv.mode=isolated`).
2. Installs the editable lab package with `--no-deps` when lib is enabled.
3. Walks `lib/pyproject.toml` deps; **keeps** satisfied baseline packages; **installs `--no-deps`**
   only gaps.

Dry-run: `SETUP_VENV_DIR=/tmp/... bash skills/runtime-env/scripts/setup_venv.sh`.

## References

| Doc | Topic |
|-----|-------|
| [references/venv-baseline.md](references/venv-baseline.md) | Inherit baseline, shadow pins, uv host pin |
| [references/gpu-reading.md](references/gpu-reading.md) | Snapshot / AVAIL_TIER / mapped≠usable |
| [references/isolation-boundaries.md](references/isolation-boundaries.md) | Host / container / docker-attempt |

## Scripts

Everything runnable lives under `scripts/`:

| Path | Role |
|------|------|
| `scripts/detect.sh` | Fast fingerprint; prints facts + policy |
| `scripts/snapshot.sh` | Probe orchestrator (bundles → `scripts/probes/`) |
| `scripts/setup_venv.sh` | Canonical repository `.venv` |
| `scripts/probes/*.sh` | Individual read-only probes |
| `scripts/lib/runtime_facts.sh` | Live facts + `RUNTIME_CAPABILITY` (sourced) |
| `scripts/lib/resolve_policy.sh` | Facts → `POLICY_*` (+ local override) |
| `scripts/lib/gpu_common.sh` | Shared NVML GPU probe body |
| `scripts/lib/common.sh` | `probe_kv`, paths, GPU PID tagging |
| `assets/docker/` | Attempt image templates for host+docker isolation |

## Detection signals

- `/.dockerenv`, `/proc/1/cgroup`: am I in a container?
- `uname` / `/etc/os-release`: OS family.
- `command -v docker podman` and `/var/run/docker.sock`: host docker?
- `/dev/nvidia*`, `nvidia-smi` GPU name, `torch.cuda` / MPS: accelerator facts.
- `command -v uv pip`, `python3 --version`: tooling.
- `whoami`, `$HOME`: identity context (hostname is not a policy input).
