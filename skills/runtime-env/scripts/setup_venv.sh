#!/usr/bin/env bash
# Create / refresh the canonical lab venv (./.venv) for core development.
# Idempotent. Default: inherit host/container site-packages via --system-site-packages
# and install only what the baseline does not already satisfy (prefer the baseline).
# Host + Docker/Podman: refuses (POLICY_REPO_VENV=require-container) — enter a container.
# Escape hatches: SETUP_VENV_ISOLATED=1 (clean isolated venv); SETUP_VENV_ALLOW_HOST=1
# (force install on a docker-capable host control plane).
#
# Installer preference: ``uv`` when on PATH; otherwise standard ``python3 -m venv`` + ``pip``.
#
# Single source of truth for *what* is required when features.lib is on: lib/pyproject.toml.
# Single source of truth for *versions already present*: the host or container baseline.
#
# Before the editable install (features.lib on): any native extension built during
# ``pip install -e lib`` needs Python.h. Cause is *interpreter packaging* (runtime Python
# without pythonX.Y-dev), not the host GPU and not any particular lab package. Decision tree:
#   1) interpreter include already has Python.h → done
#   2) C_INCLUDE_PATH / CPLUS_INCLUDE_PATH already points at Python.h → export/keep
#   3) same-minor uv-managed CPython headers already on disk → export those
#   4) may install OS pythonX.Y-dev (apt + root/passwordless sudo) → install, recheck
#   5) uv on PATH → ``uv python install <minor>`` and export its include dir
#   6) else fail with the concrete missing piece
# A shim written *after* the editable install cannot help that build.
#
# After install, if the venv interpreter still lacks Python.h but uv-managed headers exist,
# write a generic ``_venv_python_header_shim`` .pth so later processes (e.g. torch.compile /
# inductor gcc) see the same include path. Lab-specific bootstraps (CPU guards, package
# hooks) belong in the lab package, not here.
#
# this template default: features.lib false → venv for dashboard/skills only (no editable package).
# For foreign reproductions with conflicting pins, see references/venv-baseline.md.
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$_SCRIPT_DIR/../../.." && pwd)"
LIB="$ROOT/lib"
# Override with SETUP_VENV_DIR for dry-runs; default is the canonical repo .venv.
VENV="${SETUP_VENV_DIR:-$ROOT/.venv}"
PY="$VENV/bin/python"

# shellcheck source=lib/resolve_policy.sh
source "$_SCRIPT_DIR/lib/resolve_policy.sh"

HAVE_UV=0
if command -v uv >/dev/null 2>&1; then
  HAVE_UV=1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[setup_venv] python3 not found on PATH" >&2
  exit 1
fi

# Pick a host interpreter for the stdlib venv path. Prefer SETUP_VENV_PYTHON; otherwise the
# newest python3.X on PATH that satisfies lib/pyproject.toml requires-python (macOS /usr/bin
# python3 is often too old). uv path keeps using ``python3`` so curated images stay pinned.
resolve_host_python() {
  if [ -n "${SETUP_VENV_PYTHON:-}" ]; then
    if [ ! -x "$SETUP_VENV_PYTHON" ]; then
      echo "[setup_venv] SETUP_VENV_PYTHON is not executable: $SETUP_VENV_PYTHON" >&2
      exit 1
    fi
    printf '%s' "$SETUP_VENV_PYTHON"
    return
  fi
  python3 - "$LIB/pyproject.toml" <<'PY'
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

pyproject = Path(sys.argv[1])
text = pyproject.read_text(encoding="utf-8")
m = re.search(r'(?m)^\s*requires-python\s*=\s*"([^"]+)"\s*$', text)
spec = m.group(1) if m else ">=3.11"

def ok(ver: tuple[int, int]) -> bool:
    # Tiny subset of PEP 440 used in this repo (>=X.Y, >=X.Y.Z).
    for part in (p.strip() for p in spec.split(",")):
        mm = re.fullmatch(r"(>=|>|<=|<|==)\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", part)
        if not mm:
            return ver >= (3, 11)
        op, major, minor, patch = mm.group(1), int(mm.group(2)), int(mm.group(3) or 0), int(mm.group(4) or 0)
        target = (major, minor)
        # Ignore patch for interpreter picking; CPython minors are what matter.
        if op == ">=" and not (ver >= target):
            return False
        if op == ">" and not (ver > target):
            return False
        if op == "<=" and not (ver <= target):
            return False
        if op == "<" and not (ver < target):
            return False
        if op == "==" and ver != target:
            return False
    return True

candidates: list[str] = []
for name in (
    "python3.14", "python3.13", "python3.12", "python3.11", "python3",
):
    path = shutil.which(name)
    if path and path not in candidates:
        candidates.append(path)
# Also walk common framework locations when PATH was stripped (CI / dry-run).
for extra in (
    "/usr/local/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
    "/opt/homebrew/bin/python3",
):
    if os.path.isfile(extra) and os.access(extra, os.X_OK) and extra not in candidates:
        candidates.append(extra)

best = None
best_ver = (-1, -1)
for path in candidates:
    try:
        out = subprocess.check_output(
            [path, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            text=True,
        ).strip()
        major, minor = (int(x) for x in out.split(".", 1))
    except (OSError, subprocess.CalledProcessError, ValueError):
        continue
    ver = (major, minor)
    if not ok(ver):
        continue
    if ver > best_ver:
        best, best_ver = path, ver

if best is None:
    print(
        f"[setup_venv] no host Python satisfies requires-python {spec!r}; "
        "install Python 3.11+ or set SETUP_VENV_PYTHON",
        file=sys.stderr,
    )
    sys.exit(1)
print(best)
PY
}

# Create $VENV (uses USE_SYSTEM from the caller).
# Always pin the host interpreter explicitly: bare ``uv venv --python python3`` can pick a
# uv-managed CPython whose site-packages are empty, so --system-site-packages inherits nothing.
create_venv() {
  HOST_PYTHON="$(resolve_host_python)"
  echo "[setup_venv] host_python=$HOST_PYTHON ($("$HOST_PYTHON" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}")'))"
  if [ "$HAVE_UV" = 1 ]; then
    if [ "$USE_SYSTEM" = true ]; then
      echo "[setup_venv] uv venv --python $HOST_PYTHON --system-site-packages $VENV  (inherit baseline for $RUNTIME_CAPABILITY)"
      uv venv --python "$HOST_PYTHON" --system-site-packages "$VENV"
    else
      echo "[setup_venv] uv venv --python $HOST_PYTHON $VENV  (isolated install for $RUNTIME_CAPABILITY)"
      uv venv --python "$HOST_PYTHON" "$VENV"
    fi
  else
    if [ "$USE_SYSTEM" = true ]; then
      echo "[setup_venv] $HOST_PYTHON -m venv --system-site-packages $VENV  (inherit baseline for $RUNTIME_CAPABILITY; no uv)"
      "$HOST_PYTHON" -m venv --system-site-packages "$VENV"
    else
      echo "[setup_venv] $HOST_PYTHON -m venv $VENV  (isolated install for $RUNTIME_CAPABILITY; no uv)"
      "$HOST_PYTHON" -m venv "$VENV"
    fi
    if ! "$PY" -m pip --version >/dev/null 2>&1; then
      echo "[setup_venv] bootstrapping pip via ensurepip"
      "$PY" -m ensurepip --upgrade
    fi
    "$PY" -m pip install --upgrade pip
  fi
}

# pip_install [pip-args…] — uv pip when available, else python -m pip.
pip_install() {
  if [ "$HAVE_UV" = 1 ]; then
    uv pip install --python "$PY" "$@"
  else
    "$PY" -m pip install "$@"
  fi
}

# True when $PY's sysconfig include dir already contains Python.h.
_python_h_in_interpreter_include() {
  "$PY" -c 'import os, sysconfig; p = sysconfig.get_path("include"); raise SystemExit(0 if os.path.isfile(os.path.join(p, "Python.h")) else 1)'
}

# Print a directory that already has Python.h, or empty. Modes: env | uv-existing
# (search only; never installs).
_find_python_h_dir() {
  local mode="$1"
  "$PY" - "$mode" <<'PY'
import glob
import os
import subprocess
import sys

mode = sys.argv[1]
ver = "%d.%d" % sys.version_info[:2]


def from_env() -> str:
    for var in ("C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH"):
        for part in os.environ.get(var, "").split(os.pathsep):
            if part and os.path.isfile(os.path.join(part, "Python.h")):
                return part
    return ""


def from_uv_disk() -> str:
    roots: list[str] = []
    env_dir = os.environ.get("UV_PYTHON_INSTALL_DIR", "").strip()
    if env_dir:
        roots.append(env_dir)
    try:
        out = subprocess.check_output(
            ["uv", "python", "dir"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        out = ""
    if out:
        roots.append(out)
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    roots.append(os.path.join(data_home, "uv", "python"))
    seen: set[str] = set()
    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        matches = sorted(
            (
                d
                for d in glob.glob(os.path.join(root, f"cpython-{ver}*", "include", f"python{ver}"))
                if os.path.isfile(os.path.join(d, "Python.h"))
            ),
            reverse=True,
        )
        if matches:
            return matches[0]
    return ""


if mode == "env":
    print(from_env())
elif mode == "uv-existing":
    print(from_uv_disk())
else:
    raise SystemExit(f"unknown mode {mode!r}")
PY
}

# Export dir onto C_INCLUDE_PATH / CPLUS_INCLUDE_PATH for this process + build subprocesses.
_export_python_h_dir() {
  local header_dir="$1"
  local reason="$2"
  [ -n "$header_dir" ] || return 0
  echo "[setup_venv] using Python.h via $reason: $header_dir"
  case ":${C_INCLUDE_PATH:-}:" in
    *":${header_dir}:"*) ;;
    *) C_INCLUDE_PATH="${header_dir}${C_INCLUDE_PATH:+:${C_INCLUDE_PATH}}"; export C_INCLUDE_PATH ;;
  esac
  case ":${CPLUS_INCLUDE_PATH:-}:" in
    *":${header_dir}:"*) ;;
    *) CPLUS_INCLUDE_PATH="${header_dir}${CPLUS_INCLUDE_PATH:+:${CPLUS_INCLUDE_PATH}}"; export CPLUS_INCLUDE_PATH ;;
  esac
}

# True when we may non-interactively install Debian/Ubuntu pythonX.Y-dev.
_can_apt_install_python_dev() {
  command -v apt-get >/dev/null 2>&1 || return 1
  if [ "$(id -u)" = 0 ]; then
    return 0
  fi
  if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

_apt_install_python_dev() {
  local ver="$1"
  local pkg="python${ver}-dev"
  echo "[setup_venv] cause=missing Python.h; branch=os-dev-package ($pkg)"
  if [ "$(id -u)" = 0 ]; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$pkg"
  else
    sudo -n apt-get update -qq
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$pkg"
  fi
}

# Ensure Python.h is visible for a native-extension editable build. Branches on the real
# cause (interpreter packaging / env / OS package rights / uv), not on lab or GPU identity.
ensure_python_headers() {
  echo "[setup_venv] checking Python.h for the Cython extension build"
  local ver include header_dir
  ver="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  include="$("$PY" -c 'import sysconfig; print(sysconfig.get_path("include"))')"

  # Branch 1: the interpreter we build against already ships headers.
  if _python_h_in_interpreter_include; then
    echo "[setup_venv] Python.h ok at $include"
    return 0
  fi
  echo "[setup_venv] cause=missing Python.h under $include (needed if lib/ builds a native extension)"

  # Branch 2: caller / prior process already put headers on the include path.
  header_dir="$(_find_python_h_dir env)"
  if [ -n "$header_dir" ]; then
    _export_python_h_dir "$header_dir" "C_INCLUDE_PATH/CPLUS_INCLUDE_PATH"
    return 0
  fi

  # Branch 3: same-minor uv-managed headers already on disk (no download).
  header_dir="$(_find_python_h_dir uv-existing)"
  if [ -n "$header_dir" ]; then
    _export_python_h_dir "$header_dir" "existing uv-managed CPython $ver"
    return 0
  fi

  # Branch 4: fix the interpreter packaging itself when apt rights allow.
  if _can_apt_install_python_dev; then
    if _apt_install_python_dev "$ver"; then
      if _python_h_in_interpreter_include; then
        echo "[setup_venv] Python.h restored at $include via python${ver}-dev"
        return 0
      fi
      echo "[setup_venv] WARNING: python${ver}-dev installed but $include still has no Python.h" >&2
    else
      echo "[setup_venv] WARNING: python${ver}-dev install failed; trying other branches" >&2
    fi
  else
    echo "[setup_venv] branch=os-dev-package skipped (no apt-get, or not root / passwordless sudo)"
  fi

  # Branch 5: fetch ABI-compatible headers via uv-managed CPython of the same minor.
  if [ "$HAVE_UV" = 1 ]; then
    echo "[setup_venv] branch=uv-managed-headers (uv python install $ver)"
    if ! uv python install "$ver" >&2; then
      echo "[setup_venv] ERROR: uv python install $ver failed while $include lacks Python.h." >&2
      echo "[setup_venv] Install python${ver}-dev, or export C_INCLUDE_PATH to a dir with Python.h." >&2
      return 1
    fi
    header_dir="$(_find_python_h_dir uv-existing)"
    if [ -n "$header_dir" ]; then
      _export_python_h_dir "$header_dir" "uv-managed CPython $ver"
      return 0
    fi
    echo "[setup_venv] ERROR: uv python install $ver finished but no Python.h was found." >&2
    return 1
  fi

  # Branch 6: nothing left that can supply headers.
  echo "[setup_venv] ERROR: no Python.h for CPython $ver and no remaining fix:" >&2
  echo "  - install python${ver}-dev (needs apt + root or passwordless sudo), or" >&2
  echo "  - install uv and re-run (uv python install $ver), or" >&2
  echo "  - export C_INCLUDE_PATH to a $ver include directory that contains Python.h" >&2
  return 1
}

# If the venv interpreter still lacks Python.h but same-minor uv headers exist, expose them
# at interpreter startup (generic; not lab-specific). Idempotent on rebuild.
write_python_header_shim() {
  local site ver venv_inc uv_py_dir header_glob
  site="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  ver="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  venv_inc="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')"
  # Drop legacy lab-named shims and the current generic one before rewriting.
  rm -f \
    "$site/_venv_python_header_shim.py" "$site/_venv_python_header_shim.pth" \
    "$site/_qeclab_header_shim.py" "$site/_qeclab_header_shim.pth" \
    "$site/qec_cpu_guard_boot.py" "$site/qec-cpu-guard.pth"

  if [ -f "$venv_inc/Python.h" ]; then
    return 0
  fi

  uv_py_dir=""
  if [ "$HAVE_UV" = 1 ]; then
    uv_py_dir="$(uv python dir 2>/dev/null || true)"
  fi
  header_glob="$uv_py_dir/cpython-$ver*/include/python$ver"
  if [ -n "$uv_py_dir" ] && compgen -G "$header_glob/Python.h" >/dev/null; then
    echo "[setup_venv] $venv_inc lacks Python.h; writing header shim -> $header_glob"
    cat >"$site/_venv_python_header_shim.py" <<EOF
"""Venv shim — expose uv-managed CPython headers on C_INCLUDE_PATH at startup.

Written by skills/runtime-env/scripts/setup_venv.sh when this venv's interpreter lacks Python.h
(no python$ver-dev) but a same-minor uv-managed build has headers. Later gcc subprocesses
(native extension rebuilds, torch.compile/inductor helpers, …) can find <Python.h>. Loaded from
_venv_python_header_shim.pth. Rebuilding the venv regenerates or removes it.
"""
import glob
import os

_UV_GLOB = "$header_glob"


def _apply() -> None:
    inc = next(
        (
            d
            for d in sorted(glob.glob(_UV_GLOB), reverse=True)  # highest concrete version first
            if os.path.isfile(os.path.join(d, "Python.h"))
        ),
        None,
    )
    if not inc:
        return
    for var in ("C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH"):
        cur = os.environ.get(var, "")
        if inc not in cur.split(os.pathsep):
            os.environ[var] = inc + (os.pathsep + cur if cur else "")


try:
    _apply()
except Exception:  # never let a startup shim break the interpreter
    pass
EOF
    echo "import _venv_python_header_shim" >"$site/_venv_python_header_shim.pth"
  else
    echo "[setup_venv] WARNING: no Python.h for $ver (install python$ver-dev); native C builds in later processes may fail" >&2
  fi
}

if [ ! -f "$LIB/pyproject.toml" ]; then
  echo "[setup_venv] missing lib/pyproject.toml under $ROOT" >&2
  exit 1
fi

# Read optional lib enable + package name from config.yml (template defaults: off / null).
FEATURE_LIB=0
PACKAGE_NAME=""
if [ -f "$ROOT/config.yml" ]; then
  eval "$(python3 - "$ROOT/config.yml" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
def grab(pattern, default=""):
    m = re.search(pattern, text, re.M)
    return m.group(1) if m else default
lib = grab(r"(?m)^\s*lib:\s*(true|false)\s*$", "false")
package = grab(r"(?m)^\s*package:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", "")
if package.lower() in {"null", "none", "true", "false"}:
    package = ""
print(f'FEATURE_LIB={"1" if lib == "true" else "0"}')
if package:
    print(f'PACKAGE_NAME={package}')
PY
)"
fi

INSTALL_LIB=0
if [ "$FEATURE_LIB" = 1 ]; then
  if [ -z "$PACKAGE_NAME" ]; then
    echo "[setup_venv] features.lib is true but config.yml has no package: <name>" >&2
    exit 1
  fi
  if [ ! -d "$LIB/src/$PACKAGE_NAME" ]; then
    echo "[setup_venv] missing lib/src/$PACKAGE_NAME/ (enable lib only after the package exists)" >&2
    exit 1
  fi
  INSTALL_LIB=1
fi

resolve_policy
echo "[setup_venv] root=$ROOT"
echo "[setup_venv] runtime_capability=$RUNTIME_CAPABILITY"
echo "[setup_venv] policy_isolation=$POLICY_ISOLATION untrusted=$POLICY_UNTRUSTED_CODE repo_venv=$POLICY_REPO_VENV"
echo "[setup_venv] features.lib=$FEATURE_LIB package=${PACKAGE_NAME:-(none)}"
if [ "$HAVE_UV" = 1 ]; then
  echo "[setup_venv] installer=uv ($(command -v uv))"
else
  echo "[setup_venv] installer=pip (uv not on PATH; using python3 -m venv + pip)"
fi

# Host + docker/podman: refuse to build the canonical .venv on the control plane.
# Bare hosts (no container runtime) may still install here; containers install in-place.
# Escape hatch: SETUP_VENV_ALLOW_HOST=1 (local override / recovery only).
if [ "${POLICY_REPO_VENV:-here}" = "require-container" ]; then
  if [ "${SETUP_VENV_ALLOW_HOST:-0}" = "1" ] || [ "${SETUP_VENV_ALLOW_HOST:-}" = "true" ]; then
    echo "[setup_venv] WARN: POLICY_REPO_VENV=require-container but SETUP_VENV_ALLOW_HOST is set — installing on the host anyway" >&2
  else
    cat >&2 <<EOF
[setup_venv] refused: this shell is on the host, and Docker/Podman is available
  capability=${RUNTIME_CAPABILITY}
  isolation=${POLICY_ISOLATION}
  repo_venv=${POLICY_REPO_VENV}
Building ./.venv here would pollute the host control plane. Enter a lab/research
container (where the curated baseline already lives) and re-run:
  bash skills/runtime-env/scripts/setup_venv.sh
Override only if you intentionally want a host-side venv:
  SETUP_VENV_ALLOW_HOST=1 bash skills/runtime-env/scripts/setup_venv.sh
See skills/runtime-env/references/isolation-boundaries.md
EOF
    exit 1
  fi
fi

if [ -d "$VENV" ]; then
  echo "[setup_venv] removing existing $VENV"
  rm -rf "$VENV"
fi

# Prefer inherit-baseline from resolve_policy; SETUP_VENV_ISOLATED always wins.
USE_SYSTEM=true
if [ "$POLICY_VENV_MODE" = "isolated" ] \
  || [ "${SETUP_VENV_ISOLATED:-0}" = "1" ] \
  || [ "${SETUP_VENV_ISOLATED:-}" = "true" ]; then
  USE_SYSTEM=false
  echo "[setup_venv] isolated mode — building venv without system-site-packages"
fi
if [ "$USE_SYSTEM" = true ]; then
  echo "[setup_venv] mode=inherit-baseline (capability=$RUNTIME_CAPABILITY; --system-site-packages)"
else
  echo "[setup_venv] mode=isolated (capability=$RUNTIME_CAPABILITY; no system-site-packages)"
fi

create_venv

# Always need pytest/dev tooling available for skills; when lib is off, install pytest only.
if [ "$INSTALL_LIB" != 1 ]; then
  echo "[setup_venv] features.lib off — installing dashboard/skills deps (pytest) only"
  pip_install pytest
else
  # Native extensions in lib/ need Python.h visible to this process (and build subprocesses).
  ensure_python_headers
  echo "[setup_venv] pip install -e lib --no-deps"
  pip_install -e "$LIB" --no-deps

  if [ "$USE_SYSTEM" = true ]; then
    if ! "$PY" -c 'import packaging' >/dev/null 2>&1; then
      echo "[setup_venv] installing packaging (needed to walk lib/pyproject.toml against the baseline)"
      pip_install packaging
    fi
    echo "[setup_venv] preferring baseline packages that already satisfy lib/pyproject.toml"
    export SETUP_VENV_INSTALLER
    if [ "$HAVE_UV" = 1 ]; then
      SETUP_VENV_INSTALLER=uv
    else
      SETUP_VENV_INSTALLER=pip
    fi
    if ! "$PY" - "$LIB/pyproject.toml" <<'PY'
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

pyproject = Path(sys.argv[1])
data = tomllib.loads(pyproject.read_text())
queue: list[str] = list(data["project"].get("dependencies", []))
for extra in ("dev",):
    queue.extend(data["project"].get("optional-dependencies", {}).get(extra, []))

def installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None

def satisfied(raw: str) -> bool:
    req = Requirement(raw)
    if req.marker is not None and not req.marker.evaluate():
        return True
    ver = installed_version(req.name)
    if ver is None:
        return False
    return (ver in req.specifier) if req.specifier else True

def log(msg: str = "") -> None:
    print(msg, flush=True)

def install_no_deps(raw: str) -> None:
    installer = os.environ.get("SETUP_VENV_INSTALLER", "uv")
    if installer == "uv":
        cmd = ["uv", "pip", "install", "--python", sys.executable, "--no-deps", raw]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--no-deps", raw]
    log(f"[setup_venv] {' '.join(cmd[:-1])} {raw}")
    subprocess.check_call(cmd, env=os.environ.copy())

log("[setup_venv] direct deps vs baseline:")
for raw in list(queue):
    req = Requirement(raw)
    ver = installed_version(req.name)
    if satisfied(raw):
        log(f"  keep     {raw}  (baseline {ver})")
    elif ver is None:
        log(f"  install  {raw}  (not in baseline)")
    else:
        log(f"  shadow   {raw}  (baseline {ver} does not satisfy)")

seen: set[str] = set()
installed_into_venv: list[str] = []
while queue:
    raw = queue.pop(0)
    req = Requirement(raw)
    key = canonicalize_name(req.name)
    if key in seen:
        continue
    if req.marker is not None and not req.marker.evaluate():
        seen.add(key)
        continue
    if satisfied(raw):
        seen.add(key)
        continue
    seen.add(key)
    install_no_deps(raw)
    installed_into_venv.append(raw)
    dist = metadata.distribution(req.name)
    for parent in dist.requires or []:
        child = Requirement(parent)
        if child.marker is not None and not child.marker.evaluate():
            continue
        queue.append(parent)

if installed_into_venv:
    log(f"[setup_venv] installed into venv ({len(installed_into_venv)}):")
    for raw in installed_into_venv:
        log(f"  {raw}")
else:
    log("[setup_venv] baseline already satisfies all lib[dev] deps; nothing else to install")
PY
    then
      echo "[setup_venv] ERROR: failed to layer missing deps onto the baseline" >&2
      exit 1
    fi
  else
    echo "[setup_venv] isolated mode; pip install -e \"lib[dev]\""
    pip_install -e "$LIB[dev]"
  fi
fi

# Prefer having uv inside the repo venv for later agent commands; optional on bare metal.
if [ ! -x "$VENV/bin/uv" ]; then
  if [ "$HAVE_UV" = 1 ]; then
    echo "[setup_venv] ensure uv is available inside repo base venv"
    pip_install uv
  else
    echo "[setup_venv] skipping uv bootstrap inside venv (host has no uv; pip is enough)"
  fi
fi

write_python_header_shim

echo "[setup_venv] verifying stack"
"$PY" - "$ROOT" "$INSTALL_LIB" "${PACKAGE_NAME:-}" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
install_lib = sys.argv[2] == "1"
package = sys.argv[3] or None

try:
    import numpy as np
    print(f"  numpy       {np.__version__}  ({np.__file__})")
except ImportError:
    print("  numpy       (not installed — ok when features.lib is off)")

try:
    import scipy
    print(f"  scipy       {scipy.__version__}  ({scipy.__file__})")
except ImportError:
    print("  scipy       (not installed — ok when features.lib is off)")

try:
    import torch
    print(f"  torch       {torch.__version__}  (cuda={torch.cuda.is_available()}, ndev={torch.cuda.device_count()})")
except ImportError:
    print("  torch       (optional)")

try:
    import jax
    import jaxlib
    print(f"  jax         {jax.__version__}  jaxlib {jaxlib.__version__}")
except ImportError:
    print("  jax         (optional)")

if install_lib and package:
    mod = __import__(package)
    src = (root / "lib" / "src").resolve()
    assert Path(mod.__file__).resolve().is_relative_to(src), (
        f"{package} imported from {mod.__file__}, expected under {src}"
    )
    print(f"  {package}     {Path(mod.__file__).parent}  version={getattr(mod, '__version__', '?')}")
    print(f"  smoke: {package} package import ok")
else:
    print("  package     (skipped — features.lib off or no package)")

print("  smoke: venv ok")
PY

echo "[setup_venv] done. Use: $VENV/bin/python  (or 'source .venv/bin/activate')"
