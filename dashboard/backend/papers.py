"""Notes project list, files and LaTeX compile API for this repository."""
from base64 import b64decode
from datetime import datetime, timezone
from hashlib import sha256
import mimetypes
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4

from . import catalog
from .catalog import FILE_LIMIT
from .notes import (
    BuildCancelled, NoteConflict, compile_note, project_directory, project_file,
    projects, read_note, save_note, snapshot,
)
from .storage import atomic_write

SOURCE = 'lab-notes'
TEXT = {'.txt', '.bib', '.tex', '.py', '.json', '.md'}
PATH_TYPES = TEXT | {'.png', '.svg', '.pdf'}
NAME_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._ -]{0,254}$')
jobs = {}
jobs_lock = Lock()
STATUS_FILE = '.project-status.json'


def note_entries():
    entries = []
    for row in projects():
        project = project_directory(row['id'])
        if row['source']:
            primary = project / Path(row['source']).name
        else:
            primary = project / 'main.pdf'
        status, _ = project_status(project)
        entries.append({
            'name': row['title'], 'path': row['id'],
            'status': status if row['source'] else 'finished',
            'modified_at': datetime.fromtimestamp(primary.stat().st_mtime, timezone.utc).isoformat(),
        })
    return {'entries': entries, 'errors': []}


def file_revision(path):
    st = path.stat()
    return sha256(f'{st.st_mtime_ns}:{st.st_size}:{path.name}'.encode()).hexdigest()


def file_entry(path, directory=False):
    entry = {
        'path': path.relative_to(catalog.ROOT / 'notes').as_posix(),
        'name': path.name,
        'extension': '' if directory else path.suffix.lower(),
        'directory': directory,
    }
    if not directory:
        entry['file_revision'] = file_revision(path)
    return entry


def project_status(folder):
    path = folder / STATUS_FILE
    if not project_file(path):
        # Stable until a status file exists so create/import does not invalidate it.
        return 'active', 'unset'
    try:
        import json
        data = json.loads(path.read_text(encoding='utf-8'))
        status = data.get('status') if isinstance(data, dict) else None
        if status not in {'active', 'inactive', 'finished', 'planning', 'archived'}:
            status = 'active'
        return status, file_revision(path)
    except (OSError, ValueError):
        return 'active', 'unset'


def details(project):
    folder = project_directory(project)
    entries = []
    for item in sorted(folder.iterdir(), key=lambda path: path.name.casefold()):
        if item.name.startswith('.'):
            continue
        if project_file(item) and item.suffix.lower() in PATH_TYPES:
            entries.append(file_entry(item))
        if item.is_dir() and not item.is_symlink() and item.resolve() == item:
            entries.append(file_entry(item, directory=True))
            if item.name == 'figures':
                entries.extend(file_entry(asset) for asset in sorted(item.iterdir())
                               if project_file(asset) and not asset.name.startswith('.')
                               and asset.suffix.lower() in PATH_TYPES)
    from .notes import source_path
    main, pdf = source_path(folder), folder / 'main.pdf'
    status, label_revision = project_status(folder)
    return {'entries': entries, 'errors': [],
            'status': status, 'label_revision': label_revision,
            'main': file_entry(main)['path'] if main is not None else None,
            'pdf': file_entry(pdf)['path'] if project_file(pdf) else None}


def file_path(raw, project=None):
    if not isinstance(raw, str) or '\\' in raw or '\0' in raw:
        raise FileNotFoundError(raw)
    path = PurePosixPath(raw)
    if path.is_absolute() or len(path.parts) < 2 or any(part.startswith('.') for part in path.parts):
        raise FileNotFoundError(raw)
    owner = path.parts[0]
    if project is not None and owner != project:
        raise FileNotFoundError(raw)
    folder = project_directory(owner)
    candidate = folder.joinpath(*path.parts[1:])
    if (len(path.parts) > 2 and (len(path.parts) != 3 or path.parts[1] != 'figures')
            or not project_file(candidate) or candidate.resolve() != candidate
            or candidate.suffix.lower() not in PATH_TYPES or candidate.stat().st_size > FILE_LIMIT):
        raise FileNotFoundError(raw)
    return candidate


def document(project, raw, metadata=False):
    candidate = file_path(raw, project)
    out = file_entry(candidate)
    out['editable'] = (
        candidate.parent == project_directory(project)
        and candidate.name in {'main.tex', 'main.txt'}
    )
    out['editor_sync'] = False
    if candidate.suffix.lower() in TEXT:
        source = snapshot(candidate)
        if metadata:
            source.pop('text')
        out.update(source)
        out['file_revision'] = out['revision']
    return out


def child_path(project, parent, name, *, directory=False):
    if not isinstance(name, str) or not NAME_OK.match(name) or name in {'.', '..'} or name.startswith('.'):
        raise ValueError('Invalid file name.')
    if parent in {project, '', None}:
        folder = project_directory(project)
        rel = PurePosixPath(project) / name
    else:
        parent_path = PurePosixPath(parent)
        if parent_path.parts[:1] != (project,) or any(part.startswith('.') for part in parent_path.parts):
            raise FileNotFoundError(parent)
        folder = project_directory(project).joinpath(*parent_path.parts[1:])
        if not folder.is_dir() or folder.is_symlink() or folder.resolve() != folder:
            raise FileNotFoundError(parent)
        allowed = {'figures', 'scripts', 'data'}
        if len(parent_path.parts) > 2 or (
            len(parent_path.parts) == 2 and parent_path.parts[1] not in allowed
        ):
            raise ValueError(
                'New files may only be created in the project root, figures/, scripts/, or data/.'
            )
        rel = parent_path / name
    target = folder / name
    if directory:
        if target.exists():
            raise ValueError('That folder already exists.')
        target.mkdir()
        return {'path': rel.as_posix()}
    if target.suffix.lower() not in PATH_TYPES:
        raise ValueError('Unsupported file type.')
    if target.exists():
        raise ValueError('That file already exists.')
    if target.suffix.lower() in TEXT:
        atomic_write(target, b'')
    else:
        atomic_write(target, b'')
    return {'path': rel.as_posix(), 'file_revision': file_revision(target)}


def import_file(project, parent, name, data):
    if not isinstance(data, str):
        raise ValueError('Expected base64 file data.')
    raw = b64decode(data)
    if len(raw) > FILE_LIMIT:
        raise ValueError('File exceeds the dashboard size limit.')
    created = child_path(project, parent, name)
    target = catalog.ROOT / 'notes' / created['path']
    atomic_write(target, raw)
    created['file_revision'] = file_revision(target)
    return created


def set_status(project, status, revision):
    folder = project_directory(project)
    current, label_revision = project_status(folder)
    if revision not in {None, '', label_revision}:
        raise NoteConflict('Project status changed on disk. Reload before updating.')
    if status == 'automatic':
        path = folder / STATUS_FILE
        if project_file(path):
            path.unlink()
        return {'status': 'active', 'label_revision': 'unset'}
    if status not in {'active', 'inactive', 'finished', 'planning', 'archived'}:
        raise ValueError('Unknown project status.')
    import json
    path = folder / STATUS_FILE
    atomic_write(path, (json.dumps({'status': status}, indent=2) + '\n').encode())
    return {'status': status, 'label_revision': file_revision(path)}


def mutate_path(project, raw, action, *, name=None, revision=None):
    if action == 'reveal':
        # Dashboard runs headless; acknowledge without shelling out.
        return {'ok': True, 'path': raw}
    if action not in {'rename', 'delete'}:
        raise FileNotFoundError(action)
    path = PurePosixPath(raw)
    folder = project_directory(project)
    if path.parts[0] != project:
        raise FileNotFoundError(raw)
    target = folder.joinpath(*path.parts[1:])
    if target.resolve() != target or any(part.startswith('.') for part in path.parts):
        raise FileNotFoundError(raw)
    if target.is_dir() and not target.is_symlink():
        if action == 'delete':
            if any(target.iterdir()):
                raise ValueError('Delete folder contents first.')
            target.rmdir()
            return {'ok': True}
        if not isinstance(name, str) or not NAME_OK.match(name):
            raise ValueError('Invalid folder name.')
        dest = target.with_name(name)
        if dest.exists():
            raise ValueError('That name is already taken.')
        target.rename(dest)
        return {'path': dest.relative_to(catalog.ROOT / 'notes').as_posix()}
    candidate = file_path(raw, project)
    if revision and revision != file_revision(candidate):
        raise NoteConflict('File changed on disk. Reload before renaming or deleting.')
    if action == 'delete':
        if candidate.name in {'main.tex', 'main.txt', 'main.pdf'}:
            raise ValueError('The main manuscript files cannot be deleted here.')
        candidate.unlink()
        return {'ok': True}
    if not isinstance(name, str) or not NAME_OK.match(name):
        raise ValueError('Invalid file name.')
    dest = candidate.with_name(name)
    if dest.suffix.lower() not in PATH_TYPES:
        raise ValueError('Unsupported file type.')
    if dest.exists():
        raise ValueError('That name is already taken.')
    candidate.rename(dest)
    return {'path': dest.relative_to(catalog.ROOT / 'notes').as_posix(),
            'file_revision': file_revision(dest)}


def selected_source(project, raw):
    from .notes import source_path
    source = source_path(project_directory(project))
    if source is None:
        raise FileNotFoundError(raw)
    expected = f'{project}/{source.name}'
    if raw not in {expected, f'{project}/main.tex', f'{project}/main.txt'}:
        raise FileNotFoundError(raw)
    return read_note(project)


def job_payload(job):
    return {key: job[key] for key in ('job', 'main', 'state', 'detail', 'log', 'result')} | {
        'elapsed_seconds': (job.get('finished') or monotonic()) - job['started'],
        'cancellable': job['state'] == 'running' and not job['cancel'].is_set(),
    }


def build(project, main):
    revision = selected_source(project, main)['revision']
    with jobs_lock:
        if any(job['state'] == 'running' for job in jobs.values()):
            raise NoteConflict('A note compile is already running.')
        for key in [key for key, value in jobs.items() if value['project'] == project]:
            del jobs[key]
        job = {'job': uuid4().hex, 'project': project, 'main': main,
               'state': 'running', 'detail': 'Compiling with XeLaTeX',
               'started': monotonic(), 'cancel': Event(), 'log': '', 'result': None}
        jobs[job['job']] = job

    def run():
        try:
            result = compile_note(project, revision, job['cancel'])
            final = {'state': 'succeeded' if result['ok'] else 'failed',
                     'log': result.get('log', ''),
                     'detail': 'Compiled' if result['ok'] else 'Compilation failed',
                     'result': {'main': main, 'path': result['path'].removeprefix('notes/')}
                     if result['ok'] else None}
        except BuildCancelled as error:
            final = {'state': 'cancelled', 'detail': str(error)}
        except (NoteConflict, ValueError, OSError) as error:
            final = {'state': 'failed', 'detail': str(error), 'log': str(error)}
        with jobs_lock:
            job.update(final, finished=monotonic())

    Thread(target=run, daemon=True).start()
    with jobs_lock:
        return job_payload(job)


def build_status(project, job_id, stop=False):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job['project'] != project:
            raise FileNotFoundError(job_id)
        if stop and job['state'] == 'running':
            job['cancel'].set()
            job['detail'] = 'Stopping compilation'
        return job_payload(job)


def synchronize(project, main, query):
    source = selected_source(project, main)
    project_dir = project_directory(project)
    cache = project_dir / '.build'
    revision = cache / 'synctex-revision'
    program = shutil.which('synctex') or '/Library/TeX/texbin/synctex'
    if (cache.is_symlink() or not project_file(revision)
            or revision.read_text() != source['revision']
            or not project_file(cache / 'main.synctex.gz') or not Path(program).is_file()):
        return {'available': False}
    # SyncTeX names the staged source main.tex and returns local page coordinates.
    pdf = str(project_dir / 'main.pdf')
    direction = query.get('direction', '')
    if direction == 'forward':
        line, column = int(query.get('line', '1')), int(query.get('column', '1'))
        command = [program, 'view', '-i', f'{line}:{column}:./main.tex', '-o', pdf, '-d', str(cache)]
    elif direction == 'inverse':
        page, x, y = int(query['page']), float(query['x']), float(query['y'])
        command = [program, 'edit', '-o', f'{page}:{x}:{y}:{pdf}', '-d', str(cache)]
    else:
        raise ValueError('Unknown synchronization direction.')
    try:
        output = subprocess.run(command, capture_output=True, text=True, timeout=4, cwd=cache).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {'available': False}
    fields = dict(re.findall(r'^(Page|x|y|h|v|Line|Column):([-\d.]+)', output, re.M))
    if direction == 'forward' and {'Page', 'x', 'y'} <= fields.keys():
        return {'available': True, 'page': int(fields['Page']),
                'x': float(fields['x']), 'y': float(fields['y'])}
    if direction == 'inverse' and 'Line' in fields:
        return {'available': True, 'path': main, 'line': int(fields['Line']),
                'column': max(1, int(fields.get('Column', '1')))}
    return {'available': False}


def read(route, query):
    if query.get('source') != SOURCE:
        raise FileNotFoundError('Unknown Notes workspace.')
    project = query.get('project', '')
    if route == 'projects':
        return note_entries()
    if route == 'project':
        return details(project)
    if route in {'project/document', 'project/document-meta'}:
        return document(project, query['path'], metadata=route.endswith('-meta') or query.get('meta') == '1')
    if route == 'project/build':
        return build_status(project, query.get('job'))
    if route == 'project/sync':
        return synchronize(project, query.get('main'), query)
    if route in {'file', 'image'}:
        path = file_path(query['path'])
        return mimetypes.guess_type(path)[0] or 'application/octet-stream', path
    raise FileNotFoundError(route)


def write(route, data):
    if data.get('source') != SOURCE or not isinstance(data.get('project'), str):
        raise FileNotFoundError('Unknown Notes workspace.')
    project = data['project']
    if route == 'project/save':
        selected_source(project, data.get('path'))
        if not isinstance(data.get('text'), str) or not isinstance(data.get('revision'), str):
            raise ValueError('Invalid source text or revision.')
        return save_note(project, data['text'], data['revision'])
    if route == 'project/compile/start':
        return build(project, data.get('main'))
    if route == 'project/compile/stop':
        return build_status(project, data.get('job'), stop=True)
    if route == 'project/status':
        return set_status(project, data.get('status'), data.get('revision'))
    if route == 'project/create':
        return child_path(project, data.get('parent'), data.get('name'),
                          directory=data.get('kind') == 'folder')
    if route == 'project/import':
        return import_file(project, data.get('parent'), data.get('name'), data.get('data'))
    if route == 'project/editor-sync':
        # Agent handoff is disabled until multi-writer editing is wired; keep the UI polling path live.
        return {'handoff': None}
    if route in {'project/rename', 'project/delete', 'project/reveal'}:
        return mutate_path(
            project, data.get('path'), route.rsplit('/', 1)[-1],
            name=data.get('name'), revision=data.get('revision'),
        )
    raise FileNotFoundError(route)
