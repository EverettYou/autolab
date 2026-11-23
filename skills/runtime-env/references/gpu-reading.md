# Reading GPU capacity

Use the runtime-env snapshot, not ad-hoc `ps`/`top`.

```bash
bash skills/runtime-env/scripts/snapshot.sh --bundle router --max-age 60
```

Read `AVAIL_TIER` (`avail_heavy` / `avail_light` / `avail_none`) and quote `SNAPSHOT_TIME` when
recording capacity. Task GPU labels (`free` / `light` / `heavy`) are requirements; `AVAIL_TIER`
is what the machine currently offers.

## Forbidden inferences

- `ps` or `top` %CPU is not GPU utilization.
- A live PID (`kill -0`) is not GPU saturation.
- When `GPU_PROBE_SOURCE=torch_mem_only`, util is `unknown` — do not invent a percentage.
- Call a job foreign only when the snapshot tags a GPU PID `foreign`.

## Mapped ≠ usable

`/dev/nvidia*` and driver libs can be present while `torch.cuda.is_available()` is still false
(NVML init failure). Prefer torch/CUDA checks and a container relaunch before concluding the
GPU is permanently dead.

`nvidia-smi` may be absent inside a container even when CUDA works via torch — test with
`torch.cuda.is_available()`, not only `nvidia-smi`.

## Expected GPU counts

The GPU probe sets `GPU_COUNT_EXPECTED` from the live product name when known (e.g. H200 → 2,
B300 → 8). Override with env only when the live topology differs.
