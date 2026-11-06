#!/usr/bin/env python3
"""Convert source PDFs you own in resources/ to text in resources/text/ for distillation.
Uses pypdf. Skips already-converted files unless --force.
"""
import argparse
import re
import sys
from pathlib import Path

import pypdf


def slugify(name: str) -> str:
    # Drop parentheticals (e.g. " (3rd edition)")
    name = re.sub(r"\s*\([^)]*\)", "", name)
    name = re.sub(r"[\s_]+", "-", name.strip())
    name = re.sub(r"[^\w\-.]", "", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:80]


def convert(pdf_path: Path, out_dir: Path, force: bool = False) -> Path | None:
    out_name = slugify(pdf_path.stem) + ".txt"
    out_path = out_dir / out_name
    if out_path.exists() and not force:
        print(f"  skip (exists): {out_name}")
        return out_path
    print(f"  reading: {pdf_path.name}")
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        pages = len(reader.pages)
        print(f"    {pages} pages")
        parts = []
        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
            except Exception as e:
                text = f"[page {i+1} extract error: {e}]"
            parts.append(f"\n\n[PAGE {i+1}]\n\n{text.strip()}")
        out_path.write_text("".join(parts), encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"    -> {out_name} ({size_kb:.1f} KB)")
        return out_path
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("patterns", nargs="*", help="optional filename substrings to limit conversion")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    resources = root / "resources"
    out_dir = resources / "text"
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(resources.glob("*.pdf"))
    if args.patterns:
        pdfs = [p for p in pdfs if any(pat.lower() in p.name.lower() for pat in args.patterns)]
    print(f"Found {len(pdfs)} PDF(s) to convert")
    for p in pdfs:
        convert(p, out_dir, force=args.force)
    print("\nDone.")


if __name__ == "__main__":
    main()
