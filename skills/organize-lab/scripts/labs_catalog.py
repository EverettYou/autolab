#!/usr/bin/env python3
"""Validate labs/*/lab.json and rebuild the labs/labs.json catalog.

Run from anywhere; the repository root is located from this file's path (override with --root).

    python3 skills/organize-lab/scripts/labs_catalog.py validate [LAB_ID ...] [--json] [-q]
    python3 skills/organize-lab/scripts/labs_catalog.py rebuild [--force]
    python3 skills/organize-lab/scripts/labs_catalog.py check

validate  Check every lab.json (or only the named labs) against the lab.json schema, and every lab
          against the layout in ../references/report-contract.md. Layout findings are errors
          (validate and check exit 1) but do not drop a schema-valid lab from the catalog.
rebuild   Validate all labs, then rewrite labs/labs.json sorted newest first (creation date, then
          id, descending). Refuses to write while any lab.json is invalid unless --force, which
          writes the valid entries only.
check     Exit 1 when labs/labs.json differs from what rebuild would write.

Exit codes: 0 ok (warnings allowed), 1 validation errors or stale catalog, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

STAGES = ("active", "blocked", "complete", "inactive")
STRING_KEYS = ("id", "title", "stage", "summary", "current_focus", "next_action", "created", "updated")
OPTIONAL_STRING_KEYS = ("blocked_reason",)
LIST_KEYS = ("references", "discussion", "parents")
LAB_KEYS = STRING_KEYS + LIST_KEYS
RETIRED_KEYS = ("report", "plan", "readme")
CATALOG_KEYS = (
    "id", "title", "stage", "summary", "current_focus", "next_action",
    "created", "updated", "parents",
)

PLAN = "PLAN.md"
REPORT = "REPORT.md"
LEGACY_REPORT = "report.md"
ROOT_FILES = ("lab.json", PLAN, REPORT, ".gitignore")
LAB_DIRS = ("notes", "scripts", "configs", "tests", "results", "figures", "data", "checkpoints", "logs")
TRACKED_OUTPUT_DIRS = ("results", "figures")
TRANSIENT = frozenset({"__pycache__", ".pytest_cache", ".ipynb_checkpoints", ".mypy_cache", ".ruff_cache", ".DS_Store"})
MAX_TRACKED_BYTES = 1 << 20
# Originating manuscript cited as reference "main" before registry entry.
LEGACY_REFERENCE_IDS = frozenset({"main"})

# What each lab directory may hold, by suffix (report-contract.md, Layout). A file that breaks its
# directory's rule gets the destination below; data/ holds anything, and a folder directly under
# scripts/ is an old sub-experiment that keeps its own layout.
_IMAGES = frozenset({".png", ".svg", ".jpg", ".jpeg", ".gif"})
_CODE = frozenset({".py", ".sh", ".bash", ".jl", ".ipynb", ".sage", ".g"})
_DOCS = frozenset({".md", ".tex", ".bib", ".rst"})
_WEIGHTS = frozenset({".pt", ".pth", ".ckpt", ".safetensors"})
_LOGS = frozenset({".log", ".out", ".err", ".pid", ".lock"})
_ARRAYS = frozenset({".npz", ".npy", ".h5", ".pkl", ".parquet"})
_INPUTS = frozenset({".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".csv"})
# A notes/ folder that holds a .tex document may keep that document's build files next to it.
_TEX_BUILD = frozenset({".sh", ".conf", ".cls", ".sty", ".bst", ".pdf"}) | _IMAGES
CONTENT_RULES = {
    "notes": _DOCS | {".pdf"},
    "results": frozenset({".json", ".jsonl", ".csv", ".tsv", ".txt"}),
    "figures": _IMAGES | {".pdf"},
    "scripts": _CODE | _INPUTS,
    "configs": _INPUTS,
    "tests": _CODE | _INPUTS | {".npz"},
    "checkpoints": _WEIGHTS | {".json", ".txt", ".md", ".sha256", ""},
    "logs": _LOGS | {".txt", ".json", ".jsonl"},
}
ALWAYS_ALLOWED = frozenset({".gitkeep", ".gitignore"})


def folder_suffixes(files) -> dict[str, set[str]]:
    """Suffixes of the files directly in each folder, keyed by lab-relative folder path."""
    out: dict[str, set[str]] = {}
    for rel in files:
        path = PurePosixPath(rel)
        out.setdefault(str(path.parent), set()).add(path.suffix.lower())
    return out


def _ancestor_suffixes(rel: str, folders: dict[str, set[str]]) -> set[str]:
    """Suffixes of the files directly in each folder that contains ``rel``, up to its top directory.

    A TeX document's build folder (fonts, figures) sits next to or below the .tex file, so this
    lets a document's build files live in a subfolder beside it, such as its fontconfig folder.
    """
    found: set[str] = set()
    for folder in PurePosixPath(rel).parents:
        if str(folder) == ".":
            break
        found |= folders.get(str(folder), set())
    return found


def content_destination(rel: str, siblings: set[str] = frozenset()) -> tuple[str | None, str] | None:
    """Where a misplaced lab-relative file belongs, or None when it is in the right directory.

    ``siblings`` are the suffixes found in the notes/ folders that contain the file (to recognise
    a TeX document's build folder). The result is (destination, reason); the destination is None when the
    file has no place in the layout (a scratch or backup file) and should be deleted.
    """
    parts = PurePosixPath(rel).parts
    if len(parts) < 2 or parts[0] not in CONTENT_RULES or parts[-1] in ALWAYS_ALLOWED:
        return None
    top, name = parts[0], parts[-1]
    suffix = PurePosixPath(name).suffix.lower()
    if top == "scripts" and len(parts) > 2:
        return None
    if suffix in CONTENT_RULES[top]:
        return None
    if top == "notes" and ".tex" in siblings and suffix in _TEX_BUILD:
        return None
    tail = "/".join(parts[1:])
    for suffixes, home, reason in (
        (_IMAGES, "figures", "figure"), (_DOCS, "notes", "document"), (_LOGS, "logs", "log"),
        (_ARRAYS, "data", "array data"), (_WEIGHTS, "checkpoints", "weights"), (_CODE, "scripts", "code"),
    ):
        if suffix in suffixes:
            return f"{home}/{tail}", reason
    if top == "figures" and suffix in _INPUTS | {".jsonl", ".tsv"}:
        return f"results/{tail}", "output"
    if suffix == ".pdf":
        return f"figures/{tail}", "figure"
    return None, f"no place in the layout for a {suffix or 'suffix-less'} file under {top}/"

LAB_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
LAB_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
THREAD_RE = re.compile(r"^thread-\d+$")


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning"
    lab: str
    message: str
    kind: str = "schema"  # "schema" (lab.json) | "layout"

    def render(self) -> str:
        tag = "ERROR" if self.level == "error" else "WARN "
        return f"{tag} {self.lab}: {self.message}"


def default_root() -> Path:
    return Path(__file__).resolve().parents[3]


def parse_date(value: str) -> date | None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def load_reference_ids(root: Path) -> set[str] | None:
    """Known reference ids (directories plus registry ids and aliases); None when references/ is absent."""
    ref_dir = root / "references"
    if not ref_dir.is_dir():
        return None
    ids = {p.name for p in ref_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))}
    ids |= LEGACY_REFERENCE_IDS
    registry = ref_dir / "references.json"
    if registry.is_file():
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ids
        for entry in data.get("references", []) if isinstance(data, dict) else []:
            if isinstance(entry, dict):
                if isinstance(entry.get("id"), str):
                    ids.add(entry["id"])
                ids.update(a for a in entry.get("aliases") or [] if isinstance(a, str))
    return ids


def load_thread_ids(root: Path) -> set[str] | None:
    """Thread ids from `.auto-research/state.json` → `threads`; None when absent/unreadable."""
    path = root / ".auto-research" / "state.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    threads = data.get("threads", []) if isinstance(data, dict) else []
    return {t["id"] for t in threads if isinstance(t, dict) and isinstance(t.get("id"), str)}


def lab_dirs(root: Path) -> tuple[list[Path], list[Finding]]:
    labs_root = root / "labs"
    findings: list[Finding] = []
    dirs: list[Path] = []
    for path in sorted(labs_root.iterdir()):
        if not path.is_dir() or path.name.startswith((".", "_")):
            continue
        if LAB_DIR_RE.match(path.name):
            dirs.append(path)
        else:
            findings.append(Finding("warning", path.name, "not a lab directory (expected YYYY-MM-DD-slug)"))
    return dirs, findings


def report_path(lab_dir: Path) -> Path | None:
    """The lab's report: REPORT.md, or report.md in a lab not yet migrated."""
    for name in (REPORT, LEGACY_REPORT):
        if (lab_dir / name).is_file():
            return lab_dir / name
    return None



def layout_exceptions(root: Path) -> dict[str, list[str]]:
    """Grandfathered paths from labs/layout-exceptions.json: {lab id: [lab-relative glob, ...]}.

    Extension for manuscript citation. Historical labs keep the paths their records cite.
    """
    path = root / "labs" / "layout-exceptions.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    labs = data.get("labs", data) if isinstance(data, dict) else {}
    return {
        lab_id: [g for g in globs if isinstance(g, str)]
        for lab_id, globs in labs.items()
        if isinstance(lab_id, str) and isinstance(globs, list)
    }


def tracked_files(root: Path, lab_ids: list[str] | None = None) -> dict[str, set[str]] | None:
    """Lab-relative files that git tracks or would track, keyed by lab id.

    Ignored local files are left out, so the layout check sees what every clone sees. None when git
    is unavailable or the root is not a work tree (the content and size checks are then skipped).
    """
    paths = [f"labs/{lab_id}" for lab_id in lab_ids] if lab_ids else ["labs"]
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *paths],
            capture_output=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    out: dict[str, set[str]] = {}
    for raw in proc.stdout.decode("utf-8", "surrogateescape").split("\0"):
        parts = PurePosixPath(raw).parts
        if len(parts) >= 3 and parts[0] == "labs":
            out.setdefault(parts[1], set()).add("/".join(parts[2:]))
    return out


def _preview(names: list[str], limit: int = 6) -> str:
    shown = ", ".join(names[:limit])
    return shown + (f", and {len(names) - limit} more" if len(names) > limit else "")


def layout_problems(lab_dir: Path, tracked: set[str] | None = None) -> list[str]:
    """Differences between a lab directory and the layout in ../references/report-contract.md."""
    names = {p.name for p in lab_dir.iterdir()}
    problems: list[str] = []
    if PLAN not in names:
        problems.append(f"{PLAN} is missing")
    if REPORT not in names:
        problems.append(f"{LEGACY_REPORT} should be named {REPORT}" if LEGACY_REPORT in names else f"{REPORT} is missing")
    if "README.md" in names:
        problems.append("README.md is retired: move its content to notes/ (lab_layout.py tidy)")
    stray_files: list[str] = []
    stray_dirs: list[str] = []
    for path in sorted(lab_dir.iterdir()):
        name = path.name
        if name in ROOT_FILES or name in TRANSIENT or name == "README.md":
            continue
        if name == LEGACY_REPORT and REPORT not in names:
            continue
        if path.is_dir():
            if name not in LAB_DIRS:
                stray_dirs.append(name + "/")
        else:
            stray_files.append(name)
    if stray_files:
        problems.append(f"{len(stray_files)} file(s) in the lab root outside the layout: {_preview(stray_files)}")
    if stray_dirs:
        problems.append(f"{len(stray_dirs)} directory(ies) outside the layout: {_preview(stray_dirs)}")
    folders = folder_suffixes(tracked or ())
    misplaced: dict[str, list[str]] = {}
    for rel in sorted(tracked or ()):
        placed = content_destination(rel, _ancestor_suffixes(rel, folders))
        if placed is not None:
            dst, reason = placed
            misplaced.setdefault(f"{PurePosixPath(rel).parts[0]}/ holds {reason} files" if dst else reason, []).append(
                f"{rel} -> {dst}" if dst else rel)
    for what, files in misplaced.items():
        problems.append(f"{len(files)} misplaced: {what}: {_preview(files, 3)} (lab_layout.py tidy)")
    for rel in sorted(tracked or ()):
        if PurePosixPath(rel).parts[0] not in TRACKED_OUTPUT_DIRS:
            continue
        path = lab_dir / rel
        size = path.stat().st_size if path.is_file() else 0
        if size > MAX_TRACKED_BYTES:
            problems.append(f"{rel} is {size / (1 << 20):.1f} MB; tracked outputs stay under 1 MB (move it to data/)")
    return problems


def validate_lab(
    lab_dir: Path,
    *,
    reference_ids: set[str] | None = None,
    thread_ids: set[str] | None = None,
    tracked: set[str] | None = None,
) -> tuple[dict | None, list[Finding]]:
    """Validate one lab directory. Returns (data if valid else None, findings).

    ``tracked`` lists the lab-relative files git tracks or would track; when given, each is
    checked against its directory's content rule, and files in results/ and figures/ for size.
    """
    name = lab_dir.name
    findings: list[Finding] = []

    def error(message: str) -> None:
        findings.append(Finding("error", name, message))

    def warn(message: str) -> None:
        findings.append(Finding("warning", name, message))

    path = lab_dir / "lab.json"
    if not path.is_file():
        error("lab.json is missing")
        return None, findings
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error(f"lab.json is not valid JSON: {exc}")
        return None, findings
    if not isinstance(data, dict):
        error("lab.json must contain a JSON object")
        return None, findings

    missing = [key for key in LAB_KEYS if key not in data]
    if missing:
        error(f"missing keys: {', '.join(missing)}")
    retired = [key for key in RETIRED_KEYS if key in data]
    if retired:
        warn(f"retired keys {', '.join(retired)}: file names are fixed ({PLAN}, {REPORT}); remove them")
    unknown = sorted(set(data) - set(LAB_KEYS) - set(OPTIONAL_STRING_KEYS) - set(RETIRED_KEYS))
    if unknown:
        warn(f"unknown keys (not shown on the catalog): {', '.join(unknown)}")

    for key in STRING_KEYS + OPTIONAL_STRING_KEYS:
        if key in data and not isinstance(data[key], str):
            error(f"{key} must be a string")
    for key in LIST_KEYS:
        value = data.get(key)
        if key in data and (not isinstance(value, list) or not all(isinstance(v, str) for v in value)):
            error(f"{key} must be a list of strings")

    lab_id = data.get("id")
    if isinstance(lab_id, str):
        if lab_id != name:
            error(f"id {lab_id!r} does not match the directory name")
        elif not LAB_ID_RE.match(lab_id):
            error("id must look like YYYY-MM-DD-slug")

    if isinstance(data.get("title"), str) and not data["title"].strip():
        error("title is empty")
    if isinstance(data.get("summary"), str) and not data["summary"].strip():
        warn("summary is empty (the catalog shows one sentence per lab)")

    stage = data.get("stage")
    if isinstance(stage, str) and stage not in STAGES:
        error(f"stage {stage!r} is not one of {', '.join(STAGES)}")
    if stage in ("active", "blocked") and isinstance(data.get("next_action"), str) and not data["next_action"].strip():
        warn(f"stage is {stage} but next_action is empty")
    if stage == "blocked":
        reason = data.get("blocked_reason")
        if not isinstance(reason, str) or not reason.strip():
            warn("stage is blocked but blocked_reason is empty")

    created = parse_date(data.get("created")) if "created" in data else None
    updated = parse_date(data.get("updated")) if "updated" in data else None
    for key, parsed in (("created", created), ("updated", updated)):
        if key in data and isinstance(data[key], str) and parsed is None:
            error(f"{key} must be an ISO date YYYY-MM-DD")
    if created and updated and updated < created:
        error(f"updated {updated} is earlier than created {created}")
    id_match = LAB_ID_RE.match(lab_id) if isinstance(lab_id, str) else None
    if created and id_match and id_match.group(1) != created.isoformat():
        warn(f"created {created} differs from the id date {id_match.group(1)}")

    if stage == "complete" and report_path(lab_dir) is None:
        error(f"stage is complete but the lab has no {REPORT}")
    findings.extend(Finding("error", name, problem, "layout") for problem in layout_problems(lab_dir, tracked))

    refs = data.get("references")
    if isinstance(refs, list):
        if len(set(refs)) != len(refs):
            warn("references contains duplicates")
        if reference_ids is not None:
            for ref in refs:
                if isinstance(ref, str) and ref not in reference_ids:
                    error(f"unknown reference id: {ref}")
    threads = data.get("discussion")
    if isinstance(threads, list):
        if len(set(threads)) != len(threads):
            warn("discussion contains duplicates")
        for thread in threads:
            if not isinstance(thread, str):
                continue
            if not THREAD_RE.match(thread):
                error(f"discussion entry is not a thread id: {thread!r}")
            elif thread_ids is not None and thread not in thread_ids:
                warn(f"discussion thread {thread} is not in this checkout's threads store")

    parents = data.get("parents")
    if isinstance(parents, list):
        if len(set(parents)) != len(parents):
            warn("parents contains duplicates")
        if isinstance(lab_id, str) and lab_id in parents:
            error("parents must not include this lab's own id")
        labs_root = lab_dir.parent
        for parent in parents:
            if not isinstance(parent, str):
                continue
            if not LAB_ID_RE.match(parent):
                error(f"parent is not a lab id: {parent!r}")
            elif not (labs_root / parent).is_dir():
                error(f"unknown parent lab: {parent}")

    schema_errors = [f for f in findings if f.level == "error" and f.kind != "layout"]
    return (data if not schema_errors else None), findings


def validate_all(root: Path, only: list[str] | None = None) -> tuple[dict[str, dict], list[Finding]]:
    labs_root = root / "labs"
    if not labs_root.is_dir():
        raise FileNotFoundError(f"no labs/ directory under {root}")
    dirs, findings = lab_dirs(root)
    if only:
        wanted = set(only)
        known = {d.name for d in dirs}
        findings = [Finding("error", name, "no such lab directory") for name in sorted(wanted - known)]
        dirs = [d for d in dirs if d.name in wanted]
    reference_ids = load_reference_ids(root)
    thread_ids = load_thread_ids(root)
    tracked = tracked_files(root, [d.name for d in dirs] if only else None) or {}
    records: dict[str, dict] = {}
    for lab_dir in dirs:
        data, lab_findings = validate_lab(
            lab_dir, reference_ids=reference_ids, thread_ids=thread_ids, tracked=tracked.get(lab_dir.name)
        )
        findings.extend(lab_findings)
        if data is not None:
            records[lab_dir.name] = data
    return records, findings


def build_catalog(records: dict[str, dict]) -> dict:
    ordered = sorted(records.values(), key=lambda d: (d["created"], d["id"]), reverse=True)
    return {"labs": [{key: lab[key] for key in CATALOG_KEYS} for lab in ordered]}


def render_catalog(catalog: dict) -> str:
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def _report(findings: list[Finding], *, quiet: bool) -> None:
    for finding in findings:
        if finding.level == "error" or not quiet:
            print(finding.render())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: located from this file)")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate", help="validate lab.json files")
    p_validate.add_argument("labs", nargs="*", help="lab ids to validate (default: all)")
    p_validate.add_argument("--json", action="store_true", dest="as_json", help="machine-readable output")
    p_validate.add_argument("-q", "--quiet", action="store_true", help="print errors only")
    p_rebuild = sub.add_parser("rebuild", help="validate and rewrite labs/labs.json")
    p_rebuild.add_argument("--force", action="store_true", help="write valid entries even when some labs are invalid")
    p_rebuild.add_argument("-q", "--quiet", action="store_true", help="print errors only")
    p_check = sub.add_parser("check", help="exit 1 when labs/labs.json is stale")
    p_check.add_argument("-q", "--quiet", action="store_true", help="print errors only")
    args = parser.parse_args(argv)

    root = (args.root or default_root()).resolve()
    try:
        records, findings = validate_all(root, getattr(args, "labs", None) or None)
    except FileNotFoundError as exc:
        print(f"labs_catalog: {exc}", file=sys.stderr)
        return 2
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]

    if args.command == "validate":
        if args.as_json:
            payload = {
                "ok": not errors,
                "labs_valid": len(records),
                "errors": [f.__dict__ for f in errors],
                "warnings": [f.__dict__ for f in warnings],
            }
            print(json.dumps(payload, indent=2))
        else:
            _report(findings, quiet=args.quiet)
            print(f"labs_catalog: {len(records)} valid, {len(errors)} errors, {len(warnings)} warnings")
        return 1 if errors else 0

    catalog_path = root / "labs" / "labs.json"
    rendered = render_catalog(build_catalog(records))
    _report(findings, quiet=args.quiet)

    if args.command == "rebuild":
        if errors and not args.force:
            print(f"labs_catalog: {len(errors)} errors; labs/labs.json not written (fix them or pass --force)")
            return 1
        catalog_path.write_text(rendered, encoding="utf-8")
        print(f"labs_catalog: wrote labs/labs.json ({len(records)} labs, {len(errors)} errors skipped)")
        return 1 if errors else 0

    current = catalog_path.read_text(encoding="utf-8") if catalog_path.is_file() else None
    if errors:
        print(f"labs_catalog: {len(errors)} errors")
        return 1
    if current != rendered:
        print("labs_catalog: labs/labs.json is stale; run: python3 skills/organize-lab/scripts/labs_catalog.py rebuild")
        return 1
    print(f"labs_catalog: labs/labs.json is current ({len(records)} labs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
