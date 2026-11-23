"""Notes compile contract: latexmk path, revision guard, PDF write."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="latexmk not installed")
def test_compile_note_writes_pdf(tmp_path, monkeypatch):
    from dashboard.backend import catalog, notes

    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    project = tmp_path / "notes" / "Tiny"
    project.mkdir(parents=True)
    tex = project / "main.tex"
    tex.write_text(
        r"""\documentclass{article}
\begin{document}
Hello EM.
\end{document}
""",
        encoding="utf-8",
    )
    snap = notes.snapshot(tex)
    result = notes.compile_note("Tiny", snap["revision"])
    assert result["ok"] is True, result.get("log", "")[-2000:]
    pdf = project / "main.pdf"
    assert pdf.is_file()
    raw = pdf.read_bytes()
    assert raw.startswith(b"%PDF-")
    assert result["path"].endswith("Tiny/main.pdf")


def test_compile_note_rejects_stale_revision(tmp_path, monkeypatch):
    from dashboard.backend import catalog, notes

    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    project = tmp_path / "notes" / "Stale"
    project.mkdir(parents=True)
    (project / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}x\\end{document}\n",
        encoding="utf-8",
    )
    with pytest.raises(notes.NoteConflict):
        notes.compile_note("Stale", "not-the-revision")
