"""Small Markdown helpers: YAML frontmatter, titles, heading slugs and record dates.

The frontmatter reader understands the subset of YAML the wiki uses (scalars, quoted strings,
inline and block lists, one level of nested mapping, block scalars). Anything richer is kept as
text, because the dashboard only displays frontmatter; it never interprets it.
"""

from __future__ import annotations

import re
import textwrap

FRONTMATTER = re.compile(r"\A\ufeff?---[ \t]*\r?\n(.*?)(?:\r?\n)?^(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S | re.M)
KEY_LINE = re.compile(r"^([A-Za-z_][\w .-]*?)\s*:(?:[ \t]+(.*?))?\s*$")
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
ATX_HEADING = re.compile(r"^\s{0,3}#\s+(.+?)\s*#*\s*$")


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return ``(frontmatter_block, body)``; the block is None when the file has none."""
    match = FRONTMATTER.match(text)
    if not match or not any(KEY_LINE.match(line) for line in match.group(1).splitlines()):
        return None, text
    return match.group(1), text[match.end():]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    block, body = split_frontmatter(text)
    return (parse_yaml_subset(block) if block is not None else {}), body


def _strip_comment(value: str) -> str:
    quote = None
    for index, char in enumerate(value):
        if char in "'\"":
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        elif char == "#" and quote is None and index > 0 and value[index - 1] in " \t":
            return value[:index].rstrip()
    return value


def _split_inline_list(inner: str) -> list[str]:
    items, depth, quote, current = [], 0, None, []
    for char in inner:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append("".join(current))
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        items.append("".join(current))
    return items


def scalar(value: str):
    value = _strip_comment(value.strip())
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\n", "\n")
    if value.startswith("[") and value.endswith("]"):
        return [scalar(item) for item in _split_inline_list(value[1:-1]) if item.strip()]
    if value in ("null", "~", "Null", "NULL"):
        return None
    return value


def _block(lines: list[str]):
    content = [line for line in lines if line.strip()]
    if not content:
        return ""
    base = min(len(line) - len(line.lstrip()) for line in content)
    top = [line for line in content if len(line) - len(line.lstrip()) == base]
    if all(line.strip().startswith("- ") or line.strip() == "-" for line in top):
        if len(top) == len(content):
            return [scalar(line.strip()[2:]) for line in top]
        return textwrap.dedent("\n".join(lines)).strip("\n")
    if all(KEY_LINE.match(line.strip()) for line in top) and len(top) == len(content):
        nested = {}
        for line in top:
            match = KEY_LINE.match(line.strip())
            nested[match.group(1)] = scalar(match.group(2) or "")
        return nested
    return textwrap.dedent("\n".join(lines)).strip("\n")


def parse_yaml_subset(block: str) -> dict:
    data: dict = {}
    lines = block.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.lstrip().startswith("#") or line[0] in " \t-":
            continue
        match = KEY_LINE.match(line)
        if not match:
            continue
        key, value = match.group(1).strip(), match.group(2)
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            body = []
            while index < len(lines) and (not lines[index].strip() or lines[index][0] in " \t"):
                body.append(lines[index])
                index += 1
            text = textwrap.dedent("\n".join(body)).strip("\n")
            data[key] = text if value.startswith("|") else " ".join(text.split())
        elif value is None or value == "":
            body = []
            while index < len(lines) and (not lines[index].strip() or lines[index][0] in " \t"
                                          or lines[index].startswith("-")):
                body.append(lines[index])
                index += 1
            data[key] = _block(body)
        else:
            data[key] = scalar(value)
    return data


def strip_inline_markdown(text: str) -> str:
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*\*|__|\*|_|`)", "", text)
    return text.strip()


def slugify(text: str) -> str:
    """Heading anchor used by both server and client: lowercase, word characters and hyphens."""
    value = strip_inline_markdown(text).lower()
    value = re.sub(r"[^\w\- ]", "", value)
    return value.strip().replace(" ", "-")


def first_heading(body: str) -> str | None:
    in_fence = None
    for line in body.splitlines():
        fence = FENCE.match(line)
        if fence:
            marker = fence.group(1)[0]
            if in_fence is None:
                in_fence = marker
            elif in_fence == marker:
                in_fence = None
            continue
        if in_fence:
            continue
        match = ATX_HEADING.match(line)
        if match:
            return strip_inline_markdown(match.group(1))
    return None


def title_from_name(name: str) -> str:
    stem = name.rsplit("/", 1)[-1]
    stem = stem[:-3] if stem.endswith(".md") else stem
    words = stem.replace("_", " ").replace("-", " ").strip()
    return words[:1].upper() + words[1:] if words else name


def date_from_name(name: str) -> str | None:
    match = DATE_PREFIX.match(name.rsplit("/", 1)[-1])
    return match.group(1) if match else None


def display_frontmatter(meta: dict) -> list[list]:
    """Frontmatter as ``[key, value]`` pairs in file order, with values made JSON-friendly."""
    return [[key, value] for key, value in meta.items()]
