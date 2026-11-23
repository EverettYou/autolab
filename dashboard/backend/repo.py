"""Read-only access to the repository: the path policy, cached reads and file classification.

Every file the dashboard shows is read at request time. Parsed JSON and text are cached by
``(st_mtime_ns, st_size)``, so an edit is visible on the next request while unchanged files cost a
single ``stat``. Missing or partially written files never raise: :meth:`Repo.load_json` returns
the data together with a human-readable warning that the API passes on to the page.
"""

from __future__ import annotations

import codecs
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEXT_PREVIEW_LIMIT = 2 * 1024 * 1024
RAW_LIMIT = 64 * 1024 * 1024
LISTING_LIMIT = 2000
SNIFF_BYTES = 8192
# Folder scans for lab and reference ids are redone at least this often (seconds): writing a
# lab.json into an existing folder does not change the parent folder's mtime.
IDS_TTL = 2.0

# Top-level folders excluded from the dashboard browser.
EXCLUDED_TOP = frozenset({"lib", "documents"})
EXCLUDED_PARTS = frozenset({"data", "checkpoints", "logs", "handoff-provenance", "__pycache__"})
EXCLUDED_SUFFIXES = frozenset({".mps", ".npz", ".npy", ".h5", ".hdf5", ".pkl", ".pickle"})


def public_parts(parts):
    return (not parts or parts[0] not in EXCLUDED_TOP) and not any(
        part.startswith((".", "_")) or part in EXCLUDED_PARTS or
        Path(part).suffix.lower() in EXCLUDED_SUFFIXES or part.lower().endswith(".mps.pkl.gz")
        for part in parts
    )
# Noise hidden from directory listings (still reachable by an explicit path).
HIDDEN_NAMES = frozenset({"__pycache__"})

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
LAB_STAGES = ("active", "blocked", "complete", "inactive")

IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".svg": "image/svg+xml", ".bmp": "image/bmp", ".ico": "image/x-icon",
    ".avif": "image/avif",
}
MARKDOWN_EXTS = frozenset({".md", ".markdown"})
JSON_EXTS = frozenset({".json", ".ipynb", ".geojson"})
LANGUAGES = {
    ".py": "python", ".pyi": "python", ".pyx": "cython", ".pxd": "cython", ".sh": "shell",
    ".bash": "shell", ".zsh": "shell", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript",
    ".json": "json", ".jsonl": "json", ".ipynb": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".ini": "ini", ".cfg": "ini", ".md": "markdown", ".markdown": "markdown",
    ".tex": "latex", ".bib": "bibtex", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".hpp": "cpp", ".cu": "cuda", ".css": "css", ".html": "html", ".htm": "html", ".xml": "xml",
    ".csv": "csv", ".tsv": "tsv", ".txt": "text", ".log": "text", ".out": "text", ".err": "text",
    ".rst": "rst", ".sql": "sql", ".r": "r", ".jl": "julia", ".rs": "rust", ".go": "go",
    ".java": "java", ".diff": "diff", ".patch": "diff", ".lock": "text", ".stim": "text",
    ".dem": "text", ".alist": "text", ".mtx": "text", ".cmake": "cmake", ".mk": "make",
    ".conf": "text", ".env": "text", ".sty": "latex", ".cls": "latex", ".bst": "text",
}
TEXT_NAMES = frozenset({"Makefile", "Dockerfile", "LICENSE", "README", "COPYING", "NOTICE", "CITATION"})
BINARY_EXTS = frozenset({
    ".pt", ".pth", ".ckpt", ".npz", ".npy", ".safetensors", ".bin", ".so", ".o", ".a", ".pyc",
    ".zip", ".gz", ".tgz", ".tar", ".bz2", ".xz", ".zst", ".7z", ".h5", ".hdf5", ".pkl",
    ".pickle", ".parquet", ".feather", ".arrow", ".db", ".sqlite", ".onnx", ".whl", ".exe", ".dll",
    ".dylib", ".class", ".jar", ".mp4", ".mov", ".mp3", ".wav", ".woff", ".woff2", ".ttf", ".otf",
    ".eot", ".xlsx", ".docx", ".pptx", ".b8", ".joblib", ".mat", ".sav", ".dat",
})


class DashboardError(Exception):
    """A request the dashboard refuses; the message is safe to show to the client."""

    status = 400


class BadRequest(DashboardError):
    status = 400


class Forbidden(DashboardError):
    status = 403


class NotFound(DashboardError):
    status = 404


class Conflict(DashboardError):
    status = 409


def iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_rel(raw: str | None) -> str:
    """Return a clean repository-relative POSIX path, or raise.

    Refuses absolute paths, parent traversal, NUL bytes, backslashes, any dot-prefixed component
    (``.git``, ``.venv``, ``.tmp``, dotfiles) and the excluded top-level folders.
    """
    if raw is None:
        raise BadRequest("a path is required")
    if "\x00" in raw or "\\" in raw:
        raise BadRequest("invalid characters in path")
    text = raw.strip()
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text) or text.startswith("~"):
        raise Forbidden("absolute paths are not served")
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise Forbidden("the path leaves the repository")
        if part.startswith("."):
            raise Forbidden("hidden files and folders are not served")
        parts.append(part)
    if parts and parts[0] in EXCLUDED_TOP:
        raise Forbidden(f"{parts[0]}/ is not shown on the dashboard")
    return "/".join(parts)


def valid_id(value: str, what: str = "identifier") -> str:
    if not isinstance(value, str) or not ID_PATTERN.match(value) or ".." in value:
        raise BadRequest(f"invalid {what}")
    return value


def text_value(value: Any) -> str | None:
    """A display string for a scalar JSON value, or None for missing/structured values."""
    if value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float)) and str(item)]


def records(data: Any, key: str) -> list[dict]:
    """The dict records under ``data[key]`` (or ``data`` itself when it is a list) whose ``id`` is a
    valid identifier; other entries cannot be addressed by a route and are skipped."""
    items = data.get(key) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)
            and ID_PATTERN.match(item["id"]) and ".." not in item["id"]]


def kind_for_name(name: str) -> str | None:
    """Classify a file by name alone; None means the content must be sniffed."""
    suffix = os.path.splitext(name)[1].lower()
    if suffix in IMAGE_TYPES:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in MARKDOWN_EXTS:
        return "markdown"
    if suffix in JSON_EXTS:
        return "json"
    if suffix in BINARY_EXTS:
        return "binary"
    if suffix in LANGUAGES or name in TEXT_NAMES:
        return "text"
    return None


def looks_textual(sample: bytes) -> bool:
    if b"\x00" in sample:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(sample, final=False)
    except UnicodeDecodeError:
        return False
    return True


class Repo:
    """The repository root plus mtime-keyed caches for JSON and text files."""

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        self._lock = threading.Lock()
        self._json: dict[str, tuple[tuple[int, int], Any, str | None]] = {}
        self._text: dict[str, tuple[tuple[int, int], str]] = {}
        self._ids: dict[str, tuple[Any, set[str]]] = {}

    # -- paths -------------------------------------------------------------------------------

    def path(self, rel: str) -> Path:
        return self.root / rel if rel else self.root

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def inside(self, resolved: Path) -> bool:
        if resolved != self.root and not resolved.is_relative_to(self.root):
            return False
        parts = resolved.relative_to(self.root).parts
        return public_parts(parts)

    def resolve(self, raw: str, *, must_exist: bool = True) -> tuple[str, Path]:
        """Apply the path policy to a user-supplied path; returns ``(rel, resolved_path)``.

        Symlinks are followed and the target must still lie inside the repository and outside
        hidden or excluded folders.
        """
        rel = normalize_rel(raw)
        if not public_parts(Path(rel).parts):
            raise Forbidden("This path is not part of the dashboard catalog.")
        try:
            resolved = self.path(rel).resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise Forbidden("the path cannot be resolved") from exc
        if not self.inside(resolved):
            raise Forbidden("the path points outside the repository or into a hidden folder")
        if must_exist and not resolved.exists():
            raise NotFound(f"{rel or '.'} does not exist")
        return rel, resolved

    # -- cached reads ------------------------------------------------------------------------

    @staticmethod
    def signature(path: Path) -> tuple[int, int] | None:
        try:
            st = path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def load_json(self, rel: str) -> tuple[Any, str | None, bool]:
        """Return ``(data, warning, exists)`` for a repository JSON file.

        A missing file gives ``(None, None, False)``; an unreadable or partially written file gives
        ``(None, warning, True)``. Parsed values are shared between requests: treat them as
        read-only.
        """
        path = self.path(rel)
        try:
            st = path.stat()
        except FileNotFoundError:
            return None, None, False
        except OSError as exc:
            return None, f"{rel}: cannot be read ({exc.strerror})", True
        if not path.is_file():
            return None, f"{rel}: is not a file", True
        sig = (st.st_mtime_ns, st.st_size)
        key = str(path)
        with self._lock:
            hit = self._json.get(key)
        if hit and hit[0] == sig:
            return hit[1], hit[2], True
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"{rel}: cannot be read ({exc})", True
        try:
            data, warning = json.loads(text), None
        except json.JSONDecodeError as exc:
            data = None
            warning = (f"{rel}: invalid JSON at line {exc.lineno}, column {exc.colno} "
                       "(the file may be partially written)")
        with self._lock:
            self._json[key] = (sig, data, warning)
        return data, warning, True

    def read_text(self, path: Path) -> str:
        """Read a text file as UTF-8 (undecodable bytes replaced), cached by mtime and size."""
        sig = self.signature(path)
        key = str(path)
        with self._lock:
            hit = self._text.get(key)
        if sig and hit and hit[0] == sig:
            return hit[1]
        text = path.read_bytes().decode("utf-8", errors="replace")
        if sig and len(text) <= TEXT_PREVIEW_LIMIT:
            with self._lock:
                if len(self._text) > 4000:
                    self._text.clear()
                self._text[key] = (sig, text)
        return text

    def replace_text(self, path: Path, content: str) -> None:
        """Replace a text file in place and drop its cached copy.

        The write goes to a temporary file in the same directory and then replaces the target, so a
        failed write does not leave a half-written source file.
        """
        data = content.encode("utf-8")
        if len(data) > TEXT_PREVIEW_LIMIT:
            raise BadRequest("the text is larger than 2 MB")
        mode = path.stat().st_mode & 0o777
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        with self._lock:
            self._text.pop(str(path), None)

    def classify(self, path: Path, name: str | None = None) -> str:
        kind = kind_for_name(name or path.name)
        if kind is not None:
            return kind
        try:
            with path.open("rb") as handle:
                sample = handle.read(SNIFF_BYTES)
        except OSError:
            return "binary"
        return "text" if looks_textual(sample) else "binary"

    # -- identities --------------------------------------------------------------------------

    def _cached_ids(self, key: str, signature: Any, build) -> set[str]:
        with self._lock:
            hit = self._ids.get(key)
        if hit and hit[0] == signature:
            return hit[1]
        ids = build()
        with self._lock:
            self._ids[key] = (signature, ids)
        return ids

    def _ids_from(self, folder: str, index_rel: str, index_key: str, marker: str) -> set[str]:
        base = self.path(folder)
        signature = (self.signature(base), self.signature(self.path(index_rel)), int(time.monotonic() / IDS_TTL))
        if signature[0] is None:
            return set()

        def build() -> set[str]:
            data, _, _ = self.load_json(index_rel)
            ids = {item["id"] for item in records(data, index_key)}
            try:
                entries = list(os.scandir(base))
            except OSError:
                entries = []
            for entry in entries:
                if entry.name.startswith((".", "_")) or not ID_PATTERN.match(entry.name):
                    continue
                if (Path(entry.path) / marker).is_file():
                    ids.add(entry.name)
            return ids

        return self._cached_ids(folder, signature, build)

    def lab_ids(self) -> set[str]:
        """Labs listed in labs/labs.json plus lab folders that carry a lab.json."""
        return self._ids_from("labs", "labs/labs.json", "labs", "lab.json")

    def reference_ids(self) -> set[str]:
        """References listed in references/references.json plus folders with a provenance.json."""
        return self._ids_from("references", "references/references.json", "references", "provenance.json")
