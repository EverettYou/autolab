---
title: Shared package
page_type: system
status: active
updated: 2026-11-20
source_refs:
  - lib/README.md
idea_ids: []
topics:
  - Lab OS Architecture
---

# Shared package

**Summary**: `lib/` is optional. When you turn it on, it is a small installable package for code
you intend to reuse — not a dumping ground for notebooks, weights, or narrative. Experiments stay
in labs; the package manual lives under `wiki/package/` when you write one.

**Sources**: [lib README](../../lib/README.md) · `skills/promote-to-lib`

**Last updated**: 2026-11-20

Many auto-research setups either have **no** shared code (everything dies in a scratch folder) or
**too much** (the “library” is a mirror of every experiment). Autolab’s default is the middle path:
start with references + labs + wiki; enable `features.lib` when something has earned a home.

## What belongs in `lib/`

- Public APIs promoted through `promote-to-lib` under `lib/src/<package>/`
- Package tests as flat modules under `lib/tests/`
- Build hooks only when the package genuinely needs them

## What stays out

- Lab drivers, notebooks, result trees, figures
- Matrices, checkpoints, and other run artifacts (keep them with the lab that produced them)
- Long explanations (write `wiki/package/` pages; the dashboard API view can render live docstrings)

The template ships an empty `lib/src/` until you opt in or the first promotion bootstraps the tree.
See [[system/distillation-tower|Distillation tower]] for why promotion rewrites instead of
copying.

## Related pages

- [[system/distillation-tower|Distillation tower]]
- [[system/what-autolab-is|Autolab]]
