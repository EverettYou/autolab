#!/usr/bin/env bash
# land.sh — single entry for landing work: branch ensure, explicit-path commit, stale sweep, push.
# The agent writes the commit message and lists paths; this script handles git mechanics.
set -euo pipefail

STALE_MESSAGE='chore(auto): commit stale uncommitted files (≥30min untouched)'
STALE_AGE_SEC=1800

usage() {
  cat <<'EOF'
Usage: land.sh [options]

Options:
  --message MSG       Commit message (required when --paths yields changes)
  --paths PATH ...    Explicit files/dirs to add (no git add -A)
  --stale-sweep       Commit files untouched ≥30 min (git status candidates)
  --co-author TRAILER Append "Co-Authored-By: TRAILER" (e.g. "Name <email>") unless the message
                      already has one. Default: $LAND_CO_AUTHOR if set, otherwise no trailer.
  --push              Push after commit (default)
  --no-push           Commit only; exit 2 if commits were made
  -h, --help          Show this help

Branch: on main or master, switches to research/auto-YYYY-MM-DD (created from the current commit if
missing); on any other branch, stays there.

Exit codes:
  0  committed and pushed
  1  hard error
  2  committed, push skipped (auth down, remote fail, or --no-push)
  3  nothing to commit
EOF
}

MESSAGE=""
PATHS=()
STALE_SWEEP=0
DO_PUSH=1
CO_AUTHOR="${LAND_CO_AUTHOR:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message)
      MESSAGE="${2:-}"
      shift 2
      ;;
    --paths)
      shift
      while [[ $# -gt 0 && "$1" != --* ]]; do
        PATHS+=("$1")
        shift
      done
      ;;
    --stale-sweep)
      STALE_SWEEP=1
      shift
      ;;
    --co-author)
      if [[ $# -lt 2 || -z "${2:-}" || "$2" == --* ]]; then
        echo "land.sh: --co-author needs a value such as \"Name <email>\"" >&2
        exit 1
      fi
      CO_AUTHOR="$2"
      shift 2
      ;;
    --push)
      DO_PUSH=1
      shift
      ;;
    --no-push)
      DO_PUSH=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "land.sh: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ${#PATHS[@]} -eq 0 && "$STALE_SWEEP" -eq 0 ]]; then
  echo "land.sh: need --paths and/or --stale-sweep" >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "land.sh: not inside a git repository" >&2
  exit 1
fi

ensure_branch() {
  local current target
  current="$(git branch --show-current)"
  if [[ -z "$current" ]]; then
    echo "land.sh: detached HEAD — check out a branch first" >&2
    exit 1
  fi
  if [[ "$current" == "main" || "$current" == "master" ]]; then
    target="research/auto-$(date +%Y-%m-%d)"
    if git rev-parse --verify "$target" >/dev/null 2>&1; then
      git checkout "$target"
    else
      git checkout -b "$target"
    fi
    echo "land.sh: on $current — switched to $target" >&2
  fi
}

ssh_agent_alive() {
  ssh-add -l >/dev/null 2>&1
}

# origin when it exists; otherwise the first GitHub remote (this checkout may name it
# something other than origin).
resolve_push_remote() {
  if git remote get-url origin >/dev/null 2>&1; then
    printf '%s\n' origin
    return 0
  fi
  local name url
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    url="$(git remote get-url "$name" 2>/dev/null || true)"
    case "$url" in
      *github.com[:/]*)
        printf '%s\n' "$name"
        return 0
        ;;
    esac
  done < <(git remote)
  return 1
}

remote_uses_ssh() {
  local url="$1"
  [[ "$url" == git@* || "$url" == ssh://* ]]
}

# SSH URL for the same GitHub repository. Does not change the stored remote.
github_ssh_url() {
  local url="$1" path
  case "$url" in
    git@github.com:*)
      printf '%s\n' "$url"
      ;;
    ssh://git@github.com/*)
      path="${url#ssh://git@github.com/}"
      path="${path%.git}"
      printf 'git@github.com:%s.git\n' "$path"
      ;;
    https://github.com/*|http://github.com/*)
      path="${url#*github.com/}"
      path="${path%.git}"
      printf 'git@github.com:%s.git\n' "$path"
      ;;
    *)
      return 1
      ;;
  esac
}

# True when the IDE askpass (or a stored HTTPS credential) can answer without a prompt.
https_credential_ready() {
  local out
  out="$(printf 'protocol=https\nhost=github.com\n\n' | GIT_TERMINAL_PROMPT=0 git credential fill 2>/dev/null || true)"
  [[ "$out" == *$'\n'"password="* || "$out" == "password="* ]]
}

compose_message() {
  local msg="$1"
  if [[ -z "$CO_AUTHOR" ]] || printf '%s' "$msg" | grep -qi 'Co-Authored-By:'; then
    printf '%s' "$msg"
  else
    printf '%s\n\nCo-Authored-By: %s' "$msg" "$CO_AUTHOR"
  fi
}

commit_with_message() {
  git commit -m "$(compose_message "$1")"
}

collect_stale_files() {
  local now f
  now="$(date +%s)"
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    [[ -e "$f" ]] || continue
    if [[ $((now - $(stat -c %Y "$f"))) -ge "$STALE_AGE_SEC" ]]; then
      printf '%s\n' "$f"
    fi
  done < <(git status --short | grep -E '^( M|\?\?|MM| A)' | sed 's/^...//')
}

COMMITTED=0

ensure_branch

SSH_OK=0
if ssh_agent_alive; then
  SSH_OK=1
fi

# Substantive commit from explicit paths
if [[ ${#PATHS[@]} -gt 0 ]]; then
  for p in "${PATHS[@]}"; do
    if [[ -e "$p" ]] || git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
      # -A so a deleted-but-tracked path stages its removal (git ls-files matches
      # tracked paths even after they're removed from disk); plain existence check
      # alone would skip legitimate deletions.
      if git check-ignore -q --no-index -- "$p"; then
        # An ignored directory can still hold tracked files (older labs' results/),
        # and git add -A refuses an ignored pathspec; stage the tracked changes only.
        git add -u -- "$p"
      else
        git add -A -- "$p"
      fi
    else
      echo "land.sh: skip missing path: $p" >&2
    fi
  done
  if ! git diff --cached --quiet; then
    if [[ -z "$MESSAGE" ]]; then
      echo "land.sh: --message required when --paths has staged changes" >&2
      exit 1
    fi
    commit_with_message "$MESSAGE"
    COMMITTED=1
    echo "land.sh: substantive commit on $(git branch --show-current)" >&2
  fi
fi

# Stale sweep — separate commit
if [[ "$STALE_SWEEP" -eq 1 ]]; then
  mapfile -t stale < <(collect_stale_files)
  if [[ ${#stale[@]} -gt 0 ]]; then
    git add -- "${stale[@]}"
    if ! git diff --cached --quiet; then
      commit_with_message "$STALE_MESSAGE"
      COMMITTED=1
      echo "land.sh: stale sweep commit (${#stale[@]} files) on $(git branch --show-current)" >&2
    fi
  fi
fi

if [[ "$COMMITTED" -eq 0 ]]; then
  echo "land.sh: nothing to commit" >&2
  exit 3
fi

if [[ "$DO_PUSH" -eq 0 ]]; then
  echo "land.sh: committed locally (--no-push)" >&2
  exit 2
fi

PUSH_REMOTE="$(resolve_push_remote || true)"
if [[ -z "${PUSH_REMOTE:-}" ]]; then
  echo "land.sh: no GitHub remote — committed locally, push skipped" >&2
  exit 2
fi
PUSH_URL="$(git remote get-url "$PUSH_REMOTE")"
BRANCH="$(git branch --show-current)"
# SSH remotes need the forwarded agent. An HTTPS remote uses the IDE askpass when that
# credential is present. When it is not, the forwarded agent is the credential: push the
# SSH URL of the same repository. Do not change the stored remote and do not create a key.
if remote_uses_ssh "$PUSH_URL" && [[ "$SSH_OK" -eq 0 ]]; then
  echo "land.sh: SSH agent down — committed locally, push skipped" >&2
  exit 2
fi

push_via_ssh() {
  local ssh_url
  ssh_url="$(github_ssh_url "$PUSH_URL" || true)"
  if [[ -z "$ssh_url" || "$SSH_OK" -eq 0 ]]; then
    return 1
  fi
  git push "$ssh_url" "HEAD:${BRANCH}"
}

if remote_uses_ssh "$PUSH_URL"; then
  if git push "$PUSH_REMOTE" "HEAD:${BRANCH}"; then
    echo "land.sh: pushed ${BRANCH} to $PUSH_REMOTE" >&2
    exit 0
  fi
elif https_credential_ready && git push "$PUSH_REMOTE" "HEAD:${BRANCH}"; then
  echo "land.sh: pushed ${BRANCH} to $PUSH_REMOTE" >&2
  exit 0
elif push_via_ssh; then
  echo "land.sh: HTTPS askpass unavailable; pushed ${BRANCH} via the forwarded SSH agent" >&2
  exit 0
fi

echo "land.sh: push failed — committed locally" >&2
exit 2
