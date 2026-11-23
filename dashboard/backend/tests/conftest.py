"""Shared fixtures: a small fixture repository, emb sample package, and a live server."""
from __future__ import annotations

import base64
import http.client
import json
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
os.environ.pop("OPENAI_CATALOG_SEARCH_ENABLED", None)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard.backend.app import App  # noqa: E402
from dashboard.server import make_server  # noqa: E402

LAB = "2026-01-02-alpha"
LAB2 = "2026-01-05-beta"
PACKAGE = "emb"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
PDF = b"%PDF-1.4\n%" + b"x" * 3000 + b"\n%%EOF\n"
SECRETS = tuple(f"SECRET-MARKER-{name}" for name in (
    "documents", "git", "venv", "tmp", "dotfile", "env", "outside"))

SAMPLE_INIT = '''"""EM Boundary platform package fixture.

Start with :class:`~emb.core.Widget`.
"""

from .core import Widget, make_widget

__all__ = ["Widget", "make_widget"]
'''

SAMPLE_CORE = '''"""Core module with ``Widget``.

Example::

    widget = Widget(3)
"""

from __future__ import annotations

LIMIT: int = 10
"""Maximum widget size."""


class Widget:
    """A widget.

    Args:
        size (int): The size.
    """

    def __init__(self, size: int) -> None:
        self.size = size

    def double(self) -> int:
        """Return twice the size."""
        return 2 * self.size


def make_widget(size: int = 1) -> Widget:
    """Build a :class:`Widget`."""
    return Widget(size)


raise RuntimeError("the API manual must parse this module, never import it")
'''


def _write(root: Path, rel: str, content) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    elif isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    return path


def make_repo(root: Path, outside: Path) -> Path:
    lab = f"labs/{LAB}"
    files = {
        "README.md": "# Fixture\n\nSee [the labs](labs/labs.json) and `wiki/index.md`.\n",
        "run.sh": "#!/usr/bin/env bash\n",
        ".auto-research/state.json": {
            "schema": "auto-research-1", "status": "paused",
            "updated": "2026-01-03T10:00:00Z",
            "next_action": f"Continue {lab}/REPORT.md.",
            "active_deliverable": {"lab": LAB, "summary": "Alpha report", "acceptance": ["Done."]},
            "last_action": {"at": "2026-01-03T09:00:00Z", "summary": f"Wrote `{lab}/REPORT.md`"},
            "tasks": [
                {"id": "alpha-followup", "title": "Follow up alpha", "for": "auto", "gpu": "free",
                 "time": "5min", "blocked_on": None, "related_labs": [LAB],
                 "detail": ".auto-research/tasks/alpha-followup.md", "added": "2026-01-03"},
                {"id": "blocked-item", "title": "Waiting", "for": "auto", "gpu": "free",
                 "time": "5min", "blocked_on": "thread-001", "related_labs": [],
                 "detail": ".auto-research/tasks/blocked-item.md", "added": "2026-01-03"},
            ],
            "threads": [{
                "id": "thread-001", "title": "Alpha question", "status": "open", "category": "decision",
                "priority": "normal", "related_labs": [LAB],
                "created": "2026-01-02T10:00:00Z", "updated": "2026-01-02T10:00:00Z",
            }],
        },
        ".auto-research/threads/thread-001.json": {
            "messages": [{"id": "msg-001", "author": "agent", "type": "question",
                          "created": "2026-01-02T10:00:00Z",
                          "content": f"See `{lab}/REPORT.md`."}],
        },
        ".auto-research/tasks/alpha-followup.md": (
            "# Alpha follow-up\n\n## Goal\nFollow up alpha.\n\n## Work\nUpdate the report.\n\n"
            "## Done when\nReport has the follow-up.\n"
        ),
        ".auto-research/tasks/blocked-item.md": (
            "# Waiting\n\n## Goal\nUnblock when the thread resolves.\n\n## Work\nWait on thread-001.\n\n"
            "## Done when\nThread-001 is applied and this item is done.\n"
        ),
        "references/references.json": {"references": [
            {"id": "alpha-ref", "title": "Alpha paper", "kind": "paper", "status": "fetched"},
        ]},
        "references/alpha-ref/provenance.json": {
            "title": "Alpha paper", "authors": ["A. Author"],
            "abstract": "We study an EM boundary model.", "pdf": "paper.pdf",
        },
        "references/alpha-ref/paper.pdf": PDF,
        "labs/labs.json": {"labs": [
            {"id": LAB, "title": "Alpha lab", "stage": "active", "summary": "Alpha summary.",
             "created": "2026-01-02", "updated": "2026-01-03", "references": ["alpha-ref"],
             "discussion": ["thread-001"]},
            {"id": LAB2, "title": "Beta lab", "stage": "complete", "created": "2026-01-05"},
        ]},
        f"{lab}/lab.json": {
            "id": LAB, "title": "Alpha lab", "stage": "active", "current_focus": "Measure alpha.",
            "next_action": "Write the report.", "references": ["alpha-ref"], "discussion": ["thread-001"],
        },
        f"{lab}/PLAN.md": "# Plan\n\nMeasure the gap.\n",
        f"{lab}/REPORT.md": "# Report\n\n## Results\n\n![plot](figures/plot.png)\n",
        f"{lab}/scripts/run.py": "print('alpha')\n",
        f"{lab}/figures/plot.png": PNG,
        f"{lab}/results/metrics.json": '{"gap": 0.1}',
        f"labs/{LAB2}/lab.json": {"id": LAB2, "title": "Beta lab", "stage": "complete"},
        f"labs/{LAB2}/PLAN.md": "# Plan\n",
        f"labs/{LAB2}/REPORT.md": "# Report\n",
        "wiki/README.md": "# Wiki schema\n",
        "wiki/index.md": "# Test wiki\n\n- [Noise](concepts/noise.md)\n",
        "wiki/taxonomy.yml": "page_types:\n  concept: {folder: concepts}\ntopics:\n  - Boundary Models\n",
        "wiki/sources.yml": "version: 1\nsources: []\n",
        "wiki/concepts/noise.md": (
            "---\ntitle: Noise\npage_type: concept\nstatus: active\nupdated: 2026-01-03\n"
            "source_refs:\n  - references/alpha-ref\nidea_ids: []\ntopics:\n  - Boundary Models\n---\n"
            "# Noise\n\n**Summary**: Fixture concept.\n\n**Sources**: `references/alpha-ref`\n\n"
            "**Last updated**: 2026-01-03\n\nBody.\n\n## Related pages\n\n- [Index](../index.md)\n"
        ),
        "skills/research-threads/scripts/research_threads.py":
            (REPO_ROOT / "skills/research-threads/scripts/research_threads.py").read_text(encoding="utf-8"),
        "skills/research-threads/SKILL.md": "# research-threads\n",
        "skills/auto-research/scripts/seed_local.py":
            (REPO_ROOT / "skills/auto-research/scripts/seed_local.py").read_text(encoding="utf-8"),
        f"lib/src/{PACKAGE}/__init__.py": SAMPLE_INIT,
        f"lib/src/{PACKAGE}/core.py": SAMPLE_CORE,
        "notes/Boundary Models and Phases/main.tex":
            "\\documentclass{article}\\begin{document}Hello EM.\\end{document}\n",
        "notes/Boundary Models and Phases/main.pdf": PDF,
        "documents/secret.md": f"# Manuscript\n\n{SECRETS[0]}\n",
        ".git/config": f"[core]\n# {SECRETS[1]}\n",
        ".venv/pyvenv.cfg": f"home = /usr/bin\n# {SECRETS[2]}\n",
        ".tmp/notes.txt": f"{SECRETS[3]}\n",
        ".hidden.txt": f"{SECRETS[4]}\n",
        f"{lab}/.env": f"TOKEN={SECRETS[5]}\n",
    }
    for rel, content in files.items():
        _write(root, rel, content)
    _write(outside, "secret.txt", f"{SECRETS[6]}\n")
    os.symlink("../../README.md", root / lab / "link-inside")
    os.symlink(outside / "secret.txt", root / lab / "link-outside")
    os.symlink("../../.git/config", root / lab / "link-git")
    os.symlink("does-not-exist", root / lab / "broken")
    return root


def make_app(root: Path) -> App:
    return App(root, package=PACKAGE, package_dir=root / "lib" / "src" / PACKAGE)


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def json(self):
        return json.loads(self.body)


class Client:
    def __init__(self, server, app: App):
        self.server = server
        self.app = app
        self.host, self.port = server.server_address[:2]

    def request(self, path: str, method: str = "GET", headers: dict | None = None,
                body: bytes | str | dict | None = None) -> Response:
        payload = None
        hdrs = dict(headers or {})
        hdrs.setdefault("Host", f"{self.host}:{self.port}")
        if isinstance(body, dict):
            payload = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            payload = body.encode()
        else:
            payload = body
        conn = http.client.HTTPConnection(self.host, self.port, timeout=15)
        try:
            conn.request(method, path, body=payload, headers=hdrs)
            response = conn.getresponse()
            body = response.read()
            return Response(response.status, {k.lower(): v for k, v in response.getheaders()}, body)
        finally:
            conn.close()

    def get_json(self, path: str, status: int = 200, headers: dict | None = None):
        response = self.request(path, headers=headers)
        assert response.status == status, (path, response.status, response.body[:300])
        assert response.headers["content-type"].startswith("application/json")
        return response.json()


def serve(app: App):
    server = make_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    return server


@pytest.fixture(scope="session")
def repo_root(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("fixture")
    return make_repo(base / "repo", base / "outside")


@pytest.fixture()
def fresh_root(tmp_path) -> Path:
    return make_repo(tmp_path / "repo", tmp_path / "outside")


@pytest.fixture(scope="session")
def app(repo_root) -> App:
    return make_app(repo_root)


@pytest.fixture(scope="session")
def client(app):
    server = serve(app)
    yield Client(server, app)
    server.shutdown()
    server.server_close()


@pytest.fixture()
def serve_root():
    servers = []

    def start(root: Path, **kwargs) -> Client:
        app = kwargs.pop("app", None) or make_app(root)
        server = serve(app)
        servers.append(server)
        return Client(server, app)

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()
