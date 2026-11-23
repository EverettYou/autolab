#!/usr/bin/env python3
"""Extract sections, algorithms, equations, tables, footnotes from paper.md."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def identify_sections(text: str) -> list[dict]:
    lines = text.split("\n")
    sections: list[dict] = []
    current_section: str | None = None
    current_lines: list[str] = []

    md_heading = re.compile(r"^(#{1,4})\s+(.+)$")
    numbered_heading = re.compile(r"^(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z\s:,\-]+)$")
    allcaps_heading = re.compile(r"^([A-Z][A-Z\s]{4,})$")
    page_marker = re.compile(r"^--- page \d+ ---$")

    def save_current() -> None:
        if current_section and current_lines:
            sections.append(
                {"title": current_section, "content": "\n".join(current_lines).strip()}
            )

    for line in lines:
        if page_marker.match(line.strip()):
            continue
        heading: str | None = None
        m = md_heading.match(line)
        if m:
            heading = m.group(2).strip()
        if not heading:
            m = numbered_heading.match(line.strip())
            if m:
                heading = f"{m.group(1)} {m.group(2).strip()}"
        if not heading:
            m = allcaps_heading.match(line.strip())
            if m and len(m.group(1).strip()) > 5:
                heading = m.group(1).strip().title()
        if heading:
            save_current()
            current_section = heading
            current_lines = []
        else:
            current_lines.append(line)
    save_current()
    return sections


def extract_algorithms(text: str) -> list[dict]:
    pattern = re.compile(
        r"(Algorithm\s+\d+[:\.]?\s*[^\n]*)\n(.*?)(?=Algorithm\s+\d+[:\.]|^#{1,4}\s|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    return [
        {"title": m.group(1).strip(), "content": m.group(2).strip()}
        for m in pattern.finditer(text)
        if m.group(2).strip()
    ]


def extract_equations(text: str) -> list[dict]:
    equations: list[dict] = []
    latex_eq = re.compile(
        r"\\begin\{(?:equation|align|gather)\*?\}(.*?)\\end\{(?:equation|align|gather)\*?\}",
        re.DOTALL,
    )
    for i, match in enumerate(latex_eq.finditer(text)):
        equations.append(
            {"number": i + 1, "content": match.group(1).strip(), "raw": match.group(0)}
        )
    display_math = re.compile(r"\$\$(.*?)\$\$\s*\((\d+)\)", re.DOTALL)
    for match in display_math.finditer(text):
        equations.append(
            {
                "number": int(match.group(2)),
                "content": match.group(1).strip(),
                "raw": match.group(0),
            }
        )
    numbered_line = re.compile(r"^(.+?)\s+\((\d+)\)\s*$", re.MULTILINE)
    for match in numbered_line.finditer(text):
        content = match.group(1).strip()
        num = int(match.group(2))
        if any(c in content for c in "=+∑∏∫_^{}\\√∞"):
            if not any(eq["number"] == num for eq in equations):
                equations.append(
                    {"number": num, "content": content, "raw": match.group(0)}
                )
    equations.sort(key=lambda e: e["number"])
    return equations


def extract_tables(text: str) -> list[dict]:
    tables: list[dict] = []
    table_caption = re.compile(
        r"(Table\s+\d+[:\.]?\s*[^\n]*)\n(.*?)(?=Table\s+\d+[:\.]|^#{1,4}\s|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    for match in table_caption.finditer(text):
        caption = match.group(1).strip()
        body = match.group(2).strip()
        if "|" in body or "\t" in body or re.search(r"\s{3,}", body):
            tables.append({"caption": caption, "content": body[:2000]})
    md_table = re.compile(r"(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n)*)", re.MULTILINE)
    for match in md_table.finditer(text):
        table_text = match.group(1).strip()
        if not any(table_text in t["content"] for t in tables):
            tables.append({"caption": "Untitled table", "content": table_text})
    return tables


def extract_footnotes(text: str) -> list[str]:
    footnotes: list[str] = []
    fn_pattern = re.compile(
        r"(?:^|\n)[\s]*(?:[\u00b9\u00b2\u00b3\u2074-\u2079]|\[(\d+)\]|(\d+)\.)[\s]+(.+?)"
        r"(?=\n[\s]*(?:[\u00b9\u00b2\u00b3\u2074-\u2079]|\[\d+\]|\d+\.)\s|\n\n|\Z)",
        re.DOTALL,
    )
    for match in fn_pattern.finditer(text):
        content = match.group(0).strip()
        if len(content) > 10:
            footnotes.append(content)
    fn_section = re.compile(
        r"(?:footnote|note)s?\s*:?\s*\n(.*?)(?=\n#{1,4}\s|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    for match in fn_section.finditer(text):
        content = match.group(1).strip()
        if content and content not in footnotes:
            footnotes.append(content)
    return footnotes


def save_list_to_dir(
    items: list[dict], output_dir: Path, name_key: str = "title"
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(items):
        name = str(item.get(name_key, item.get("caption", f"item_{i+1}")))
        clean = re.sub(r"[^\w\s-]", "", name)
        clean = re.sub(r"\s+", "_", clean).strip("_").lower() or f"item_{i+1}"
        clean = clean[:80]
        path = output_dir / f"{i+1:02d}_{clean}.md"
        body = item.get("content", item.get("raw", ""))
        path.write_text(f"# {name}\n\n{body}\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <paper.md> <output_dir>", file=sys.stderr)
        return 1

    paper_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    if not paper_path.is_file():
        print(f"ERROR: {paper_path} not found", file=sys.stderr)
        return 1

    text = paper_path.read_text(encoding="utf-8")
    sections = identify_sections(text)
    if sections:
        save_list_to_dir(sections, output_dir / "sections")
    else:
        sec_dir = output_dir / "sections"
        sec_dir.mkdir(parents=True, exist_ok=True)
        (sec_dir / "01_full_text.md").write_text(text, encoding="utf-8")

    algorithms = extract_algorithms(text)
    if algorithms:
        save_list_to_dir(algorithms, output_dir / "algorithms")

    equations = extract_equations(text)
    if equations:
        save_list_to_dir(equations, output_dir / "equations", name_key="number")

    tables = extract_tables(text)
    if tables:
        save_list_to_dir(tables, output_dir / "tables", name_key="caption")

    footnotes = extract_footnotes(text)
    fn_path = output_dir / "footnotes.md"
    if footnotes:
        parts = ["# Footnotes\n"]
        for i, fn in enumerate(footnotes, 1):
            parts.append(f"## Footnote {i}\n\n{fn}\n\n---\n")
        fn_path.write_text("\n".join(parts), encoding="utf-8")
    else:
        fn_path.write_text("# Footnotes\n\nNone extracted.\n", encoding="utf-8")

    summary = (
        f"sections={len(sections)} algorithms={len(algorithms)} "
        f"equations={len(equations)} tables={len(tables)} footnotes={len(footnotes)}"
    )
    (output_dir / "SUMMARY.txt").write_text(summary + "\n", encoding="utf-8")
    print(f"{output_dir}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
