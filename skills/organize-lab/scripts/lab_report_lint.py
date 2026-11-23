#!/usr/bin/env python3
"""Deterministic completion checks for one lab (see ../references/report-contract.md).

    python3 skills/organize-lab/scripts/lab_report_lint.py LAB [--json] [--max-lines N] [--root DIR]

LAB is a lab id (resolved under labs/) or a path to a lab directory. The lint checks lab.json
against the schema and the lab against the layout, REPORT.md's required sections and order, local
link targets in REPORT.md and PLAN.md (and, as warnings, in notes/), evidence links in Results, a
non-empty Verdict, a Setting that names the scripts/ command, the registered PLAN.md, and leftover
template markers. It does not judge scientific quality; the organize-lab review does that.

Exit codes: 0 pass (warnings allowed), 1 errors found, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labs_catalog  # noqa: E402

REQUIRED_SECTIONS = ("Question", "Setting", "Results", "Interpretation", "Verdict", "Next steps")
PLAN_HEADINGS = ("question", "success criteri")
TEMPLATE_MARKER = "<!-- fill:"
MACHINE_SUFFIXES = (".json", ".jsonl", ".csv", ".tsv", ".npz", ".npy", ".parquet", ".yaml", ".yml", ".h5")
DEFAULT_MAX_LINES = 400

FENCE_RE = re.compile(r"^\s*(```|~~~)")
H2_RE = re.compile(r"^##\s+(.+?)\s*#*\s*$")
ANY_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
LINK_RE = re.compile(r"(!?)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
CODE_SPAN_RE = re.compile(r"`([^`\s]+)`")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_fences(lines: list[str]) -> list[str]:
    """Blank out fenced code blocks so headings and links inside them are ignored."""
    out: list[str] = []
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return out


def normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """(heading, start_line_index, end_line_index_exclusive) for every H2 section."""
    heads = [(i, H2_RE.match(line).group(1)) for i, line in enumerate(lines) if H2_RE.match(line)]
    result = []
    for n, (i, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        result.append((title, i, end))
    return result


def find_section(secs: list[tuple[str, int, int]], name: str) -> tuple[str, int, int] | None:
    want = name.lower()
    for sec in secs:
        if normalize_heading(sec[0]).startswith(want):
            return sec
    return None


def is_external(target: str) -> bool:
    return "://" in target or target.startswith(("mailto:", "#"))


def broken_links(path: Path, label: str) -> list[str]:
    """Relative link targets in a Markdown file that do not exist, as '<label>:<line>: ...' messages."""
    problems = []
    for n, line in enumerate(strip_fences(path.read_text(encoding="utf-8").splitlines()), 1):
        for match in LINK_RE.finditer(line):
            target = match.group(2)
            if is_external(target):
                continue
            path_part = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not path_part:
                continue
            if path_part.startswith("/"):
                problems.append(f"{label}:{n}: absolute link target {path_part} (use a relative path)")
            elif not (path.parent / path_part).exists():
                problems.append(f"{label}:{n}: broken link target {path_part}")
    return problems


def lint_lab(lab_dir: Path, root: Path, max_lines: int = DEFAULT_MAX_LINES) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    tracked = labs_catalog.tracked_files(root, [lab_dir.name]) or {}
    data, findings = labs_catalog.validate_lab(
        lab_dir,
        reference_ids=labs_catalog.load_reference_ids(root),
        thread_ids=labs_catalog.load_thread_ids(root),
        tracked=tracked.get(lab_dir.name),
    )
    errors += [f"{'lab.json' if f.kind == 'schema' else 'layout'}: {f.message}" for f in findings if f.level == "error"]
    warnings += [f"{'lab.json' if f.kind == 'schema' else 'layout'}: {f.message}" for f in findings if f.level == "warning"]
    if data is not None and data.get("stage") != "complete":
        notes.append(f"lab.json stage is {data.get('stage')}; set it to complete only after this lint passes")

    plan_name = labs_catalog.PLAN
    report_path = labs_catalog.report_path(lab_dir) or lab_dir / labs_catalog.REPORT
    report_name = report_path.name
    for name in (report_name, plan_name):
        path = lab_dir / name
        if path.is_file():
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if TEMPLATE_MARKER in line:
                    errors.append(f"{name}:{n}: unfilled template marker")

    plan_path = lab_dir / plan_name
    if not plan_path.is_file():
        errors.append(f"{plan_name} is missing (register the plan before running the lab)")
    else:
        plan_heads = [
            normalize_heading(m.group(1))
            for line in strip_fences(plan_path.read_text(encoding="utf-8").splitlines())
            if (m := ANY_HEADING_RE.match(line))
        ]
        for want in PLAN_HEADINGS:
            if not any(want in head for head in plan_heads):
                label = "Success criterion" if want.startswith("success") else "Question"
                errors.append(f"{plan_name} has no '{label}' heading")
        errors += broken_links(plan_path, plan_name)
    notes_dir = lab_dir / "notes"
    if notes_dir.is_dir():
        for note in sorted(notes_dir.rglob("*.md")):
            warnings += broken_links(note, note.relative_to(lab_dir).as_posix())

    if not report_path.is_file():
        errors.append(f"{report_name} is missing")
        return {"lab": lab_dir.name, "ok": False, "errors": errors, "warnings": warnings, "notes": notes}

    text = report_path.read_text(encoding="utf-8")
    raw_lines = text.splitlines()
    lines = strip_fences(raw_lines)
    if len(raw_lines) > max_lines:
        warnings.append(f"{report_name} has {len(raw_lines)} lines (budget {max_lines}); move detail to linked files")

    secs = sections(lines)
    positions = []
    for name in REQUIRED_SECTIONS:
        sec = find_section(secs, name)
        if sec is None:
            errors.append(f"{report_name} is missing the '## {name}' section")
        else:
            positions.append((sec[1], name))
    ordered = [name for _, name in sorted(positions)]
    expected = [name for name in REQUIRED_SECTIONS if name in ordered]
    if ordered != expected:
        errors.append(f"{report_name} sections are out of order: {', '.join(ordered)} (expected {', '.join(expected)})")

    errors += broken_links(report_path, report_name)

    setting = find_section(secs, "Setting")
    if setting is not None and "scripts/" not in "\n".join(raw_lines[setting[1] + 1 : setting[2]]):
        warnings.append(f"{report_name}: Setting names no scripts/ command (write the exact commands that produced the results)")

    results = find_section(secs, "Results")
    if results is not None:
        body = "\n".join(lines[results[1] + 1 : results[2]])
        cited = [m.group(2) for m in LINK_RE.finditer(body) if not is_external(m.group(2))]
        cited += CODE_SPAN_RE.findall(body)
        if not any(c.split("#", 1)[0].lower().endswith(MACHINE_SUFFIXES) or "results/" in c for c in cited):
            errors.append(f"{report_name}: Results cites no machine-readable artifact (link results/*.json or similar)")

    verdict = find_section(secs, "Verdict")
    if verdict is not None:
        body = COMMENT_RE.sub("", "\n".join(lines[verdict[1] + 1 : verdict[2]])).strip()
        if not body:
            errors.append(f"{report_name}: Verdict section is empty")

    for i, line in enumerate(lines):
        if not line.lstrip().startswith("!["):
            continue
        following = next((nxt.strip() for nxt in lines[i + 1 : i + 3] if nxt.strip()), "")
        if not following.startswith(("*", "_")):
            warnings.append(f"{report_name}:{i + 1}: figure has no italic caption line below it")

    return {"lab": lab_dir.name, "ok": not errors, "errors": errors, "warnings": warnings, "notes": notes}


def resolve_lab(arg: str, root: Path) -> Path | None:
    candidate = Path(arg)
    if candidate.is_dir() and ((candidate / "lab.json").exists() or candidate.resolve().parent.name == "labs"):
        return candidate.resolve()
    by_id = root / "labs" / arg
    return by_id if by_id.is_dir() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lab", help="lab id or path to the lab directory")
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: located from this file)")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES, help="report line budget (warning)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="machine-readable output")
    args = parser.parse_args(argv)

    root = (args.root or labs_catalog.default_root()).resolve()
    lab_dir = resolve_lab(args.lab, root)
    if lab_dir is None:
        print(f"lab_report_lint: no lab directory for {args.lab!r}", file=sys.stderr)
        return 2
    result = lint_lab(lab_dir, root, args.max_lines)
    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        for message in result["errors"]:
            print(f"ERROR {message}")
        for message in result["warnings"]:
            print(f"WARN  {message}")
        for message in result["notes"]:
            print(f"NOTE  {message}")
        verdict = "PASS" if result["ok"] else "FAIL"
        print(f"lab_report_lint: {result['lab']}: {verdict} ({len(result['errors'])} errors, {len(result['warnings'])} warnings)")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
