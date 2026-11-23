#!/usr/bin/env python3
"""Append new wiki topics to wiki/taxonomy.yml (idempotent).

Controlled vocabulary is a living list: pages must use declared topics, and ingest
may declare new ones when the source introduces a subject that is not listed yet.

Usage (from anywhere; repo root is found from this file):

    ensure_topics.py "Imaging" "Calibration"
    ensure_topics.py --dry-run "Rydberg blockade"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# Do not use re.DOTALL: list-item ".*" must not cross into the next top-level key.
TOPIC_BLOCK = re.compile(
    r"(?m)^(?P<head>topics:\n)(?P<body>(?:[ \t]*-[ \t]+[^\n]*\n)*)(?P<tail>(?=[A-Za-z_]|\Z))"
)


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "wiki" / "README.md").is_file():
            return candidate
    raise SystemExit(f"no wiki/README.md above {here}")


def normalize(name: str) -> str:
    value = " ".join(name.split())
    if not value:
        raise SystemExit("empty topic name")
    return value


def ensure_topics(path: Path, names: list[str], *, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must be a YAML mapping")
    existing = data.get("topics") or []
    if not isinstance(existing, list) or not all(isinstance(item, str) for item in existing):
        raise SystemExit(f"{path}: topics must be a list of strings")
    existing_set = set(existing)
    to_add = [name for name in names if name not in existing_set]
    # de-dupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for name in to_add:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    if not ordered:
        return []

    match = TOPIC_BLOCK.search(text)
    if not match:
        raise SystemExit(f"{path}: could not find a topics: list to extend")
    addition = "".join(f"  - {name}\n" for name in ordered)
    updated = text[: match.start("body")] + match.group("body") + addition + text[match.start("tail") :]
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return ordered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topics", nargs="+", help="topic names to ensure exist")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root (default: discover from this script)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else find_repo_root()
    path = root / "wiki" / "taxonomy.yml"
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    names = [normalize(item) for item in args.topics]
    added = ensure_topics(path, names, dry_run=args.dry_run)
    if not added:
        print("already present:" + "".join(f"\n  - {name}" for name in names))
        return 0
    prefix = "would add" if args.dry_run else "added"
    print(prefix + ":" + "".join(f"\n  - {name}" for name in added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
