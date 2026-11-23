#!/usr/bin/env python3
"""Lint the governing docs: README.md, AGENTS.md, and everything under skills/.

Checks that procedures stay tool-agnostic and on the current layout, and that the skill catalog is
complete:

  tool-specific   assistant-specific constructs (project-dir variables, home-directory config paths,
                  scheduler or subagent tools, vendor names)
  slash-command   invocations of retired slash commands
  retired-path    paths from the retired layout and the retired queue files
  claude-md       references to the retired rules file (only section references in README.md)
  section-ref     letter-numbered section references from the retired rules file
  anti-parking    phrases that made autonomous loops idle
  smoke-cap       a 30-minute cap not qualified as the smoke cap
  git-push        raw pushes outside the git-workflow skill
  emoji           emoji characters
  frontmatter     every skills/<name>/SKILL.md has name (equal to the directory), description, and usage
  catalog         skills/README.md lists every skill, and every catalog link resolves
  missing-script  a skills/.../*.sh or *.py path named in a doc that does not exist
  broken-link     a relative markdown link in skills/ that does not resolve
  missing-path    a repository path in inline code that does not exist (warning)

Lint scripts (*lint*.py, *lint*.sh) have to name what they forbid, so in them only real usages
(project-dir variables and tool config paths), raw pushes, and emojis are checked. A line containing
"rules-lint: allow" is skipped by the line rules.

Usage: rules_lint.py [--root DIR] [-q]
Exit: 0 clean (warnings allowed), 1 failures, 2 usage error.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {".md", ".sh", ".py", ".yaml", ".yml", ".json", ".txt", ".toml", ".template"}
TOP_LEVEL = ("skills", "wiki", "lib", "labs", "references", "documents", "dashboard", "notes")
SELF = Path(__file__).resolve()

TOOL_RE = re.compile(
    r"CLAUDE_PROJECT_DIR|~/\.claude|\.claude/|CronCreate|CronList|ScheduleWakeup|TodoWrite|WebSearch|WebFetch"
    r"|\bsub-?agents?\b|\bClaude\b(?!\.md)",
    re.IGNORECASE,
)
TOOL_USE_RE = re.compile(r"\$\{?CLAUDE_PROJECT_DIR|~/\.claude/|\.claude/(?:skills|commands|agents|hooks)/")
ALLOW_MARKER = "rules-lint: allow"
SLASH_RE = re.compile(
    r"(?<![\w.~/-])/(?:auto|scout|reproduce|integrate|audit|guard|steer|feedback|replan|maintain|synthesize"
    r"|research|ideate|serve-docs)\b(?![/.\w-])"
)
RETIRED_RE = re.compile(
    # This lab OS keeps first-class `notes/` (Overleaf-like manuscripts); do not retire it.
    r"(?<![\w./-])(?:inbox|sandbox|archive|projects|lab)/(?=[\w.<{*-])"
    r"|(?<![\w./-])docs/(?:concepts|api)/"
    r"|\b(?:STEERING|TODO)\.md\b"
)
RETIRED_ALLOW = ("legacy_paths",)
CLAUDE_MD_RE = re.compile(r"\bCLAUDE\.md\b")
CLAUDE_MD_SECTION_RE = re.compile(r"\bCLAUDE\.md\s*§")
SECTION_RE = re.compile(r"§\s*[A-H]\.\d")
ANTI_PARKING = ("HOLD-and-ready", "monitor-and-ready", "awaiting your steer", "stays parked", "stop and report", "stop and ask")
ANTI_PARKING_ALLOW = re.compile(
    r"not substantive|counts as parking|never park|do not use|forbidden|avoid|do not |never stop|never wait"
    r"|do not halt|do not block|not a stop|don't park",
    re.IGNORECASE,
)
SMOKE_CAP_RE = re.compile(r"30.min cap", re.IGNORECASE)
GIT_PUSH_RE = re.compile(r"\bgit push\b")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\uFE0F]")
SCRIPT_REF_RE = re.compile(r"(?<![\w./-])(skills/[\w.-]+/[\w./-]*?[\w-]+\.(?:sh|py))\b")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
PLACEHOLDER_RE = re.compile(r"[<>{}*$]|\.\.\.")


@dataclass
class Finding:
    level: str
    rule: str
    where: str
    message: str

    def render(self) -> str:
        return f"{self.level:<5} {self.rule:<14} {self.where}: {self.message}"


def tracked_count(root: Path, rel: str) -> int:
    """Files git tracks under rel; 0 outside a git work tree. Untracked tool-local state is allowed."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "--", rel], capture_output=True, text=True)
    except OSError:
        return 0
    return len(out.stdout.splitlines()) if out.returncode == 0 else 0


def governed_files(root: Path) -> list[Path]:
    files = [root / name for name in ("README.md", "AGENTS.md") if (root / name).is_file()]
    skills = root / "skills"
    if skills.is_dir():
        for path in sorted(skills.rglob("*")):
            if not path.is_file() or path.resolve() == SELF:
                continue
            parts = set(path.relative_to(skills).parts)
            if "__pycache__" in parts or "tests" in parts:
                continue
            if path.suffix in TEXT_SUFFIXES or path.name.startswith("Dockerfile"):
                files.append(path)
    return files


def strip_fences(lines: list[str]) -> list[tuple[int, str, bool]]:
    """Yield (line number, text, inside fenced code) for markdown files."""
    out, fenced = [], False
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append((number, line, True))
            continue
        out.append((number, line, fenced))
    return out


def lint_text(root: Path, path: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    in_skills = rel.startswith("skills/")
    is_markdown = path.suffix == ".md"
    is_template = bool({"assets", "templates"} & set(path.relative_to(root).parts))
    is_lint_script = path.suffix in (".py", ".sh") and "lint" in path.stem
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [Finding("FAIL", "unreadable", rel, str(exc))]
    findings: list[Finding] = []

    def add(level: str, rule: str, number: int, message: str, line: str) -> None:
        excerpt = line.strip()
        if len(excerpt) > 110:
            excerpt = excerpt[:107] + "..."
        findings.append(Finding(level, rule, f"{rel}:{number}", f"{message} | {excerpt}"))

    for number, line, fenced in strip_fences(lines) if is_markdown else [(n, l, False) for n, l in enumerate(lines, 1)]:
        if ALLOW_MARKER in line:
            continue
        if is_lint_script:
            if TOOL_USE_RE.search(line):
                add("FAIL", "tool-specific", number, "assistant-specific construct; write tool-agnostic steps", line)
        else:
            if TOOL_RE.search(line):
                add("FAIL", "tool-specific", number, "assistant-specific construct; write tool-agnostic steps", line)
            if SLASH_RE.search(line):
                add("FAIL", "slash-command", number, "retired slash command; name the skill instead", line)
            if RETIRED_RE.search(line) and not any(token in line for token in RETIRED_ALLOW):
                add("FAIL", "retired-path", number, "retired layout path or queue file; use the current path", line)
            if in_skills and CLAUDE_MD_RE.search(line):
                add("FAIL", "claude-md", number, "point to AGENTS.md or a wiki/system page", line)
            elif not in_skills and CLAUDE_MD_SECTION_RE.search(line):
                add("FAIL", "claude-md", number, "section reference into the retired rules file", line)
            if in_skills and SECTION_RE.search(line):
                add("FAIL", "section-ref", number, "retired section numbering; link the rule's page instead", line)
            lowered = line.lower()
            for phrase in ANTI_PARKING:
                if phrase.lower() in lowered and not ANTI_PARKING_ALLOW.search(line):
                    add("FAIL", "anti-parking", number, f"phrase '{phrase}' idles autonomous loops", line)
            if SMOKE_CAP_RE.search(line) and "smoke" not in lowered:
                add("FAIL", "smoke-cap", number, "qualify the 30-minute cap as the smoke cap", line)
        if in_skills and not rel.startswith("skills/git-workflow/") and GIT_PUSH_RE.search(line):
            add("FAIL", "git-push", number, "push only through skills/git-workflow/scripts/land.sh", line)
        if EMOJI_RE.search(line):
            add("FAIL", "emoji", number, "no emojis", line)
        if not is_markdown:
            continue
        for match in SCRIPT_REF_RE.finditer(line):
            if not (root / match.group(1)).exists():
                add("FAIL", "missing-script", number, f"{match.group(1)} does not exist", line)
        if fenced:
            continue
        if in_skills and not is_template:
            for match in LINK_RE.finditer(INLINE_CODE_RE.sub("", line)):
                target = match.group(1).split("#", 1)[0]
                if not target or re.match(r"^[a-z]+:", target) or PLACEHOLDER_RE.search(target):
                    continue
                if not (path.parent / target).exists():
                    add("FAIL", "broken-link", number, f"link target {target} does not exist", line)
        for match in INLINE_CODE_RE.finditer(line):
            token = match.group(1).strip().split()[0] if match.group(1).strip() else ""
            if not token or PLACEHOLDER_RE.search(token) or "/" not in token:
                continue
            if token.split("/", 1)[0] not in TOP_LEVEL or SCRIPT_REF_RE.fullmatch(token):
                continue
            if not (root / token.rstrip("/")).exists():
                add("WARN", "missing-path", number, f"{token} does not exist (yet)", line)
    return findings


def parse_frontmatter(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields: dict[str, str] = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            fields[key] = "" if value in (">", "|", ">-", "|-") else value.strip("'\"")
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return None


def lint_skills(root: Path) -> list[Finding]:
    skills = root / "skills"
    findings: list[Finding] = []
    if not skills.is_dir():
        return [Finding("FAIL", "catalog", "skills/", "no skills/ directory")]
    names = []
    for folder in sorted(p for p in skills.iterdir() if p.is_dir()):
        if folder.name.startswith(("_", ".")) or folder.name == "__pycache__":
            continue
        names.append(folder.name)
        skill_md = folder / "SKILL.md"
        where = f"skills/{folder.name}/SKILL.md"
        if not skill_md.is_file():
            findings.append(Finding("FAIL", "frontmatter", where, "missing SKILL.md"))
            continue
        meta = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        if meta is None:
            findings.append(Finding("FAIL", "frontmatter", where, "no YAML frontmatter block"))
            continue
        if meta.get("name") != folder.name:
            findings.append(Finding("FAIL", "frontmatter", where, f"name '{meta.get('name')}' differs from the directory"))
        if not meta.get("description"):
            findings.append(Finding("FAIL", "frontmatter", where, "empty description"))
        if not meta.get("usage"):
            findings.append(Finding("FAIL", "frontmatter", where, "empty usage"))
    catalog = skills / "README.md"
    if not catalog.is_file():
        findings.append(Finding("FAIL", "catalog", "skills/README.md", "missing skill catalog"))
        return findings
    text = catalog.read_text(encoding="utf-8")
    for name in names:
        if not re.search(r"(`|\[|\(|/)%s(`|\]|/)" % re.escape(name), text):
            findings.append(Finding("FAIL", "catalog", "skills/README.md", f"skill '{name}' is not listed"))
    for match in re.finditer(r"\(([\w.-]+)/SKILL\.md\)", text):
        if not (skills / match.group(1) / "SKILL.md").is_file():
            findings.append(Finding("FAIL", "catalog", "skills/README.md", f"entry '{match.group(1)}' has no skill"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=SELF.parents[3], help="repository root")
    parser.add_argument("-q", "--quiet", action="store_true", help="print failures and the summary only")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / "skills").is_dir():
        print(f"rules_lint: {root} has no skills/ directory", file=sys.stderr)
        return 2
    findings: list[Finding] = []
    for path in governed_files(root):
        findings.extend(lint_text(root, path))
    findings.extend(lint_skills(root))
    if tracked_count(root, ".claude"):
        findings.append(Finding("WARN", "retired-path", ".claude/", "tracked files in a tool-local directory"))
    fails = [f for f in findings if f.level == "FAIL"]
    warns = [f for f in findings if f.level == "WARN"]
    for finding in fails + ([] if args.quiet else warns):
        print(finding.render())
    print(f"rules_lint: {len(fails)} failures, {len(warns)} warnings over {len(governed_files(root))} files")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
