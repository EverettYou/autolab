"""Link resolution covers wiki, labs, notes, and platform sources."""
from __future__ import annotations

from conftest import LAB


def test_wiki_and_lab_links_resolve(client):
    page = client.get_json("/api/wiki/concepts/noise")
    assert page["title"] == "Noise" or "Noise" in page.get("title", "")
    lab = client.get_json(f"/api/labs/{LAB}")
    assert lab["id"] == LAB or lab.get("item", {}).get("id") == LAB or "title" in lab


def test_notes_route_from_catalog(client):
    catalog = client.get_json("/api/catalog")
    note = next(row for row in catalog["notes"] if row["id"] == "Boundary Models and Phases")
    assert note["source"].endswith("main.tex")
    details = client.get_json(
        "/api/workspaces/project?source=lab-notes&project=Boundary%20Models%20and%20Phases"
    )
    assert details["main"].endswith("main.tex")


def test_resolve_internal_targets(client):
    resolved = client.get_json("/api/resolve?href=wiki/concepts/noise.md&source=README.md")
    assert resolved["resolved"] is not None
    resolved_lab = client.get_json(f"/api/resolve?href=labs/{LAB}/REPORT.md&source=README.md")
    assert resolved_lab["resolved"] is not None
