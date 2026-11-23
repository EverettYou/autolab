"""Notes/Overleaf contract: main.tex is editable, main.txt is legacy-compatible."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_live_boundary_models_is_editable_tex():
    from dashboard.backend.notes import projects, read_note, source_path

    project = ROOT / "notes" / "Boundary Models and Phases"
    if not project.is_dir():
        pytest.skip("live notes project not present in this checkout")
    assert source_path(project).name == "main.tex"
    rows = {row["id"]: row for row in projects()}
    assert rows["Boundary Models and Phases"]["source"].endswith("main.tex")
    note = read_note("Boundary Models and Phases")
    assert "documentclass" in note["text"] or "begin{document}" in note["text"] or len(note["text"]) > 100


def test_projects_accept_legacy_main_txt(tmp_path, monkeypatch):
    from dashboard.backend import catalog, notes

    notes_root = tmp_path / "notes"
    project = notes_root / "Legacy Note"
    project.mkdir(parents=True)
    (project / "main.txt").write_text("plain legacy source\n", encoding="utf-8")
    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    rows = notes.projects()
    assert rows[0]["source"].endswith("main.txt")
    assert notes.read_note("Legacy Note")["text"] == "plain legacy source\n"


def test_tex_preferred_when_both_exist(tmp_path, monkeypatch):
    from dashboard.backend import catalog, notes

    notes_root = tmp_path / "notes"
    project = notes_root / "Both"
    project.mkdir(parents=True)
    (project / "main.txt").write_text("txt\n", encoding="utf-8")
    (project / "main.tex").write_text("tex\n", encoding="utf-8")
    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    assert notes.source_path(project).name == "main.tex"
    assert notes.read_note("Both")["text"] == "tex\n"


def test_papers_details_expose_main_tex(tmp_path, monkeypatch):
    from dashboard.backend import catalog, papers

    notes_root = tmp_path / "notes"
    project = notes_root / "PaperNote"
    project.mkdir(parents=True)
    (project / "main.tex").write_text("\\documentclass{article}\\begin{document}Hi\\end{document}\n", encoding="utf-8")
    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    details = papers.details("PaperNote")
    assert details["main"] == "PaperNote/main.tex"
    doc = papers.document("PaperNote", "PaperNote/main.tex")
    assert doc["editable"] is True
