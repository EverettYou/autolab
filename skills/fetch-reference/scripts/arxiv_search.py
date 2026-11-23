#!/usr/bin/env python3
"""
arXiv search — adapted from langchain-samples/deepagent-coder arxiv-search skill.
https://github.com/langchain-samples/deepagent-coder/tree/main/src/agent/skills/arxiv-search

Uses the export.arxiv.org HTTP API directly (rate-limited, one retry on 429).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from arxiv_http import RATE_LIMIT_SEC, is_rate_limited, search_api


def build_query(query: str, categories: list[str] | None, since_days: int | None = None,
                now: datetime | None = None) -> str:
    """The API query: ``query``, AND-ed with a category clause and, with ``since_days``, a submission window."""
    cat_clause = " OR ".join(f"cat:{c.strip()}" for c in categories or () if c.strip())
    if ":" not in query and '"' not in query and " " in query.strip():
        # The API ORs bare words. Relevance ranking hides that; a date-sorted window does not (2026-10-12: "quantum oracle sketching"
        # returned the newest quant-ph papers on any topic). AND them unless the caller wrote a fielded query.
        query = " AND ".join(f"all:{w}" for w in query.split())
    full = f"({query}) AND ({cat_clause})" if cat_clause else query
    if since_days is not None:
        hi = now or datetime.now(timezone.utc)
        lo = hi - timedelta(days=int(since_days))
        full = f"({full}) AND submittedDate:[{lo:%Y%m%d%H%M} TO {hi:%Y%m%d%H%M}]"
    return full


def search_arxiv(
    query: str,
    *,
    max_papers: int = 10,
    categories: list[str] | None = None,
    since_days: int | None = None,
) -> list[dict[str, Any]]:
    """Relevance-ranked search, or, with ``since_days``, the newest submissions inside that window.

    A relevance search is not a freshness check: on 2026-08-22 it returned 3 of 23 hits inside a three-week
    window where the date-sorted query returned 19 of 19.
    """
    full_query = build_query(query, categories, since_days)
    sort = "relevance" if since_days is None else "submittedDate"
    try:
        return search_api(full_query, max_results=max_papers, sort=sort)
    except Exception as exc:
        if is_rate_limited(exc):
            print(
                f"note: arXiv search rate-limited, retrying once after {RATE_LIMIT_SEC:.0f}s…",
                file=sys.stderr,
            )
            time.sleep(RATE_LIMIT_SEC)
            try:
                return search_api(full_query, max_results=max_papers, sort=sort)
            except Exception as exc2:
                raise RuntimeError(
                    f"arXiv search still rate-limited after retry — wait {RATE_LIMIT_SEC:.0f}s "
                    f"and retry, or scout with known arXiv IDs via ingest"
                ) from exc2
        raise


def format_text(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No papers found on arXiv."
    blocks = []
    for r in results:
        authors = ", ".join(r["authors"][:5])
        if len(r["authors"]) > 5:
            authors += ", ..."
        cats = ", ".join(r["categories"])
        blocks.append(
            "\n".join(
                [
                    f"arXiv ID: {r['arxiv_id']}",
                    f"Title: {r['title']}",
                    f"Authors: {authors}",
                    f"Categories: {cats}",
                    f"Published: {r['published']}",
                    f"PDF: {r['pdf_url']}",
                    f"Summary: {r['abstract']}",
                ]
            )
        )
    return "\n\n".join(blocks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search arXiv for research papers")
    parser.add_argument("query", type=str, help="Search query string")
    parser.add_argument(
        "--max-papers",
        type=int,
        default=10,
        help="Maximum number of papers to retrieve (default: 10)",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default="quant-ph,cs.ET",
        help="Comma-separated arXiv categories to filter (default: quant-ph,cs.ET). "
        "Pass empty string to disable.",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only papers submitted in the last N days, newest first (use this for freshness scouting)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one JSON object per line (JSONL)",
    )
    args = parser.parse_args()

    cats = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else None
    try:
        results = search_arxiv(args.query, max_papers=args.max_papers, categories=cats,
                               since_days=args.since_days)
    except Exception as exc:
        print(f"Error querying arXiv: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        for row in results:
            print(json.dumps(row, ensure_ascii=False))
    else:
        print(format_text(results))


if __name__ == "__main__":
    main()
