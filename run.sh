#!/usr/bin/env bash
# Start, stop and inspect the lab dashboard (dashboard/).
#
# Usage: ./run.sh [start|stop|restart|status|logs [-f]|foreground|check]
#
#   start       check the environment, start in the background, print a status card (default)
#   stop        stop this project's dashboard, whoever started it
#   restart     stop, then start
#   status      report whether the server runs and answers (exit 0 running, 3 stopped)
#   logs        print the end of the log; "logs -f" follows it
#   foreground  run the server in this terminal (Ctrl-C stops it)
#   check       run the environment checks only
#
# Environment: <NAME>_DASHBOARD_HOST / <NAME>_DASHBOARD_PORT override host/port
# (prefix = env_prefix(config.name), e.g. name: autolab → AUTOLAB_DASHBOARD_*).
# Fallback: LAB_DASHBOARD_HOST / LAB_DASHBOARD_PORT. Default port is hash(name)
# in 1024–65535 with linear probe; same name reclaims across checkouts.
# Only .venv/bin/python is used.
# If .venv is missing, or features.lib is on but the editable package does not
# resolve to lib/src/<package>/ (stale path, missing install), start/check/
# foreground delegate to skills/runtime-env/scripts/setup_venv.sh.
# If downloadable frontend vendor libs are missing, install_vendor.py fetches them.

set -euo pipefail
cd -- "$(dirname -- "$0")"
ROOT=$(pwd -P)
PY="$ROOT/.venv/bin/python"
STATE_DIR="$ROOT/.cache/dashboard"
PID_FILE="$STATE_DIR/process"
STATE_FILE="$STATE_DIR/dashboard.state"
LOG_FILE="$STATE_DIR/dashboard.log"
# Filled by load_config_yml from config.yml (name is required).
PROJECT_NAME=""
HOST=127.0.0.1
PORT=""
FEATURE_NOTES=0
FEATURE_LIB=0
PACKAGE_NAME=""
REQUIRED_DIRS="dashboard/frontend wiki labs skills references .auto-research"

load_config_yml() {
    [ -f "$ROOT/config.yml" ] || die "config.yml is missing (required name: <slug>)"
    local cfg_out cfg_err cfg_file
    cfg_file=$(mktemp)
    set +e
    cfg_out=$(
        ROOT="$ROOT" python3 - <<'PY' 2>"$cfg_file"
import os
import re
import sys
from pathlib import Path

root = Path(os.environ["ROOT"]).resolve()
sys.path.insert(0, str(root / "dashboard"))
from backend.project_config import (  # noqa: E402
    ConfigError,
    env_prefix,
    optional_config_port,
    project_name,
    read_config_text,
    resolve_port,
)

try:
    text = read_config_text(root)
    name = project_name(text=text)
except ConfigError as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
prefix = env_prefix(name)
notes = "true" if re.search(r"(?m)^\s*notes:\s*true\s*$", text) else "false"
lib = "true" if re.search(r"(?m)^\s*lib:\s*true\s*$", text) else "false"
package = ""
pm = re.search(r"(?m)^\s*package:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", text)
if pm and pm.group(1).lower() not in {"null", "none", "true", "false"}:
    package = pm.group(1)
override = os.environ.get(f"{prefix}_PORT") or os.environ.get("LAB_DASHBOARD_PORT")
host = os.environ.get(f"{prefix}_HOST") or os.environ.get("LAB_DASHBOARD_HOST") or "127.0.0.1"
cfg_port = optional_config_port(text)
chosen_override = None
if override not in (None, ""):
    chosen_override = int(override)
elif cfg_port is not None:
    chosen_override = cfg_port
try:
    port = resolve_port(name, host, override=chosen_override)
except ConfigError as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
print(f"PROJECT_NAME={name}")
print(f"HOST={host}")
print(f"PORT={port}")
print(f"FEATURE_NOTES={'1' if notes == 'true' else '0'}")
print(f"FEATURE_LIB={'1' if lib == 'true' else '0'}")
if package:
    print(f"PACKAGE_NAME={package}")
PY
    )
    cfg_err=$?
    set -e
    if [ "$cfg_err" -ne 0 ]; then
        err=$(cat "$cfg_file" 2>/dev/null || true)
        rm -f -- "$cfg_file"
        die "${err:-invalid config.yml / port allocation}"
    fi
    rm -f -- "$cfg_file"
    eval "$cfg_out"
    if [ "$FEATURE_NOTES" = 1 ]; then
        REQUIRED_DIRS="$REQUIRED_DIRS notes"
    fi
    if [ "$FEATURE_LIB" = 1 ]; then
        REQUIRED_DIRS="$REQUIRED_DIRS lib"
    fi
}

die() {
    printf 'run.sh: %s\n' "$*" >&2
    exit 1
}

say() {
    printf '%s\n' "$*"
}

ensure_config() {
    if [ -n "${PROJECT_NAME:-}" ] && [ -n "${PORT:-}" ]; then
        return 0
    fi
    load_config_yml
}

url() {
    case $HOST in
        0.0.0.0|'') printf 'http://127.0.0.1:%s/' "$PORT" ;;
        ::) printf 'http://[::1]:%s/' "$PORT" ;;
        *:*) printf 'http://[%s]:%s/' "$HOST" "$PORT" ;;
        *) printf 'http://%s:%s/' "$HOST" "$PORT" ;;
    esac
}

print_card() {
    status_label=$1
    code_label=$2
    pid_label=${3:-—}
    python3 - "$status_label" "$code_label" "$pid_label" "$(url)" "$PROJECT_NAME" <<'PY'
import sys
status, code, process, address, name = sys.argv[1:6]
title = f"{name} dashboard" if name else "Lab dashboard"
rows = [
    f"Status    {status}",
    f"Project   {name or '—'}",
    f"Address   {address}",
    f"Process   {process}",
    f"Code      {code}",
    "",
    "Commands  start · status · restart · stop · logs",
]
width = max([len(title) + 4, *(len(row) for row in rows)]) + 2
rule = "─" * (width - len(title) - 3)
print()
print("┌─ " + title + " " + rule + "┐")
for row in rows:
    print("│ " + row + " " * (width - len(row) - 1) + "│")
print("└" + "─" * width + "┘")
PY
}

# Exit 0 when features.lib is off, or when PACKAGE_NAME imports from lib/src/<package>/.
lib_package_ok() {
    if [ "$FEATURE_LIB" != 1 ]; then
        return 0
    fi
    if [ -z "$PACKAGE_NAME" ] || [ ! -x "$PY" ]; then
        return 1
    fi
    "$PY" - "$ROOT" "$PACKAGE_NAME" <<'PYEOF' >/dev/null 2>&1
import importlib.util
import os
import sys

root, package = sys.argv[1], sys.argv[2]
expected = os.path.realpath(os.path.join(root, "lib", "src", package))
try:
    spec = importlib.util.find_spec(package)
except (ImportError, ValueError):
    sys.exit(1)
if spec is None:
    sys.exit(1)
locations = list(spec.submodule_search_locations or [])
found = os.path.realpath(locations[0]) if locations else ""
sys.exit(0 if found == expected else 1)
PYEOF
}

ensure_venv() {
    if [ -x "$PY" ]; then
        return 0
    fi
    local setup="$ROOT/skills/runtime-env/scripts/setup_venv.sh"
    [ -f "$setup" ] || die "$PY is missing and $setup is not available to recreate it."
    say "Repository .venv is missing; delegating to skills/runtime-env/scripts/setup_venv.sh…"
    bash "$setup" || die "failed to create the repository virtualenv"
    [ -x "$PY" ] || die "$PY is still missing after setup_venv.sh"
}

ensure_vendor() {
    local installer="$ROOT/dashboard/frontend/vendor/install_vendor.py"
    [ -f "$installer" ] || die "missing $installer"
    # Prefer repo .venv when present — PATH python3 can be a broken wrapper.
    local boot_py=""
    if [ -x "$PY" ]; then
        boot_py="$PY"
    elif command -v python3 >/dev/null 2>&1; then
        boot_py=$(command -v python3)
    else
        die "no python available to run $installer"
    fi
    if "$boot_py" "$installer" --check >/dev/null 2>&1; then
        return 0
    fi
    say "Frontend vendor libraries missing or incomplete; installing…"
    "$boot_py" "$installer" || die "failed to install dashboard frontend vendor libraries"
    "$boot_py" "$installer" --check >/dev/null 2>&1 \
        || die "vendor still incomplete after install_vendor.py"
}

check_python() {
    ensure_venv
    ensure_vendor
    "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
        || die "$PY is not Python 3.11 or newer."
}

check_package() {
    if [ "$FEATURE_LIB" != 1 ]; then
        return 0
    fi
    if [ -z "$PACKAGE_NAME" ]; then
        die "features.lib is true but config.yml has no package: <name>"
    fi
    if lib_package_ok; then
        return 0
    fi
    # Stale .venv is common after platform/ → lib/ renames or a partial setup:
    # interpreter exists so ensure_venv no-ops, but the editable install is wrong.
    local setup="$ROOT/skills/runtime-env/scripts/setup_venv.sh"
    [ -f "$setup" ] || die "editable package $PACKAGE_NAME is missing or does not resolve to lib/ and $setup is not available to recreate it."
    say "editable package $PACKAGE_NAME is missing or does not resolve to lib/; delegating to skills/runtime-env/scripts/setup_venv.sh…"
    bash "$setup" || die "failed to repair the repository virtualenv"
    lib_package_ok || die "editable package $PACKAGE_NAME still missing or not resolving to lib/ after setup_venv.sh"
}

check_dirs() {
    local dir
    for dir in $REQUIRED_DIRS; do
        [ -d "$ROOT/$dir" ] || die "required folder $dir/ is missing under $ROOT"
    done
    [ -f "$ROOT/wiki/README.md" ] || die "wiki/README.md is missing"
    [ -f "$ROOT/.auto-research/README.md" ] || die ".auto-research/README.md is missing"
    [ -f "$ROOT/dashboard/server.py" ] || die "dashboard/server.py is missing"
    [ -n "$PROJECT_NAME" ] || die "config.yml name: <slug> is required"
}

seed_local() {
    "$PY" - <<'PY'
from pathlib import Path
import sys
root = Path('.').resolve()
sys.path.insert(0, str(root / 'skills' / 'auto-research' / 'scripts'))
from seed_local import seed_local_files
seed_local_files(root)
from dashboard.backend.catalog import catalog
catalog()
PY
}

check_env() {
    check_python
    ensure_config
    check_package
    # Seed missing state.json before check_dirs (README contracts come from git/sync).
    seed_local
    check_dirs
    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
        die "dashboard port must be from 1 to 65535"
    fi
}

process_started() {
    local state
    state=$(ps -p "$1" -o stat=) || return 1
    [[ -n "$state" && "$state" != Z* ]] || return 1
    ps -p "$1" -o lstart=
}

read_process() {
    [[ -f "$PID_FILE" ]] || return 1
    IFS= read -r pid < "$PID_FILE" || return 1
    started=$(sed -n '2p' "$PID_FILE")
    running_port=$(sed -n '3p' "$PID_FILE")
    [[ "$pid" =~ ^[0-9]+$ && "$pid" -gt 1 && "$running_port" =~ ^[0-9]+$ && -n "$started" ]]
}

is_current() {
    [[ "$(process_started "$pid" 2>/dev/null || true)" == "$started" ]]
}

# Print the pid when this *project name* holds the port (any checkout).
# Exit 0: this project. Exit 1: nothing is listening. Exit 2: something else.
project_listener() {
    "$PY" - "$HOST" "$PORT" "$PROJECT_NAME" "$ROOT" <<'PYEOF'
import sys
from pathlib import Path

host, port, name = sys.argv[1], int(sys.argv[2]), sys.argv[3]
root = Path(sys.argv[4])
sys.path.insert(0, str(root / "dashboard"))
from backend.project_config import health_listener, port_occupancy

kind = port_occupancy(host, port, name)
if kind == "free":
    sys.exit(1)
if kind == "ours":
    pid = health_listener(host, port, name)
    if pid is None:
        sys.exit(2)
    print(pid)
    sys.exit(0)
sys.exit(2)
PYEOF
}

wait_gone() {
    local tries=0
    while kill -0 "$1" 2>/dev/null; do
        tries=$((tries + 1))
        [ "$tries" -le 50 ] || return 1
        sleep 0.15
    done
    return 0
}

stop_process() {
    kill -TERM "$1" 2>/dev/null || true
    if ! wait_gone "$1"; then
        kill -KILL "$1" 2>/dev/null || true
        wait_gone "$1" || return 1
    fi
    return 0
}

health_pid() {
    "$PY" - "$1" <<'PY' 2>/dev/null || true
import json, sys, urllib.request
port = sys.argv[1]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
        raw = response.read().decode()
except Exception:
    sys.exit(0)
try:
    data = json.loads(raw)
except Exception:
    print(raw.strip())
    sys.exit(0)
pid = data.get("pid")
if isinstance(pid, int):
    print(pid)
PY
}

dashboard_fingerprint() {
    (cd "$ROOT/dashboard" && find . -type f -name '*.py' -print | sort | while IFS= read -r path; do
        sha1sum "$path"
    done) | sha1sum | awk '{print $1}'
}

saved_fingerprint() {
    [[ -f "$STATE_FILE" ]] || return 1
    sed -n 's/^fingerprint=//p' "$STATE_FILE" | sed -n '1p'
}

fingerprint_current() {
    saved=$(saved_fingerprint || true)
    [[ -n "$saved" && "$saved" == "$(dashboard_fingerprint)" ]]
}

write_state() {
    mkdir -p "$STATE_DIR"
    printf 'fingerprint=%s\n' "$(dashboard_fingerprint)" >"$STATE_FILE"
}

clear_state() {
    rm -f -- "$PID_FILE" "$STATE_FILE"
}

start() {
    check_env
    local status=0 holder=""
    holder=$(project_listener) || status=$?
    case $status in
        0)
            if read_process && [[ "$pid" == "$holder" ]] && fingerprint_current && is_current; then
                print_card "RUNNING" "current" "PID $pid"
                return
            fi
            say "Taking over previous lab dashboard (PID $holder)…"
            stop_process "$holder" || {
                print_card "FAILED" "process did not stop" "PID $holder" >&2
                return 1
            }
            clear_state
            ;;
        1) ;;
        *)
            print_card "UNAVAILABLE" "port $PORT is already in use by another process" "—" >&2
            return 1
            ;;
    esac
    if read_process && is_current; then
        stop_process "$pid" || die "pid $pid did not stop"
        clear_state
    fi
    mkdir -p "$STATE_DIR"
    printf '\n== %s start ==\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >>"$LOG_FILE"
    nohup "$PY" -m dashboard.server --host "$HOST" --port "$PORT" --root "$ROOT" </dev/null >>"$LOG_FILE" 2>&1 &
    pid=$!
    started=$(process_started "$pid" 2>/dev/null || true)
    for ((attempt = 0; attempt < 50; attempt++)); do
        [[ -n "$started" ]] && is_current || break
        if [[ "$(health_pid "$PORT")" == "$pid" ]]; then
            printf '%s\n%s\n%s\n' "$pid" "$started" "$PORT" > "$PID_FILE"
            write_state
            print_card "RUNNING" "current" "PID $pid"
            return
        fi
        sleep 0.15
    done
    if [[ -n "$started" ]] && is_current; then kill "$pid" 2>/dev/null || true; fi
    print_card "FAILED" "see $LOG_FILE" "—" >&2
    tail -12 "$LOG_FILE" >&2 || true
    return 1
}

status() {
    ensure_config
    local status=0 holder=""
    if [[ -x "$PY" ]]; then
        holder=$(project_listener) || status=$?
    else
        status=1
    fi
    case $status in
        0)
            if fingerprint_current && read_process && [[ "$pid" == "$holder" ]]; then
                print_card "RUNNING" "current" "PID $holder"
                return 0
            fi
            print_card "STALE" "previous dashboard instance — run ./run.sh start to take over" "PID $holder"
            return 1
            ;;
        2)
            print_card "UNAVAILABLE" "port $PORT is already in use by another process" "—" >&2
            return 1
            ;;
    esac
    print_card "STOPPED" "not running" "—"
    return 3
}

stop() {
    ensure_config
    local status=0 holder=""
    if read_process && is_current; then
        stop_process "$pid" || die "pid $pid did not stop"
        clear_state
        print_card "STOPPED" "not running" "—"
        return 0
    fi
    holder=$(project_listener) || status=$?
    if [[ $status -eq 0 ]]; then
        say "Stopping lab dashboard (PID $holder)…"
        stop_process "$holder" || die "pid $holder did not stop"
        clear_state
        print_card "STOPPED" "not running" "—"
        return 0
    fi
    clear_state
    print_card "STOPPED" "not running" "—"
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    logs)
        if [[ ! -f "$LOG_FILE" ]]; then
            printf 'No dashboard log yet.\n'
        elif [[ ${2:-} == -f ]]; then
            tail -f "$LOG_FILE"
        else
            tail -n 40 "$LOG_FILE"
        fi
        ;;
    foreground) check_env; exec "$PY" -m dashboard.server --host "$HOST" --port "$PORT" --root "$ROOT" ;;
    check) check_env; printf 'Dashboard configuration is valid.\n' ;;
    -h|--help|help) printf 'Usage: %s [start|stop|restart|status|logs [-f]|foreground|check]\n' "$0" ;;
    *) printf 'Usage: %s [start|stop|restart|status|logs [-f]|foreground|check]\n' "$0" >&2; exit 2 ;;
esac
