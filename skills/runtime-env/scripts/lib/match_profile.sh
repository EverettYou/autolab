#!/usr/bin/env bash
# Emit machine profile id (stdout) from read-only signals. No side effects.
set -u

_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=profile_signals.sh
source "$_LIB_DIR/profile_signals.sh"
profile_match_id
