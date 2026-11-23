"""Discover repository skills for the QEC Lab catalog views."""
import os
import re
from pathlib import Path

from .links import Resolver
from .markup import parse_frontmatter
from .repo import ID_PATTERN, NotFound, valid_id
from .sections import markdown_doc

_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
_DESC_LIMIT = 1024
_SKILL_PATH = re.compile(
    r"skills/([A-Za-z0-9][A-Za-z0-9._-]{0,200})/([A-Za-z0-9_][A-Za-z0-9_./-]{0,180}\.[A-Za-z0-9]{1,8})"
)


def catalog(app) -> dict:
    root = app.root / "skills"
    items = []
    resolver = Resolver(app)
    if root.is_dir():
        for entry in sorted(root.iterdir(), key=lambda item: item.name):
            record = _skill_record(entry)
            if record is not None:
                record["links"] = resolver.link_map(
                    "\n".join(part for part in (record["description"], record["usage"]) if part),
                    f"skills/{record['id']}/SKILL.md")
                items.append(record)
    return {"skills": items}


def skill(app, name: str) -> dict:
    skill_id = valid_id(name, "skill")
    path = app.root / "skills" / skill_id / "SKILL.md"
    if not path.is_file():
        raise NotFound(f"no skill {skill_id}")
    items = catalog(app)["skills"]
    listed = next((item for item in items if item["id"] == skill_id), None)
    if listed is None:
        raise NotFound(f"no skill {skill_id}")
    doc = markdown_doc(app, f"skills/{skill_id}/SKILL.md", path)
    doc["frontmatter"] = [
        pair for pair in doc.get("frontmatter", []) if pair[0] not in ("name", "description", "usage")]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    return {**listed, "doc": doc, "related": _related(skill_id, text, items)}


def _skill_record(entry: Path) -> dict | None:
    if not entry.is_dir() or entry.name.startswith(".") or not ID_PATTERN.match(entry.name):
        return None
    document = entry / "SKILL.md"
    if not document.is_file():
        return None
    try:
        text = document.read_text(encoding="utf-8")
    except OSError:
        return None
    meta_block, _body = parse_frontmatter(text)
    declared = meta_block.get("name")
    description = meta_block.get("description")
    usage = meta_block.get("usage")
    collapsed = " ".join(description.split()) if isinstance(description, str) else ""
    usage_text = " ".join(usage.split()) if isinstance(usage, str) else ""
    files = _skill_files(entry)
    return {
        "id": entry.name,
        "name": declared.strip() if isinstance(declared, str) and declared.strip() else entry.name,
        "description": collapsed,
        "usage": usage_text,
        "route": f"/skills/{entry.name}",
        "files": files,
        "issues": _issues(entry.name, declared, collapsed, usage_text, files, text),
    }


def _skill_files(folder: Path) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(name for name in dirnames if name not in _SKIP_DIRS and not name.startswith("."))
        for name in filenames:
            if name.startswith(".") or name.endswith((".pyc", ".pyo")):
                continue
            rel = (Path(dirpath) / name).relative_to(folder).as_posix()
            if ".." not in rel.split("/"):
                found.append(rel)
    found.sort()
    return found


def _issues(skill_id: str, declared, description: str, usage: str, files: list[str], text: str) -> list[str]:
    """Problems that stop an agent from discovering the skill or following its instructions."""
    issues = []
    if isinstance(declared, str) and declared.strip() and declared.strip() != skill_id:
        issues.append(
            f"The name in SKILL.md is {declared.strip()}, and the folder is {skill_id}. "
            "Agents load this skill by the folder name.")
    if not description:
        issues.append("No description. An agent cannot tell what this skill does.")
    elif len(description) > _DESC_LIMIT:
        issues.append(
            f"The description is {len(description)} characters. Discovery text stays within {_DESC_LIMIT} "
            "characters so every skill can stay loaded at once.")
    if not usage:
        issues.append("No usage. An agent cannot tell when to open this skill.")
    present = set(files)
    missing: list[str] = []
    for match in _SKILL_PATH.finditer(text):
        if match.group(1) != skill_id:
            continue
        rel = match.group(2)
        if ".." in rel.split("/") or rel in present or rel in missing:
            continue
        missing.append(rel)
    issues.extend(f"SKILL.md points at {rel}, and that file is not in the skill folder." for rel in missing)
    return issues


def _related(skill_id: str, text: str, items: list[dict]) -> list[dict]:
    found = []
    for item in items:
        other = item["id"]
        if other == skill_id:
            continue
        if re.search(rf"(?<![A-Za-z0-9._-]){re.escape(other)}(?![A-Za-z0-9._-])", text):
            found.append({"id": other, "name": item["name"], "route": item["route"]})
    return found
