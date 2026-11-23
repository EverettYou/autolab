"""Optional Notes workbench vendors (PDF.js viewer + markdown renderer).

Shipped as ``dashboard/frontend/vendor/notes-stack.tar.gz`` so labs with
``features.notes: false`` (the template default) do not keep ~10MB of unpacked
trees in the working copy. Extract on first Notes enable / Notes API use.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

NAMES = ("notes-pdfjs", "notes-markdown")
ARCHIVE = "notes-stack.tar.gz"


def vendor_dir(root: Path) -> Path:
    return Path(root) / "dashboard" / "frontend" / "vendor"


def archive_path(root: Path) -> Path:
    return vendor_dir(root) / ARCHIVE


def extracted(root: Path) -> bool:
    base = vendor_dir(root)
    return all((base / name).is_dir() for name in NAMES)


def ensure(root: Path) -> Path:
    """Extract the Notes vendor stack if missing. Returns the vendor directory."""
    base = vendor_dir(root)
    if extracted(root):
        return base
    archive = archive_path(root)
    if not archive.is_file():
        raise FileNotFoundError(
            f"Notes vendor archive missing: {archive.as_posix()}. "
            "Restore dashboard/frontend/vendor/notes-stack.tar.gz from the template."
        )
    base.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        # Python 3.12+ supports filter=; keep compatible extract for 3.11 runners.
        try:
            tar.extractall(base, filter="data")
        except TypeError:
            tar.extractall(base)
    missing = [name for name in NAMES if not (base / name).is_dir()]
    if missing:
        raise RuntimeError(f"Notes vendor archive incomplete; missing {', '.join(missing)}")
    return base
