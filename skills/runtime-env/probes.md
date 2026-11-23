# runtime-env probes

Read-only probes live in `scripts/probes/` and are composed by `scripts/snapshot.sh`.
**GPU utilization claims must come from these probes** — never from `ps`/`top` CPU%.
See also [references/gpu-reading.md](references/gpu-reading.md).

## Bundles

| Bundle | Probes | When |
|--------|--------|------|
| `fingerprint` | fingerprint | Machine unknown; facts + policy |
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

## GPU probe

`scripts/probes/gpu.sh` runs the shared NVML logic in `scripts/lib/gpu_common.sh`. It sets
`GPU_COUNT_EXPECTED` from the **live** GPU product name (`nvidia-smi`):

| Name contains | `GPU_COUNT_EXPECTED` |
|---------------|----------------------|
| B300 | 8 |
| H200 | 2 |
| other / none | 0 (unset topology; tier from whatever GPUs are visible) |

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `GPU_IDLE_UTIL_MAX` | 10 | GPU util ≤ this counts as idle |
| `GPU_MIN_FREE_GIB_HEAVY` | 20 | Min free VRAM for `avail_heavy` / `avail_light` |
| `GPU_COUNT_EXPECTED` | from live name | When >0, all expected GPUs must be idle for `avail_heavy` |

### `AVAIL_TIER` (machine capacity, not a task's GPU requirement)

| Value | Meaning |
|-------|---------|
| `avail_heavy` | All expected GPUs idle by thresholds (or all visible if expect=0) |
| `avail_light` | ≥1 GPU idle |
| `avail_none` | No GPU idle |

## Probe reference

### fingerprint

Runs `scripts/detect.sh` and emits `RUNTIME_CAPABILITY`, `POLICY_*`, and `FACT_*` kv fields.

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
