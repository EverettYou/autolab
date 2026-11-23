#!/usr/bin/env bash
# Parse a task "time" tier to seconds (the reproduction cap is min(2 * seconds, cap)).
# Usage: parse_time.sh <tier>   → prints seconds to stdout; exit 1 if unknown.
set -euo pipefail

tier="${1:?tier required}"

case "$tier" in
  0)     echo 0 ;;
  1min)  echo 60 ;;
  5min)  echo 300 ;;
  15min) echo 900 ;;
  30min) echo 1800 ;;
  1hr)   echo 3600 ;;
  2hr)   echo 7200 ;;
  4hr)   echo 14400 ;;
  8hr)   echo 28800 ;;
  1d)    echo 86400 ;;
  2d)    echo 172800 ;;
  *)
    echo "parse_time: unknown tier '$tier'" >&2
    exit 1
    ;;
esac
