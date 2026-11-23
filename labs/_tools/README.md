# Lab Tools

Shared helpers for dated lab drivers. Not a lab — do not add experiment code here.

Import path (from a script under `labs/<id>/scripts/`):

```python
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1] / "_tools"))  # labs/_tools

from paths import lab_output, truncate_for_run, require_absent
from progress import Progress
```

## `paths.py` — output paths

Three layers. Most drivers use `lab_output` once, then a policy helper.

| Function | Layer | Role |
| -------- | ----- | ---- |
| `lab_place(path, category=None, *, create_parent=False)` | Layout | Move a path into the correct category (`results`, `data`, `figures`, …) under `labs/<id>/`. |
| `lab_run_file(directory, kind, ext, **params)` | Identity | Build `kind_h64_seed1.jsonl` from sorted `**params` inside an existing directory. |
| `lab_output(lab_dir, kind, ext, *, category="results", **params)` | Both | One step: `HERE` + category + parametric filename. |
| `truncate_for_run(path, *, resume=False)` | Policy | Truncate before writing (stops append-mode concat on rerun). |
| `require_absent(path)` | Policy | Exit if the file exists — for results already cited in `REPORT.md`. |

**Typical pattern**

```python
metrics = truncate_for_run(
    lab_output(HERE, "metrics", "jsonl", seed=args.seed, h=args.h)
)
summary = require_absent(
    lab_output(HERE, "summary", "json", seed=args.seed, h=args.h)
)
```

**Split steps** (relocate an existing path, then name a new file):

```python
from paths import lab_place, lab_run_file

target = lab_place(HERE / "results" / "weights.pkl", create_parent=True)
# → labs/<id>/data/weights.pkl

path = lab_run_file(HERE / "results", "ler", "csv", beta=0.5)
```

Suffix → category defaults live in `OUTPUT_CATEGORIES` inside `paths.py`.

## `progress.py` — long loops

Flush a line at most every 10 minutes (default) so monitors see work, not only a live PID.

```python
prog = Progress("sweep", target=60_000)  # every=600.0 seconds default
for batch in ...:
    ...
    prog.tick(done=done, extra=f"fails {fails}")

prog.done(done, extra="time cap")  # early stop: force a final line
```

- First `tick` and the final `tick` always print.
- Before ~1 s elapsed, rate/ETA are omitted (`rate not yet measurable`).

## See also

- [labs/README.md](../README.md) — human layout summary (SSOT pointer + tree)
- `skills/organize-lab/references/report-contract.md` — canonical machine-checked contract
- `skills/organize-lab/SKILL.md` — Enforcement table (validate / tidy / report lint / guards)