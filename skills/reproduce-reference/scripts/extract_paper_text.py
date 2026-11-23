#!/usr/bin/env python3
"""Extract searchable plain text from paper PDF for grep-based spec mining."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def extract_pymupdf(pdf: Path) -> str:
    import fitz

    doc = fitz.open(pdf)
    try:
        parts = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            parts.append(f"\n\n--- page {i} ---\n\n{text}")
        return "".join(parts)
    finally:
        doc.close()


def extract_pypdf(pdf: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        parts.append(f"\n\n--- page {i} ---\n\n{text}")
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("out_md", type=Path, help="Output paper.md path")
    args = parser.parse_args()

    if not args.pdf.is_file():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    try:
        text = extract_pymupdf(args.pdf)
    except ImportError:
        text = extract_pypdf(args.pdf)

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(text, encoding="utf-8")
    pages = text.count("--- page ")
    print(f"wrote {args.out_md} ({pages} pages, {len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
