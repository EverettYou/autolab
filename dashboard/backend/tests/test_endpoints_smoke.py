"""Live HTTP smoke tests against make_server(App)."""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def live_server():
    from dashboard.backend.app import App
    from dashboard.server import make_server

    app = App(ROOT)
    server = make_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"{host}:{port}"
    server.shutdown()
    server.server_close()


def _get(addr: str, path: str, origin: bool = False):
    conn = HTTPConnection(addr, timeout=5)
    headers = {"Host": addr}
    if origin:
        headers["Origin"] = f"http://{addr}"
    conn.request("GET", path, headers=headers)
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, body


API_SMOKE = (
    "/api/health",
    "/api/home",
    "/api/meta",
    "/api/settings",
    "/api/auto-research",
    "/api/auto-research/system",
    "/api/discussion",
    "/api/references",
    "/api/labs",
    "/api/wiki",
    "/api/wiki/graph",
    "/api/search?q=boundary",
    "/api/apidocs",
    "/api/apidocs/search?q=test",
    "/api/catalog",
    "/api/skills",
    "/api/fs?path=",
    "/api/file?path=README.md",
    "/api/resolve?href=wiki/index.md",
)


def test_health_and_core_gets(live_server):
    status, body = _get(live_server, "/api/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert Path(payload["root"]).resolve() == ROOT.resolve()
    # Package name is always a string; "(none)" when features.lib / package are unset.
    assert isinstance(payload["package"]["name"], str) and payload["package"]["name"]
    if payload["package"]["name"] == "(none)":
        assert payload["package"].get("error")
    else:
        assert payload["package"].get("error") in (None, "")

    for path in API_SMOKE:
        status, body = _get(live_server, path)
        assert status == 200, (path, body[:200])
        json.loads(body)

    status, body = _get(live_server, "/api/apidocs")
    assert status == 200, body[:200]
    tree = json.loads(body)
    assert "available" in tree

    for path in ("/", "/notes", "/apidocs", "/wiki", "/labs", "/threads"):
        status, body = _get(live_server, path)
        assert status == 200, path
        assert b"<!doctype html>" in body.lower() or b"<html" in body.lower()


def test_api_emits_etag(live_server):
    status, body = _get(live_server, "/api/health")
    assert status == 200
    conn = HTTPConnection(live_server, timeout=5)
    conn.request("GET", "/api/health", headers={"Host": live_server})
    response = conn.getresponse()
    etag = response.getheader("ETag")
    response.read()
    conn.close()
    assert etag and etag.startswith('"')
    conn = HTTPConnection(live_server, timeout=5)
    conn.request("GET", "/api/health", headers={"Host": live_server, "If-None-Match": etag})
    response = conn.getresponse()
    assert response.status == 304
    response.read()
    conn.close()


def test_reorder_requires_origin(live_server):
    conn = HTTPConnection(live_server, timeout=5)
    conn.request(
        "POST", "/api/auto-research/order",
        body=json.dumps({"id": "x", "before": "y"}).encode(),
        headers={"Host": live_server, "Content-Type": "application/json"},
    )
    response = conn.getresponse()
    assert response.status == 403
    response.read()
    conn.close()


def _request(addr: str, path: str, headers: dict | None = None):
    conn = HTTPConnection(addr, timeout=5)
    req_headers = {"Host": addr}
    if headers:
        req_headers.update(headers)
    conn.request("GET", path, headers=req_headers)
    response = conn.getresponse()
    body = response.read()
    result = {
        "status": response.status,
        "headers": {key.lower(): value for key, value in response.getheaders()},
        "body": body,
    }
    conn.close()
    return result


def test_notes_pdf_range_requests(live_server):
    pdf_path = ROOT / "notes" / "Symmetric Toric Code Boundary" / "main.pdf"
    if not pdf_path.is_file():
        pytest.skip("notes PDF missing")
    full = pdf_path.read_bytes()
    route = "/raw/notes/Symmetric%20Toric%20Code%20Boundary/main.pdf"
    response = _request(live_server, route)
    assert response["status"] == 200
    assert response["headers"]["content-type"] == "application/pdf"
    assert response["headers"]["accept-ranges"] == "bytes"
    assert response["body"] == full
    partial = _request(live_server, route, {"Range": "bytes=0-7"})
    assert partial["status"] == 206
    assert partial["body"] == full[:8]
    assert partial["headers"]["content-range"] == f"bytes 0-7/{len(full)}"
    suffix = _request(live_server, route, {"Range": "bytes=-7"})
    assert suffix["status"] == 206
    assert suffix["body"] == full[-7:]
    beyond = _request(live_server, route, {"Range": f"bytes={len(full)}-"})
    assert beyond["status"] == 416
    etag = response["headers"]["etag"]
    cached = _request(live_server, route, {"If-None-Match": etag})
    assert cached["status"] == 304
    opened = _request(live_server, route, {
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
    })
    assert opened["status"] == 302
    assert opened["headers"]["location"].startswith("/pdf?src=")
    assert "src=%2Fraw%2F" in opened["headers"]["location"]


def test_pdf_reader_reference_paper(live_server):
    """Regression: /pdf shell + a reference paper.pdf (Opening PDF stuck = JS lifecycle)."""
    pdfs = sorted((ROOT / "references").glob("*/paper.pdf"))
    if not pdfs:
        pytest.skip("no references/*/paper.pdf in this checkout")
    pdf = pdfs[0]
    rel = pdf.relative_to(ROOT).as_posix()
    full = pdf.read_bytes()
    assert full.startswith(b"%PDF")

    bytes_resp = _request(live_server, f"/{rel}")
    assert bytes_resp["status"] == 200
    assert bytes_resp["headers"]["content-type"] == "application/pdf"
    assert bytes_resp["body"] == full

    opened = _request(live_server, f"/{rel}", {
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
    })
    assert opened["status"] == 302
    location = opened["headers"]["location"]
    assert location.startswith("/pdf?src=")
    assert pdf.parent.name in location

    page = _request(live_server, f"/pdf?src=/{rel}")
    assert page["status"] == 200
    html = page["body"].decode("utf-8", errors="replace")
    assert 'id="app"' in html or "pdf" in html.lower()
    # SPA shell must load; mount happens client-side under content-core.lifecycle.
    assert "/static/js/app.js" in html or 'type="module"' in html
