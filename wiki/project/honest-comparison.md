---
title: Honest comparison
page_type: project
status: active
updated: 2026-11-20
source_refs:
  - README.md
idea_ids: []
project_topics:
  - Research Pipeline
  - Lab Practice
---

# Honest comparison

**Summary**: Numbers only mean something inside a locked setting. Tag what moved the result, cite
the artifact, and say plainly what was reproduced, partial, or not tested here. Different
evaluation kinds answer different questions — do not substitute one for another.

**Sources**: repository README · `skills/research-workflow` · `skills/promote-to-lib`

**Last updated**: 2026-11-20

Agentic loops love tables. Without hygiene, you get beautiful comparisons across incompatible
setups — the fastest way to ship a false story into the wiki.

## Evaluation kinds

| Kind | Question | Typical home |
| --- | --- | --- |
| **Discovery / selection** | Worth our time to fetch or reproduce? | discover report, reference catalog |
| **Reproduction** | Do results support the **paper’s** claims? | `references/<id>/reproduce/` |
| **Lab finding** | What did **we** show in this dated experiment? | `labs/…/REPORT.md` |
| **Alignment** | Does the **package port** track the evidence we care about? | `promote-to-lib` VERIFY |
| **Audit / quality** | Does promoted source still match intent and bar? | `skills/audit`, wiki records |
| **Arena / roster** (optional) | Where does it sit among **our** comparisons? | informs taste; does **not** gate VERIFY |

## Principles

1. **Lock the setting, then measure.** Vary only the factors you declared. Everything else is
   noise dressed as science.
2. **Cite an artifact.** A claim in `REPORT.md` points at `results/…`, a recipe, or a pin — not at
   “the run from Tuesday.”
3. **Do not mix conventions silently.** If two rows use different metrics or decode conventions,
   say so or convert explicitly.
4. **Separate jobs.** Reproduction, lab findings, and port alignment are different questions.
   Arena numbers can inform; they do not replace the promotion gate.

These are lab habits, not bureaucracy. They keep distillation honest when something finally moves
from a lab report into the wiki or into `lib/`.

## Related pages

- [[project/what-autolab-is|Autolab]]
- [[project/spending-compute|Spending compute]]
- [[project/distillation-tower|Distillation tower]]
