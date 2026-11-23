"""Build the dashboard view from repository files."""
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'dashboard/frontend'
PUBLIC_FOLDERS = {'labs', 'notes', 'wiki', 'references', 'skills'}
DOCUMENT_TYPES = {'.md', '.txt', '.tex', '.json', '.py', '.bib'}
ASSET_TYPES = {'.png', '.svg', '.pdf'}
LAB_ID = re.compile(r'^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$')
FILE_LIMIT = 4 * 1024 * 1024


def confined(base, raw):
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or '\\' in raw or '\0' in raw:
        raise FileNotFoundError(raw)
    if any(part.startswith('.') for part in path.parts):
        raise FileNotFoundError(raw)
    target = base.joinpath(*path.parts).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise FileNotFoundError(raw)
    return target


def research_file(raw, suffixes):
    target = confined(ROOT, raw)
    path = target.relative_to(ROOT)
    if path.parts[0] not in PUBLIC_FOLDERS and str(path) != 'README.md':
        raise FileNotFoundError(raw)
    if any(part in {'handoff-provenance', 'data', 'checkpoints', 'logs'} or part.startswith('_')
           for part in path.parts):
        raise FileNotFoundError(raw)
    if path.suffix not in suffixes or target.stat().st_size > FILE_LIMIT:
        raise FileNotFoundError(raw)
    return target


def entry(path, title=None):
    absolute = ROOT / path
    if title is None:
        title = next(
            (line[2:].strip() for line in absolute.read_text().splitlines() if line.startswith('# ')),
            absolute.stem,
        )
    return {'path': path, 'title': title}


def catalog():
    labs = []
    labs_index = ROOT / 'labs/labs.json'
    if labs_index.is_file():
        try:
            index = json.loads(labs_index.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            index = {'labs': []}
        for lab in sorted(index.get('labs') or [], key=lambda row: row.get('id', ''), reverse=True):
            lab_id = lab.get('id', '')
            if not LAB_ID.fullmatch(lab_id):
                continue
            folder = f'labs/{lab_id}'
            labs.append({**lab, 'path': f'{folder}/REPORT.md', 'plan': f'{folder}/PLAN.md'})
    from .notes import projects

    notes = projects()
    wiki_root = ROOT / 'wiki'
    wiki = []
    if wiki_root.is_dir():
        wiki = [
            entry(path.relative_to(ROOT).as_posix())
            for path in sorted(wiki_root.rglob('*.md'))
            if path.name not in {'README.md', 'index.md'}
            and 'records' not in path.parts
        ]
    skills_root = ROOT / 'skills'
    skills = []
    if skills_root.is_dir():
        skills = [
            entry(path.relative_to(ROOT).as_posix())
            for path in sorted(skills_root.glob('*/SKILL.md'))
        ]
    overview = [note for note in notes if note['source']]
    if (ROOT / 'wiki/concepts/notation.md').is_file():
        overview.append(entry('wiki/concepts/notation.md', 'Notation guide'))
    references = [entry(note['path'], note['title']) for note in notes if not note['source']]
    if (ROOT / 'references/README.md').is_file():
        references.append(entry('references/README.md', 'Reference provenance'))
    return {
        'labs': labs,
        'notes': notes,
        'wiki': wiki,
        'references': references,
        'skills': skills,
        'overview': overview,
    }
