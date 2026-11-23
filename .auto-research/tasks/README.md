# Task Bodies

Each file here is one task’s body. Scheduling fields (`for`, `gpu`, `time`, `blocked_on`, …)
live in `../state.json` under `tasks[]` — not in these files. Parent contract: `../README.md`.

Bodies are created by the loop (not part of the tracked scaffold). In consumer labs the whole
`.auto-research/` folder is local. **Every task file uses the same sections** — do not invent
extra headings (that is how queues drift into one-off formats).

## File shape

Path: `<id>.md` where `<id>` is the kebab-case task id (same as `state.tasks[].id` and
`state.tasks[].detail` → `.auto-research/tasks/<id>.md`).

Exact structure (three `##` sections, this order, no others):

```markdown
# <title>

## Goal
What “done” is aiming at, in one short paragraph (or a few lines). Not a diary.

## Work
The imperative: what to do, constraints, and which paths/skills to use. Bullets are fine.

## Done when
Observable acceptance criteria. One or more lines. When these hold, run `task done` (the
file is deleted — do not leave a “done” checkbox in the body).
```

Rules:

1. Line 1 is exactly one `# <title>` (non-empty title text after `# `).
2. The only `##` headings allowed are **`Goal`**, **`Work`**, **`Done when`**, in that order.
3. No second `# ` title, no `###` (or deeper) headings.
4. Each of the three sections must contain at least one non-blank line of body text.
5. Prefer links to labs/wiki/skills over pasting long quotes.

## `task add` content

`loop_state.py task add` writes `# <title>` for you from `--title`. Pass **only the three
sections** as `--content` / `--content-file`:

```bash
L=".venv/bin/python skills/auto-research/scripts/loop_state.py"
$L task add --title "Port the relay decoder" --for integrator --gpu free --time 5min \
  --content "$(cat <<'EOF'
## Goal
Relay decoder runs through the package API on the lab’s fixture.

## Work
Wire the driver under labs/<id>/scripts/; compare against the reference numbers in REPORT.md.

## Done when
Lab REPORT.md shows a matching figure and the package test for the port passes.
EOF
)"
```

## Lint

```bash
.venv/bin/python skills/auto-research/scripts/auto_research_lint.py
```

Findings name the file and the concrete rule (missing `## Goal`, wrong heading order, empty
section, …). Writers refuse bodies that break this contract.
