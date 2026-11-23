# Tool permission denials on the sanctioned path

This note is for agents (Claude Code auto mode, Cursor, or similar) when a **tool <!-- rules-lint: allow (this guide names the tool by design) -->
permission classifier** refuses a command that the project already treats as the
sanctioned isolation path for untrusted reference code.

It is **not** a substitute for `runtime-env` isolation. Project policy still forbids
running `references/` material from the repo-root `.venv` or importing it into
`lib/`.

## What the project already allows

| Action | Sanctioned? | How |
|--------|-------------|-----|
| Run upstream / paper rebuild for claims | Yes | `bash skills/reproduce-reference/scripts/run_attempt.sh <id> <slug> [timeout]` → attempt `run.sh` + per-attempt `.venv` (or docker mode) |
| Rehydrate a promoted record | Yes | `bash skills/reproduce-reference/scripts/rehydrate.sh <id> <new-slug>` |
| Compare attempt outputs to the lab package / lab scripts | Yes | Trusted lab or gate scripts that **only read** attempt `output/` (never import upstream) |
| Import upstream into `lib/` or root `.venv` | **No** | Re-implement via `promote-lib` |

When the resolved policy is `this-container`, the current container is the isolation
boundary; see `skills/runtime-env/references/isolation-boundaries.md` and
`skills/runtime-env/references/venv-baseline.md`.

## Classifier label vs project meaning

Claude Code auto mode may reject with `classifierCategory: code_from_external` <!-- rules-lint: allow (this guide names the tool by design) -->
(`[Code from External]`). That label means **provenance** (third-party /
reference material), not “path outside the repo”.

- **Label can be accurate** for Zhao (or any) code under `references/`.
- **Blanket block is wrong** for the table above: the project’s rule is “run only
  in isolation”, not “never run”.
- Soft-deny text itself says asking to **run / build / install / test** a named
  source meets the consent bar; a researcher decision that names
  `run_attempt.sh <id> <slug>` is that consent.

## When a denial hits a sanctioned command

Do **not** invent a workaround that runs upstream outside `run_attempt.sh`.
Do **not** open a scientific “may I run external code?” thread if policy and a
named attempt already authorize isolation (that was the thread-003 miss).

1. **Name the block in durable state** (task `blocked_on` or lab note), with:
   - the exact command;
   - the classifier reason / category if given;
   - the sanctioned path that command already is;
   - the next human act (below).
2. **Continue other work** (`AGENTS.md`: never park the whole loop). Block only the gated task.
3. **Escalate as a tool-permission act**, not a science decision, using
   `thread-interaction` only if the allow rule is still missing after settings below.
   The brief must include **reason + remedy** (never a bare “denied”):

```markdown
**Why blocked:** Claude Code auto mode rejected `<exact command>` as <!-- rules-lint: allow (this guide names the tool by design) -->
`code_from_external`. That label is provenance; this command is already the
lab's sanctioned isolation path (`skills/reproduce-reference`).

**What to do (pick one):**
1. Confirm user settings include the reproduce-reference `autoMode.allow` exception and Bash
   allow rules for `run_attempt.sh` (see `~/.claude/settings.json`; autoMode is <!-- rules-lint: allow (this guide names the tool by design) -->
   user-scoped, not repo `settings.local.json`). Then ask the agent to retry.
2. Run it yourself from the repo root:
   `! bash skills/reproduce-reference/scripts/run_attempt.sh <id> <slug> <timeout>`
   After `result.json` is `success` (or `output/` has the arrays), the agent
   continues with compare / gate update — no further permission needed for
   reading those artifacts.
```

4. **After the run succeeds**, clear the task block, run the compare step, update
   the gate. Do not leave “permission classifier” as a permanent blocked_on once
   outputs exist.

## Standing configuration (researcher)

User file `~/.claude/settings.json` (required for `autoMode`; project <!-- rules-lint: allow (this guide names the tool by design) -->
`.claude/settings.local.json` does **not** feed autoMode): <!-- rules-lint: allow (this guide names the tool by design) -->

- `autoMode.allow`: keep `"$defaults"`, plus the **reproduce-reference isolation**
  exception (allows `run_attempt.sh` / attempt `run.sh` / per-attempt venv only).
- `autoMode.environment`: **Host containment** — on curated GPU-cloud profiles the
  EdenCode-style dev container is the isolation boundary (`runtime-env` machine docs).
- `permissions.allow`: Bash patterns for
  `skills/reproduce-reference/scripts/run_attempt.sh` (and rehydrate / promote).

If a denial persists after those rules, use the human `!` command above; then
fix the agent on compare.
