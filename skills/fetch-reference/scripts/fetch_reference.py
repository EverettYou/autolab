#!/usr/bin/env python3
"""fetch-reference: search arXiv, archive papers and repositories under references/<id>/, and
keep references/references.json in sync.

    fetch_reference.py search QUERY [--max-papers N] [--categories LIST] [--text]
    fetch_reference.py paper --id ID (--arxiv ARXIV | --url URL | --pdf PATH | --adopt)
                             [--title T] [--alias A ...] [--note TEXT] [--allow-title-mismatch]
                             [--allow-duplicate] [--force]
    fetch_reference.py repo --id ID --url URL [--name NAME] [--commit SHA] [--depth N]
                            [--kind repository|dataset] [--title T] [--alias A ...] [--note TEXT]
    fetch_reference.py register --id ID [--kind KIND] [--title T] [--url URL] [--arxiv ARXIV]
                                [--alias A ...] [--note TEXT]
    fetch_reference.py status (ID ... | --all)
    fetch_reference.py refetch (ID ... | --all)

Run from anywhere; the repository root is located from this file (override with --root).
Exit codes: 0 ok; 1 download or network failure, or a missing local copy; 2 invalid input
(bad PDF, checksum mismatch, usage error); 3 title mismatch; 4 refused (would overwrite an
archived copy, or the reference is already registered under another name).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arxiv_fetch as af  # noqa: E402
import references_registry as reg  # noqa: E402

EXIT_OK, EXIT_FETCH, EXIT_INVALID, EXIT_TITLE, EXIT_REFUSED = 0, 1, 2, 3, 4


class Refused(RuntimeError):
    pass


class UsageError(RuntimeError):
    pass


def ref_dir(root: Path, ref_id: str) -> Path:
    return root / "references" / ref_id


def check_id(ref_id: str) -> None:
    if not reg.REF_ID_RE.match(ref_id):
        raise Refused(f"reference id must be lowercase kebab-case: {ref_id!r}")


def load_or_new(root: Path, ref_id: str, kind: str, title: str | None) -> tuple[dict, bool]:
    prov = reg.load_provenance(ref_dir(root, ref_id))
    if prov is None:
        return reg.new_provenance(ref_id, kind, title or ref_id), True
    return prov, False


def check_duplicates(root: Path, ref_id: str, arxiv: str | None, aliases: list[str]) -> None:
    wanted = reg.normalize_arxiv(arxiv)
    for entry in reg.build_registry(root)[0]["references"]:
        if entry["id"] == ref_id:
            continue
        if wanted and entry["arxiv_id"] and reg.normalize_arxiv(entry["arxiv_id"]) == wanted:
            raise Refused(f"arXiv {wanted} is already registered as {entry['id']} (use that id, or --allow-duplicate)")
        taken = {entry["id"], *entry["aliases"]}
        for name in (ref_id, *aliases):
            if name in taken:
                raise Refused(f"name {name!r} is already used by reference {entry['id']}")


def finish(root: Path, ref_id: str, prov: dict, *, aliases: list[str], note: str | None) -> None:
    if aliases:
        prov["aliases"] = sorted(set(prov.get("aliases") or []) | set(aliases))
    if note:
        prov["note"] = note
    reg.save_provenance(ref_dir(root, ref_id), prov)
    reg.sync_one(root, ref_id)
    for error in reg.rebuild(root):
        print(f"warning: registry: {error}", file=sys.stderr)


def cmd_search(args: argparse.Namespace) -> int:
    from arxiv_search import format_text, search_arxiv

    cats = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else None
    try:
        results = search_arxiv(args.query, max_papers=args.max_papers, categories=cats, since_days=args.since_days)
    except Exception as exc:
        print(f"error querying arXiv: {exc}", file=sys.stderr)
        return EXIT_FETCH
    if args.text:
        print(format_text(results))
    else:
        for row in results:
            print(json.dumps(row, ensure_ascii=False))
    return EXIT_OK


def cmd_paper(root: Path, args: argparse.Namespace) -> int:
    check_id(args.id)
    if sum(map(bool, (args.arxiv, args.url, args.pdf, args.adopt))) != 1:
        raise UsageError("paper: give exactly one of --arxiv, --url, --pdf, --adopt")
    directory = ref_dir(root, args.id)
    prov, is_new = load_or_new(root, args.id, "paper", args.title)
    if is_new and (args.url or args.pdf or args.adopt) and not args.title:
        raise UsageError("paper: --title is required for a new reference without arXiv metadata")
    source = Path(args.pdf).expanduser().resolve() if args.pdf else None
    if source is not None and not source.is_file():
        raise UsageError(f"paper: no such PDF file: {source}")
    new_arxiv = bool(args.arxiv) and reg.normalize_arxiv(args.arxiv) != reg.normalize_arxiv(prov.get("arxiv_id"))
    if not args.allow_duplicate:
        check_duplicates(root, args.id, args.arxiv if new_arxiv else None, args.alias)

    dest = directory / "paper.pdf"
    recorded = prov.get("pdf_sha256")
    fields: dict = {}
    if args.adopt:
        if not dest.is_file():
            raise Refused(f"--adopt needs an existing references/{args.id}/paper.pdf")
        fields = af.adopt_local_pdf(dest)
        if recorded and fields["pdf_sha256"] != recorded and not args.force:
            raise Refused("paper.pdf differs from the recorded sha256; inspect it, then rerun with --force")
        if not prov.get("metadata_source"):
            fields["metadata_source"] = "local"
    elif dest.exists() and not args.force:
        if not (recorded and af.sha256_file(dest) == recorded):
            raise Refused(
                f"references/{args.id}/paper.pdf exists and is not the recorded copy; "
                "inspect it, then rerun with --force (or --adopt to record it as is)"
            )
        if source is not None and af.sha256_file(source) != recorded:
            raise Refused(f"references/{args.id}/paper.pdf is archived with a different sha256; rerun with --force to replace it")
        print(f"references/{args.id}/paper.pdf is already archived (sha256 {recorded[:12]}); pass --force to fetch again")
    else:
        expected = recorded if recorded and not args.force and not new_arxiv else None
        title = args.title or prov.get("title") or args.id
        if args.arxiv:
            fields = af.fetch_arxiv(
                args.arxiv, dest, allow_title_mismatch=args.allow_title_mismatch, expected_sha256=expected
            )
        elif args.url:
            fields = af.fetch_url(args.url, dest, title=title, expected_sha256=expected)
        else:
            if expected and af.sha256_file(source) != expected:
                raise Refused("the given PDF differs from the recorded sha256; rerun with --force to replace the record")
            fields = af.ingest_local_pdf(source, dest, title=title)

    fetched_title = fields.pop("title", None)
    prov.update(fields)
    if args.title:
        prov["title"] = args.title
    elif fetched_title and (is_new or not prov.get("title") or prov.get("title") == args.id):
        prov["title"] = fetched_title
    if is_new:
        prov["kind"] = "paper"
        prov["status"] = "fetched"
    finish(root, args.id, prov, aliases=args.alias, note=args.note)
    sha = str(prov.get("pdf_sha256") or "")[:12]
    print(
        f"references/{args.id}/paper.pdf {prov.get('fetch_status')} pages={prov.get('pages')} "
        f"sha256={sha} registered in references/references.json"
    )
    return EXIT_OK


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/").removesuffix(".git").lower()


def git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)


def cmd_repo(root: Path, args: argparse.Namespace) -> int:
    check_id(args.id)
    name = args.name or re.sub(r"\.git$", "", args.url.rstrip("/").rsplit("/", 1)[-1])
    if not reg.REPO_NAME_RE.match(name):
        raise UsageError(f"repo: invalid repository name {name!r} (use --name)")
    directory = ref_dir(root, args.id)
    dest = directory / "repos" / name
    prov, is_new = load_or_new(root, args.id, args.kind or "repository", args.title or name)
    if not args.allow_duplicate:
        check_duplicates(root, args.id, None, args.alias)

    if dest.exists():
        origin = reg.git_output(dest, "remote", "get-url", "origin") if (dest / ".git").exists() else None
        if origin is None or normalize_url(origin) != normalize_url(args.url):
            raise Refused(f"references/{args.id}/repos/{name} exists and is not a clone of {args.url}")
        print(f"references/{args.id}/repos/{name} is already a clone of {args.url}; recording it")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["clone"]
        if args.depth and not args.commit:
            cmd += ["--depth", str(args.depth)]
        result = git([*cmd, "--", args.url, str(dest)])
        if result.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            print(f"error: git clone failed: {result.stderr.strip()}", file=sys.stderr)
            return EXIT_FETCH
    if args.commit:
        result = git(["checkout", "--quiet", "--detach", args.commit], cwd=dest)
        if result.returncode != 0:
            git(["fetch", "--quiet", "origin", args.commit], cwd=dest)
            result = git(["checkout", "--quiet", "--detach", args.commit], cwd=dest)
        if result.returncode != 0:
            print(f"error: cannot check out {args.commit}: {result.stderr.strip()}", file=sys.stderr)
            return EXIT_FETCH

    record = reg.repo_record(directory, name, url=args.url)
    repos = [r for r in prov.get("repos") or [] if not (isinstance(r, dict) and r.get("name") == name)]
    prov["repos"] = [*repos, record]
    if is_new:
        prov["status"] = "fetched"
    finish(root, args.id, prov, aliases=args.alias, note=args.note)
    print(f"references/{args.id}/repos/{name} at {str(record.get('commit'))[:12]} registered in references/references.json")
    return EXIT_OK


def cmd_register(root: Path, args: argparse.Namespace) -> int:
    check_id(args.id)
    directory = ref_dir(root, args.id)
    prov, is_new = load_or_new(root, args.id, args.kind or "paper", args.title)
    if is_new and not (args.title and args.kind):
        raise UsageError("register: --kind and --title are required for a new reference")
    if not args.allow_duplicate:
        new_arxiv = args.arxiv and reg.normalize_arxiv(args.arxiv) != reg.normalize_arxiv(prov.get("arxiv_id"))
        check_duplicates(root, args.id, args.arxiv if new_arxiv else None, args.alias)
    directory.mkdir(parents=True, exist_ok=True)
    if args.kind:
        prov["kind"] = args.kind
    if args.title:
        prov["title"] = args.title
    if args.arxiv:
        prov["arxiv_id"] = reg.normalize_arxiv(args.arxiv)
        prov["entry_url"] = prov.get("entry_url") or f"https://arxiv.org/abs/{prov['arxiv_id']}"
    if args.url:
        prov["entry_url"] = args.url
    if is_new:
        prov["fetched_at"] = reg.utc_now()
        prov["status"] = "fetched"
    finish(root, args.id, prov, aliases=args.alias, note=args.note)
    print(f"references/{args.id}/provenance.json registered in references/references.json")
    return EXIT_OK


def selected_ids(root: Path, ids: list[str], use_all: bool) -> list[str]:
    if use_all:
        return [p.name for p in reg.reference_dirs(root)]
    out = []
    for name in ids:
        if ref_dir(root, name).is_dir():
            out.append(name)
            continue
        hits = reg.resolve(root, name)
        if len(hits) != 1:
            raise UsageError(f"no unique reference for {name!r} (matches: {', '.join(hits) or 'none'})")
        out.append(hits[0])
    return out


def cmd_status(root: Path, args: argparse.Namespace) -> int:
    worst = EXIT_OK
    for ref_id in selected_ids(root, args.ids, args.all):
        directory = ref_dir(root, ref_id)
        prov = reg.load_provenance(directory)
        if prov is None:
            print(f"INVALID  {ref_id}: no provenance.json")
            worst = max(worst, EXIT_INVALID)
            continue
        errors, warnings = reg.check_local(directory, prov)
        pdf_name = prov.get("pdf")
        if pdf_name and not prov.get("pdf_sha256"):
            errors.append(f"{ref_id}: no sha256 recorded for {pdf_name} (run: fetch_reference.py paper --id {ref_id} --adopt)")
        if pdf_name and (directory / pdf_name).is_file():
            try:
                af.validate_pdf(directory / pdf_name)
            except af.PdfValidationError as exc:
                errors.append(f"{ref_id}: {pdf_name} is not a valid PDF: {exc}")
        parts = []
        if pdf_name:
            parts.append(f"pdf={prov.get('fetch_status')} pages={prov.get('pages')} sha256={str(prov.get('pdf_sha256'))[:12]}")
        if prov.get("repos"):
            parts.append(f"repos={len(prov['repos'])}")
        if errors:
            worst = max(worst, EXIT_INVALID)
            print(f"INVALID  {ref_id}: " + "; ".join(e.split(': ', 1)[-1] for e in errors))
        elif warnings:
            worst = max(worst, EXIT_FETCH)
            print(f"MISSING  {ref_id}: " + "; ".join(w.split(': ', 1)[-1] for w in warnings))
        else:
            print(f"ok       {ref_id}: {' '.join(parts) or 'no local assets recorded'}")
    return worst


def cmd_refetch(root: Path, args: argparse.Namespace) -> int:
    worst = EXIT_OK
    ids = selected_ids(root, args.ids, args.all)
    for ref_id in ids:
        directory = ref_dir(root, ref_id)
        prov = reg.load_provenance(directory) or {}
        pdf_name, recorded = prov.get("pdf"), prov.get("pdf_sha256")
        if not pdf_name:
            if not args.all:
                print(f"skip     {ref_id}: no PDF recorded")
            continue
        dest = directory / pdf_name
        if dest.is_file():
            if recorded and af.sha256_file(dest) == recorded:
                print(f"ok       {ref_id}: present, sha256 matches")
            else:
                print(f"MISMATCH {ref_id}: local {pdf_name} is not the recorded copy; left untouched")
                worst = max(worst, EXIT_INVALID)
            continue
        url = prov.get("pdf_url") or (af.arxiv_pdf_url(prov["arxiv_id"]) if prov.get("arxiv_id") else None)
        if not url:
            print(f"MISSING  {ref_id}: no pdf_url or arxiv_id recorded; cannot refetch")
            worst = max(worst, EXIT_FETCH)
            continue
        try:
            af.fetch_url(url, dest, title=prov.get("title") or ref_id, expected_sha256=recorded)
            print(f"restored {ref_id}: {pdf_name} from {url}")
        except af.FetchError as exc:
            print(f"FAILED   {ref_id}: {exc}")
            worst = max(worst, EXIT_FETCH)
        except af.PdfValidationError as exc:
            print(f"INVALID  {ref_id}: {exc}")
            worst = max(worst, EXIT_INVALID)
    return worst


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search, fetch, and register references under references/<id>/")
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: located from this file)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="search arXiv (JSONL by default)")
    p.add_argument("query")
    p.add_argument("--max-papers", type=int, default=10)
    p.add_argument("--categories", default="quant-ph,cs.ET", help="comma-separated filter; empty disables")
    p.add_argument("--text", action="store_true", help="human-readable output")
    p.add_argument("--since-days", type=int, default=None,
                   help="only submissions in the last N days, newest first (a freshness check; relevance search is not one)")

    p = sub.add_parser("paper", help="archive a paper PDF as references/<id>/paper.pdf")
    p.add_argument("--id", required=True, help="reference id (lowercase kebab-case)")
    p.add_argument("--arxiv", help="arXiv id or URL")
    p.add_argument("--url", help="direct PDF URL (non-arXiv)")
    p.add_argument("--pdf", help="local PDF file to copy in")
    p.add_argument("--adopt", action="store_true", help="validate and record references/<id>/paper.pdf as it is")
    p.add_argument("--title")
    p.add_argument("--allow-title-mismatch", action="store_true", help="accept a first page that differs from the arXiv title")

    p_repo = sub.add_parser("repo", help="clone a repository into references/<id>/repos/<name>/")
    p_repo.add_argument("--id", required=True)
    p_repo.add_argument("--url", required=True)
    p_repo.add_argument("--name", help="directory name under repos/ (default: from the URL)")
    p_repo.add_argument("--commit", help="commit to check out (detached)")
    p_repo.add_argument("--depth", type=int, help="shallow clone depth (ignored with --commit)")
    p_repo.add_argument("--kind", choices=("repository", "dataset"), help="kind for a new reference")
    p_repo.add_argument("--title")

    p_reg = sub.add_parser("register", help="create or update provenance.json for assets placed by hand")
    p_reg.add_argument("--id", required=True)
    p_reg.add_argument("--kind", choices=reg.KINDS)
    p_reg.add_argument("--title")
    p_reg.add_argument("--url", help="landing page or DOI URL")
    p_reg.add_argument("--arxiv")

    for sp in (p, p_repo, p_reg):
        sp.add_argument("--alias", action="append", default=[], help="alternate name (repeatable)")
        sp.add_argument("--note", help="why this reference was fetched")
        sp.add_argument("--allow-duplicate", action="store_true", help="register even if the arXiv id is already used")
    p.add_argument("--force", action="store_true", help="replace an existing or recorded copy")

    for name, help_text in (("status", "check local copies against provenance.json"), ("refetch", "restore missing PDFs, verifying the recorded sha256")):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("ids", nargs="*")
        sp.add_argument("--all", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = (args.root or reg.default_root()).resolve()
    if args.command == "search":
        return cmd_search(args)
    if not (root / "references").is_dir():
        print(f"error: no references/ directory under {root}", file=sys.stderr)
        return EXIT_INVALID
    if args.command in ("status", "refetch") and not (args.ids or args.all):
        print(f"error: {args.command} needs reference ids or --all", file=sys.stderr)
        return EXIT_INVALID
    handlers = {"paper": cmd_paper, "repo": cmd_repo, "register": cmd_register, "status": cmd_status, "refetch": cmd_refetch}
    try:
        return handlers[args.command](root, args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except af.TitleMismatchError as exc:
        print(f"error: {exc} (verify the PDF by hand, then rerun with --allow-title-mismatch)", file=sys.stderr)
        return EXIT_TITLE
    except af.PdfValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except (af.FetchError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FETCH


if __name__ == "__main__":
    raise SystemExit(main())
