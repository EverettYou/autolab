#!/usr/bin/env python3
"""Do the result files that prose cites exist, or can they be regenerated?

Promoted from the census `labs/2026-08-22-cited-results-census/scripts/census.py` (discussion
thread-130), with its scan roots moved to the current layout. `reproduce_lint.sh` covers the attempt
files a reproduction record cites; this covers every `results/...json` path quoted in prose, which
nothing else checks.

Sources: `wiki/**/*.md`, `references/<id>/reproduce/**/*.md`, `labs/**/*.md`, the task bodies in
`.auto-research/tasks/`, and, entry by entry, the tasks of `.auto-research/state.json` and the
threads of `.auto-research/state.json`. A path inside a fenced code block, after `--out`/`--output`/`-o`,
or containing `...` is not a citation.

Each cited path resolves one of four ways, reported separately because only the last is a candidate
for loss:

  literal    exists as written, from the repository root
  doc_rel    exists relative to the citing document's lab or reference directory (a correct citation);
             a task, thread, or task body resolves against the labs that entry names
  relocated  a file of that basename exists elsewhere (a stale path to a live record)
  missing    no file of that basename anywhere

Two ways to cite a file that is no longer in the tree, both explicit in the prose:

  pinned     written as ``<commit>:<repo path>`` (``<commit>^:`` allowed), e.g. a file deleted on purpose;
             it resolves if ``git cat-file -e <commit>:<path>`` succeeds, and FAILs otherwise
  lost       a missing path on a line carrying ``<!-- lost-citation -->``: the file was never preserved,
             and the citation stays as the historical record; counted, never FAIL. Other paths on that
             line resolve as usual

A missing path is counted and never reported as a failure: `labs/**/results/` is gitignored by
design, and the researcher decided on 2026-10-13 (thread-009) that unrecovered results are deliberate
and the guard does not chase them. The only FAIL is a pin (``<commit>:<path>``) whose commit lacks the file.

Modes:
  (default)   every citation
  --changed   only citations on lines added since --base (default HEAD), plus untracked documents

Exit: 0 no FAIL, 1 at least one FAIL, 2 usage or git error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from changed_paths import added_lines, changed_files  # noqa: E402

LABDIR = re.compile(r"labs/(20\d\d-\d\d-\d\d-[\w.-]+)")
CITE = re.compile(r"(?<![\w/.-])((?:[\w./-]*)results/[\w./-]+\.jsonl?)(?![\w])")  # .jsonl too; a .jsonl path is not its .json prefix
FENCE = re.compile(r"```.*?```", re.S)
OUTFLAG = re.compile(r"(--out|--output|-o)\s+\S*results/[\w./-]+\.jsonl?")
PIN = re.compile(r"([0-9a-f]{7,40}\^?):$")
LOST = "<!-- lost-citation -->"
ENTRY_DOCS = {".auto-research/state.json": "tasks", ".auto-research/state.json": "threads"}
PATHSPECS = ["wiki", "references", "labs", ".auto-research", ".auto-research/state.json"]


def _entry_bases(text: str, related=()) -> "list[str]":
    labs = set(LABDIR.findall(text)) | {str(r).split("/")[-1] for r in related or () if r}
    return sorted(f"labs/{lab}" for lab in labs)


def _strings(obj) -> str:
    """Every string in a JSON value, one per line, so escapes do not hide a citation."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return "\n".join(_strings(v) for v in obj.values())
    if isinstance(obj, list):
        return "\n".join(_strings(v) for v in obj)
    return ""


def sources(root: Path) -> "list[tuple[str, str, str, list[str]]]":
    """``(file, label, text, base_dirs)`` for every citing document or entry."""
    out = []
    for doc in sorted((root / "wiki").rglob("*.md")):
        rel = doc.relative_to(root).as_posix()
        out.append((rel, rel, doc.read_text(errors="replace"), []))
    for doc in sorted((root / "references").glob("*/reproduce/**/*.md")):
        rel = doc.relative_to(root).as_posix()
        ref = "/".join(rel.split("/")[:2])
        out.append((rel, rel, doc.read_text(errors="replace"), [f"{ref}/reproduce", ref]))
    for doc in sorted((root / "labs").rglob("*.md")):
        rel = doc.relative_to(root).as_posix()
        out.append((rel, rel, doc.read_text(errors="replace"), ["/".join(rel.split("/")[:2])]))
    for doc in sorted((root / ".auto-research" / "tasks").glob("*.md")):
        rel = doc.relative_to(root).as_posix()
        text = doc.read_text(errors="replace")
        out.append((rel, rel, text, _entry_bases(text)))
    for rel, key in ENTRY_DOCS.items():
        path = root / rel
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        entries = data.get(key, []) if isinstance(data, dict) else []
        rest = {k: v for k, v in data.items() if k != key} if isinstance(data, dict) else {}
        if rest:
            text = _strings(rest)
            out.append((rel, rel, text, _entry_bases(text)))
        for entry in entries:
            text = _strings(entry)
            label = f"{rel}#{entry.get('id', '?')}" if isinstance(entry, dict) else rel
            related = entry.get("related_labs") if isinstance(entry, dict) else ()
            out.append((rel, label, text, _entry_bases(text, related)))
    return out


def citations(text: str) -> "list[tuple[str, str | None, bool]]":
    """``(path, pinned commit or None, lost)`` for every citation in ``text``."""
    text = OUTFLAG.sub("", FENCE.sub("", text))
    out = []
    for line in text.splitlines():
        lost = LOST in line
        for m in CITE.finditer(line):
            if "..." in m.group(1):
                continue
            pin = PIN.search(line[:m.start()])
            out.append((m.group(1), pin.group(1) if pin else None, lost))
    return out


def pinned_exists(root: Path, rev: str, path: str) -> bool:
    return subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{rev}:{path}"],
                          capture_output=True).returncode == 0


def tracked_files(root: Path) -> "set[str]":
    out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True)
    return set(out.stdout.split())


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--root", default=str(HERE.parents[2]))
    ap.add_argument("--changed", action="store_true", help="only citations on lines added since --base")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--json", metavar="FILE", help="also write the census as JSON to FILE")
    ap.add_argument("-q", "--quiet", action="store_true", help="omit the WARN list")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    scope = None  # file -> set of cited paths on its added lines
    if args.changed:
        try:
            status = changed_files(root, PATHSPECS, args.base)
            scope = {}
            for path, st in status.items():
                if path.endswith((".md", ".json")):
                    cited = set(CITE.findall("\n".join(added_lines(root, path, st, args.base))))
                    if cited:
                        scope[path] = cited
        except RuntimeError as exc:
            print(f"cited_results_lint: {exc}", file=sys.stderr)
            return 2

    cites: dict[str, list[str]] = defaultdict(list)
    bases: dict[str, set[str]] = defaultdict(set)
    pinned: dict[tuple[str, str], list[str]] = defaultdict(list)
    lost: dict[str, list[str]] = defaultdict(list)
    for file, label, text, doc_bases in sources(root):
        if scope is not None and file not in scope:
            continue
        for path, rev, is_lost in citations(text):
            if scope is not None and path not in scope[file]:
                continue
            if rev:
                pinned[(rev, path)].append(label)
                continue
            if is_lost:
                lost[path].append(label)
            cites[path].append(label)
            bases[path].update(doc_bases)

    on_disk = {p.name for pat in ("*.json", "*.jsonl") for p in root.rglob(pat) if ".git" not in p.parts}
    buckets: dict[str, list] = {"literal": [], "doc_rel": [], "relocated": [], "missing": []}
    for path, docs in cites.items():
        if (root / path).exists():
            kind = "literal"
        elif any((root / b / path).exists() for b in bases[path]):
            kind = "doc_rel"
        elif Path(path).name in on_disk:
            kind = "relocated"
        elif path in lost:
            continue  # missing, and declared lost where it is cited
        else:
            kind = "missing"
        buckets[kind].append((path, docs))
    declared_lost = sorted(p for p in lost if p not in {q for v in buckets.values() for q, _ in v})

    fail = []  # only a pin to a commit that lacks the file; a missing result is never a failure
    pin_ok = [(r, p) for (r, p) in pinned if pinned_exists(root, r, p)]
    for (r, p), docs in pinned.items():
        if (r, p) not in pin_ok:
            fail.append({"path": f"{r}:{p}", "cited_by": sorted(set(docs)), "generator": None,
                         "reason": "not in that commit"})

    where = f"lines added since {args.base}" if args.changed else "all documents"
    print(f"cited_results_lint ({where}): {len(cites)} cited path(s): "
          + ", ".join(f"{k} {len(v)}" for k, v in buckets.items()))
    print(f"  pinned to a commit: {len(pin_ok)} of {len(pinned)} found; marked lost: {len(declared_lost)}")
    print(f"  missing, not checked (results are gitignored by design): {len(buckets['missing'])}")
    for r in fail:
        print(f"  FAIL {r['path']}  cited by {', '.join(r['cited_by'][:3])}")
    if args.json:
        Path(args.json).write_text(json.dumps({
            "scope": where, "distinct_cited_paths": len(cites),
            "counts": {k: len(v) for k, v in buckets.items()},
            "relocated": [{"path": p, "cited_by": sorted(set(d))} for p, d in buckets["relocated"]],
            "pinned": [{"commit": r, "path": p} for r, p in pinned], "lost": declared_lost,
            "missing": [{"path": p, "cited_by": sorted(set(d))} for p, d in buckets["missing"]], "fail": fail,
        }, indent=1) + "\n")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
