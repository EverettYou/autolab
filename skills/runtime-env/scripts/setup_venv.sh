#!/usr/bin/env bash
# Create / refresh the canonical lab venv (./.venv) for core development.
# Idempotent. On machines with a curated preinstalled ML stack (e.g. EdenCode), it inherits the
# baseline via --system-site-packages and installs only what the image does not already satisfy.
#
# Single source of truth for *what* is required when features.lib is on: lib/pyproject.toml.
# Single source of truth for *versions of anything already on the image*: the container itself.
#
# this template default: features.lib false → venv for dashboard/skills only (no editable package).
# For foreign reproductions with conflicting pins, do NOT use this: make an isolated venv inside the
# attempt workspace instead (see machines/*.md "conflicting pins").
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$_SCRIPT_DIR/../../.." && pwd)"
LIB="$ROOT/lib"
# Override with SETUP_VENV_DIR for dry-runs; default is the canonical repo .venv.
VENV="${SETUP_VENV_DIR:-$ROOT/.venv}"
PY="$VENV/bin/python"

# shellcheck source=lib/profile_signals.sh
source "$_SCRIPT_DIR/lib/profile_signals.sh"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. This script targets machines with uv (e.g. EdenCode dev container)." >&2
  echo "On a bare machine, see skills/runtime-env/machines/ for alternatives." >&2
  exit 1
fi
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

PROFILE="$(profile_match_id)"
echo "[setup_venv] root=$ROOT"
echo "[setup_venv] matched_profile=$PROFILE"
echo "[setup_venv] features.lib=$FEATURE_LIB package=${PACKAGE_NAME:-(none)}"

if [ -d "$VENV" ]; then
  echo "[setup_venv] removing existing $VENV"
  rm -rf "$VENV"
fi

# Inherit a curated container baseline only when the runtime-env profile says so.
USE_SYSTEM=false
case "$PROFILE" in
  edencode-b300|edencode-h200)
    USE_SYSTEM=true
    ;;
  generic-container)
    if python3 -c 'import torch' >/dev/null 2>&1; then
      USE_SYSTEM=true
    fi
    ;;
esac

if [ "$USE_SYSTEM" = true ]; then
  echo "[setup_venv] uv venv --system-site-packages $VENV  (curated baseline for $PROFILE)"
  uv venv --python python3 --system-site-packages "$VENV"
else
  echo "[setup_venv] uv venv $VENV  (isolated install for $PROFILE)"
  uv venv --python python3 "$VENV"
fi

# Always need pytest/dev tooling available for skills; when lib is off, install pytest only.
if [ "$INSTALL_LIB" != 1 ]; then
  echo "[setup_venv] features.lib off — installing dashboard/skills deps (pytest) only"
  uv pip install --python "$PY" pytest
else
  echo "[setup_venv] uv pip install -e lib --no-deps"
  uv pip install --python "$PY" -e "$LIB" --no-deps

  if [ "$USE_SYSTEM" = true ]; then
    if ! "$PY" -c 'import packaging' >/dev/null 2>&1; then
      echo "[setup_venv] installing packaging (needed to walk lib/pyproject.toml against the baseline)"
      uv pip install --python "$PY" packaging
    fi
    echo "[setup_venv] preferring container packages that already satisfy lib/pyproject.toml"
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

log("[setup_venv] direct deps vs container:")
for raw in list(queue):
    req = Requirement(raw)
    ver = installed_version(req.name)
    if satisfied(raw):
        log(f"  keep     {raw}  (container {ver})")
    elif ver is None:
        log(f"  install  {raw}  (not in container)")
    else:
        log(f"  shadow   {raw}  (container {ver} does not satisfy)")

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
    log(f"[setup_venv] uv pip install --no-deps {raw}")
    subprocess.check_call(
        ["uv", "pip", "install", "--python", sys.executable, "--no-deps", raw],
        env=os.environ.copy(),
    )
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
    log("[setup_venv] container already satisfies all lib[dev] deps; nothing else to install")
PY
    then
      echo "[setup_venv] ERROR: failed to layer missing deps onto the container baseline" >&2
      exit 1
    fi
  else
    echo "[setup_venv] no curated baseline detected; uv pip install -e \"lib[dev]\""
    uv pip install --python "$PY" -e "$LIB[dev]"
  fi
fi

if [ ! -x "$VENV/bin/uv" ]; then
  echo "[setup_venv] ensure uv is available inside repo base venv"
  uv pip install --python "$PY" uv
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
