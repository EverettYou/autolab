"""Serve the lab dashboard on the local machine."""
from __future__ import annotations

import argparse
import email.utils
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import gzip
import hashlib
import json
import mimetypes
import os
import re
import subprocess
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .backend.catalog import ASSET_TYPES, DOCUMENT_TYPES, FRONTEND, catalog, confined, research_file
from .backend import threads_write, loop_control, papers, search, sections, site, skills, system_status
from .backend.app import App
from .backend.repo import BadRequest, DashboardError, RAW_LIMIT
from .backend.notes import SOURCE_LIMIT, NoteConflict, compile_note, read_note, save_note

MODULE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
PAGE_ROUTES = {
    'references', 'labs', 'wiki', 'notes', 'threads', 'files', 'search',
    'auto-research', 'skills', 'settings', 'pdf', 'image', 'view', 'apidocs',
}
CONTENT_POLICY = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
    "object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
)
RAW_POLICY = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; frame-ancestors 'self'"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8040
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
CHUNK = 64 * 1024
RANGE_RE = re.compile(r"\s*bytes=(\d*)-(\d*)\s*")


def meta(app: App):
    try:
        commit = subprocess.check_output(
            ['git', 'rev-parse', '--short=7', 'HEAD'], cwd=app.root,
            text=True, stderr=subprocess.DEVNULL, timeout=2,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {'commit': commit}


def discussion_action(app: App, path, data):
    """Route dashboard discussion writes through the research-threads threads store contract."""
    parts = path.strip('/').split('/')
    body = dict(data)
    if 'content' not in body and isinstance(body.get('text'), str):
        body['content'] = body['text']
    if parts == ['api', 'threads'] or parts == ['api', 'threads', 'new']:
        return threads_write.open_thread(app, body)
    if len(parts) == 4 and parts[3] == 'messages':
        return threads_write.reply_thread(app, parts[2], body)
    if len(parts) == 4 and parts[3] == 'close':
        return threads_write.close_thread(app, parts[2], body)
    if len(parts) == 4 and parts[3] == 'reopen':
        return threads_write.reopen_thread(app, parts[2], body)
    if len(parts) == 3 and parts[2] == 'reply':
        return threads_write.reply_thread(app, body.get('id') or body.get('thread_id'), body)
    if len(parts) == 3 and parts[2] == 'status':
        status = body.get('status')
        thread_id = body.get('id') or body.get('thread_id')
        if status in {'closed', 'resolved'}:
            return threads_write.close_thread(app, thread_id, body)
        if status == 'open':
            return threads_write.reopen_thread(app, thread_id, body)
        raise BadRequest('status must be open or closed')
    raise FileNotFoundError(path)


def catalog_api(app: App, path, query):
    head, _, rest = path.partition('/')
    value = lambda key, default='': query.get(key, default)
    if path == 'home':
        return sections.home(app)
    if path == 'meta':
        return meta(app)
    if path == 'features':
        root = app.root
        notes_dir = root / 'notes'
        notes_on = notes_dir.is_dir() and any(p.is_dir() for p in notes_dir.iterdir())
        lib_on = (root / 'lib' / 'src').is_dir() and any((root / 'lib' / 'src').iterdir())
        # Also honor config.yml features when present
        cfg = root / 'config.yml'
        if cfg.is_file():
            try:
                text = cfg.read_text(encoding='utf-8')
                def flag(name: str):
                    match = re.search(rf'(?m)^\s*{name}\s*:\s*(true|false)\s*$', text)
                    return None if match is None else match.group(1) == 'true'
                notes_flag, lib_flag = flag('notes'), flag('lib')
                if notes_flag is not None:
                    notes_on = notes_flag and notes_dir.is_dir()
                if lib_flag is not None:
                    lib_on = lib_flag and (root / 'lib').is_dir()
            except OSError:
                pass
        return {'notes': notes_on, 'lib': lib_on, 'threads': True}

    if path == 'settings':
        return {'document': site.read_settings()}
    if head == 'labs':
        return sections.lab_detail(app, rest, query.get('doc') or None) if rest else sections.labs_list(app)
    if head == 'wiki':
        if rest == 'graph':
            return app.wiki.graph()
        return sections.wiki_page(app, rest) if rest else sections.wiki_tree(app)
    if head == 'references':
        return sections.reference_detail(app, rest) if rest else sections.references_list(app)
    if head == 'skills':
        return skills.skill(app, rest) if rest else skills.catalog(app)
    if head in {'threads', 'discussion'}:
        return sections.thread_detail(app, rest) if rest else sections.discussion_list(app, value('status') or None)
    if head == 'auto-research':
        if rest == 'system':
            return system_status.collect(app.root)
        return sections.task_item(app, rest) if rest else sections.auto_research(app)
    if head == 'apidocs':
        private = value('private', '') in {'1', 'true', 'yes'}
        if not rest:
            return app.apidocs.tree(private, app.root)
        if rest == 'search':
            return {'query': value('q'), 'results': app.apidocs.search(value('q'), private)}
        if not MODULE_NAME.match(rest):
            raise BadRequest('invalid module name')
        payload = app.apidocs.module(rest, private, app.root)
        if payload is None:
            route = app.apidocs.route_for(rest)
            if route and not route.startswith(f'/apidocs/{rest}#') and route != f'/apidocs/{rest}':
                return {'redirect': route}
            raise FileNotFoundError(rest)
        return payload
    if path == 'search':
        return search.search(
            app, value('q'),
            limit=max(1, min(500, int(value('limit', '12')))),
            include_private=value('private', '') in {'1', 'true', 'yes'},
            refine=value('refine', '') in {'1', 'true', 'yes'},
            scope=value('scope', 'all') or 'all',
            stage=value('stage', 'lexical') or 'lexical',
        )
    if path == 'file':
        return sections.file_view(app, value('path'))
    if path == 'fs':
        return sections.fs_listing(app, value('path'))
    if path == 'resolve':
        return {'resolved': app.resolver().href(value('href'), value('source') or None)}
    raise FileNotFoundError(path)


class Dashboard(BaseHTTPRequestHandler):
    @property
    def app(self) -> App:
        return self.server.app

    def do_GET(self):
        self.serve()

    def do_HEAD(self):
        self.serve()

    def do_POST(self):
        host = self.local_host()
        if not host or self.headers.get('Origin') != f'http://{host}':
            self.respond_json({'error': 'Edit requests must come from this dashboard.'}, 403)
            return
        if self.headers.get_content_type() != 'application/json':
            self.respond_json({'error': 'Expected a JSON request.'}, 415)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 2 * SOURCE_LIMIT:
                raise ValueError('Edit request is too large or empty.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            if (self.path == '/api/discussion' or self.path.startswith('/api/discussion/')
                    or self.path == '/api/threads' or self.path.startswith('/api/threads/')):
                # Normalize /api/threads → /api/discussion for the write router
                path = self.path.replace('/api/threads', '/api/discussion', 1)
                self.respond_json(discussion_action(self.app, path, data))
                return
            if self.path.startswith('/api/workspaces/'):
                self.respond_json(papers.write(self.path.removeprefix('/api/workspaces/'), data))
                return
            if self.path == '/api/auto-research/order':
                loop_control.move(
                    self.app.root,
                    data.get('id') or data.get('item_id') or '',
                    before=data.get('before'),
                    after=data.get('after'),
                )
                self.respond_json(sections.auto_research(self.app))
                return
            if self.path == '/api/settings':
                self.respond_json({'document': site.save_settings(data)})
                return
            note_id, revision = data['id'], data['revision']
            if not isinstance(note_id, str) or not isinstance(revision, str):
                raise ValueError('Invalid note identifier or revision.')
            if self.path == '/api/notes/save':
                if not isinstance(data['text'], str):
                    raise ValueError('Invalid source text.')
                self.respond_json(save_note(note_id, data['text'], revision))
            elif self.path == '/api/notes/compile':
                self.respond_json(compile_note(note_id, revision))
            else:
                raise FileNotFoundError(self.path)
        except NoteConflict as error:
            self.respond_json({'error': str(error)}, 409)
        except BadRequest as error:
            self.respond_json({'error': str(error)}, 400)
        except FileNotFoundError:
            self.respond_json({'error': 'This note or input file is unavailable.'}, 404)
        except (ValueError, KeyError, TypeError) as error:
            self.respond_json({'error': str(error)}, 400)
        except OSError:
            self.respond_json({'error': 'The note could not be written or compiled.'}, 500)

    def local_host(self):
        host = self.headers.get('Host')
        port = self.server.server_port
        return host if host in {f'127.0.0.1:{port}', f'localhost:{port}'} else None

    def _etag_matches(self, etag: str) -> bool:
        raw = self.headers.get('If-None-Match')
        if not raw:
            return False
        tags = {part.strip() for part in raw.split(',')}
        return '*' in tags or etag in tags or f'W/{etag}' in tags

    def respond(self, code, kind, body, policy=None, download=None):
        if not isinstance(body, (bytes, bytearray)):
            body = bytes(body)
        etag = '"' + hashlib.sha1(body).hexdigest()[:20] + '"' if code == 200 else None
        if etag and self._etag_matches(etag):
            self.send_response(304)
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            return
        encoding = None
        if (code == 200 and len(body) >= 512 and not download
                and (kind.startswith('text/') or kind.startswith('application/json')
                     or kind in {'application/javascript', 'text/javascript', 'image/svg+xml'})
                and 'gzip' in (self.headers.get('Accept-Encoding') or '')):
            body, encoding = gzip.compress(body, compresslevel=5), 'gzip'
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Content-Security-Policy', policy or CONTENT_POLICY)
        if download:
            from urllib.parse import quote
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(download, safe=''))
        if encoding:
            self.send_header('Content-Encoding', encoding)
            self.send_header('Vary', 'Accept-Encoding')
        if etag:
            self.send_header('ETag', etag)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def respond_json(self, payload, code=200):
        self.respond(code, 'application/json; charset=utf-8',
                     json.dumps(payload, ensure_ascii=False).encode())

    def _redirect_document_pdf(self, byte_path: str) -> bool:
        """Send a browser page-load of a PDF to the reader. Fetches and range requests keep the bytes."""
        if self.command != 'GET' or self.headers.get('Range'):
            return False
        if (self.headers.get('Sec-Fetch-Dest') or '').lower() != 'document':
            return False
        location = '/pdf?src=' + quote(byte_path, safe='')
        self.send_response(302)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        return True

    def respond_file(self, path: Path, kind: str, *, policy=None, download=None, inline_name=None):
        """Serve a file with Accept-Ranges / Range / ETag support for PDF.js and large assets."""
        st = path.stat()
        size = st.st_size
        etag = f'"{st.st_mtime_ns:x}-{size:x}"'
        last_modified = email.utils.formatdate(st.st_mtime, usegmt=True)
        if self._etag_matches(etag):
            self.send_response(304)
            self.send_header('ETag', etag)
            self.send_header('Last-Modified', last_modified)
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            return
        start, end = 0, size - 1
        status = 200
        range_header = self.headers.get('Range')
        if_range = self.headers.get('If-Range')
        if range_header and (not if_range or if_range == etag or if_range == last_modified):
            match = RANGE_RE.fullmatch(range_header)
            if match and (match.group(1) or match.group(2)):
                if match.group(1):
                    start = int(match.group(1))
                    end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
                else:
                    start = max(0, size - int(match.group(2)))
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    return
                status = 206
        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Last-Modified', last_modified)
        self.send_header('ETag', etag)
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Security-Policy', policy or CONTENT_POLICY)
        self.send_header('X-Content-Type-Options', 'nosniff')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if download:
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(download, safe=''))
        elif inline_name:
            ascii_name = inline_name.encode('ascii', 'replace').decode().replace('"', '_')
            self.send_header(
                'Content-Disposition',
                f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(inline_name, safe="")}',
            )
        self.end_headers()
        if self.command == 'HEAD' or not length:
            return
        with path.open('rb') as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(CHUNK, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def serve(self):
        if not self.local_host():
            self.respond_json({'error': 'Open the dashboard on localhost.'}, 403)
            return
        url = urlsplit(self.path)
        path = unquote(url.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        app = self.app
        try:
            if path == '/api/health':
                located, error = app.apidocs.locate()
                self.respond_json({
                    'ok': True,
                    'pid': os.getpid(),
                    'name': getattr(app, 'project_name', None),
                    'root': str(app.root),
                    'package': {
                        'name': app.apidocs.package,
                        'location': str(located) if located else None,
                        'error': error,
                    },
                })
                return
            if path == '/api/catalog':
                self.respond_json(catalog())
                return
            if path == '/api/notes/source':
                self.respond_json(read_note(query.get('id', '')))
                return
            if path == '/api/document':
                name = query.get('path', '')
                file = research_file(name, DOCUMENT_TYPES)
                self.respond_json({'path': name, 'text': file.read_text(encoding='utf-8')})
                return
            if path.startswith('/api/workspaces/'):
                payload = papers.read(path.removeprefix('/api/workspaces/'), query)
                if isinstance(payload, tuple):
                    kind, data = payload
                    if isinstance(data, (bytes, bytearray)):
                        self.respond(200, kind, data, policy=RAW_POLICY)
                    else:
                        self.respond_file(Path(data), kind, policy=RAW_POLICY)
                else:
                    self.respond_json(payload)
                return
            if path.startswith('/api/'):
                self.respond_json(catalog_api(app, path.removeprefix('/api/'), query))
                return
            if path == '/static/site.json':
                self.respond_json(site.read_settings())
                return
            frontend = app.frontend
            if path == '/favicon.svg':
                file = frontend / 'favicon.svg'
            elif path.startswith('/static/'):
                file = confined(frontend, path.removeprefix('/static/'))
            elif path.startswith('/raw/') or (path.startswith('/references/') and path.endswith('/paper.pdf')):
                if path.startswith('/raw/'):
                    _, file = app.repo.resolve(path.removeprefix('/raw/'))
                else:
                    file = sections.reference_pdf(app, path.split('/')[2])
                if not file.is_file() or file.stat().st_size > RAW_LIMIT:
                    raise FileNotFoundError(path)
                kind = mimetypes.guess_type(file)[0] or 'application/octet-stream'
                if kind == 'application/pdf' and self._redirect_document_pdf(path):
                    return
                inline = kind == 'application/pdf' or kind.startswith('image/')
                self.respond_file(
                    file, kind, policy=RAW_POLICY,
                    download=None if inline else file.name,
                    inline_name=file.name if inline else None,
                )
                return
            elif path == '/' or path.strip('/').split('/')[0] in PAGE_ROUTES:
                file = frontend / 'index.html'
            else:
                raise FileNotFoundError(path)
            if not file.is_file():
                raise FileNotFoundError(path)
            content_type = mimetypes.guess_type(file)[0] or 'application/octet-stream'
            if file.suffix in {'.js', '.mjs'}:
                content_type = 'text/javascript'
            self.respond(200, content_type, file.read_bytes(), policy=CONTENT_POLICY)
        except DashboardError as error:
            self.respond_json({'error': str(error)}, error.status)
        except (FileNotFoundError, IsADirectoryError):
            self.respond_json({'error': 'This file is unavailable.'}, 404)
        except (ValueError, KeyError, TypeError):
            self.respond_json({'error': 'Invalid request.'}, 400)
        except OSError:
            self.respond_json({'error': 'The research catalog could not be read.'}, 500)


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app: App):
        super().__init__(address, Dashboard)
        self.app = app


def make_server(app: App, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> DashboardServer:
    """Construct a dashboard server bound to ``(host, port)`` for the given app."""
    return DashboardServer((host, port), app)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=os.environ.get('LAB_DASHBOARD_HOST', DEFAULT_HOST))
    parser.add_argument('--port', type=int, default=int(os.environ.get('LAB_DASHBOARD_PORT', DEFAULT_PORT)))
    parser.add_argument('--root', default=None, help='repository root (default: this checkout)')
    args = parser.parse_args(argv)
    app = App(args.root) if args.root else App()
    app.warm()
    try:
        server = make_server(app, args.host, args.port)
    except OSError as exc:
        print(f'dashboard: cannot listen on {args.host}:{args.port}: {exc}', flush=True)
        return 1
    print(f'Lab · http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
