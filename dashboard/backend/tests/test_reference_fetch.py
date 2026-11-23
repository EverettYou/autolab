"""Restore missing reference PDFs and repos via POST /api/references/<id>/…"""
from __future__ import annotations

import json
from pathlib import Path

from conftest import PDF


def _origin(client) -> dict:
    return {
        "Origin": f"http://{client.host}:{client.port}",
        "Content-Type": "application/json",
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_list_and_detail_expose_can_fetch_pdf(fresh_root, serve_root):
    folder = fresh_root / "references" / "missing-pdf"
    _write_json(folder / "provenance.json", {
        "title": "Missing PDF",
        "pdf": "paper.pdf",
        "arxiv_id": "1706.03762",
        "pdf_url": "https://arxiv.org/pdf/1706.03762",
        "status": "fetched",
    })
    registry = json.loads((fresh_root / "references" / "references.json").read_text(encoding="utf-8"))
    registry["references"].append({
        "id": "missing-pdf", "title": "Missing PDF", "kind": "paper", "status": "fetched",
    })
    _write_json(fresh_root / "references" / "references.json", registry)

    client = serve_root(fresh_root)
    listed = client.get_json("/api/references")
    row = next(item for item in listed["references"] if item["id"] == "missing-pdf")
    assert row["has_pdf"] is False
    assert row["can_fetch_pdf"] is True

    present = next(item for item in listed["references"] if item["id"] == "alpha-ref")
    assert present["has_pdf"] is True
    assert present["can_fetch_pdf"] is False

    detail = client.get_json("/api/references/missing-pdf")
    assert detail["pdf"] is None
    assert detail["can_fetch_pdf"] is True


def test_refetch_pdf_restores_missing_file(fresh_root, serve_root, monkeypatch):
    folder = fresh_root / "references" / "restore-me"
    _write_json(folder / "provenance.json", {
        "title": "Restore me",
        "pdf": "paper.pdf",
        "arxiv_id": "1706.03762",
        "pdf_url": "https://arxiv.org/pdf/1706.03762",
        "pdf_sha256": "abc",
        "status": "fetched",
    })

    def fake_run(cmd, **kwargs):
        assert "refetch" in cmd
        (folder / "paper.pdf").write_bytes(PDF)

        class Result:
            returncode = 0
            stdout = "restored restore-me: paper.pdf"
            stderr = ""

        return Result()

    monkeypatch.setattr("dashboard.backend.reference_fetch.subprocess.run", fake_run)
    client = serve_root(fresh_root)
    response = client.request(
        "/api/references/restore-me/pdf",
        method="POST",
        headers=_origin(client),
        body={},
    )
    assert response.status == 200, response.body
    payload = response.json()
    assert payload["route"] == "/references/restore-me/paper.pdf"
    assert payload["size"] == len(PDF)
    assert (folder / "paper.pdf").is_file()


def test_refetch_pdf_rejects_when_no_source(fresh_root, serve_root):
    folder = fresh_root / "references" / "no-source"
    _write_json(folder / "provenance.json", {
        "title": "No source",
        "pdf": "paper.pdf",
        "status": "fetched",
    })
    client = serve_root(fresh_root)
    response = client.request(
        "/api/references/no-source/pdf",
        method="POST",
        headers=_origin(client),
        body={},
    )
    assert response.status == 400
    assert "pdf_url" in response.json()["error"] or "arxiv" in response.json()["error"]


def test_refetch_pdf_returns_existing_without_download(fresh_root, serve_root, monkeypatch):
    called = []

    def fake_run(*args, **kwargs):
        called.append(True)
        raise AssertionError("refetch should not run when the PDF is already local")

    monkeypatch.setattr("dashboard.backend.reference_fetch.subprocess.run", fake_run)
    client = serve_root(fresh_root)
    response = client.request(
        "/api/references/alpha-ref/pdf",
        method="POST",
        headers=_origin(client),
        body={},
    )
    assert response.status == 200, response.body
    assert response.json()["route"] == "/references/alpha-ref/paper.pdf"
    assert not called


def test_list_and_detail_expose_repo_fetch_flags(fresh_root, serve_root):
    folder = fresh_root / "references" / "code-ref"
    _write_json(folder / "provenance.json", {
        "title": "Code ref",
        "kind": "repository",
        "status": "fetched",
        "repos": [{
            "name": "tool",
            "path": "repos/tool",
            "url": "https://github.com/example/tool.git",
        }],
    })
    registry = json.loads((fresh_root / "references" / "references.json").read_text(encoding="utf-8"))
    registry["references"].append({
        "id": "code-ref", "title": "Code ref", "kind": "repository", "status": "fetched",
        "repos": ["tool"],
    })
    _write_json(fresh_root / "references" / "references.json", registry)

    client = serve_root(fresh_root)
    listed = client.get_json("/api/references")
    row = next(item for item in listed["references"] if item["id"] == "code-ref")
    assert row["primary_repo"]["name"] == "tool"
    assert row["primary_repo"]["exists"] is False
    assert row["primary_repo"]["can_fetch"] is True

    detail = client.get_json("/api/references/code-ref")
    assert detail["repos"][0]["exists"] is False
    assert detail["repos"][0]["can_fetch"] is True


def test_refetch_repo_clones_missing(fresh_root, serve_root, monkeypatch):
    folder = fresh_root / "references" / "code-ref"
    _write_json(folder / "provenance.json", {
        "title": "Code ref",
        "kind": "repository",
        "status": "fetched",
        "repos": [{
            "name": "tool",
            "path": "repos/tool",
            "url": "https://github.com/example/tool.git",
        }],
    })

    def fake_run(cmd, **kwargs):
        assert "repo" in cmd
        dest = folder / "repos" / "tool"
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("hi\n", encoding="utf-8")

        class Result:
            returncode = 0
            stdout = "cloned"
            stderr = ""

        return Result()

    monkeypatch.setattr("dashboard.backend.reference_fetch.subprocess.run", fake_run)
    client = serve_root(fresh_root)
    response = client.request(
        "/api/references/code-ref/repos/tool",
        method="POST",
        headers=_origin(client),
        body={},
    )
    assert response.status == 200, response.body
    payload = response.json()
    assert payload["route"] == "/references/code-ref?file=repos/tool#files"
    assert (folder / "repos" / "tool").is_dir()


def test_refetch_repo_rejects_when_no_url(fresh_root, serve_root):
    folder = fresh_root / "references" / "code-ref"
    _write_json(folder / "provenance.json", {
        "title": "Code ref",
        "kind": "repository",
        "status": "fetched",
        "repos": [{"name": "tool", "path": "repos/tool"}],
    })
    client = serve_root(fresh_root)
    response = client.request(
        "/api/references/code-ref/repos/tool",
        method="POST",
        headers=_origin(client),
        body={},
    )
    assert response.status == 400
    assert "URL" in response.json()["error"] or "url" in response.json()["error"]
