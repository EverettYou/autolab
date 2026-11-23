"""Local source editing and reproducible PDF builds for the Notes projects."""
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic

from . import catalog
from .catalog import FILE_LIMIT
from .storage import atomic_write

GRAPHICS = re.compile(r'(\\includegraphics\*?\s*(?:\[[^\]]*\]\s*)?\{)([^{}]+)(\})')
SOURCE_LIMIT = 1024 * 1024
source_lock = Lock()
build_lock = Lock()


class NoteConflict(Exception):
    """The requested source revision no longer matches the working copy."""


def project_directory(note_id):
    notes = catalog.ROOT / 'notes'
    if (not note_id or Path(note_id).name != note_id or note_id.startswith('.')
            or '\\' in note_id or '\0' in note_id):
        raise FileNotFoundError(note_id)
    project = notes / note_id
    if not project.is_dir() or project.resolve() != project:
        raise FileNotFoundError(note_id)
    return project


def project_file(path):
    return path.is_file() and not path.is_symlink()


def source_path(folder):
    """Prefer main.tex (canonical); accept legacy main.txt when present."""
    tex, txt = folder / 'main.tex', folder / 'main.txt'
    if project_file(tex):
        return tex
    if project_file(txt):
        return txt
    return None


def projects():
    result = []
    notes_root = catalog.ROOT / 'notes'
    if not notes_root.is_dir():
        return result
    for folder in sorted(notes_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith('.') or folder.is_symlink():
            continue
        source = source_path(folder)
        pdf = folder / 'main.pdf'
        has_source, has_pdf = source is not None, project_file(pdf)
        if not (has_source or has_pdf):
            continue
        assets = [
            path.relative_to(catalog.ROOT).as_posix()
            for path in sorted([*folder.glob('*.bib'), *(folder / 'figures').glob('*')])
            if path.suffix in {'.bib', '.png', '.pdf', '.svg'} and project_file(path)
            and path.resolve().is_relative_to(folder)
        ]
        result.append({'id': folder.name, 'title': folder.name,
                       'source': source.relative_to(catalog.ROOT).as_posix() if has_source else None,
                       'path': pdf.relative_to(catalog.ROOT).as_posix(), 'has_pdf': has_pdf, 'assets': assets})
    return result


def note_source(note_id):
    source = source_path(project_directory(note_id))
    if source is None:
        raise FileNotFoundError(note_id)
    return source


def snapshot(source):
    with source.open('rb') as stream:
        raw = stream.read(SOURCE_LIMIT + 1)
    if len(raw) > SOURCE_LIMIT:
        raise ValueError('Source file exceeds the editor limit.')
    return {'text': raw.decode('utf-8'), 'revision': sha256(raw).hexdigest()}


def read_note(note_id):
    return snapshot(note_source(note_id))


def save_note(note_id, text, revision):
    raw = text.encode('utf-8')
    if len(raw) > SOURCE_LIMIT:
        raise ValueError('Source file exceeds the editor limit.')
    with source_lock:
        source = note_source(note_id)
        current = snapshot(source)
        if current['revision'] != revision:
            raise NoteConflict('Source changed on disk. Your edits remain in the editor.')
        if text != current['text']:
            atomic_write(source, raw)
        return {'revision': sha256(raw).hexdigest()}


def prepare_source(source, document, build_dir):
    project = source.parent
    for match in GRAPHICS.finditer(document):
        rel = Path(match[2].strip())
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0] != 'figures':
            raise ValueError('Use a figure path inside this note project’s figures folder.')
        asset = project / rel
        if not project_file(asset) or asset.resolve() != asset:
            raise FileNotFoundError(asset)
        if asset.stat().st_size > FILE_LIMIT:
            raise ValueError('A figure exceeds the dashboard build size limit.')
        target = build_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, target)
    for bib in project.glob('*.bib'):
        if project_file(bib) and bib.stat().st_size <= FILE_LIMIT:
            shutil.copy2(bib, build_dir / bib.name)
    (build_dir / 'main.tex').write_text(document, encoding='utf-8')
    return 'main.tex'


def run_latex(command, build_dir, cancel=None):
    env = {**os.environ, 'openin_any': 'p', 'openout_any': 'p',
           'XDG_CACHE_HOME': str(build_dir / 'cache')}
    tex_bin = Path('/Library/TeX/texbin')
    if tex_bin.is_dir():
        env['PATH'] = str(tex_bin) + os.pathsep + env.get('PATH', '')
    with subprocess.Popen(command, cwd=build_dir, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, start_new_session=True) as job:
        deadline = monotonic() + 90
        while True:
            try:
                raw, _ = job.communicate(timeout=0.25 if cancel is not None else 90)
                break
            except subprocess.TimeoutExpired:
                if (cancel is not None and cancel.is_set()) or monotonic() >= deadline:
                    try:
                        os.killpg(job.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    job.communicate()
                    if cancel is not None and cancel.is_set():
                        raise BuildCancelled('Compilation stopped.') from None
                    raise ValueError('Compilation timed out.') from None
        return job.returncode, raw.decode('utf-8', errors='replace')[-16000:]


class BuildCancelled(Exception):
    pass


def compile_note(note_id, revision, cancel=None):
    if not build_lock.acquire(blocking=False):
        raise NoteConflict('A note is already compiling. Try again when it finishes.')
    try:
        source = note_source(note_id)
        before = snapshot(source)
        if before['revision'] != revision:
            raise NoteConflict('Source changed on disk. Reload before compiling.')
        engine = shutil.which('latexmk')
        if not engine and Path('/Library/TeX/texbin/latexmk').is_file():
            engine = '/Library/TeX/texbin/latexmk'
        if not engine:
            raise ValueError('Install latexmk and XeLaTeX to compile notes locally.')
        cache = source.parent / '.build'
        if cache.is_symlink():
            raise ValueError('The build directory cannot be a symlink.')
        cache.mkdir(exist_ok=True)
        with TemporaryDirectory(prefix='compile-', dir=cache) as temp:
            work = Path(temp)
            name = prepare_source(source, before['text'], work)
            code, log = run_latex([engine, '-norc', '-xelatex', '-latexoption=-no-shell-escape',
                                  '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
                                  '-latexoption=-synctex=1', name], work, cancel)
            atomic_write(cache / 'last-build.log', log.encode('utf-8'))
            candidate = work / 'main.pdf'
            if code or not candidate.is_file():
                return {'ok': False, 'log': log}
            if candidate.stat().st_size > FILE_LIMIT:
                return {'ok': False, 'log': log + '\nThe output exceeds the dashboard PDF size limit.'}
            raw = candidate.read_bytes()
            if not (raw.startswith(b'%PDF-') and raw.rstrip().endswith(b'%%EOF')):
                return {'ok': False, 'log': log + '\nInvalid PDF output.'}
            target = source.with_suffix('.pdf')
            with source_lock:
                if cancel is not None and cancel.is_set():
                    raise BuildCancelled('Compilation stopped.')
                if snapshot(source)['revision'] != revision:
                    raise NoteConflict('Source changed during compilation. The previous PDF was kept.')
                if target.is_symlink():
                    raise ValueError('The PDF destination must be a regular project file.')
                atomic_write(target, raw)
                sync = work / 'main.synctex.gz'
                if sync.is_file():
                    atomic_write(cache / 'main.synctex.gz', sync.read_bytes())
                    atomic_write(cache / 'synctex-revision', revision.encode())
            return {'ok': True, 'path': target.relative_to(catalog.ROOT).as_posix(), 'log': log}
    finally:
        build_lock.release()
