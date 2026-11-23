---
name: git-workflow
description: How to commit and push. Land only through `land.sh` with explicit paths; automatic loops land on `research/auto-<date>`, human-authorized task branches stay where they are. Do not open pull requests or merge to main — the researcher does both when ready.
usage: Use before any commit or push.
---

# Git workflow

Resolve the GitHub owner/repo from `git remote get-url origin` (HTTPS or SSH). Read this before you
commit or push. Do not open pull requests.

## The two things to internalize

1. **Land on `research/auto-<date>` and stay there.** Push that branch. Do **not** run
   `gh pr create`, `gh pr merge`, or any merge into `main`. The researcher opens the PR and merges
   when they choose. An unopened PR is not a blocked item and not a next action.
2. **There is no saved `gh` login and no on-disk key.** `gh auth status` reports logged out, and
   `~/.config/gh` is absent. Leave it that way. `~/.ssh/` holds `authorized_keys` only. Git over
   HTTPS authenticates through the IDE askpass (`GIT_ASKPASS`); a remote that is `git@` or `ssh://`
   still needs the forwarded SSH agent. Use `gh` only if the researcher explicitly asks for PR
   inspection — never to create or merge.

## GitHub CLI

Check `command -v gh` before the first `gh` call in a session. When it is present, `gh auth status`
still fails until a token is supplied. Take that token from the git HTTPS credential for one command,
then unset it. The credential is the same one `git fetch` and `git push` over HTTPS already use. It
requires `GIT_ASKPASS` from the IDE session.

```bash
# Do not print the token, write it to a file, or run `gh auth login`.
export GH_TOKEN="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | sed -n 's/^password=//p')"
REPO="$(git remote get-url origin | sed -E 's#(git@github\.com:|https://github\.com/)##; s#\.git$##')"
gh pr list --repo "$REPO"
unset GH_TOKEN
```

If `git credential fill` returns no `password`, the IDE session has no GitHub credential. Commit
locally and tell the human. A stored token in `~/.config/gh` is a secret on the server; the one-shot
`GH_TOKEN` is the login.

## Authentication

Read the remote URL (`git remote get-url`) and use the path that matches it.

| Remote | Auth | When it is down |
|--------|------|-----------------|
| `https://github.com/...` | IDE askpass (`GIT_ASKPASS`), when `git credential fill` returns a password. | No password, but `ssh-add -l` lists an identity: the local key is already forwarded. Push that same repository at `git@github.com:<owner>/<repo>.git`. Do not change the stored remote, do not run `gh auth login`, and do not create a key on the server. |
| `git@github.com:...` or `ssh://` | Forwarded SSH agent. `ssh-add -l` lists an identity. | Agent socket dead or no identities. `land.sh` commits and skips the push (exit 2). |

Both of the above are down only when credential fill returns no password and `ssh-add -l` lists no
identity. Then commit locally (exit 2) and tell the human. A missing `GIT_ASKPASS` is not, by
itself, a reason to start a new login.

This B300 checkout's remote is HTTPS. An older checkout may still be SSH. The push credential on
this machine is the forwarded agent from the human's SSH session (`SSH_AUTH_SOCK`), not a key file
in `~/.ssh/`. `~/.ssh/` holds `authorized_keys` only; do not generate or store a private key here.

## Branch discipline

Land only through `land.sh`. Do not run ad-hoc `git commit` or `git push` in procedures.

| Situation | Branch behavior |
|-----------|-----------------|
| On `main` or `master` at landing time | `land.sh` creates or checks out `research/auto-YYYY-MM-DD` (local date) |
| On a human-authorized task branch (for example `refactor/*`) | Stay on it; `land.sh` never switches away from a non-main branch |
| Already on today's or an older `research/auto-*` branch | Stay on it until the human merges and you are back on `main` |
| Human merged the PR and you are back on `main` | Normal; the next landing opens today's `research/auto-<date>` |

Automatic loops use `research/auto-<date>`: one branch per cycle, date-based, never task-named.

### When the tree is dirty or huge: land boldly

A large uncommitted reorganization, dozens of new paths, or a dirty `main` is **normal loop
work**, not a crisis. The researcher reviews everything on the PR before it reaches `main`. Your
job is to get settled work onto `research/auto-<date>` continuously.

**Do this:**

1. Run `land.sh` from the repository root. If you are on `main` / `master`, it creates or checks
   out today's `research/auto-<YYYY-MM-DD>`. That move off `main` is expected and safe.
2. Land with **explicit paths**. When the tick needs a shared baseline that is still uncommitted
   (`skills/`, `dashboard/`, `wiki/`, `lib/`, `run.sh`, root docs, …), land those paths first
   as one or a few coherent baseline commits. Then land the tick's own paths as later commits on
   the **same** branch.
3. Prefer more, smaller commits over waiting for a perfect single shot. Push is the default; if
   push fails, keep committing locally (exit 2) and retry later.
4. If a `land` guard fails, fix the guard or the file, or drop paths that must not land yet — then
   land again. That is ordinary engineering.
5. If you are already on a `research/auto-*` branch, **keep landing on it** until the human merges.

**Confidence:** landing onto `research/auto-<date>` does not merge to `main`, does not force-push,
and does not skip review. A dirty or huge tree is exactly when you should land, not when you should
pause. When in doubt between "ask" and "land through `land.sh`", **land**.

Only after that: do **not** open a `research-threads` thread about landing policy, branch names, or
whether the human should commit the baseline first. This section already answers those questions.
Needing the human to **merge a PR** is separate and covered below; it does not delay landing.

Forbidden:

- Inferring branch names from old records, transcripts, or repository history.
- Creating a branch yourself with any name other than what `land.sh` creates from `main`, unless the
  human asked for that branch.
- Per-task feature branches for promotions or reproductions; everything lands on the current branch.
- Merging or pushing to `main`. Merging is always the human's action on GitHub (branch protection
  enforces it). `gh pr merge` is that merge.
- External `git worktree` checkouts or sibling clones; work inside the repository and the runtime
  that `runtime-env` describes.
- Asking the researcher how to land, which branch to use, or whether they want to commit a baseline
  themselves first — instead, land boldly as above.

## Landing procedure

Script: `skills/git-workflow/scripts/land.sh` (run it from the repository root).

### 1. Prepare

```bash
git status
git diff                    # and/or git diff --cached
bash skills/guards/scripts/run_guards.sh land    # when governed files changed
```

- Write a commit message in the repository convention (`type(scope): summary`).
- List the explicit paths changed in this unit of work; never `git add -A` for substantive work.
- In this repository, commit only the `.auto-research/` **scaffold** (READMEs + empty `state.json`). Do not
  commit live task bodies, thread message files, or a dirty personal queue. Consumer labs gitignore
  the whole folder. A pull request carries the shared trees: `references/`, `labs/`, `wiki/`,
  `lib/` and `skills/`.
- Never include secrets in messages, paths, or committed files.
- Commit the artifact a person reads. A compiled manuscript (`notes/<paper>/main.pdf`) and the figures it includes are part of the paper, so they belong in the commit with the source. A checkout should show the paper without running the compiler. Leave out compiler intermediates (`build/`, `dist/`, tectonic temp dirs), editor leftovers (`*.orig`, `*.tmp`, `backup/`), and secrets. Lab weights and large experiment dumps stay out under the `labs/` rules in `.gitignore`; that is a size limit, not a ban on readable build products.

### 2. Run land.sh

```bash
bash skills/git-workflow/scripts/land.sh \
  --message "type(scope): summary" \
  --paths path1 path2 ...

# optional: also commit files untouched for 30 minutes, as a separate commit
bash skills/git-workflow/scripts/land.sh \
  --message "type(scope): summary" \
  --paths path1 path2 ... \
  --stale-sweep
```

Flags: `--push` (default), `--no-push` (commit only), `--stale-sweep`, and
`--co-author "Name <email>"` to append a `Co-Authored-By:` trailer. The trailer is optional: set it
per call, or export `LAND_CO_AUTHOR` for a session; without either, no trailer is added. A message
that already carries a trailer is left alone.

`land.sh` pushes to `origin` when that remote exists, otherwise to the first GitHub remote.

### 3. Handle the exit code

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Committed and pushed | Continue |
| 1 | Hard error | Fix and retry; a transient hook failure does not stop a loop once fixed |
| 2 | Committed, push skipped | Record "push pending" in the loop state (`auto-research`) or tell the human; retry later |
| 3 | Nothing to commit | Normal when no settled changes; skip |

A failed push never stops the work: keep committing locally and retry the push later.

### 4. Verify auth (once per session, or after a push failure)

HTTPS remote:

```bash
printf 'protocol=https\nhost=github.com\n\n' | git credential fill | awk -F= '$1=="password"{print "password: present"}'
```

A line `password: present` means the IDE credential is available. Empty output means it is down.

SSH remote:

```bash
ssh-add -l            # lists an identity: the agent is forwarded and ready
                      # "Connection refused" or "no identities": the agent is down
```

If auth is down, `land.sh` still commits (exit 2); work is never lost. Pushing is outward facing:
push at sane checkpoints, when work is ready for review. Committing locally is always fine.

## Do not open pull requests — and do not ask about them

Keep landing and pushing on the current `research/auto-*` (or authorized task) branch. Stack
commits there. **Do not** open a PR. **Do not** ask whether to open one, whether the branch is
“ready for main,” or whether to merge. **Do not** put PR/merge reminders in `next_action`,
`blocked_on`, or a discussion thread.

Merge-to-`main` is solely the researcher's judgment and timing. After a tick, you are done when
settled paths are landed and pushed on the research branch (or committed locally with push pending
if auth is down). Stop thinking about `main` after that.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gh auth status` says not logged in | No saved `gh` login; that is the expected state | One-shot `GH_TOKEN` from `git credential fill`. Leave `gh auth login` unused. |
| `gh: command not found` | Older image without the CLI | Irrelevant for landing; do not open PRs anyway |
| `could not read Username for 'https://github.com'`, while `ssh-add -l` lists a key | The remote URL is HTTPS, so Git ignores the forwarded agent | Push `git@github.com:<owner>/<repo>.git`. Leave the remote URL unchanged. Do not run `gh auth login`. |
| `git credential fill` returns no password and `ssh-add -l` has no identity | Neither askpass nor the forwarded agent is available | Commit locally; the human restores the SSH session |
| `ssh-add -l` says "Connection refused" on an SSH remote | The forwarded agent socket died | The human restores the remote-SSH session; `land.sh` commits locally (exit 2) |
| push fails with `Permission denied (publickey)` | SSH remote and the agent is down | Same as above |
| `land.sh` exit 3 | No settled changes | Normal; skip |
| `land.sh: detached HEAD` | No branch checked out | Check out the working branch first |
| Tempted to create a branch from an old record | Branch sprawl or a wrong name | Land from `main` and let `land.sh` pick the name |
| Tempted to ask who should commit a dirty `main` / reorganization | Hesitating instead of landing | Land boldly: baseline paths then tick paths on `research/auto-<date>` via `land.sh` |

Restoring an SSH agent (human side, SSH remotes only), on the local machine: `eval "$(ssh-agent -s)"`,
then `ssh-add ~/.ssh/id_ed25519`, make sure `ForwardAgent yes` is set in the SSH config, and reconnect
the remote-SSH session. Verify from here with `ssh-add -l` and `ssh -T git@github.com`.
