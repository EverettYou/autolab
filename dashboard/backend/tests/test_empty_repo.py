"""Missing repository trees degrade to empty JSON states."""
from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_app
from dashboard.backend.app import App


EMPTY_ROUTES = [
    "/api/health",
    "/api/home",
    "/api/auto-research",
    "/api/references",
    "/api/labs",
    "/api/wiki",
    "/api/discussion",
    "/api/apidocs",
    "/api/catalog",
    "/api/search?q=x",
]


def test_empty_repository(tmp_path, serve_root):
    root = tmp_path / "empty"
    root.mkdir()
    app = App(root)  # template default: no package
    client = serve_root(root, app=app)
    payloads = {route: client.get_json(route) for route in EMPTY_ROUTES}
    assert payloads["/api/health"]["ok"] is True
    assert payloads["/api/health"]["package"]["name"] == "(none)"
    assert payloads["/api/health"]["package"]["error"]
    assert payloads["/api/home"]["auto_research"]["exists"] is False
    assert payloads["/api/references"]["references"] == []
    assert payloads["/api/labs"]["labs"] == []
    assert payloads["/api/wiki"]["exists"] is False
    assert payloads["/api/discussion"]["threads"] == []
    assert payloads["/api/apidocs"]["available"] is False
    assert payloads["/api/catalog"] == {
        "labs": [], "notes": [], "wiki": [], "references": [], "skills": [], "overview": [],
    }
    assert payloads["/api/search?q=x"]["total"] == 0


def test_missing_frontend_still_serves_api(tmp_path, serve_root):
    root = tmp_path / "repo"
    root.mkdir()
    app = App(root, package_dir=root / "none", frontend=tmp_path / "no-frontend")
    client = serve_root(root, app=app)
    assert client.get_json("/api/health")["ok"] is True
    page = client.request("/")
    assert page.status == 404
