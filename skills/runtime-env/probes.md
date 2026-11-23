# runtime-env probes

Read-only probes composed by `scripts/snapshot.sh`. **GPU utilization claims must come from these
probes** — never from `ps`/`top` CPU%.

## Bundles

| Bundle | Probes | When |
|--------|--------|------|
| `fingerprint` | fingerprint | Machine unknown; profile match |
| `router` | fingerprint, gpu, host_resources | Choosing work by GPU capacity (`--max-age 60` ok within one loop iteration) |
| `scout` | network, git_ssh | Before an external fetch (`fetch-reference`) |
| `repro-run` | fingerprint, python_env, gpu | `reproduce-reference` RUN (called by `run_attempt.sh`) |
| `train-launch` | gpu, host_resources | Before detached GPU training |
| `full` | all | Debugging |

```bash
bash skills/runtime-env/scripts/snapshot.sh --bundle router
bash skills/runtime-env/scripts/snapshot.sh --bundle router --json --max-age 60
bash skills/runtime-env/scripts/snapshot.sh --probe gpu
```

**Exit codes:** `0` PASS · `1` DEGRADED (WARN probes) · `2` FAIL

**Cache:** `.cache/runtime-env/snapshot-<bundle>.{txt,json}` (gitignored). Use `--max-age SEC` to
reuse a recent snapshot.

## Machine-specific GPU probes

GPU checks dispatch via `probes/gpu.sh` → `machines/probes/<profile>-gpu.sh`:

| Profile | Script | Notes |
|---------|--------|-------|
| `edencode-b300` | `edencode-b300-gpu.sh` | Container NVML → host B300s (driver-mapped); 8× GPU thresholds |
| `edencode-h200` | `edencode-h200-gpu.sh` | Container NVML → host H200s (driver-mapped); 2× GPU thresholds |
| *fallback* | `generic-gpu.sh` | Current namespace `nvidia-smi` / pynvml / torch mem |

Add `machines/probes/<new-profile>-gpu.sh` when onboarding a machine.

### EdenCode thresholds

`edencode-h200.md` and `edencode-b300.md` share the util and free-VRAM defaults. `GPU_COUNT_EXPECTED` is 2 on the H200 profile and 8 on the B300 profile.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `GPU_IDLE_UTIL_MAX` | 10 | GPU util ≤ this counts as idle |
| `GPU_MIN_FREE_GIB_HEAVY` | 20 | Min free VRAM for `avail_heavy` / `avail_light` |
| `GPU_COUNT_EXPECTED` | 2 (H200) or 8 (B300) | All expected GPUs must be idle for `avail_heavy` |

### `AVAIL_TIER` (machine capacity, not a task's GPU requirement)

| Value | Meaning |
|-------|---------|
| `avail_heavy` | All expected GPUs idle by thresholds |
| `avail_light` | ≥1 GPU idle |
| `avail_none` | No GPU idle |

## Probe reference

### fingerprint

Wraps `detect.sh` (which prints `matched_profile:` using the same rules as `match_profile.sh`). Sets `MACHINE_PROFILE` kv field.

### gpu

`utilization.gpu` + VRAM + compute PIDs with `tag=repo|foreign|unknown` (`repo`: the PID appears in
`.auto-research/state.json`, its command line names `references/`, `labs/`, or `lib/` under the
repository, or its working directory is inside the repository). Sources:
`GPU_PROBE_SOURCE=container_nvidia_smi|pynvml|torch_mem_only|unavailable`.

### network

`curl` reachability: arxiv export, arxiv.org, github api/site, pypi. HTTP 403 on GitHub API = reachable.

### host_resources

Load, mem avail, repo disk %. Top RSS processes (memory only — not GPU).

### git_ssh

`SSH_AUTH_SOCK`, `ssh-add -l`, `git ls-remote origin`.

### python_env

Python version, torch CUDA line, repo `.venv` presence.

## Agent rules

1. Run the right bundle before acting; quote `SNAPSHOT_TIME` + `AVAIL_TIER` in GPU claims.
2. **`ps` %CPU ≠ GPU util.** `kill -0` = process alive only.
3. Say **foreign** only when snapshot shows `tag=foreign` on a GPU PID.
4. If `GPU_PROBE_SOURCE=torch_mem_only`, util is `unknown` — do not claim a percentage.
