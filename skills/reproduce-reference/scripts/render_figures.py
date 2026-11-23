#!/usr/bin/env python3
"""Render PDF pages to PNG for build-from-paper figure inspection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_pages(spec: str | None, max_pages: int) -> list[int]:
    if not spec:
        return list(range(1, max_pages + 1))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
            pages.update(range(lo, hi + 1))
        else:
            pages.add(int(part))
    return sorted(p for p in pages if p >= 1)


def render_pymupdf(pdf: Path, out_dir: Path, pages: list[int], dpi: int) -> list[Path]:
    import fitz  # PyMuPDF

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf)
    written: list[Path] = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    try:
        for page_num in pages:
            if page_num > len(doc):
                print(f"skip page {page_num}: PDF has {len(doc)} pages", file=sys.stderr)
                continue
            page = doc[page_num - 1]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            dest = out_dir / f"page-{page_num:03d}.png"
            pix.save(dest)
            written.append(dest)
    finally:
        doc.close()
    return written


def render_pypdf_fallback(pdf: Path, out_dir: Path, pages: list[int]) -> list[Path]:
    """Fallback: extract embedded images only (no full page render)."""
    from pypdf import PdfReader

    out_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(pdf))
    written: list[Path] = []
    for page_num in pages:
        if page_num > len(reader.pages):
            continue
        page = reader.pages[page_num - 1]
        for idx, img in enumerate(page.images):
            dest = out_dir / f"page-{page_num:03d}-img-{idx:02d}.{img.name.split('.')[-1]}"
            dest.write_bytes(img.data)
            written.append(dest)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--pages", help="e.g. 3,4,7-9")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--max-pages", type=int, default=40)
    args = parser.parse_args()

    if not args.pdf.is_file():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    pages = parse_pages(args.pages, args.max_pages)
    try:
        written = render_pymupdf(args.pdf, args.out_dir, pages, args.dpi)
        mode = "pymupdf"
    except ImportError:
        written = render_pypdf_fallback(args.pdf, args.out_dir, pages)
        mode = "pypdf-images-only"
        if not written:
            print(
                "Install pymupdf for full page render: pip install pymupdf",
                file=sys.stderr,
            )

    print(f"mode={mode} wrote {len(written)} file(s) to {args.out_dir}")
    for path in written:
        print(path)
    return 0 if written else 2


if __name__ == "__main__":
    raise SystemExit(main())
