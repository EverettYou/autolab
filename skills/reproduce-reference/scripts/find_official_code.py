#!/usr/bin/env python3
"""Find author code links in paper text and arXiv abstract page."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore


REPO_URL = re.compile(
    r"https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
)
CODE_PHRASES = [
    r"code\s+(?:is\s+)?(?:available|released|open[\s-]?sourced)\s+at\s+(https?://\S+)",
    r"(?:our|the)\s+code\s+(?:can be found|is hosted)\s+at\s+(https?://\S+)",
    r"implementation\s+(?:is\s+)?(?:available|released)\s+at\s+(https?://\S+)",
    r"source\s+code[:\s]+(https?://\S+)",
]


def scan_text(text: str) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()

    def add(url: str, source: str, context: str = "") -> None:
        key = url.rstrip("/").lower()
        if key in seen:
            return
        seen.add(key)
        found.append({"url": url.rstrip("/"), "source": source, "context": context.strip()})

    for match in REPO_URL.finditer(text):
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 120)
        add(match.group(0), "paper_text", text[start:end].replace("\n", " "))

    for pattern in CODE_PHRASES:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            url = match.group(1).rstrip(".,;:)")
            add(url, "paper_text", match.group(0))

    return found


def scan_arxiv_page(arxiv_id: str) -> list[dict]:
    if requests is None:
        return []
    base_id = re.sub(r"v\d+$", "", arxiv_id)
    url = f"https://arxiv.org/abs/{base_id}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        print(f"arxiv page fetch failed: {exc}", file=sys.stderr)
        return []

    found: list[dict] = []
    seen: set[str] = set()
    for match in re.findall(
        r'href="(https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"',
        resp.text,
    ):
        key = match.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "url": match.rstrip("/"),
                "source": "arxiv_page",
                "context": "Link on arxiv abstract page",
            }
        )
    return found


def load_arxiv_id(reference_dir: Path | None, explicit: str | None) -> str | None:
    if explicit:
        return re.sub(r"v\d+$", "", explicit.strip())
    if reference_dir and (reference_dir / "provenance.json").is_file():
        try:
            meta = json.loads((reference_dir / "provenance.json").read_text(encoding="utf-8"))
            aid = meta.get("arxiv_id")
            if aid:
                return re.sub(r"v\d+$", "", str(aid))
        except (OSError, ValueError):
            pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper_md", type=Path)
    parser.add_argument("out_json", type=Path)
    parser.add_argument("--arxiv-id", default=None)
    parser.add_argument(
        "--reference-dir", type=Path, default=None, help="references/<id> directory (reads arxiv_id from provenance.json)"
    )
    args = parser.parse_args()

    if not args.paper_md.is_file():
        print(f"paper md not found: {args.paper_md}", file=sys.stderr)
        return 1

    text = args.paper_md.read_text(encoding="utf-8")
    links = scan_text(text)

    arxiv_id = load_arxiv_id(args.reference_dir, args.arxiv_id)
    if arxiv_id:
        for item in scan_arxiv_page(arxiv_id):
            if item["url"].rstrip("/").lower() not in {x["url"].rstrip("/").lower() for x in links}:
                links.append(item)

    payload = {
        "arxiv_id": arxiv_id,
        "links": links,
        "count": len(links),
        "pivot_run_the_repo": len(links) > 0,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.out_json} links={len(links)} pivot={payload['pivot_run_the_repo']}")
    for link in links:
        print(f"  {link['url']} ({link['source']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
