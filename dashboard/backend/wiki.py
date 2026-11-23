"""Index of wiki/: page titles, frontmatter, the category tree and backlinks.

Pages are identified by their path under ``wiki/`` without ``.md`` (``concepts/coset-selection``,
``records/synthesis/2026-08-04-...``). Parsed pages are cached by mtime and size; the directory walk
is repeated at most once per second, so new and edited pages appear on the next request.
"""

from __future__ import annotations

import os
import posixpath
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .markup import date_from_name, first_heading, parse_frontmatter, title_from_name

WIKILINK_TARGET = re.compile(r"\[\[([^\[\]\n|#]+)(?:#[^\[\]\n|]*)?(?:\|[^\[\]\n]*)?\]\]")
EXCERPT_MARKUP = re.compile(r"[#>*_`\[\]|]")
MD_HREF = re.compile(r"\]\(\s*<?([^)\s>]+?\.md)(?:#[^)\s>]*)?>?(?:\s+[\"'(][^)]*)?\)")
MENTION = re.compile(r"(?<![\w-])(references|labs)/([A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9])")
TOP_ORDER = ("system", "project", "concepts", "methods", "comparisons", "questions", "models",
             "techniques", "deadends", "implementations", "literature", "lib", "records")
TOP_PAGE_ORDER = ("index", "README", "thesis")
ATTACHMENT_EXTS = frozenset({".yml", ".yaml", ".json", ".csv", ".txt"})
SCAN_TTL = 1.0


def _excerpt(body: str) -> str:
    """Plain-text opening of a page, so search can match a description and not only the title."""
    text = EXCERPT_MARKUP.sub(" ", body)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:800]


@dataclass
class Page:
    id: str
    path: str
    title: str
    meta: dict
    date: str | None
    updated: str | None
    page_type: str | None
    status: str | None
    wikilinks: tuple[str, ...]
    md_links: tuple[str, ...]
    source_refs: tuple[str, ...]
    mentions: frozenset[tuple[str, str]]
    excerpt: str
    size: int
    mtime: float

    def summary(self) -> dict:
        out = {"id": self.id, "title": self.title}
        for key in ("date", "updated", "page_type", "status"):
            value = getattr(self, key)
            if value:
                out["type" if key == "page_type" else key] = value
        return out


@dataclass
class WikiIndex:
    pages: dict[str, Page] = field(default_factory=dict)
    attachments: list[str] = field(default_factory=list)
    lower: dict[str, str] = field(default_factory=dict)
    by_basename: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    _backlinks: dict[str, list[str]] | None = None

    def lookup(self, target: str, source: str | None = None) -> str | None:
        """Resolve an Obsidian link target to a page id (path-qualified, relative, or basename)."""
        target = target.strip().strip("/")
        if target.endswith(".md"):
            target = target[:-3]
        if target in self.pages:
            return target
        if source and source.startswith("wiki/"):
            relative = posixpath.normpath(posixpath.join(posixpath.dirname(source[5:]), target))
            if relative in self.pages:
                return relative
        lowered = target.lower()
        if lowered in self.lower:
            return self.lower[lowered]
        matches = self.by_basename.get(lowered.rsplit("/", 1)[-1], [])
        if len(matches) == 1:
            return matches[0]
        suffix = [pid for pid in matches if pid.lower().endswith("/" + lowered)]
        return suffix[0] if len(suffix) == 1 else None

    def mentioning(self, area: str, item_id: str) -> list[Page]:
        """Pages whose text or frontmatter cites ``<area>/<item_id>`` (area: labs or references)."""
        key = (area, item_id)
        return sorted((page for page in self.pages.values() if key in page.mentions),
                      key=lambda page: page.id)

    def backlinks(self) -> dict[str, list[str]]:
        if self._backlinks is not None:
            return self._backlinks
        reverse: dict[str, set[str]] = {}
        for page in self.pages.values():
            targets: set[str] = set()
            for target in page.wikilinks:
                found = self.lookup(target, page.path)
                if found:
                    targets.add(found)
            for href in page.md_links:
                for rel in _md_candidates(page.path, href):
                    if rel.startswith("wiki/") and rel[5:-3] in self.pages:
                        targets.add(rel[5:-3])
                        break
            targets.discard(page.id)
            for target in targets:
                reverse.setdefault(target, set()).add(page.id)
        self._backlinks = {key: sorted(value) for key, value in reverse.items()}
        return self._backlinks


def _md_candidates(source: str, href: str) -> list[str]:
    href = href.split("#", 1)[0]
    out = []
    if not href.startswith("/"):
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(source), href))
        if not joined.startswith(".."):
            out.append(joined)
    root = posixpath.normpath(href.lstrip("/"))
    if not root.startswith(".."):
        out.append(root)
    return out


class Wiki:
    def __init__(self, repo):
        self.repo = repo
        self._lock = threading.Lock()
        self._scan_lock = threading.Lock()
        self._pages: dict[str, tuple[tuple[int, int], Page]] = {}
        self._snapshot: tuple[float, WikiIndex] | None = None

    @property
    def base(self) -> Path:
        return self.repo.path("wiki")

    def _parse(self, rel: str, path: Path, sig: tuple[int, int]) -> Page:
        page_id = rel[5:-3]
        try:
            text = path.read_bytes()[: 4 * 1024 * 1024].decode("utf-8", errors="replace")
        except OSError:
            text = ""
        meta, body = parse_frontmatter(text)
        name = page_id.rsplit("/", 1)[-1]
        title = meta.get("title") if isinstance(meta.get("title"), str) and meta.get("title") else None
        title = title or first_heading(body) or title_from_name(name)
        date = date_from_name(name)
        if not date and isinstance(meta.get("date"), str):
            date = meta["date"][:10]
        updated = meta.get("updated") if isinstance(meta.get("updated"), str) else None
        refs = meta.get("source_refs")
        return Page(
            id=page_id, path=rel, title=title, meta=meta, date=date, updated=updated,
            page_type=meta.get("page_type") if isinstance(meta.get("page_type"), str) else None,
            status=meta.get("status") if isinstance(meta.get("status"), str) else None,
            wikilinks=tuple(dict.fromkeys(m.group(1).strip() for m in WIKILINK_TARGET.finditer(text))),
            md_links=tuple(dict.fromkeys(m.group(1) for m in MD_HREF.finditer(text))),
            source_refs=tuple(str(item) for item in refs) if isinstance(refs, list) else (),
            mentions=frozenset((m.group(1), m.group(2)) for m in MENTION.finditer(text)),
            excerpt=_excerpt(body),
            size=sig[1], mtime=sig[0] / 1e9,
        )

    def _scan(self) -> WikiIndex:
        index = WikiIndex()
        base = self.base
        if not base.is_dir():
            return index
        seen: set[str] = set()
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
            rel_dir = Path(dirpath).relative_to(self.repo.root).as_posix()
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                rel = f"{rel_dir}/{name}"
                path = Path(dirpath) / name
                suffix = os.path.splitext(name)[1].lower()
                if suffix != ".md":
                    if suffix in ATTACHMENT_EXTS:
                        index.attachments.append(rel[5:])
                    continue
                sig = self.repo.signature(path)
                if sig is None:
                    continue
                seen.add(rel)
                with self._lock:
                    hit = self._pages.get(rel)
                if hit and hit[0] == sig:
                    page = hit[1]
                else:
                    page = self._parse(rel, path, sig)
                    with self._lock:
                        self._pages[rel] = (sig, page)
                index.pages[page.id] = page
        with self._lock:
            for stale in set(self._pages) - seen:
                del self._pages[stale]
        for page_id in index.pages:
            index.lower.setdefault(page_id.lower(), page_id)
            index.by_basename.setdefault(page_id.rsplit("/", 1)[-1].lower(), []).append(page_id)
        return index

    def index(self) -> WikiIndex:
        with self._lock:
            snapshot = self._snapshot
        if snapshot and time.monotonic() - snapshot[0] < SCAN_TTL:
            return snapshot[1]
        with self._scan_lock:
            with self._lock:
                snapshot = self._snapshot
            if snapshot and time.monotonic() - snapshot[0] < SCAN_TTL:
                return snapshot[1]
            index = self._scan()
            with self._lock:
                self._snapshot = (time.monotonic(), index)
            return index

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None

    def graph(self) -> dict:
        """Compiled pages and the links between them.

        Dated records and the overview are omitted so the graph emphasizes links between topics.
        An isolated page is omitted until it links to another topic.
        """
        index = self.index()
        compiled = [page for page in index.pages.values()
                    if not page.id.startswith("records/") and page.id not in {"index", "README"}]
        ids = {page.id for page in compiled}
        edges = []
        seen: set[tuple[str, str]] = set()
        degree: dict[str, int] = {page.id: 0 for page in compiled}
        for page in compiled:
            targets: set[str] = set()
            for raw in page.wikilinks:
                target = index.lookup(raw, page.path)
                if target:
                    targets.add(target)
            for href in page.md_links:
                for rel in _md_candidates(page.path, href):
                    if rel.startswith("wiki/") and rel[5:-3] in ids:
                        targets.add(rel[5:-3])
                        break
            targets.discard(page.id)
            for target in targets:
                if target not in ids:
                    continue
                key = (page.id, target) if page.id < target else (target, page.id)
                if key in seen:
                    continue
                seen.add(key)
                edges.append({"source": page.id, "target": target})
                degree[page.id] += 1
                degree[target] += 1
        nodes = [{"id": page.id, "title": page.title,
                  "folder": page.id.split("/", 1)[0] if "/" in page.id else "overview",
                  "links": degree[page.id]} for page in compiled if degree[page.id]]
        nodes.sort(key=lambda node: (-node["links"], node["id"]))
        return {"nodes": nodes, "edges": edges}

    # -- tree --------------------------------------------------------------------------------

    def tree(self) -> dict:
        index = self.index()
        root: dict = {"name": "wiki", "path": "", "pages": [], "files": [], "folders": {}}

        def folder(parts: list[str]) -> dict:
            node = root
            for depth, part in enumerate(parts):
                node = node["folders"].setdefault(part, {
                    "name": part, "path": "/".join(parts[: depth + 1]), "pages": [], "files": [],
                    "folders": {}})
            return node

        for page in index.pages.values():
            parts = page.id.split("/")
            folder(parts[:-1])["pages"].append(page.summary())
        for rel in index.attachments:
            parts = rel.split("/")
            folder(parts[:-1])["files"].append({"name": parts[-1], "path": f"wiki/{rel}"})
        return _finish(root, in_records=False, top=True)


def _page_sort_key(page: dict):
    order = TOP_PAGE_ORDER.index(page["id"]) if page["id"] in TOP_PAGE_ORDER else len(TOP_PAGE_ORDER)
    is_index = 0 if page["id"].rsplit("/", 1)[-1] == "index" else 1
    return (order, is_index, page["title"].casefold())


def _finish(node: dict, in_records: bool, top: bool) -> dict:
    records = in_records or node["path"] == "records" or node["path"].startswith("records/")
    if records:
        dated = sorted((p for p in node["pages"] if p.get("date")),
                       key=lambda p: (p["date"], p["title"].casefold()), reverse=True)
        undated = sorted((p for p in node["pages"] if not p.get("date")), key=_page_sort_key)
        node["pages"] = dated + undated
    else:
        node["pages"].sort(key=_page_sort_key)
    node["files"].sort(key=lambda item: item["name"].casefold())
    children = [_finish(child, records, False) for child in node["folders"].values()]
    if top:
        def order(child):
            name = child["name"]
            return (TOP_ORDER.index(name) if name in TOP_ORDER else TOP_ORDER.index("records") - 0.5,
                    name.casefold())
        children.sort(key=order)
    else:
        children.sort(key=lambda child: child["name"].casefold())
    node["folders"] = children
    node["count"] = len(node["pages"]) + sum(child["count"] for child in children)
    node["records"] = records
    return node
