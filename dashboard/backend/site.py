"""Dashboard display settings stored locally alongside the launcher state."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from threading import Lock

from . import catalog
from .catalog import FRONTEND
from .storage import atomic_write


settings_lock = Lock()
EMBEDDING_DEFAULT = 'text-embedding-3-small'
SEARCH_DEFAULT = 'gpt-4o'


def _settings_path():
    return catalog.ROOT / '.cache/dashboard/site.json'


@dataclass(frozen=True)
class SearchRuntime:
    enabled: bool
    key: str
    embedding_model: str
    search_model: str
    key_source: str


def read_settings():
    defaults = json.loads((FRONTEND / 'site.defaults.json').read_text())
    try:
        saved = json.loads(_settings_path().read_text())
    except (FileNotFoundError, ValueError):
        return defaults
    if not isinstance(saved, dict):
        return defaults
    merged = defaults | {key: saved[key] for key in defaults if key in saved}
    # Allow additive search settings without rejecting older saved files.
    if isinstance(saved.get('search'), dict):
        base = merged.get('search') if isinstance(merged.get('search'), dict) else {}
        merged['search'] = {**base, **saved['search']}
    return merged


def save_settings(data):
    document = data.get('document')
    if not isinstance(document, dict):
        raise ValueError('Expected a settings document.')
    with settings_lock:
        current = read_settings()
        updates = {key: document[key] for key in current if key in document}
        for key, value in updates.items():
            original = current[key]
            if type(value) is not type(original) or len(json.dumps(value)) > 4000:
                raise ValueError(f'Invalid value for {key}.')
            if isinstance(original, dict) and key != 'search' and (
                value.keys() != original.keys() or any(
                    type(value[name]) is not type(original[name]) for name in original
                )
            ):
                raise ValueError(f'Invalid settings in {key}.')
        result = current | updates
        if isinstance(document.get('search'), dict):
            result['search'] = {**(current.get('search') or {}), **document['search']}
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
        return result


def search_runtime(app=None) -> SearchRuntime:
    """Prefer local settings; fall back to OPENAI_* environment variables."""
    del app
    document = read_settings()
    search = document.get('search') if isinstance(document.get('search'), dict) else {}
    site_key = search.get('api_key')
    site_key = site_key.strip() if isinstance(site_key, str) else ''
    env_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if site_key:
        key, source = site_key, 'site'
    elif env_key:
        key, source = env_key, 'default'
    else:
        key, source = '', 'none'
    if isinstance(search.get('enabled'), bool):
        flag = search['enabled']
    elif site_key:
        flag = True
    else:
        flag = os.environ.get('OPENAI_CATALOG_SEARCH_ENABLED', '').strip().lower() in {'1', 'true', 'yes'}
    embedding = search.get('embedding_model') if isinstance(search.get('embedding_model'), str) else ''
    model = search.get('search_model') if isinstance(search.get('search_model'), str) else ''
    return SearchRuntime(
        enabled=bool(flag and key),
        key=key,
        embedding_model=embedding.strip() or os.environ.get('OPENAI_SEARCH_EMBEDDING_MODEL', EMBEDDING_DEFAULT),
        search_model=model.strip() or os.environ.get('OPENAI_SEARCH_MODEL', SEARCH_DEFAULT),
        key_source=source if key else 'none',
    )


def ensure_site(path=None) -> None:
    """Compatibility shim: EM settings live under `.cache/dashboard/site.json`."""
    del path
    _settings_path().parent.mkdir(parents=True, exist_ok=True)
