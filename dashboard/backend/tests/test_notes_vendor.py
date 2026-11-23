"""Notes workbench vendor pack extracts on demand."""

from __future__ import annotations

import shutil
from pathlib import Path

from dashboard.backend import notes_vendor


def test_ensure_extracts_and_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path
    vendor = root / "dashboard" / "frontend" / "vendor"
    vendor.mkdir(parents=True)
    archive = Path(__file__).resolve().parents[2] / "frontend" / "vendor" / "notes-stack.tar.gz"
    shutil.copy2(archive, vendor / notes_vendor.ARCHIVE)

    assert not notes_vendor.extracted(root)
    notes_vendor.ensure(root)
    assert notes_vendor.extracted(root)
    notes_vendor.ensure(root)
    assert (vendor / "notes-pdfjs" / "build" / "pdf.mjs").is_file()
    assert (vendor / "notes-markdown" / "markdown-renderer.js").is_file()
