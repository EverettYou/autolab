#!/usr/bin/env python3
"""Maintain references/references.json, the index generated from references/<id>/provenance.json.

    python3 skills/fetch-reference/scripts/references_registry.py rebuild
    python3 skills/fetch-reference/scripts/references_registry.py check
    python3 skills/fetch-reference/scripts/references_registry.py validate [--local] [--json]
    python3 skills/fetch-reference/scripts/references_registry.py sync ID [ID ...] | --all
    python3 skills/fetch-reference/scripts/references_registry.py set ID [--status S] [--kind K] [--title T] [--alias A ...]
    python3 skills/fetch-reference/scripts/references_registry.py dispose ID ATTEMPT --decision D --note TEXT
    python3 skills/fetch-reference/scripts/references_registry.py resolve NAME

provenance.json is the per-reference source of truth (tracked). references.json is rebuilt from
the provenance files and never edited by hand. `sync` refreshes the fields a provenance file
mirrors from disk (reproduce/, attempts/, repos/) and then rebuilds the index. `validate --local`
also checks the gitignored local copies (paper.pdf checksum, repo commits).

Exit codes: 0 ok (warnings allowed), 1 errors or stale index, 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

KINDS = ("paper", "repository", "dataset")
STATUSES = ("pending", "fetched", "attempted", "reproduced", "partial", "failed")
# The only names allowed directly under references/<id>/. Everything else is optional.
LAYOUT_NAMES = frozenset({"provenance.json", "paper.pdf", "README.md", "repos", "attempts", "reproduce"})
DECISIONS = ("promoted", "superseded", "dead-end", "dropped", "keep")
ENTRY_KEYS = (
    "id", "kind", "title", "arxiv_id", "aliases", "has_pdf", "repos",
    "reproduction", "attempts", "status", "provenance",
)
PROVENANCE_REQUIRED = (
    "id", "kind", "title", "arxiv_id", "aliases", "pdf", "pdf_sha256",
    "repos", "reproduction", "attempts", "status",
)
REF_ID_RE = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")
REPO_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def default_root() -> Path:
    return Path(__file__).resolve().parents[3]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_arxiv(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    raw = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", raw)
    raw = re.sub(r"^arxiv:", "", raw, flags=re.IGNORECASE).removesuffix(".pdf")
    return re.sub(r"v\d+$", "", raw)


def new_provenance(ref_id: str, kind: str, title: str) -> dict:
    return {
        "id": ref_id,
        "kind": kind,
        "title": title,
        "arxiv_id": None,
        "authors": [],
        "abstract": "",
        "categories": [],
        "published": None,
        "upstream_updated": None,
        "entry_url": None,
        "pdf_url": None,
        "pdf": None,
        "pdf_sha256": None,
        "pages": None,
        "fetched_at": None,
        "fetch_status": None,
        "metadata_source": None,
        "title_match_score": None,
        "aliases": [],
        "repos": [],
        "reproduction": None,
        "attempts": [],
        "status": "fetched",
        "legacy_paths": [],
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def references_dir(root: Path) -> Path:
    return root / "references"


def registry_path(root: Path) -> Path:
    return references_dir(root) / "references.json"


def reference_dirs(root: Path) -> list[Path]:
    base = references_dir(root)
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def load_provenance(ref_dir: Path) -> dict | None:
    path = ref_dir / "provenance.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def save_provenance(ref_dir: Path, data: dict) -> None:
    write_json(ref_dir / "provenance.json", data)


def entry_from_provenance(prov: dict) -> dict:
    ref_id = prov["id"]
    return {
        "id": ref_id,
        "kind": prov.get("kind"),
        "title": prov.get("title"),
        "arxiv_id": prov.get("arxiv_id"),
        "aliases": list(prov.get("aliases") or []),
        "has_pdf": prov.get("pdf") is not None,
        "repos": [r.get("name") for r in prov.get("repos") or [] if isinstance(r, dict)],
        "reproduction": prov.get("reproduction"),
        "attempts": list(prov.get("attempts") or []),
        "status": prov.get("status"),
        "provenance": f"references/{ref_id}/provenance.json",
    }


def build_registry(root: Path) -> tuple[dict, list[str]]:
    """Registry built from every provenance.json, plus errors for unreadable or missing files."""
    entries, errors = [], []
    for ref_dir in reference_dirs(root):
        try:
            prov = load_provenance(ref_dir)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{ref_dir.name}: provenance.json unreadable: {exc}")
            continue
        if prov is None:
            errors.append(f"{ref_dir.name}: no provenance.json")
            continue
        if prov.get("id") != ref_dir.name:
            errors.append(f"{ref_dir.name}: provenance id {prov.get('id')!r} does not match the directory")
            continue
        entries.append(entry_from_provenance(prov))
    entries.sort(key=lambda e: e["id"])
    return {"references": entries}, errors


def render_registry(registry: dict) -> str:
    return json.dumps(registry, indent=2, ensure_ascii=False) + "\n"


def rebuild(root: Path) -> list[str]:
    registry, errors = build_registry(root)
    write_json(registry_path(root), registry)
    return errors


def load_registry(root: Path) -> dict:
    path = registry_path(root)
    if not path.is_file():
        return {"references": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"references": []}


def git_output(repo: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def tree_sha256(directory: Path) -> tuple[str, int]:
    """Content hash of a directory tree (relative paths and bytes, sorted), and its file count."""
    digest = hashlib.sha256()
    count = 0
    for path in sorted(p for p in directory.rglob("*") if p.is_file() and ".git" not in p.parts):
        rel = path.relative_to(directory).as_posix()
        digest.update(rel.encode() + b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        digest.update(b"\0")
        count += 1
    return digest.hexdigest(), count


def repo_record(ref_dir: Path, name: str, url: str | None = None) -> dict:
    """Describe repos/<name>/ as found on disk: git origin and HEAD, or a tree checksum otherwise."""
    path = ref_dir / "repos" / name
    record = {"name": name, "path": f"repos/{name}", "url": url, "commit": None, "retrieved_at": utc_now()}
    if (path / ".git").exists():
        record["url"] = url or git_output(path, "remote", "get-url", "origin")
        record["commit"] = git_output(path, "rev-parse", "HEAD")
    elif path.is_dir():
        record["tree_sha256"], record["files"] = tree_sha256(path)
    return record


def disk_attempts(ref_dir: Path) -> list[str]:
    base = ref_dir / "attempts"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def disk_repos(ref_dir: Path) -> list[str]:
    base = ref_dir / "repos"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))


def has_reproduction(ref_dir: Path) -> bool:
    repro = ref_dir / "reproduce"
    return repro.is_dir() and any(repro.iterdir())


def sync_one(root: Path, ref_id: str) -> list[str]:
    """Refresh mirrored disk facts in one provenance.json. Returns human-readable changes."""
    ref_dir = references_dir(root) / ref_id
    prov = load_provenance(ref_dir)
    if prov is None:
        raise FileNotFoundError(f"references/{ref_id}/provenance.json does not exist")
    changes = []
    reproduction = "reproduce/" if has_reproduction(ref_dir) else None
    if prov.get("reproduction") != reproduction:
        changes.append(f"reproduction -> {reproduction}")
        prov["reproduction"] = reproduction
    attempts = sorted(set(prov.get("attempts") or []) | set(disk_attempts(ref_dir)))
    if attempts != list(prov.get("attempts") or []):
        changes.append(f"attempts -> {attempts}")
        prov["attempts"] = attempts
    recorded = {r.get("name") for r in prov.get("repos") or [] if isinstance(r, dict)}
    for name in disk_repos(ref_dir):
        if name not in recorded:
            prov.setdefault("repos", []).append(repo_record(ref_dir, name))
            changes.append(f"recorded repos/{name}")
    if attempts and prov.get("status") in ("pending", "fetched"):
        prov["status"] = "attempted"
        changes.append("status -> attempted")
    if changes:
        save_provenance(ref_dir, prov)
    return changes


def set_fields(
    root: Path,
    ref_id: str,
    *,
    status: str | None = None,
    kind: str | None = None,
    title: str | None = None,
    aliases: list[str] | None = None,
) -> None:
    ref_dir = references_dir(root) / ref_id
    prov = load_provenance(ref_dir)
    if prov is None:
        raise FileNotFoundError(f"references/{ref_id}/provenance.json does not exist")
    if status is not None:
        prov["status"] = status
    if kind is not None:
        prov["kind"] = kind
    if title is not None:
        prov["title"] = title
    if aliases:
        prov["aliases"] = sorted(set(prov.get("aliases") or []) | set(aliases))
    save_provenance(ref_dir, prov)


def dispose(root: Path, ref_id: str, attempt: str, decision: str, note: str) -> None:
    """Record the fate of an attempt workspace in the tracked provenance file."""
    ref_dir = references_dir(root) / ref_id
    prov = load_provenance(ref_dir)
    if prov is None:
        raise FileNotFoundError(f"references/{ref_id}/provenance.json does not exist")
    known = set(prov.get("attempts") or []) | set(disk_attempts(ref_dir))
    if attempt not in known:
        raise ValueError(f"references/{ref_id} has no attempt named {attempt!r}")
    prov.setdefault("dispositions", {})[attempt] = {
        "decision": decision,
        "note": note,
        "date": date.today().isoformat(),
    }
    save_provenance(ref_dir, prov)


def resolve(root: Path, name: str) -> list[str]:
    """Reference ids matching an id, alias, attempt slug, repo name, or arXiv id."""
    wanted_arxiv = normalize_arxiv(name)
    hits = []
    for entry in build_registry(root)[0]["references"]:
        if (
            name == entry["id"]
            or name in entry["aliases"]
            or name in entry["attempts"]
            or name in entry["repos"]
            or (entry["arxiv_id"] and normalize_arxiv(entry["arxiv_id"]) == wanted_arxiv)
        ):
            hits.append(entry["id"])
    return hits


def validate(root: Path, *, local: bool = False) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for every reference and for the generated index."""
    errors: list[str] = []
    warnings: list[str] = []
    names: dict[str, str] = {}
    arxiv_ids: dict[str, str] = {}

    for ref_dir in reference_dirs(root):
        rid = ref_dir.name
        try:
            prov = load_provenance(ref_dir)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{rid}: provenance.json unreadable: {exc}")
            continue
        if prov is None:
            errors.append(f"{rid}: no provenance.json")
            continue
        stray = sorted(
            child.name for child in ref_dir.iterdir()
            if not child.name.startswith(".") and child.name not in LAYOUT_NAMES
        )
        if stray:
            allowed = ", ".join(sorted(LAYOUT_NAMES))
            verb = "is" if len(stray) == 1 else "are"
            errors.append(f"{rid}: {', '.join(stray)} {verb} outside the reference layout ({allowed})")
        for sub in ("repos", "attempts"):
            folder = ref_dir / sub
            if not folder.exists():
                continue
            if not folder.is_dir():
                errors.append(f"{rid}: {sub} must be a directory of subdirectories")
                continue
            loose = sorted(
                child.name for child in folder.iterdir()
                if not child.name.startswith(".") and not child.is_dir()
            )
            if loose:
                errors.append(
                    f"{rid}: {sub}/ holds {', '.join(loose)}; each entry is a subdirectory"
                )
        missing = [k for k in PROVENANCE_REQUIRED if k not in prov]
        if missing:
            errors.append(f"{rid}: provenance.json missing keys: {', '.join(missing)}")
        if prov.get("id") != rid:
            errors.append(f"{rid}: provenance id {prov.get('id')!r} does not match the directory")
        if not REF_ID_RE.match(rid):
            errors.append(f"{rid}: id must be lowercase kebab-case")
        kind = prov.get("kind")
        kind_list = kind if isinstance(kind, list) else [kind]
        if not kind_list or any(item not in KINDS for item in kind_list):
            errors.append(f"{rid}: kind {kind!r} must be one or more of {', '.join(KINDS)}")
        if prov.get("status") not in STATUSES:
            errors.append(f"{rid}: status {prov.get('status')!r} is not one of {', '.join(STATUSES)}")
        if not isinstance(prov.get("title"), str) or not prov.get("title", "").strip():
            errors.append(f"{rid}: title is empty")
        for key in ("aliases", "attempts"):
            value = prov.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.append(f"{rid}: {key} must be a list of strings")
        repos = prov.get("repos", [])
        if not isinstance(repos, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in repos):
            errors.append(f"{rid}: repos must be a list of objects with a name")
            repos = []
        if prov.get("pdf") is not None and not SHA256_RE.match(str(prov.get("pdf_sha256") or "")):
            errors.append(f"{rid}: pdf is recorded without a valid pdf_sha256")

        on_disk = has_reproduction(ref_dir)
        if on_disk != (prov.get("reproduction") == "reproduce/"):
            errors.append(f"{rid}: reproduction field disagrees with reproduce/ on disk (run sync)")
        if prov.get("status") in ("reproduced", "partial") and not on_disk:
            errors.append(f"{rid}: status {prov.get('status')} but no reproduce/ record")
        if on_disk and prov.get("status") in ("pending", "fetched", "attempted"):
            warnings.append(f"{rid}: has a reproduce/ record but status is {prov.get('status')}")
        unrecorded = sorted(set(disk_attempts(ref_dir)) - set(prov.get("attempts") or []))
        if unrecorded:
            errors.append(f"{rid}: attempts not recorded in provenance.json: {', '.join(unrecorded)} (run sync)")
        recorded_repos = {r["name"] for r in repos}
        for name in sorted(set(disk_repos(ref_dir)) - recorded_repos):
            errors.append(f"{rid}: repos/{name} is not recorded in provenance.json (run sync)")
        for name in sorted(recorded_repos):
            if not REPO_NAME_RE.match(name):
                errors.append(f"{rid}: invalid repo name {name!r}")

        for alias in [rid, *(prov.get("aliases") or [])]:
            if not isinstance(alias, str):
                continue
            owner = names.get(alias)
            if owner and owner != rid:
                errors.append(f"{rid}: name {alias!r} is already used by {owner}")
            names.setdefault(alias, rid)
        arxiv = normalize_arxiv(prov.get("arxiv_id"))
        if arxiv:
            if arxiv in arxiv_ids:
                warnings.append(f"{rid}: arXiv {arxiv} is also registered as {arxiv_ids[arxiv]}")
            arxiv_ids.setdefault(arxiv, rid)

        if local:
            errors_l, warnings_l = check_local(ref_dir, prov)
            errors += errors_l
            warnings += warnings_l

    registry, build_errors = build_registry(root)
    path = registry_path(root)
    if not path.is_file():
        errors.append("references/references.json is missing (run rebuild)")
    elif path.read_text(encoding="utf-8") != render_registry(registry):
        errors.append("references/references.json is stale (run rebuild)")
    return errors, warnings


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_local(ref_dir: Path, prov: dict) -> tuple[list[str], list[str]]:
    """Compare gitignored local copies against the recorded checksums and commits."""
    rid = ref_dir.name
    errors: list[str] = []
    warnings: list[str] = []
    pdf_name = prov.get("pdf")
    if pdf_name:
        pdf = ref_dir / pdf_name
        if not pdf.is_file():
            warnings.append(f"{rid}: {pdf_name} missing locally (restore with fetch_reference.py refetch {rid})")
        elif prov.get("pdf_sha256") and sha256_file(pdf) != prov["pdf_sha256"]:
            errors.append(f"{rid}: {pdf_name} sha256 differs from provenance.json")
    for repo in prov.get("repos") or []:
        if not isinstance(repo, dict) or not repo.get("name"):
            continue
        path = ref_dir / (repo.get("path") or f"repos/{repo['name']}")
        if not path.is_dir():
            warnings.append(f"{rid}: repos/{repo['name']} missing locally")
            continue
        if repo.get("commit") and (path / ".git").exists():
            head = git_output(path, "rev-parse", "HEAD")
            if head != repo["commit"]:
                warnings.append(f"{rid}: repos/{repo['name']} HEAD {str(head)[:12]} differs from recorded {repo['commit'][:12]}")
        elif repo.get("tree_sha256") and tree_sha256(path)[0] != repo["tree_sha256"]:
            errors.append(f"{rid}: repos/{repo['name']} content differs from recorded tree_sha256")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: located from this file)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rebuild", help="rewrite references.json from the provenance files")
    sub.add_parser("check", help="exit 1 when references.json is stale")
    p_val = sub.add_parser("validate", help="validate provenance files and the index")
    p_val.add_argument("--local", action="store_true", help="also check local PDFs and repo clones")
    p_val.add_argument("--json", action="store_true", dest="as_json")
    p_sync = sub.add_parser("sync", help="refresh mirrored disk facts, then rebuild")
    p_sync.add_argument("ids", nargs="*")
    p_sync.add_argument("--all", action="store_true")
    p_set = sub.add_parser("set", help="set curated fields, then rebuild")
    p_set.add_argument("id")
    p_set.add_argument("--status", choices=STATUSES)
    p_set.add_argument("--kind", choices=KINDS)
    p_set.add_argument("--title")
    p_set.add_argument("--alias", action="append", default=[])
    p_disp = sub.add_parser("dispose", help="record the fate of an attempt workspace")
    p_disp.add_argument("id")
    p_disp.add_argument("attempt")
    p_disp.add_argument("--decision", required=True, choices=DECISIONS)
    p_disp.add_argument("--note", required=True)
    p_res = sub.add_parser("resolve", help="print reference ids matching a name, alias, attempt, or arXiv id")
    p_res.add_argument("name")
    args = parser.parse_args(argv)

    root = (args.root or default_root()).resolve()
    if not references_dir(root).is_dir():
        print(f"references_registry: no references/ directory under {root}", file=sys.stderr)
        return 2

    try:
        if args.command == "rebuild":
            errors = rebuild(root)
            for error in errors:
                print(f"ERROR {error}")
            count = len(load_registry(root)["references"])
            print(f"references_registry: wrote references/references.json ({count} references)")
            return 1 if errors else 0
        if args.command == "check":
            registry, errors = build_registry(root)
            path = registry_path(root)
            current = path.read_text(encoding="utf-8") if path.is_file() else None
            for error in errors:
                print(f"ERROR {error}")
            if current != render_registry(registry):
                print("references_registry: references.json is stale (run rebuild)")
                return 1
            print(f"references_registry: references.json is current ({len(registry['references'])} references)")
            return 1 if errors else 0
        if args.command == "validate":
            errors, warnings = validate(root, local=args.local)
            if args.as_json:
                print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, indent=2))
            else:
                for error in errors:
                    print(f"ERROR {error}")
                for warning in warnings:
                    print(f"WARN  {warning}")
                print(f"references_registry: {len(errors)} errors, {len(warnings)} warnings")
            return 1 if errors else 0
        if args.command == "sync":
            ids = [p.name for p in reference_dirs(root)] if args.all else args.ids
            if not ids:
                parser.error("sync needs reference ids or --all")
            for ref_id in ids:
                for change in sync_one(root, ref_id):
                    print(f"{ref_id}: {change}")
            errors = rebuild(root)
            for error in errors:
                print(f"ERROR {error}")
            return 1 if errors else 0
        if args.command == "set":
            set_fields(root, args.id, status=args.status, kind=args.kind, title=args.title, aliases=args.alias)
            errors = rebuild(root)
            for error in errors:
                print(f"ERROR {error}")
            return 1 if errors else 0
        if args.command == "dispose":
            dispose(root, args.id, args.attempt, args.decision, args.note)
            print(f"references/{args.id}: recorded {args.decision} for attempt {args.attempt}")
            return 0
        if args.command == "resolve":
            hits = resolve(root, args.name)
            for hit in hits:
                print(hit)
            return 0 if hits else 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"references_registry: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
