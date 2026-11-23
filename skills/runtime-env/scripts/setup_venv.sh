#!/usr/bin/env bash
# Create / refresh the canonical lab venv (./.venv) for core development.
# Idempotent. Default: inherit host/container site-packages via --system-site-packages
# and install only what the baseline does not already satisfy (prefer the baseline).
# Escape hatch: SETUP_VENV_ISOLATED=1 builds a clean isolated venv.
#
# Installer preference: ``uv`` when on PATH; otherwise standard ``python3 -m venv`` + ``pip``.
#
# Single source of truth for *what* is required when features.lib is on: lib/pyproject.toml.
# Single source of truth for *versions already present*: the host or container baseline.
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
echo "[setup_venv] policy_isolation=$POLICY_ISOLATION untrusted=$POLICY_UNTRUSTED_CODE"
echo "[setup_venv] features.lib=$FEATURE_LIB package=${PACKAGE_NAME:-(none)}"
if [ "$HAVE_UV" = 1 ]; then
  echo "[setup_venv] installer=uv ($(command -v uv))"
else
  echo "[setup_venv] installer=pip (uv not on PATH; using python3 -m venv + pip)"
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
