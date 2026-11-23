#!/usr/bin/env python3
"""Lint the project wiki for deterministic structural problems.

Run from the repository root:

    .venv/bin/python skills/wiki-lint/scripts/lint_wiki.py

The scope defaults to the repository that contains this script. Pass another directory that holds
``wiki/README.md`` to lint a different wiki.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import yaml


SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))


def find_repo_root(start: Path = SCRIPT_ROOT) -> Path:
    """Return the nearest directory at or above ``start`` that holds ``wiki/README.md``."""
    for candidate in (start, *start.parents):
        if (candidate / "wiki" / "README.md").is_file():
            return candidate
    return start.parents[2] if len(start.parents) > 2 else start


REQUIRED_WIKI_FILES = (
    "README.md",
    "index.md",
    "thesis.md",
    "records/log.md",
    "sources.yml",
    "taxonomy.yml",
)
# Root README.md is the contract. Root index.md is the classifier (SPECIAL). Folder index.md
# files are sub-indexes (GUIDE_NAME). Operation log lives under records/.
CONTRACT_NAME = "README.md"
SPECIAL_FILES = {"index.md", "records/log.md"}
GUIDE_NAME = "index.md"
REQUIRED_FRONTMATTER = ("title", "page_type", "status", "updated", "source_refs", "idea_ids")
VISIBLE_FIELDS = ("**Summary**:", "**Sources**:", "**Last updated**:")
RELATED_HEADING = "## Related pages"
LOG_KINDS = ("ingest", "query", "lint", "reorganize")
LOG_PATTERN = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\] (?:" + "|".join(LOG_KINDS) + r") \| .+$")
SOURCE_KINDS = {
    "paper",
    "repository",
    "dataset",
    "reproduction",
    "lab",
    "record",
    "knowledge",
    "query",
    "project",
    "skill",
    "other",
}
TOPIC_REQUIREMENTS = {"topics", "project_topics", "either", "none"}
DEFAULT_PAGE_TYPES = {
    "concept": {"folder": "concepts", "requires": "topics"},
    "method": {"folder": "methods", "requires": "topics"},
    "comparison": {"folder": "comparisons", "requires": "topics"},
    "implementation": {"folder": "implementations", "requires": "either"},
    "question": {"folder": "questions", "requires": "none"},
    "paper": {"folder": "papers", "requires": "none"},
    "project": {"folder": "project", "requires": "project_topics"},
    "thesis": {"folder": ".", "requires": "none"},
}
DEFAULT_STATUSES = {"provisional", "active", "settled", "open", "closed", "superseded"}
PAGE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
QUESTION_TITLE_PATTERN = re.compile(
    r"^(what|why|how|when|where|which|who|does|do|is|are|can|should|did|will|must|you)\b",
    re.IGNORECASE,
)
LEADING_ARTICLE_PATTERN = re.compile(r"^(a|an|the)\b", re.IGNORECASE)

MARKDOWN_LINK_PATTERN = re.compile(
    r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(<[^>\n]*>|[^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
REFERENCE_DEFINITION_PATTERN = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
WIKILINK_PATTERN = re.compile(r"!?\[\[([^\[\]\n]+)\]\]")
WIKILINK_TARGET_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./ -]*")
URL_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
FENCE_PATTERN = re.compile(r"^(?:\s{0,3}>)*\s{0,3}(`{3,}|~{3,})(.*)$")
COLON_DIRECTIVE_PATTERN = re.compile(r"^(?:\s{0,3}>)*\s{0,3}:{3,}\s*\{[A-Za-z][\w:-]*\}")
MYST_LABEL_PATTERN = re.compile(r"^(?:\s{0,3}>)*\s{0,3}\([A-Za-z0-9_.:-]+\)=\s*$")
MYST_ROLE_PATTERN = re.compile(r"\{(?:[a-z0-9]+:)?[a-z][a-z0-9-]*\}`")
RST_ROLE_PATTERN = re.compile(
    r"(?<![\w:]):(?:py:)?(?:class|func|meth|mod|attr|data|exc|obj|doc|ref|term):`"
)
NONPORTABLE_CITATION_PATTERN = re.compile(
    r"\[@[a-z][a-z0-9_-]*:[a-z0-9][a-z0-9_-]*(?:,\s*[^\]]+)?\]|\(source:\s*[^)]+\)",
    re.IGNORECASE,
)
RESOLVER_CITATION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:global|benchmark|source):[A-Za-z0-9][A-Za-z0-9_.:-]*",
    re.IGNORECASE,
)
CODE_PATH_PATTERN = re.compile(r"^(?:\./|(?:\.\./)+)?([A-Za-z0-9_.-]+/[^\s`]*|[A-Z][A-Z_]*\.md)$")


# --------------------------------------------------------------------------- text handling


def code_spans(line: str) -> list[tuple[int, int, int]]:
    """Return ``(start, end, fence_length)`` for each inline code span on one line."""
    spans: list[tuple[int, int, int]] = []
    position = 0
    while True:
        start = line.find("`", position)
        if start < 0:
            return spans
        run_end = start
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1
        run = run_end - start
        search = run_end
        closing = -1
        while True:
            candidate = line.find("`" * run, search)
            if candidate < 0:
                break
            candidate_end = candidate
            while candidate_end < len(line) and line[candidate_end] == "`":
                candidate_end += 1
            if candidate_end - candidate == run:
                closing = candidate
                break
            search = candidate_end
        if closing < 0:
            position = run_end
            continue
        spans.append((start, closing + run, run))
        position = closing + run


def mask_code_spans(line: str) -> str:
    """Blank the contents of inline code spans, keeping their backtick delimiters and length."""
    characters = list(line)
    for start, end, run in code_spans(line):
        for index in range(start + run, end - run):
            characters[index] = "x"
    return "".join(characters)


def code_span_contents(line: str) -> list[str]:
    return [line[start + run : end - run].strip() for start, end, run in code_spans(line)]


@dataclass
class ScannedText:
    """Page text with fenced code blanked and inline code masked, plus structural findings."""

    lines: list[str]
    raw_lines: list[str]
    directive_lines: list[int] = field(default_factory=list)
    label_lines: list[int] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)


def scan_text(text: str) -> ScannedText:
    raw_lines = text.splitlines()
    scanned = ScannedText(lines=[], raw_lines=raw_lines)
    fence: tuple[str, int] | None = None
    in_frontmatter = bool(raw_lines) and raw_lines[0] == "---"
    for number, line in enumerate(raw_lines, 1):
        if in_frontmatter:
            scanned.lines.append("")
            if number > 1 and line == "---":
                in_frontmatter = False
            continue
        match = FENCE_PATTERN.match(line)
        if fence is not None:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= fence[1] and not match.group(2).strip():
                fence = None
            scanned.lines.append("")
            continue
        if match:
            fence = (match.group(1)[0], len(match.group(1)))
            if match.group(2).strip().startswith("{"):
                scanned.directive_lines.append(number)
            scanned.lines.append("")
            continue
        if COLON_DIRECTIVE_PATTERN.match(line):
            scanned.directive_lines.append(number)
        if MYST_LABEL_PATTERN.match(line):
            scanned.label_lines.append(number)
        if line.startswith("## "):
            scanned.headings.append(line.rstrip())
        scanned.lines.append(mask_code_spans(line))
    return scanned


def frontmatter_text(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    return text[4:end]


def frontmatter(path: Path) -> dict | None:
    block = frontmatter_text(path.read_text(encoding="utf-8"))
    if block is None:
        return None
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def text_without_fenced_code(path: Path) -> str:
    """Keep inline citation-like text while excluding literal fenced examples."""
    text = path.read_text(encoding="utf-8")
    return re.sub(r"^(?:```|~~~).*?^(?:```|~~~)\s*$", "", text, flags=re.DOTALL | re.MULTILINE)


def resolver_citation_ids(path: Path) -> list[str]:
    """Return nonportable source IDs that require a resolver to become citations."""
    return RESOLVER_CITATION_PATTERN.findall(text_without_fenced_code(path))


def markdown_link_targets(scanned: ScannedText) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    for number, line in enumerate(scanned.lines, 1):
        found = [match.group(1) for match in MARKDOWN_LINK_PATTERN.finditer(line)]
        definition = REFERENCE_DEFINITION_PATTERN.match(line)
        if definition:
            found.append(definition.group(1))
        for target in found:
            target = target.strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1].strip()
            targets.append((number, target))
    return targets


def wikilink_bodies(scanned: ScannedText) -> list[tuple[int, str]]:
    return [
        (number, match.group(1))
        for number, line in enumerate(scanned.lines, 1)
        for match in WIKILINK_PATTERN.finditer(line)
    ]


def wikilink_target(body: str) -> str | None:
    """Return the page target of an Obsidian link body, or None when the brackets are plain text.

    Double brackets also write code parameters such as ``[[144,12,12]]``; a body with a comma or with
    no letter is text, not a link. An escaped ``\\|`` (the Obsidian form inside tables) separates the label
    like a bare ``|``.
    """
    target = body.replace("\\|", "|").split("|", 1)[0].split("#", 1)[0].strip()
    if not target or "," in target or not re.search(r"[A-Za-z]", target):
        return None
    if not WIKILINK_TARGET_PATTERN.fullmatch(target):
        return None
    return target


# --------------------------------------------------------------------------- configuration


@dataclass
class Taxonomy:
    allowed_source_prefixes: list[str]
    citable_wiki_prefixes: list[str]
    record_folders: set[str]
    page_types: dict[str, dict[str, str]]
    statuses: set[str]
    topics: set[str]
    project_topics: set[str]
    retired_path_prefixes: list[str]
    problems: list[str]

    @property
    def folder_types(self) -> dict[str, str]:
        return {spec["folder"]: page_type for page_type, spec in self.page_types.items()}


def _string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def load_taxonomy(wiki: Path) -> Taxonomy:
    path = wiki / "taxonomy.yml"
    problems: list[str] = []
    content: object = {}
    if path.is_file():
        try:
            content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            problems.append(f"invalid wiki/taxonomy.yml YAML: {error}")
    if not isinstance(content, dict):
        problems.append("wiki/taxonomy.yml must be a mapping")
        content = {}
    page_types: dict[str, dict[str, str]] = {}
    raw_types = content.get("page_types")
    if isinstance(raw_types, dict) and raw_types:
        for page_type, spec in raw_types.items():
            if not isinstance(spec, dict) or not isinstance(spec.get("folder"), str):
                problems.append(f"wiki/taxonomy.yml page_types.{page_type} needs a folder")
                continue
            requires = spec.get("requires", "none")
            if requires not in TOPIC_REQUIREMENTS:
                problems.append(
                    f"wiki/taxonomy.yml page_types.{page_type}.requires must be one of "
                    + ", ".join(sorted(TOPIC_REQUIREMENTS))
                )
                requires = "none"
            page_types[str(page_type)] = {"folder": spec["folder"].strip("/") or ".", "requires": requires}
    else:
        page_types = {key: dict(value) for key, value in DEFAULT_PAGE_TYPES.items()}
    statuses = set(_string_list(content.get("statuses"))) or set(DEFAULT_STATUSES)
    return Taxonomy(
        allowed_source_prefixes=_string_list(content.get("allowed_source_prefixes")),
        citable_wiki_prefixes=_string_list(content.get("citable_wiki_prefixes")),
        record_folders=set(_string_list(content.get("record_folders"))) or {"records"},
        page_types=page_types,
        statuses=statuses,
        topics=set(_string_list(content.get("topics"))),
        project_topics=set(_string_list(content.get("project_topics"))),
        retired_path_prefixes=_string_list(content.get("retired_path_prefixes")),
        problems=problems,
    )


# --------------------------------------------------------------------------- lint


class IgnoreOracle:
    """Answer whether a repository path is gitignored (local-only), caching git's answers."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.cache: dict[str, bool] = {}

    def ignored(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return False
        if relative not in self.cache:
            try:
                result = subprocess.run(
                    ["git", "-C", str(self.root), "check-ignore", "-q", "--", relative],
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                self.cache[relative] = result.returncode == 0
            except (OSError, subprocess.SubprocessError):
                self.cache[relative] = False
        return self.cache[relative]


def page_kind(rel: Path, taxonomy: Taxonomy) -> str:
    posix = rel.as_posix()
    if posix in SPECIAL_FILES:
        return "special"
    if posix == CONTRACT_NAME or rel.name == GUIDE_NAME:
        return "guide"
    if len(rel.parts) > 1 and rel.parts[0] in taxonomy.record_folders:
        return "record"
    return "compiled"


def page_folder(rel: Path) -> str:
    return rel.parts[0] if len(rel.parts) > 1 else "."


def question_shaped_title(title: str) -> bool:
    text = title.strip()
    if text.endswith(("?", ".", ",", ":", ";", "!")):
        return True
    return QUESTION_TITLE_PATTERN.match(text) is not None


def source_path_allowed(ref: str, prefixes: list[str], citable: list[str] | None = None) -> bool:
    raw = Path(ref.split("#", 1)[0])
    if raw.is_absolute() or ".." in raw.parts:
        return False
    if prefixes:
        return any(ref.startswith(prefix) for prefix in prefixes)
    if ref.startswith("wiki/"):
        return any(ref.startswith(prefix) for prefix in citable or [])
    return True


def lint(scope: Path, *, check_paths: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    scope = scope.resolve()
    wiki = scope / "wiki"
    if not wiki.is_dir():
        return ["missing wiki/ directory"], warnings

    taxonomy = load_taxonomy(wiki)
    errors.extend(taxonomy.problems)
    folder_types = taxonomy.folder_types
    ignore = IgnoreOracle(scope)

    for name in REQUIRED_WIKI_FILES:
        if not (wiki / name).is_file():
            errors.append(f"missing wiki/{name}")

    paths = sorted(wiki.rglob("*.md"))
    relative_pages = {path.relative_to(wiki) for path in paths}
    stems: defaultdict[str, list[Path]] = defaultdict(list)
    for rel in relative_pages:
        stems[rel.stem].append(rel)
    outgoing: defaultdict[Path, set[Path]] = defaultdict(set)
    titles: defaultdict[str, list[Path]] = defaultdict(list)

    def report(kind: str, message: str) -> None:
        (warnings if kind == "record" else errors).append(message)

    def missing_target(path: Path) -> str:
        """Classify a missing repository target: 'local-only' when gitignored, else 'broken'."""
        return "local-only" if ignore.ignored(path) else "broken"

    def check_source_ref(ref: str, label: str) -> None:
        if re.match(r"^https?://", ref):
            return
        if URL_SCHEME_PATTERN.match(ref):
            errors.append(f"unsupported source URL scheme in {label}: {ref}")
            return
        raw = ref.split("#", 1)[0]
        if not source_path_allowed(ref, taxonomy.allowed_source_prefixes, taxonomy.citable_wiki_prefixes):
            if raw.startswith("wiki/"):
                errors.append(
                    f"source_ref cites a compiled wiki page in {label}: {ref}; cite the lab, reference, "
                    "or record underneath, or link the page under Related pages"
                )
            else:
                errors.append(f"unsafe source path in {label}: {ref}")
            return
        target = scope / raw
        if target.exists():
            return
        if missing_target(target) == "local-only":
            warnings.append(f"local-only source missing on this machine in {label}: {ref}")
        else:
            errors.append(f"unresolved raw source_ref in {label}: {ref}")

    for path in paths:
        rel = path.relative_to(wiki)
        kind = page_kind(rel, taxonomy)
        label = f"wiki/{rel.as_posix()}"
        text = path.read_text(encoding="utf-8")
        scanned = scan_text(text)

        if kind != "record":
            if scanned.directive_lines:
                errors.append(
                    f"MyST/Sphinx directive in {label} (line {scanned.directive_lines[0]}); "
                    "use plain Markdown (blockquote admonitions, fenced code, bulleted links)"
                )
            if scanned.label_lines:
                errors.append(f"MyST label target in {label} (line {scanned.label_lines[0]}); use a heading anchor")
            roles = sorted(
                {match.group(0)[:-1] for line in scanned.lines for match in MYST_ROLE_PATTERN.finditer(line)}
                | {match.group(0)[:-1] for line in scanned.lines for match in RST_ROLE_PATTERN.finditer(line)}
            )
            if roles:
                errors.append(
                    f"MyST/Sphinx role in {label}: {', '.join(roles)}; use a relative link or inline code"
                )

        if kind == "compiled":
            if not PAGE_NAME_PATTERN.fullmatch(path.name):
                errors.append(f"wiki page filename must use lowercase kebab-case: {label}")
            masked = "\n".join(scanned.lines)
            if NONPORTABLE_CITATION_PATTERN.search(masked):
                errors.append(f"nonportable citation syntax in {label}; use [readable label](relative-path#locator)")
            resolver_ids = sorted(set(resolver_citation_ids(path)), key=str.casefold)
            if resolver_ids:
                errors.append(
                    f"resolver-style source ID in {label}: {', '.join(resolver_ids)}; "
                    "use [readable label](relative-path#locator)"
                )
            data = frontmatter(path)
            if data is None:
                errors.append(f"missing or invalid frontmatter: {label}")
            else:
                missing = sorted(set(REQUIRED_FRONTMATTER) - data.keys())
                if missing:
                    errors.append(f"missing frontmatter fields in {label}: {', '.join(missing)}")
                title = data.get("title")
                if isinstance(title, str) and title.strip():
                    titles[title.strip().casefold()].append(rel)
                    stripped = title.strip()
                    if page_folder(rel) != "questions" and question_shaped_title(stripped):
                        errors.append(
                            f"compiled page title must name the topic, not a question or instruction: "
                            f"{label}: {stripped!r}. A question title belongs in questions/."
                        )
                    elif page_folder(rel) != "questions" and LEADING_ARTICLE_PATTERN.match(stripped):
                        warnings.append(
                            f"compiled page title starts with an article; name the topic directly: "
                            f"{label}: {stripped!r}"
                        )
                page_type = data.get("page_type")
                expected = folder_types.get(page_folder(rel))
                if expected is None:
                    errors.append(f"unknown wiki category folder for {label}: {page_folder(rel)}/")
                elif page_type != expected:
                    errors.append(f"page_type '{page_type}' in {label} does not match its folder (expected '{expected}')")
                status = data.get("status")
                if "status" in data and status not in taxonomy.statuses:
                    errors.append(f"status '{status}' in {label} is not one of: {', '.join(sorted(taxonomy.statuses))}")
                updated = data.get("updated")
                if not isinstance(updated, (str, date)) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(updated)):
                    warnings.append(f"missing or invalid updated date: {label}")
                else:
                    visible = re.search(r"^\*\*Last updated\*\*:\s*(\S+)", text, re.MULTILINE)
                    if visible and visible.group(1).rstrip(".") != str(updated):
                        warnings.append(
                            f"visible Last updated {visible.group(1)} differs from frontmatter {updated} in {label}"
                        )
                idea_ids = data.get("idea_ids")
                if "idea_ids" in data and not isinstance(idea_ids, list):
                    errors.append(f"idea_ids must be a list in {label}")
                refs = data.get("source_refs")
                if not isinstance(refs, list) or not refs:
                    warnings.append(f"no raw source_refs: {label}")
                else:
                    for ref in refs:
                        if not isinstance(ref, str) or not ref.strip():
                            errors.append(f"invalid source_ref in {label}")
                        else:
                            check_source_ref(ref.strip(), label)
                requirement = taxonomy.page_types.get(str(page_type), {}).get("requires", "none")
                for field_name, vocabulary in (("topics", taxonomy.topics), ("project_topics", taxonomy.project_topics)):
                    values = data.get(field_name)
                    if values is None or values == []:
                        continue
                    if not isinstance(values, list) or not 1 <= len(values) <= 3 or not all(
                        isinstance(value, str) and (not vocabulary or value in vocabulary) for value in values
                    ):
                        errors.append(f"{field_name} must list one to three controlled values in {label}")
                has_topics = bool(data.get("topics"))
                has_project_topics = bool(data.get("project_topics"))
                if requirement == "topics" and not has_topics:
                    errors.append(f"topic-indexed page needs one to three controlled topics in {label}")
                elif requirement == "project_topics" and not has_project_topics:
                    errors.append(f"{page_type} page needs one to three controlled project_topics in {label}")
                elif requirement == "either" and not (has_topics or has_project_topics):
                    errors.append(f"{page_type} page needs controlled topics or project_topics in {label}")

            for marker in (*VISIBLE_FIELDS, RELATED_HEADING):
                if marker not in text:
                    errors.append(f"missing visible page field '{marker}' in {label}")
            if RELATED_HEADING in scanned.headings and scanned.headings[-1] != RELATED_HEADING:
                errors.append(f"'{RELATED_HEADING}' must be the last section in {label}")

        for number, target in markdown_link_targets(scanned):
            location = f"{label}:{number}"
            if not target or target.startswith("#") or URL_SCHEME_PATTERN.match(target):
                continue
            clean = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not clean:
                continue
            if clean.startswith("/"):
                report(kind, f"root-relative link in {location}: {target}; use a relative path")
                continue
            resolved = (path.parent / clean).resolve()
            try:
                resolved.relative_to(scope)
            except ValueError:
                report(kind, f"link escapes the repository in {location}: {target}")
                continue
            if resolved.exists():
                if resolved.is_dir() and (resolved / "index.md").is_file():
                    resolved = resolved / "index.md"
                try:
                    target_rel = resolved.relative_to(wiki)
                except ValueError:
                    continue
                if target_rel in relative_pages:
                    outgoing[rel].add(target_rel)
                continue
            inside_wiki = wiki in resolved.parents
            if not inside_wiki and missing_target(resolved) == "local-only":
                warnings.append(f"local-only link target missing on this machine in {location}: {target}")
            elif inside_wiki:
                report(kind, f"broken wiki link in {location}: {target}")
            else:
                report(kind, f"broken local link in {location}: {target}")

        for number, raw_line in enumerate(scanned.raw_lines, 1):
            masked = scanned.lines[number - 1]
            if not masked.strip():
                continue
            for opening in re.finditer(r"\[\[([^\[\]\n|]+)\|", raw_line):
                if masked[opening.start()] != "[":
                    continue
                closing = raw_line.find("]]", opening.end())
                if closing >= 0 and "[" in raw_line[opening.end():closing]:
                    report(
                        kind,
                        f"wikilink label with square brackets in {label}:{number}: [[{opening.group(1)}|...]]; "
                        "write code parameters in a label as ⟦n,k,d⟧",
                    )

        for number, body in wikilink_bodies(scanned):
            location = f"{label}:{number}"
            target = wikilink_target(body)
            if target is None:
                continue
            if kind != "record" and "|" in body and scanned.lines[number - 1].lstrip().startswith("|"):
                warnings.append(
                    f"labelled wikilink in a table row in {location}: [[{target}|...]]; "
                    "its '|' breaks the cell, use a relative Markdown link"
                )
            raw_target = Path(target)
            if raw_target.is_absolute() or ".." in raw_target.parts:
                report(kind, f"unsafe Obsidian wikilink in {location}: [[{target}]]")
                continue
            page_target = Path(target if target.endswith(".md") else f"{target}.md")
            if page_target in relative_pages:
                outgoing[rel].add(page_target)
                continue
            if (wiki / raw_target).is_file():
                continue
            if raw_target / "index.md" in relative_pages:
                outgoing[rel].add(raw_target / "index.md")
                continue
            candidates = stems.get(page_target.stem, []) if "/" not in target else []
            if len(candidates) == 1:
                outgoing[rel].add(candidates[0])
                if kind != "record":
                    qualified = candidates[0].with_suffix("").as_posix()
                    warnings.append(f"bare Obsidian wikilink in {location}: [[{target}]]; use [[{qualified}|...]]")
            elif len(candidates) > 1:
                report(
                    kind,
                    f"ambiguous Obsidian wikilink in {location}: [[{target}]] -> "
                    + ", ".join(sorted(map(str, candidates))),
                )
            else:
                report(kind, f"broken Obsidian wikilink in {location}: [[{target}]]")

        if check_paths and kind in {"compiled", "guide"}:
            for number, line in enumerate(scanned.raw_lines, 1):
                if not scanned.lines[number - 1]:
                    continue
                for content in code_span_contents(line):
                    candidate = content.rstrip(".,;:)").split("#", 1)[0].split("::", 1)[0]
                    candidate = re.sub(r":\d+(?:-\d+)?$", "", candidate)
                    match = CODE_PATH_PATTERN.match(candidate)
                    if not match or any(character in candidate for character in "<>*{}[]|$ "):
                        continue
                    repo_path = match.group(1)
                    if any(repo_path.startswith(prefix) for prefix in taxonomy.retired_path_prefixes):
                        warnings.append(f"mention of a retired path in {label}:{number}: {repo_path}")
                        continue
                    top = repo_path.split("/", 1)[0]
                    if not (scope / top).exists() or "/" not in repo_path:
                        continue
                    if not (scope / repo_path).exists() and missing_target(scope / repo_path) == "broken":
                        warnings.append(f"code-span path does not exist in {label}:{number}: {repo_path}")

    for title, title_paths in titles.items():
        if len(title_paths) > 1:
            errors.append(f"duplicate wiki title '{title}': " + ", ".join(sorted(map(str, title_paths))))

    # Root index is a classifier: hubs and sub-indexes only (plus thesis). Leaves are listed in
    # their folder index.md; nesting under a category may be arbitrarily deep.
    root_listed = outgoing.get(Path("index.md"), set())
    if Path("thesis.md") in relative_pages and Path("thesis.md") not in root_listed:
        warnings.append("thesis.md is not linked from wiki/index.md")
    for target in sorted(root_listed):
        kind = page_kind(target, taxonomy)
        if kind == "compiled" and target.as_posix() != "thesis.md":
            warnings.append(
                f"root index should link classifiers/sub-indexes, not leaf pages: wiki/{target.as_posix()}"
            )
        elif kind == "guide" and target.name != GUIDE_NAME and target.as_posix() != CONTRACT_NAME:
            warnings.append(f"root index unexpected guide link: wiki/{target.as_posix()}")

    for rel in sorted(relative_pages):
        if page_kind(rel, taxonomy) != "compiled":
            continue
        if rel.as_posix() == "thesis.md":
            continue
        guide_rel = rel.parent / GUIDE_NAME
        if guide_rel not in relative_pages:
            warnings.append(
                f"compiled page has no folder sub-index ({GUIDE_NAME}): wiki/{rel.as_posix()}"
            )
            continue
        if rel not in outgoing.get(guide_rel, set()):
            warnings.append(
                f"compiled page not listed in wiki/{guide_rel.as_posix()}: wiki/{rel.as_posix()}"
            )

    registry_path = wiki / "sources.yml"
    registered_paths: list[str] = []
    if registry_path.is_file():
        try:
            registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            registry = None
            errors.append(f"invalid wiki/sources.yml YAML: {error}")
        if not isinstance(registry, dict) or registry.get("version") != 1:
            errors.append("wiki/sources.yml must be a version 1 mapping")
        sources = registry.get("sources") if isinstance(registry, dict) else None
        if not isinstance(sources, list):
            errors.append("wiki/sources.yml must contain a sources list")
            sources = []
        source_ids: set[str] = set()
        source_paths: set[str] = set()
        for position, source in enumerate(sources):
            label = f"wiki/sources.yml sources[{position}]"
            if not isinstance(source, dict):
                errors.append(f"{label} must be a mapping")
                continue
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not source_id.strip() or any(
                character.isspace() for character in source_id
            ):
                errors.append(f"{label}.source_id must be non-empty and contain no whitespace")
            elif source_id in source_ids:
                errors.append(f"duplicate source_id in wiki/sources.yml: {source_id}")
            else:
                source_ids.add(source_id)
            if source.get("kind") not in SOURCE_KINDS:
                errors.append(f"{label}.kind is unsupported")
            raw_value = source.get("path")
            if not isinstance(raw_value, str) or not raw_value.strip():
                errors.append(f"{label}.path must be non-empty text")
            else:
                raw_path = raw_value.split("#", 1)[0]
                if not source_path_allowed(raw_value, taxonomy.allowed_source_prefixes, taxonomy.citable_wiki_prefixes):
                    errors.append(f"unsafe source path in {label}: {raw_value}")
                elif not (scope / raw_path).exists():
                    if missing_target(scope / raw_path) == "local-only":
                        warnings.append(f"local-only source missing on this machine in {label}: {raw_value}")
                    else:
                        errors.append(f"unresolved source path in {label}: {raw_value}")
                if raw_value in source_paths:
                    errors.append(f"duplicate source path in wiki/sources.yml: {raw_value}")
                else:
                    source_paths.add(raw_value)
                    registered_paths.append(raw_value)
            revision = source.get("revision")
            if not isinstance(revision, str) or not revision.strip():
                errors.append(f"{label}.revision must be non-empty text")
            ingested_at = source.get("ingested_at")
            if not isinstance(ingested_at, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ingested_at
            ):
                errors.append(f"{label}.ingested_at must be a UTC timestamp")
            updated_pages = source.get("updated_pages")
            if not isinstance(updated_pages, list) or not updated_pages:
                errors.append(f"{label}.updated_pages must be a non-empty list")
            else:
                for updated_page in updated_pages:
                    if not isinstance(updated_page, str):
                        errors.append(f"invalid updated page in {label}")
                        continue
                    page_path = Path(updated_page)
                    if (
                        page_path.is_absolute()
                        or ".." in page_path.parts
                        or not updated_page.startswith("wiki/")
                        or page_path.suffix != ".md"
                        or not (scope / page_path).is_file()
                    ):
                        errors.append(f"unresolved updated page in {label}: {updated_page}")

    log = wiki / "records" / "log.md"
    if log.is_file():
        headings = [line for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("## [")]
        for heading in headings:
            if not LOG_PATTERN.fullmatch(heading):
                errors.append(f"malformed wiki log heading: {heading}")

    for report_path in iter_lab_reports(scope):
        report_text = report_path.read_text(encoding="utf-8")
        metadata = frontmatter(report_path) or {}
        completed = str(metadata.get("status") or "").casefold() in {"complete", "completed"}
        if completed or re.search(r"^- Status:\s*(complete|completed)\s*$", report_text, re.MULTILINE | re.IGNORECASE):
            rel = report_path.relative_to(scope).as_posix()
            if rel not in registered_paths:
                warnings.append(f"completed lab report not registered in wiki/sources.yml: {rel}")

    return errors, warnings


def iter_lab_reports(scope: Path) -> list[Path]:
    directory = scope / "labs"
    if not directory.is_dir():
        return []
    reports = [*directory.glob("*/report.md"), *directory.glob("*/REPORT.md")]
    return sorted(set(reports))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "scope",
        type=Path,
        nargs="?",
        default=None,
        help="directory that holds wiki/README.md (default: this repository's root)",
    )
    parser.add_argument(
        "--check-paths",
        action="store_true",
        help="also warn about code-formatted repository paths that do not exist or use a retired prefix",
    )
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="run the optional cached LLM knowledge-health review after structural lint",
    )
    parser.add_argument(
        "--semantic-model",
        help="override OPENAI_SEMANTIC_LINT_MODEL for this run",
    )
    parser.add_argument(
        "--semantic-limit",
        type=int,
        help="review only the first N semantic pages (useful for a smoke test)",
    )
    parser.add_argument(
        "--semantic-refresh",
        action="store_true",
        help="ignore cached semantic results and call the model again",
    )
    args = parser.parse_args()
    if args.semantic_limit is not None and args.semantic_limit < 1:
        parser.error("--semantic-limit must be at least 1")
    scope = (args.scope or find_repo_root()).resolve()
    errors, warnings = lint(scope, check_paths=args.check_paths)
    for message in errors:
        print(f"ERROR: {message}")
    for message in warnings:
        print(f"WARNING: {message}")
    print(f"Wiki lint: {len(errors)} error(s), {len(warnings)} warning(s)")

    if args.semantic:
        if errors:
            print("SEMANTIC SKIPPED: fix structural errors before semantic review")
        else:
            from llm import LLMConfigurationError, LLMSettings, StructuredLLM
            from semantic_wiki_lint import semantic_lint

            try:
                settings = LLMSettings.from_project(
                    scope,
                    model_env="OPENAI_SEMANTIC_LINT_MODEL",
                )
                if args.semantic_model:
                    settings = LLMSettings(
                        api_key=settings.api_key,
                        model=args.semantic_model,
                        timeout_seconds=settings.timeout_seconds,
                        max_retries=settings.max_retries,
                    )
                llm = StructuredLLM(
                    settings,
                    cache_path=scope / ".tmp" / "semantic-wiki-lint.json",
                    usage_path=scope / ".tmp" / "llm-usage.jsonl",
                )
                findings, stats = semantic_lint(
                    scope,
                    llm,
                    limit=args.semantic_limit,
                    refresh=args.semantic_refresh,
                    progress=lambda current, total: print(
                        f"Semantic lint: reviewing batch {current}/{total}...", flush=True
                    ),
                )
            except LLMConfigurationError as error:
                print(f"SEMANTIC ERROR: {error}")
                raise SystemExit(2) from error
            except Exception as error:
                print(f"SEMANTIC ERROR: {type(error).__name__}: {error}")
                raise SystemExit(2) from error

            for finding in findings:
                print(
                    f"SEMANTIC {finding['severity'].upper()} [{finding['confidence']:.2f}] "
                    f"{finding['path']}:{finding['line']} {finding['kind']}: {finding['claim']}"
                )
                print(f"  Reason: {finding['reason']}")
                if finding["evidence_paths"]:
                    print(f"  Evidence: {', '.join(finding['evidence_paths'])}")
                print(f"  Suggested action: {finding['suggested_action']}")
            print(
                f"Semantic wiki lint: {len(findings)} finding(s), {stats.pages} page(s), "
                f"{stats.batches} batch(es), {stats.cached_batches} cached; "
                f"API tokens {stats.input_tokens} input / {stats.output_tokens} output"
            )
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
