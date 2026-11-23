#!/usr/bin/env bash
# Dispatch GPU probe to machine-specific script (machines/probes/<profile>-gpu.sh).
set -u

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib" && pwd)/common.sh"

PROFILE="${MACHINE_PROFILE:-}"
if [[ -z "$PROFILE" ]]; then
  PROFILE="$(bash "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/match_profile.sh")"
fi

probe_script="${MACHINE_PROBES_DIR}/${PROFILE}-gpu.sh"
if [[ ! -f "$probe_script" ]]; then
  probe_script="${MACHINE_PROBES_DIR}/generic-gpu.sh"
fi

export MACHINE_PROFILE="$PROFILE"
exec bash "$probe_script"
