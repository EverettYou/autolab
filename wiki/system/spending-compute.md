---
title: Spending compute
page_type: system
status: active
updated: 2026-11-20
source_refs:
  - README.md
idea_ids: []
topics:
  - Research Pipeline
  - Lab Practice
---

# Spending compute

**Summary**: Treat GPU and wall-clock as scarce. Smoke first, write a numeric ETA, watch progress,
and ask the researcher before burning a new or larger allocation. Do not kill unrelated jobs to
“make room.”

**Sources**: repository README · `skills/runtime-env` · `skills/research-workflow` ·
`skills/auto-research`

**Last updated**: 2026-11-20

An unsupervised loop will happily spend a weekend on the wrong experiment. Budgeting compute is
how you keep agentic research **manageable**: small proofs of life before large burns, visible
ETAs on the dashboard and in the task list, and a human gate when the ask grows.

## Principles

1. **Smoke before soak.** Prove the driver on a tiny slice before a long cell.
2. **Numeric ETA.** Record a measured step time and an ETA in the lab report or task body — not
   “should be fine.”
3. **Visible progress.** Long cells should flush progress on a timer (see `labs/_tools/progress.py`
   when used) so a stalled run is obvious.
4. **One axis at a time.** Prefer paired comparisons that change a single declared factor.
5. **Do not pre-empt the lab.** Do not kill unrelated research jobs to free a machine.
6. **Escalate big burns.** New GPU windows or larger budgets need a researcher decision through
   Threads (`skills/research-threads`). Tier caps the loop uses are applied in `skills/auto-research`; this
   page is the policy those tiers implement.

## Related pages

- [[system/what-autolab-is|Autolab]]
- [[system/dashboard-and-threads|Dashboard and Threads]]
