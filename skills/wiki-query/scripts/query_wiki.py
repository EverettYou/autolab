#!/usr/bin/env python3
"""Search compiled wiki pages by title, Summary, and topics.

Records are skipped. Dead ends and open questions that match are listed on their own,
with a dead end's Revisit-if text, so a new line of work can see what the wiki already decided.

    .venv/bin/python skills/wiki-query/scripts/query_wiki.py "relay-bp" "bb144"

Pass ``--root`` only for a different directory that holds ``wiki/README.md``.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


SKIP_ROOT_FILES = {"README.md", "index.md"}
SUMMARY_LIMIT = 360
REVISIT_LIMIT = 400


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "wiki" / "README.md").is_file():
            return candidate
    raise ValueError(f"no wiki/README.md above {here}")


@dataclass
class Page:
    rel: str
    title: str
    summary: str
    topics: list[str]
    status: str
    folder: str
    revisit: str
    score: int = 0
    matched: list[str] = field(default_factory=list)


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    data = yaml.safe_load(text[4:end]) or {}
    if not isinstance(data, dict):
        return {}, text[end + 4 :]
    return data, text[end + 4 :]


def summary_of(body: str) -> str:
    match = re.search(r"^\*\*Summary\*\*:\s*(.*)", body, re.MULTILINE)
    if not match:
        return ""
    lines = [match.group(1).strip()]
    for line in body[match.end() :].splitlines():
        if not line.strip() or line.startswith("**"):
            break
        lines.append(line.strip())
    return " ".join(lines)


def section_after(body: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$", body, re.MULTILINE)
    if not match:
        return ""
    rest = body[match.end() :]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    chunk = rest[: nxt.start()] if nxt else rest
    return " ".join(line.strip() for line in chunk.splitlines() if line.strip())


def clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def load_pages(root: Path) -> list[Page]:
    wiki = root / "wiki"
    pages: list[Page] = []
    for path in sorted(wiki.rglob("*.md")):
        rel = path.relative_to(wiki)
        if rel.parts[0] == "records" or path.name == "README.md" or path.name in SKIP_ROOT_FILES:
            continue
        try:
            data, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"skipped wiki/{rel.as_posix()}: {exc}", file=sys.stderr)
            continue
        title = data.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        topics = []
        for key in ("topics", "project_topics"):
            values = data.get(key) or []
            if isinstance(values, list):
                topics.extend(str(item) for item in values)
        status = data.get("status")
        pages.append(
            Page(
                rel=rel.as_posix(),
                title=title.strip(),
                summary=summary_of(body),
                topics=topics,
                status=str(status).strip() if isinstance(status, str) else "",
                folder=rel.parts[0] if len(rel.parts) > 1 else "",
                revisit=section_after(body, "Revisit if"),
            )
        )
    return pages


def needles(term: str) -> set[str]:
    text = term.strip().lower()
    found = {text, text.replace("-", " "), text.replace(" ", "-")}
    return {item for item in found if item}


def term_score(term: str, page: Page) -> int:
    forms = needles(term)
    title = page.title.lower()
    title_spaced = title.replace("-", " ")
    topics = " ".join(page.topics).lower()
    summary = page.summary.lower()
    summary_spaced = summary.replace("-", " ")
    path = page.rel.lower()
    path_spaced = path.replace("-", " ").replace("/", " ")
    score = 0
    if any(form in title or form in title_spaced for form in forms):
        score += 3
    if any(form in topics for form in forms):
        score += 2
    if any(form in summary or form in summary_spaced for form in forms):
        score += 1
    if any(form in path or form in path_spaced for form in forms):
        score += 1
    return score


def rank(pages: list[Page], terms: list[str]) -> list[Page]:
    cleaned = [term.strip() for term in terms if term.strip()]
    if not cleaned:
        raise ValueError("give at least one search term")
    ranked: list[Page] = []
    for page in pages:
        scores = [(term, term_score(term, page)) for term in cleaned]
        matched = [term for term, score in scores if score]
        if not matched:
            continue
        page.matched = matched
        page.score = sum(score for _, score in scores)
        ranked.append(page)
    ranked.sort(key=lambda page: (-len(page.matched), -page.score, page.rel))
    return ranked


def render(root: Path, terms: list[str], *, limit: int = 8) -> str:
    ranked = rank(load_pages(root), terms)
    def still_open(page: Page) -> bool:
        return page.folder == "questions" and page.status not in {"closed", "superseded"}

    pages = [page for page in ranked if page.folder != "dead-ends" and not still_open(page)][:limit]
    dead_ends = [page for page in ranked if page.folder == "dead-ends"][:limit]
    open_questions = [page for page in ranked if still_open(page)][:limit]
    lines = [f"query: {' '.join(term.strip() for term in terms if term.strip())}", ""]
    lines.extend(_page_section(pages))
    lines.append("")
    lines.extend(_dead_end_section(dead_ends))
    lines.append("")
    lines.extend(_question_section(open_questions))
    if not pages and not dead_ends and not open_questions:
        lines.extend(["", "No compiled page matches these terms. Look in labs/ and references/."])
    return "\n".join(lines).rstrip() + "\n"


def _page_section(pages: list[Page]) -> list[str]:
    lines = ["## Pages"]
    if not pages:
        lines.append("(none)")
        return lines
    for index, page in enumerate(pages, start=1):
        lines.append(f"{index}. wiki/{page.rel} — {page.title}")
        if page.summary:
            lines.append(f"   Summary: {clip(page.summary, SUMMARY_LIMIT)}")
        lines.append(f"   matched: {', '.join(page.matched)}")
    return lines


def _dead_end_section(pages: list[Page]) -> list[str]:
    lines = ["## Dead ends"]
    if not pages:
        lines.append("(none)")
        return lines
    for page in pages:
        lines.append(f"- wiki/{page.rel} — {page.title}")
        revisit = clip(page.revisit, REVISIT_LIMIT) if page.revisit else "(section missing)"
        lines.append(f"  Revisit if: {revisit}")
    return lines


def _question_section(pages: list[Page]) -> list[str]:
    lines = ["## Open questions"]
    if not pages:
        lines.append("(none)")
        return lines
    for page in pages:
        lines.append(f"- wiki/{page.rel} — {page.title}")
        if page.summary:
            lines.append(f"  Summary: {clip(page.summary, SUMMARY_LIMIT)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search compiled wiki pages by title, Summary, and topics.")
    parser.add_argument("terms", nargs="+", help="words or phrases to search for")
    parser.add_argument("--limit", type=int, default=8, help="matches to show in each section (default 8)")
    parser.add_argument("--root", type=Path, help="directory that holds wiki/README.md (default: this repository)")
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else find_repo_root()
    if not (root / "wiki" / "README.md").is_file():
        print(f"no wiki/README.md in {root}", file=sys.stderr)
        return 2
    if args.limit < 1:
        print("--limit must be at least 1", file=sys.stderr)
        return 2
    try:
        print(render(root, args.terms, limit=args.limit), end="")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
