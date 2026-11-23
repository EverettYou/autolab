#!/usr/bin/env bash
# Machine fingerprint — wraps detect.sh for uniform snapshot output.
set -u

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib" && pwd)/common.sh"

DETECT="$(dirname "${BASH_SOURCE[0]}")/../scripts/detect.sh"
PROFILE="$(bash "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/match_profile.sh")"

probe_note "## probe: fingerprint"
bash "$DETECT"
probe_kv "MACHINE_PROFILE" "$PROFILE"
probe_kv "fingerprint_status" "PASS"
