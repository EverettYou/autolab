"""Resolve Markdown links, wikilinks, and repository paths to dashboard routes."""

from __future__ import annotations

import posixpath
import re
from functools import cached_property
from urllib.parse import quote, unquote

from .markup import slugify
from .repo import EXCLUDED_TOP, IMAGE_TYPES, string_list

SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
THREAD_ID = re.compile(r"^thread-\d+$")
DASHBOARD_PREFIXES = ("/references", "/labs", "/wiki", "/threads", "/notes", "/files",
                      "/search", "/auto-research", "/raw/")
KNOWN_AREAS = frozenset({"labs", "references", "wiki", "notes", "skills", "dashboard"})
ROOT_FILES = frozenset({"README.md", "AGENTS.md", "CLAUDE.md", "run.sh"})
LEGACY_AREAS = frozenset({"lab"})
STATIC_LEGACY = (("lab", "labs"),)

INLINE_LINK = re.compile(
    r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(<[^>\n]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
REF_DEFINITION = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*<?([^\s>]+)>?", re.M)
HTML_LINK = re.compile(r"""<(?:a|img)\b[^>]*?\b(?:href|src)\s*=\s*["']([^"']+)["']""", re.I)
WIKILINK = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
ROLE = re.compile(r"(?::(?:py:)?([a-z]+):|\{((?:py:)?[a-z][\w-]*)\})`([^`\n]+)`")
WIKI_TARGET = re.compile(r"^[^\[\]|#,\n<>*]+$")
CODE_PATH = re.compile(
    r"^(?:\./)?(?:labs|references|wiki|lib|skills|dashboard|"
    r"\.auto-research|lab|notes|archive|inbox|sandbox|projects)(?:/[^\s`'\"<>|*{}]*)?$")
RELATIVE_CODE_PATH = re.compile(r"^(?:\./)?[\w.-]+(?:/[\w.-]+)*/?$")
# Keep in sync with BARE_PATH in frontend/js/markdown.js (ASCII classes on purpose: a path often
# follows CJK text without a space).
BARE_PATH = re.compile(
    r"(?<![A-Za-z0-9_./@-])((?:labs|references|wiki|lib|skills|dashboard|"
    r"lab|notes|archive|inbox|sandbox|projects)/[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*/?"
    r"(?:#[A-Za-z0-9_-]+)?)")
LINE_SUFFIX = re.compile(r":(\d+)(?:[-:]\d+)?$")
PY_ROLES = frozenset({"class", "func", "meth", "mod", "attr", "data", "obj", "exc", "const",
                      "function", "method", "module", "attribute"})
MAX_ENTRIES = 5000


def q(value: str) -> str:
    return quote(value, safe="/")


def pdf_reader_route(byte_path: str) -> str:
    """Page that paints ``byte_path`` (a same-origin PDF URL) in the dashboard's reader."""
    return "/pdf?src=" + quote(byte_path, safe="")


def join_rel(base_dir: str, path: str) -> str | None:
    """Join and normalize repository paths; None when the result would leave the root."""
    joined = posixpath.normpath(posixpath.join(base_dir, path) if base_dir else path)
    if joined in (".", ""):
        return ""
    if joined == ".." or joined.startswith("../") or joined.startswith("/"):
        return None
    return joined


def module_for_source(parts: list[str]) -> str | None:
    """``["qec", "dem", "core.py"]`` -> ``qec.dem.core``; None for non-Python files."""
    parts = list(parts)
    if not parts:
        return None
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def role_label(text: str) -> tuple[str, str]:
    """Split a role body into ``(label, target)``: ``Title <target>``, ``~a.b.C`` or plain."""
    match = re.match(r"^(.*?)\s*<([^<>]+)>$", text.strip())
    if match and match.group(1):
        return match.group(1).strip(), match.group(2).strip()
    target = text.strip()
    if target.startswith("~"):
        target = target[1:]
        return target.rsplit(".", 1)[-1], target
    return target, target


class Resolver:
    """Link resolution for one request; memoizes id sets and existence checks."""

    def __init__(self, app):
        self.app = app
        self.repo = app.repo
        self._exists: dict[str, bool] = {}

    @cached_property
    def lab_ids(self) -> set[str]:
        return self.repo.lab_ids()

    @cached_property
    def reference_ids(self) -> set[str]:
        return self.repo.reference_ids()

    @cached_property
    def wiki(self):
        return self.app.wiki.index()

    @cached_property
    def legacy(self) -> list[tuple[str, str]]:
        pairs = list(STATIC_LEGACY)
        for rid in sorted(self.reference_ids):
            provenance, _, _ = self.repo.load_json(f"references/{rid}/provenance.json")
            if not isinstance(provenance, dict):
                continue
            for legacy in string_list(provenance.get("legacy_paths")):
                if not legacy.strip("/"):
                    continue
                legacy = legacy.strip("/")
                if legacy.startswith("archive/reproductions/"):
                    target = f"references/{rid}/reproduce"
                elif legacy.startswith("inbox/repos/"):
                    target = f"references/{rid}/repos/{legacy.split('/', 2)[2]}"
                elif legacy.startswith("sandbox/"):
                    target = f"references/{rid}/attempts/{legacy.split('/', 1)[1]}"
                else:
                    target = f"references/{rid}"
                pairs.append((legacy, target))
        return sorted(pairs, key=lambda pair: -len(pair[0]))

    # -- paths -------------------------------------------------------------------------------

    def exists(self, rel: str) -> bool:
        if rel in self._exists:
            return self._exists[rel]
        parts = rel.split("/") if rel else []
        hidden = any(part.startswith(".") for part in parts) and parts[0] != ".auto-research"
        result = (not hidden and not (parts and parts[0] in EXCLUDED_TOP)
                  and self.repo.path(rel).exists())
        self._exists[rel] = result
        return result

    def legacy_rewrite(self, rel: str) -> str | None:
        for old, new in self.legacy:
            if rel == old or rel.startswith(old + "/"):
                return new + rel[len(old):]
        return None

    def route_for_path(self, rel: str, fragment: str = "") -> str | None:
        """The dashboard view for a repository path (existence is not checked here)."""
        parts = [part for part in rel.split("/") if part] if rel else []
        frag = f"#{fragment}" if fragment else ""
        if not parts:
            return "/"
        head, count = parts[0], len(parts)
        if head in EXCLUDED_TOP:
            return None
        if head == "wiki":
            if count == 1:
                return "/wiki"
            sub = "/".join(parts[1:])
            if sub.endswith(".md"):
                return f"/wiki/{q(sub[:-3])}{frag}"
            if "." not in parts[-1] and self.exists(f"{rel}.md"):
                return f"/wiki/{q(sub)}{frag}"
            return f"/files/{q(rel)}{frag}"
        if head == "labs":
            if count == 1 or rel == "labs/labs.json":
                return "/labs"
            lab = parts[1]
            if lab not in self.lab_ids:
                return f"/files/{q(rel)}{frag}"
            inner = "/".join(parts[2:])
            if not inner or inner == "lab.json":
                return f"/labs/{q(lab)}"
            if (count == 3 or parts[2] == "notes") and inner.lower().endswith(".md"):
                return f"/labs/{q(lab)}?doc={quote(inner, safe='/')}{frag}"
            return f"/labs/{q(lab)}?path={quote(inner, safe='/')}{frag}"
        if head == "references":
            if count == 1 or rel == "references/references.json":
                return "/references"
            rid = parts[1]
            if rid not in self.reference_ids:
                return f"/files/{q(rel)}{frag}"
            inner = "/".join(parts[2:])
            if not inner or inner == "provenance.json":
                return f"/references/{q(rid)}"
            if inner == "paper.pdf":
                return pdf_reader_route(f"/references/{q(rid)}/paper.pdf")
            return f"/references/{q(rid)}?file={quote(inner, safe='/')}{frag}"
        if head == "notes" and count >= 2:
            return f"/notes/{q(parts[1])}" if count == 2 or parts[-1] in {"main.tex", "main.txt", "main.pdf"} else None
        if head == ".auto-research":
            if count == 1 or rel == ".auto-research/state.json":
                return "/auto-research"
            if rel == ".auto-research/state.json":
                if fragment and THREAD_ID.match(fragment):
                    return f"/threads/{fragment}"
                return "/threads"
            if count == 3 and parts[1] == "tasks" and parts[2].endswith(".md"):
                return f"/auto-research/{q(parts[2][:-3])}"
            return None
        if any(part.startswith(".") for part in parts):
            return None
        return f"/files/{q(rel)}{frag}"

    def info(self, rel: str, fragment: str, exists: bool, legacy: str | None = None) -> dict | None:
        route = self.route_for_path(rel, fragment)
        if route is None:
            return None
        result = {"route": route, "exists": exists, "path": rel}
        suffix = posixpath.splitext(rel)[1].lower()
        if suffix in IMAGE_TYPES:
            result["raw"] = f"/raw/{q(rel)}"
        elif suffix == ".pdf":
            parent, name = posixpath.split(rel)
            if name == "paper.pdf" and parent.startswith("references/") and "/" not in parent[len("references/"):]:
                result["raw"] = f"/references/{q(parent.split('/', 1)[1])}/paper.pdf"
            else:
                result["raw"] = f"/raw/{q(rel)}"
        if legacy:
            result["legacy"] = legacy
        return result

    def resolve_candidates(self, candidates: list[str], fragment: str, prefer_root: bool) -> dict | None:
        ordered = list(dict.fromkeys(candidate for candidate in candidates if candidate is not None))
        if not ordered:
            return None
        for rel in ordered:
            if self.exists(rel):
                return self.info(rel, fragment, True)
        for rel in ordered:
            mapped = self.legacy_rewrite(rel)
            if mapped is not None and self.exists(mapped):
                return self.info(mapped, fragment, True, legacy=rel)
        fallback = ordered[-1] if prefer_root else ordered[0]
        mapped = self.legacy_rewrite(fallback)
        if mapped is not None and fallback.split("/")[0] in LEGACY_AREAS:
            return self.info(mapped, fragment, False, legacy=fallback)
        return self.info(fallback, fragment, False)

    # -- link kinds --------------------------------------------------------------------------

    def href(self, href: str, source: str | None = None) -> dict | None:
        href = (href or "").strip()
        if href.startswith("<") and href.endswith(">"):
            href = href[1:-1].strip()
        if not href or href.startswith("#") or href.startswith("//") or SCHEME.match(href):
            return None
        path_part, _, fragment = href.partition("#")
        path_part = unquote(path_part.partition("?")[0])
        if not path_part or "\x00" in path_part or "\\" in path_part:
            return None
        if path_part.startswith("/"):
            if path_part == "/" or path_part.startswith(DASHBOARD_PREFIXES):
                return {"route": href, "exists": True, "path": None}
            return self.resolve_candidates([join_rel("", path_part.lstrip("/"))], fragment, True)
        candidates = []
        if source:
            candidates.append(join_rel(posixpath.dirname(source), path_part))
        candidates.append(join_rel("", path_part))
        bare = re.sub(r"^(?:\./)+", "", path_part)
        first = bare.split("/")[0]
        prefer_root = not bare.startswith("../") and (
            first in KNOWN_AREAS or first in LEGACY_AREAS or first in ROOT_FILES)
        return self.resolve_candidates(candidates, fragment, prefer_root)

    def wikilink(self, raw: str, source: str | None = None) -> dict | None:
        target, _, heading = raw.split("|", 1)[0].partition("#")
        target = target.strip()
        if target.endswith(".md"):
            target = target[:-3]
        if target.startswith("wiki/"):
            target = target[5:]
        if not target or not WIKI_TARGET.match(target) or re.fullmatch(r"[\d.\s]+", target):
            return None
        frag = f"#{slugify(heading)}" if heading.strip() else ""
        page = self.wiki.lookup(target, source)
        if page is not None:
            return {"route": f"/wiki/{q(page)}{frag}", "exists": True, "path": f"wiki/{page}.md"}
        first = target.split("/")[0]
        if first in KNOWN_AREAS and first != "wiki":
            for candidate in (f"{target}.md", target):
                rel = join_rel("", candidate)
                if rel is not None and self.exists(rel):
                    return self.info(rel, heading.strip() and slugify(heading), True)
        return None

    def code_span(self, text: str, source: str | None = None) -> dict | None:
        """A path quoted in a code span: repository-root paths anywhere, and paths relative to
        the quoting document (``scripts/run.py`` in a lab README) when that file exists."""
        value = text.strip()
        if not value or len(value) > 300 or " " in value:
            return None
        value = LINE_SUFFIX.sub("", value)
        path_part, _, fragment = value.partition("#")
        if CODE_PATH.match(path_part) or path_part in ROOT_FILES or self.legacy_rewrite(path_part):
            info = self.href(value, None)
            return info if info and info.get("exists") else None
        if source and RELATIVE_CODE_PATH.match(path_part) and (
                "/" in path_part or "." in path_part.lstrip(".")):
            rel = join_rel(posixpath.dirname(source), path_part)
            if rel is not None and self.exists(rel):
                return self.info(rel, fragment, True)
        return None

    def bare_path(self, text: str) -> dict | None:
        info = self.href(text, None)
        return info if info and info.get("exists") else None

    def role(self, role: str, text: str, source: str | None) -> dict | None:
        name = role[3:] if role.startswith("py:") else role
        label, target = role_label(text)
        if role.startswith("py:") or name in PY_ROLES:
            return None
        if name == "doc" and source:
            rel = join_rel(posixpath.dirname(source), target)
            if rel is None:
                return None
            if not rel.endswith(".md"):
                rel += ".md"
            info = self.info(rel, "", self.exists(rel))
            if info:
                info["label"] = label
            return info
        return None

    def link_map(self, text: str, source: str | None = None) -> dict:
        hrefs: dict[str, dict] = {}
        wikilinks: dict[str, dict] = {}
        code: dict[str, dict] = {}
        roles: dict[str, dict] = {}
        paths: dict[str, dict] = {}
        result = {"hrefs": hrefs, "wikilinks": wikilinks, "code": code, "roles": roles, "paths": paths}
        if not text:
            return result
        seen: set[str] = set()

        def add(table: dict, key: str, compute) -> None:
            marker = f"{id(table)}:{key}"
            if marker in seen or len(seen) >= MAX_ENTRIES:
                return
            seen.add(marker)
            info = compute()
            if info:
                table[key] = info

        for pattern in (INLINE_LINK, REF_DEFINITION, HTML_LINK):
            for match in pattern.finditer(text):
                raw = match.group(1).strip()
                key = raw[1:-1].strip() if raw.startswith("<") and raw.endswith(">") else raw
                add(hrefs, key, lambda key=key: self.href(key, source))
        for match in WIKILINK.finditer(text):
            key = match.group(1).split("|", 1)[0].strip()
            add(wikilinks, key, lambda key=key: self.wikilink(key, source))
        for match in CODE_SPAN.finditer(text):
            body = match.group(2)
            if len(body) >= 2 and body.startswith(" ") and body.endswith(" ") and body.strip():
                body = body[1:-1]
            if len(match.group(1)) >= 3:
                continue
            add(code, body, lambda body=body: self.code_span(body, source))
        for match in ROLE.finditer(text):
            role, body = match.group(1) or match.group(2), match.group(3)
            add(roles, f"{role}|{body}", lambda role=role, body=body: self.role(role, body, source))
        for match in BARE_PATH.finditer(text):
            key = match.group(1).rstrip(".")
            add(paths, key, lambda key=key: self.bare_path(key))
        return result


def link_map(app, text: str, source: str | None = None) -> dict:
    return Resolver(app).link_map(text, source)


def resolve_href(app, href: str, source: str | None = None) -> dict | None:
    return Resolver(app).href(href, source)


def route_for_path(app, rel: str, fragment: str = "") -> str | None:
    return Resolver(app).route_for_path(rel, fragment)
