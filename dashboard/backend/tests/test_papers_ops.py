"""Notes workspace create/import/status/editor-sync contracts."""
from __future__ import annotations

from base64 import b64encode

import pytest


def test_create_import_status_and_editor_sync(tmp_path, monkeypatch):
    from dashboard.backend import catalog, papers

    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    project = tmp_path / "notes" / "OpsNote"
    project.mkdir(parents=True)
    (project / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}\n", encoding="utf-8")

    details = papers.details("OpsNote")
    assert details["status"] == "active"
    assert details["label_revision"]

    created = papers.write("project/create", {
        "source": papers.SOURCE, "project": "OpsNote",
        "parent": "OpsNote", "name": "notes.bib", "kind": "file",
    })
    assert created["path"] == "OpsNote/notes.bib"
    assert (project / "notes.bib").is_file()

    papers.write("project/create", {
        "source": papers.SOURCE, "project": "OpsNote",
        "parent": "OpsNote", "name": "figures", "kind": "folder",
    })
    imported = papers.write("project/import", {
        "source": papers.SOURCE, "project": "OpsNote",
        "parent": "OpsNote/figures", "name": "plot.png",
        "data": b64encode(b"\x89PNG\r\n").decode(),
    })
    assert imported["path"] == "OpsNote/figures/plot.png"
    assert (project / "figures" / "plot.png").read_bytes().startswith(b"\x89PNG")

    updated = papers.write("project/status", {
        "source": papers.SOURCE, "project": "OpsNote",
        "status": "finished", "revision": details["label_revision"],
    })
    assert updated["status"] == "finished"
    assert papers.details("OpsNote")["status"] == "finished"

    assert papers.write("project/editor-sync", {
        "source": papers.SOURCE, "project": "OpsNote",
        "path": "OpsNote/main.tex", "session": "s1",
    }) == {"handoff": None}

    doc = papers.document("OpsNote", "OpsNote/main.tex")
    assert doc["editable"] is True
    assert doc["editor_sync"] is False


def test_delete_blocks_main_tex(tmp_path, monkeypatch):
    from dashboard.backend import catalog, papers

    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    project = tmp_path / "notes" / "Keep"
    project.mkdir(parents=True)
    (project / "main.tex").write_text("x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        papers.write("project/delete", {
            "source": papers.SOURCE, "project": "Keep",
            "path": "Keep/main.tex",
        })
