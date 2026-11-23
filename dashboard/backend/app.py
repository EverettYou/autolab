"""Repository services used by the lab dashboard views."""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from .apidoc import ApiDocs
from . import catalog
from .catalog import FRONTEND, ROOT
from .links import Resolver
from .project_config import ConfigError, project_name
from .repo import Repo
from .site import ensure_site
from .wiki import Wiki


_YAML_UNSET = frozenset({"null", "none", "~", "true", "false"})


def _config_package(root: Path) -> str | None:
    """Import name from config.yml ``package:`` (None when unset / YAML null)."""
    path = root / "config.yml"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"(?m)^\s*package:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", text)
    if not match:
        return None
    name = match.group(1)
    if name.lower() in _YAML_UNSET:
        return None
    return name


class App:
    def __init__(self, root: str | os.PathLike | None = None, package: str | None = None,
                 package_dir: str | os.PathLike | None = None,
                 frontend: str | os.PathLike | None = None):
        root_path = Path(root or ROOT).resolve()
        catalog.ROOT = root_path
        self.repo = Repo(root_path)
        self.wiki = Wiki(self.repo)
        try:
            self.project_name = project_name(root_path)
        except ConfigError:
            self.project_name = None
        pkg = package if package is not None else _config_package(root_path)
        if package_dir is not None:
            resolved_package: Path | None = Path(package_dir)
        elif pkg:
            resolved_package = root_path / "lib" / "src" / pkg
        else:
            resolved_package = None
        self.apidocs = ApiDocs(pkg if pkg else "(none)", resolved_package)
        self.frontend = Path(frontend or FRONTEND).resolve()
        if self.frontend.is_dir():
            ensure_site(self.frontend / "site.json")

    @property
    def root(self):
        return self.repo.root

    def resolver(self):
        return Resolver(self)

    def warm(self) -> threading.Thread:
        """Build wiki / API / search indexes in the background."""

        def run() -> None:
            try:
                self.wiki.index()
                self.apidocs.index()
                from .semantic import schedule_index
                schedule_index(self)
            except Exception:  # noqa: BLE001 - warming is best effort
                pass

        thread = threading.Thread(target=run, name="dashboard-warm", daemon=True)
        thread.start()
        return thread
