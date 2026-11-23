# Spending compute

Treat GPU and wall-clock as scarce. Smoke first, write a numeric ETA, watch progress, and ask the
researcher before burning a new or larger allocation. Do not kill unrelated jobs to “make room.”

This is the **agent policy** behind task `gpu` / `time` fields and the training gate. The loop
applies the tiers in `skills/auto-research` (`SKILL.md`, [router.md](router.md)); other skills
cross-link here rather than restating it.

## Principles

1. **Smoke before soak.** Prove the driver on a tiny slice before a long cell.
2. **Numeric ETA.** Record a measured step time and an ETA in the lab report or task body — not
   “should be fine.”
3. **Visible progress.** Long cells should flush progress on a timer (see `labs/_tools/progress.py`
   when used) so a stalled run is obvious.
4. **One axis at a time.** Prefer paired comparisons that change a single declared factor.
5. **Do not pre-empt the lab.** Do not kill unrelated research jobs to free a machine.
6. **Escalate big burns.** New GPU windows or larger budgets need a researcher decision through
   Threads (`skills/thread-interaction`).

## Who uses this

| Skill / doc | How |
| --- | --- |
| `auto-research` | Task `gpu` / `time`, training gate, router |
| `run-lab` | Budget before sweeps inside a lab |
| `create-lab` | Heavy GPU training hygiene when scaffolding |
| `runtime-env` | Machine fingerprint vs compute discipline |
| `AGENTS.md` | Ask first on large GPU-day commitments |
