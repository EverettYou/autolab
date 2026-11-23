#!/usr/bin/env python3
"""Scaffold labs/<YYYY-MM-DD-slug>/ with lab.json, PLAN.md, REPORT.md and .gitignore.

    python3 skills/create-lab/scripts/new_lab.py --slug SLUG --title TITLE --summary SENTENCE \
        [--date YYYY-MM-DD] [--parent LAB-ID ...] [--reference ID ...] [--thread thread-NNN ...] \
        [--focus TEXT] [--next TEXT] [--no-catalog] [--root DIR]

The new lab starts in stage "active" with template sections marked <!-- fill: ... -->. The
script refuses to overwrite an existing lab, checks reference and thread ids against their
registries, validates the new lab.json, and rebuilds labs/labs.json unless --no-catalog.

Exit codes: 0 created, 1 created but the catalog rebuild failed, 2 refused (nothing written).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL_DIR / "templates"
sys.path.insert(0, str(SKILL_DIR.parent / "organize-lab" / "scripts"))
import labs_catalog  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG = 60


def render(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--slug", required=True, help="lowercase kebab-case slug, e.g. g3-bb144-circuit")
    parser.add_argument("--title", required=True, help="human-readable title")
    parser.add_argument("--summary", required=True, help="one sentence for the catalog")
    parser.add_argument("--date", default=date.today().isoformat(), help="creation date (default: today)")
    parser.add_argument(
        "--parent", action="append", default=[], metavar="LAB-ID",
        help="parent lab id this work continues (repeatable); inheritance, not a results rollup",
    )
    parser.add_argument("--reference", action="append", default=[], metavar="ID", help="reference id (repeatable)")
    parser.add_argument("--thread", action="append", default=[], metavar="ID", help="discussion thread id (repeatable)")
    parser.add_argument("--focus", default="Register the plan in PLAN.md.", help="initial current_focus")
    parser.add_argument("--next", dest="next_action", default="Fill PLAN.md, then run a smoke test.", help="initial next_action")
    parser.add_argument("--no-catalog", action="store_true", help="do not rebuild labs/labs.json")
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: located from this file)")
    args = parser.parse_args(argv)

    root = (args.root or labs_catalog.default_root()).resolve()
    problems: list[str] = []
    if not SLUG_RE.match(args.slug) or len(args.slug) > MAX_SLUG:
        problems.append(f"slug must be lowercase kebab-case, at most {MAX_SLUG} characters: {args.slug!r}")
    if labs_catalog.parse_date(args.date) is None:
        problems.append(f"date must be YYYY-MM-DD: {args.date!r}")
    if not args.title.strip() or not args.summary.strip():
        problems.append("title and summary must be non-empty")
    reference_ids = labs_catalog.load_reference_ids(root)
    if reference_ids is not None:
        problems += [f"unknown reference id: {r}" for r in args.reference if r not in reference_ids]
    thread_ids = labs_catalog.load_thread_ids(root)
    for thread in args.thread:
        if not labs_catalog.THREAD_RE.match(thread):
            problems.append(f"not a thread id: {thread!r}")
        elif thread_ids is not None and thread not in thread_ids:
            problems.append(f"unknown discussion thread: {thread}")

    lab_id = f"{args.date}-{args.slug}"
    lab_dir = root / "labs" / lab_id
    parents = list(dict.fromkeys(args.parent))
    if lab_id in parents:
        problems.append("parents must not include the new lab's own id")
    for parent in parents:
        if not labs_catalog.LAB_ID_RE.match(parent):
            problems.append(f"parent is not a lab id: {parent!r}")
        elif not (root / "labs" / parent).is_dir():
            problems.append(f"unknown parent lab: {parent}")
    if not (root / "labs").is_dir():
        problems.append(f"no labs/ directory under {root}")
    elif lab_dir.exists():
        problems.append(f"labs/{lab_id} already exists")
    if problems:
        for problem in problems:
            print(f"new_lab: {problem}", file=sys.stderr)
        return 2

    values = {"TITLE": args.title.strip(), "LAB_ID": lab_id, "DATE": args.date}
    lab_dir.mkdir()
    for name in ("PLAN.md", "REPORT.md"):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        (lab_dir / name).write_text(render(text, values), encoding="utf-8")
    (lab_dir / ".gitignore").write_text((TEMPLATES / "lab.gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    record = {
        "id": lab_id,
        "title": args.title.strip(),
        "stage": "active",
        "summary": args.summary.strip(),
        "current_focus": args.focus,
        "next_action": args.next_action,
        "created": args.date,
        "updated": args.date,
        "references": list(dict.fromkeys(args.reference)),
        "discussion": list(dict.fromkeys(args.thread)),
        "parents": parents,
    }
    (lab_dir / "lab.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _, findings = labs_catalog.validate_lab(lab_dir, reference_ids=reference_ids, thread_ids=thread_ids)
    for finding in findings:
        print(finding.render())
    print(f"new_lab: created labs/{lab_id}/ (lab.json, PLAN.md, REPORT.md, .gitignore)")
    if args.no_catalog:
        return 0
    code = labs_catalog.main(["--root", str(root), "rebuild", "-q"])
    if code != 0:
        print("new_lab: the lab exists but labs/labs.json was not fully rebuilt; see errors above")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
