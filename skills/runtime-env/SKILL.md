---
name: runtime-env
description: Detect the current machine and runtime, run read-only environment probes (GPU, network, host resources, git and SSH), and apply the isolation and Python-environment strategy for that machine; also builds the canonical `.venv`.
usage: Use before running code, classifying GPU capacity, fetching external sources, or executing a reproduction attempt, especially on a machine not yet fingerprinted in this session.
---

# Runtime environment

This repository syncs to GitHub and may run on very different machines (a curated GPU dev
container, a bare host with Docker, a plain container, a laptop). The boundaries in `AGENTS.md`
and the pages `wiki/project/distillation-tower.md` and `wiki/project/spending-compute.md`
state the machine-agnostic invariants; this skill resolves them into the concrete mechanism for the
machine you are on:

- External (untrusted) code runs only inside an isolated runtime, never on a host control plane.
- Do not rebuild a known-good preinstalled stack; layer onto it.
- Time limits: smoke runs 30 minutes; detached GPU jobs at most 2 days; heavy GPU work only when
  a usable GPU is present.

> **Confinement and GPU.** The Docker dev container is the sanctioned runtime: it mounts the project
> (so the filesystem is confined to it) and may ship CUDA and PyTorch ready. If your shell runs on the
> host as `root` (`whoami` is root, `nvidia-smi` fails with `NVML init`, the project directory is
> owned by another uid), you are outside the container. Fix that before training by entering the
> container, not by improvising a host-level venv or an external `git worktree`.

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

- `ps` or `top` %CPU is not GPU utilization; they measure CPU cores, not `utilization.gpu`.
- A live process (`kill -0`) is not GPU saturation.
- Call a job foreign only when the snapshot shows `tag=foreign` on a GPU PID, not from old notes.
- Do not claim a GPU utilization percentage when `GPU_PROBE_SOURCE=torch_mem_only` (util is
  `unknown`).

Quote `SNAPSHOT_TIME` and `AVAIL_TIER` from the snapshot output in maintenance and synthesis records.

## Procedure

### 1. Fingerprint the machine

```bash
bash skills/runtime-env/scripts/detect.sh
# or as part of a bundle:
bash skills/runtime-env/scripts/snapshot.sh --bundle fingerprint
```

### 2. Take an environment snapshot (when routing, fetching, training, or recording GPU state)

```bash
bash skills/runtime-env/scripts/snapshot.sh --bundle router --max-age 60
bash skills/runtime-env/scripts/snapshot.sh --bundle router --json   # flat JSON
```

Read `OVERALL`, `AVAIL_TIER`, and the per-probe `*_status` lines. Classify capacity from
`AVAIL_TIER` only (`avail_heavy`, `avail_light`, `avail_none`), which is distinct from a task list
item's GPU requirement (`free`, `light`, `heavy`).

### 3. Match a machine profile

Pick the first row that matches `MACHINE_PROFILE` from the snapshot and read that profile:

| If | Machine | Profile |
|----|---------|---------|
| inside a container (`/.dockerenv`), `/dev/nvidia*` present, no `edencode` or `docker` CLI inside, and `nvidia-smi` reports a B300 | EdenCode B300 dev container | [machines/edencode-b300.md](machines/edencode-b300.md) |
| inside a container (`/.dockerenv`) and `torch` is `*+cu124` with `/dev/nvidia*` present and no `edencode` or `docker` CLI inside | EdenCode H200 dev container | [machines/edencode-h200.md](machines/edencode-h200.md) |
| not in a container and `docker` (or `podman`) on PATH | bare host with Docker | [machines/generic-host-with-docker.md](machines/generic-host-with-docker.md) |
| inside a container, no nested `docker`, not EdenCode | generic container | [machines/generic-container.md](machines/generic-container.md) |
| none of the above, or ambiguous | unknown | [machines/unknown.md](machines/unknown.md) |

GPU probes are machine-specific: `machines/probes/<profile>-gpu.sh` (see [probes.md](probes.md)).

### 4. Apply the matched profile

Follow its isolation strategy and Python environment sections. If the profile conflicts with a
human instruction, record the conflict in a discussion thread (`research-threads`) and continue with
work that does not depend on it.

### 5. Record what you learned

Machine-specific facts that would help the next run go in the matching `machines/*.md`, not in the
`AGENTS.md` (which stays machine-agnostic) and not in the wiki. Add a profile file and a
row in the table above when you meet a new machine.

## Canonical venv

`bash skills/runtime-env/scripts/setup_venv.sh` rebuilds `./.venv` (it wipes the old one). When
`features.lib` and `package` are set it installs `lib/` editable and smoke-imports that package;
otherwise it only ensures a working interpreter/venv. It fingerprints via `profile_match_id`
first and chooses isolated vs baseline install from that profile. Run it only when the venv is
missing or broken, never during another agent's run. `./run.sh` only invokes this script when
`.venv` is absent — it does not re-implement profile matching or install policy.

### Prefer the container baseline (standing rule)

On a curated image (EdenCode and similar — profiles `edencode-b300` / `edencode-h200`, or a
`generic-container` that already ships torch), the container's installed distributions are the
matched stack (CUDA / torch / jax / numpy / …). Host profiles (`generic-host-with-docker`,
`unknown`) always get an isolated venv; a stray host `torch` install must not trigger baseline
mode. On curated profiles `setup_venv.sh` therefore:

1. Creates `./.venv` with `--system-site-packages`.
2. Installs the editable lab package (from `config.yml` `package`) with `--no-deps` when lib is enabled.
3. Walks `lib/pyproject.toml` direct deps plus their transitive requirements.
4. **Keeps** any distribution already importable whose version satisfies the specifier — does not
   reinstall it into the venv.
5. **Installs `--no-deps`** only what is missing or whose container copy does not meet the
   specifier (those may shadow into the venv).

Do not special-case one package at a time. A floor like `jax>=0.8.1` is not permission to float to
the newest PyPI wheel when the image already ships a satisfying build. Hand-upgrading CUDA-adjacent
packages in `.venv` is forbidden; change the image, or open a researcher thread, if the baseline is
truly insufficient. Dry-run with `SETUP_VENV_DIR=/tmp/... bash skills/runtime-env/scripts/setup_venv.sh`.

## Scripts

| Script | Role |
|--------|------|
| `scripts/detect.sh` | Fast fingerprint (profile match signals); prints `matched_profile:` |
| `scripts/snapshot.sh` | Probe orchestrator with cache and flat JSON |
| `scripts/setup_venv.sh` | Canonical repository `.venv` |
| `scripts/lib/profile_signals.sh` | Shared profile-matching rules (`detect.sh` and `match_profile.sh`) |
| `scripts/lib/gpu_common.sh` | Shared NVML GPU probe logic |
| `scripts/lib/common.sh` | `probe_kv`, `probe_note`, paths, GPU process tagging |
| `probes/*.sh` | Individual probes |
| `machines/probes/*-gpu.sh` | Machine-specific GPU configuration (thin wrappers over `gpu_common.sh`) |

## Detection signals

- `/.dockerenv`, `/proc/1/cgroup`: am I in a container?
- `/etc/os-release`: distribution and version.
- `command -v docker podman nerdctl` and `/var/run/docker.sock`: nested containers?
- `command -v edencode`: host tool; absent inside the launched dev container.
- `/dev/nvidia*`, `nvidia-smi`, `torch.cuda.is_available()`: mapped against usable.
- `command -v uv pip`, `python --version`: environment tooling.
- `whoami`, `$HOME`, `hostname`: identity (do not rely on the hostname alone).
