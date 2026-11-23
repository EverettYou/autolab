"""Path policy: nothing outside the repository, no dot folders or documents/."""
from __future__ import annotations

import os
from urllib.parse import quote

import pytest
from conftest import LAB, SECRETS

from dashboard.backend.repo import TEXT_PREVIEW_LIMIT, BadRequest, Forbidden, normalize_rel


def assert_no_secret(body: bytes) -> None:
    for marker in SECRETS:
        assert marker.encode() not in body, marker


REFUSED = [
    ("../outside/secret.txt", 403),
    ("labs/../../outside/secret.txt", 403),
    ("/etc/passwd", 403),
    ("C:/Windows/win.ini", 403),
    ("~/.ssh/id_rsa", 403),
    (".git/config", 403),
    (".venv/pyvenv.cfg", 403),
    (".tmp/notes.txt", 403),
    (".hidden.txt", 403),
    (".auto-research/state.json", 403),
    (f"labs/{LAB}/.env", 403),
    ("documents", 403),
    ("documents/secret.md", 403),
    (f"labs/{LAB}/link-outside", 403),
    (f"labs/{LAB}/link-git", 403),
    ("labs\\..\\..\\outside", 400),
    ("README.md\x00.png", 400),
]


@pytest.mark.parametrize("path,status", REFUSED)
@pytest.mark.parametrize("endpoint", ["/api/file?path=", "/api/fs?path="])
def test_api_refuses_paths(client, endpoint, path, status):
    response = client.request(endpoint + quote(path, safe=""))
    assert response.status == status, response.body
    assert "error" in response.json()
    assert_no_secret(response.body)


@pytest.mark.parametrize("path", [
    "/raw/../outside/secret.txt",
    "/raw/.git/config",
    "/raw/.venv/pyvenv.cfg",
    "/raw/.tmp/notes.txt",
    "/raw/.hidden.txt",
    "/raw/documents/secret.md",
    f"/raw/labs/{LAB}/.env",
    f"/raw/labs/{LAB}/link-outside",
    f"/raw/labs/{LAB}/link-git",
])
def test_raw_refuses_paths(client, path):
    response = client.request(path)
    assert response.status in {403, 404}, (path, response.body)
    assert_no_secret(response.body)


@pytest.mark.parametrize("path", [
    "/static/../server.py",
    "/static/.hidden",
    "/static/",
])
def test_static_refuses_paths(client, path):
    assert client.request(path).status == 404


def test_item_routes_refuse_traversal(client):
    for route, status in [
        ("/api/wiki/../../outside/secret", 403),
        ("/api/labs/..", 400),
        ("/api/references/..", 400),
        ("/api/discussion/..%2Fthread-001", 400),
        ("/api/auto-research/..%2Fstate", 400),
    ]:
        response = client.request(route)
        assert response.status == status, (route, response.body)


def test_no_listing_or_search_exposes_hidden_content(client):
    pending, seen = [""], set()
    while pending:
        rel = pending.pop()
        if rel in seen:
            continue
        seen.add(rel)
        response = client.request("/api/fs?path=" + quote(rel, safe="/"))
        assert response.status == 200, rel
        assert_no_secret(response.body)
        for entry in response.json()["entries"]:
            assert not entry["name"].startswith(".")
            assert entry["path"].split("/")[0] != "documents"
            if entry["type"] == "dir":
                pending.append(entry["path"])
            elif entry["type"] == "file":
                assert_no_secret(client.request("/api/file?path=" + quote(entry["path"], safe="/")).body)
    assert f"labs/{LAB}/figures" in seen
    for query in ("secret", "marker", "documents", "git", "env"):
        assert_no_secret(client.request(f"/api/search?q={query}").body)


def test_resolve_never_points_outside(client):
    assert client.get_json("/api/resolve?href=../../outside/secret.txt")["resolved"] is None
    assert client.get_json("/api/resolve?href=.git/config")["resolved"] is None
    assert client.get_json("/api/resolve?href=documents/secret.md")["resolved"] is None


def test_host_header_allowlist(client):
    assert client.request("/api/health", headers={"Host": "evil.example"}).status == 403
    assert client.request("/api/health", headers={"Host": f"127.0.0.1:{client.port}"}).status == 200
    assert client.request("/api/health", headers={"Host": f"localhost:{client.port}"}).status == 200


def test_normalize_rel():
    assert normalize_rel("labs//x/./y/") == "labs/x/y"
    assert normalize_rel("") == ""
    for raw, error in (
        ("../x", Forbidden), ("/x", Forbidden), (".git", Forbidden), ("a/.b/c", Forbidden),
        ("documents/x", Forbidden), ("a\\b", BadRequest), ("a\x00", BadRequest),
        (None, BadRequest), ("~/x", Forbidden), ("D:/x", Forbidden),
    ):
        with pytest.raises(error):
            normalize_rel(raw)


def test_directory_symlink_out_of_the_repository(fresh_root, serve_root, tmp_path):
    os.symlink(tmp_path / "outside", fresh_root / "labs" / LAB / "outdir")
    client = serve_root(fresh_root)
    assert client.request(f"/api/fs?path=labs/{LAB}/outdir").status == 403
    assert client.request(f"/api/file?path=labs/{LAB}/outdir/secret.txt").status == 403


def test_text_previews_are_capped(fresh_root, serve_root):
    lab = fresh_root / "labs" / LAB
    (lab / "big.log").write_bytes(b"x" * (TEXT_PREVIEW_LIMIT + 100))
    (lab / "big.md").write_bytes(b"# Big\n" + b"y" * (TEXT_PREVIEW_LIMIT + 100))
    client = serve_root(fresh_root)
    log = client.get_json(f"/api/file?path=labs/{LAB}/big.log")
    assert log["truncated"] is True and len(log["content"]) == TEXT_PREVIEW_LIMIT
    markdown = client.get_json(f"/api/file?path=labs/{LAB}/big.md")
    assert markdown["truncated"] is True
    small = client.get_json(f"/api/file?path=labs/{LAB}/scripts/run.py")
    assert small["truncated"] is False


def test_core_catalog_endpoints(client):
    home = client.get_json("/api/home")
    assert "labs" in home or "warnings" in home or isinstance(home, dict)
    auto = client.get_json("/api/auto-research")
    assert auto["exists"] is True
    assert auto["counts"]["tasks"] >= 1
    discussion = client.get_json("/api/discussion")
    assert discussion["exists"] is True
    notes = client.get_json("/api/catalog")
    assert any(row["id"] == "Boundary Models and Phases" for row in notes["notes"])
    search = client.get_json("/api/search?q=Noise")
    assert "semantic_enabled" in search
    wiki = client.get_json("/api/wiki")
    assert wiki["exists"] is True
