#!/usr/bin/env bash
# Git remote + SSH agent — integrate / land / clone preflight.
set -u

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib" && pwd)/common.sh"

PROBE_STATUS="PASS"
GIT_TIMEOUT="${GIT_TIMEOUT:-10}"

probe_note "## probe: git_ssh"

if [[ -n "${SSH_AUTH_SOCK:-}" ]]; then
  probe_kv "ssh_agent_sock" "present"
  probe_note "ssh_agent: present"
  if ssh-add -l >/dev/null 2>&1; then
    key_count="$(ssh-add -l 2>/dev/null | wc -l | tr -d ' ')"
    probe_kv "ssh_agent_keys" "$key_count"
    probe_note "ssh_agent_keys: ${key_count}"
  else
    probe_set_status WARN
    probe_kv "ssh_agent_keys" "0"
    probe_note "WARN: SSH_AUTH_SOCK set but no keys loaded (ssh-add -l failed)"
  fi
else
  probe_kv "ssh_agent_sock" "absent"
  probe_note "ssh_agent: absent (HTTPS git may still work)"
fi

if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  origin="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || echo "none")"
  probe_kv "git_origin_url" "$origin"
  probe_note "git_origin: ${origin}"
  if [[ "$origin" != "none" ]]; then
    if run_with_timeout "$GIT_TIMEOUT" git -C "$REPO_ROOT" ls-remote --heads origin >/dev/null 2>&1; then
      probe_kv "git_origin_reachable" "PASS"
      probe_note "git_origin_reachable: PASS"
    else
      probe_set_status WARN
      probe_kv "git_origin_reachable" "FAIL"
      probe_note "WARN: git ls-remote origin failed"
    fi
  fi
else
  probe_set_status WARN
  probe_note "WARN: not a git work tree at REPO_ROOT"
fi

probe_kv "git_ssh_status" "$PROBE_STATUS"
