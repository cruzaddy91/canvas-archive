"""Extract Canvas wiki pages as markdown.

The default canvas_only extractor only pulls assignments. Module lecture
content (slides, notes) lives on Canvas Pages — this script grabs those.

Page body HTML is converted to markdown (small, grep-able, exam-friendly).
Slides links inside the body are preserved as markdown links; binaries are
not downloaded.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import urllib.request
from pathlib import Path

import pypdf
from canvasapi.exceptions import CanvasException

from canvas_archive.core.canvas import get_canvas
from canvas_archive.core.markdown import to_md

GSLIDES_RE = re.compile(r"https://docs\.google\.com/presentation/d/([A-Za-z0-9_-]+)")


def fetch_slides_md(slides_id: str) -> str | None:
    """Download Google Slides as PDF and extract per-slide text as markdown."""
    url = f"https://docs.google.com/presentation/d/{slides_id}/export/pdf"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
    except Exception as e:
        print(f"    [slides fetch failed] {e}")
        return None
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
    except Exception as e:
        print(f"    [pdf parse failed] {e}")
        return None
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        parts.append(f"## Slide {i}\n\n{text}" if text else f"## Slide {i}\n\n_(empty)_")
    return "\n\n".join(parts) + "\n"


def page_md(page) -> str:
    body = getattr(page, "body", "") or ""
    md = to_md(body)
    out = [f"# {page.title}", ""]
    url = getattr(page, "html_url", "") or ""
    if url:
        out.append(f"[Open in Canvas]({url})")
        out.append("")
    out.append(md or "_No content._")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("canvas_id", type=int)
    ap.add_argument("target_dir", type=Path, help="output dir; pages/ subdir created inside")
    ap.add_argument("--prefix", default=None,
                    help="comma-separated url prefixes to filter (e.g. '3-,4-')")
    args = ap.parse_args()

    target = args.target_dir.expanduser().resolve()
    out_dir = target / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)

    canvas = get_canvas()
    course = canvas.get_course(args.canvas_id)

    pages = list(course.get_pages())
    if args.prefix:
        prefixes = tuple(p.strip() for p in args.prefix.split(","))
        pages = [p for p in pages if p.url.startswith(prefixes)]

    print(f"writing {len(pages)} page(s) to {out_dir}")
    written = 0
    for page in pages:
        try:
            full = course.get_page(page.url)
        except CanvasException as e:
            print(f"  [skip] {page.url}: {e}")
            continue
        path = out_dir / f"{page.url}.md"
        body = page_md(full)
        path.write_text(body)
        print(f"  wrote {path.name} ({path.stat().st_size / 1024:.1f} KB)")
        written += 1

        for slides_id in set(GSLIDES_RE.findall(getattr(full, "body", "") or "")):
            slides_md = fetch_slides_md(slides_id)
            if slides_md is None:
                continue
            slides_path = out_dir / f"{page.url}.slides.md"
            header = f"# {full.title} — Slides\n\nSource: https://docs.google.com/presentation/d/{slides_id}\n\n"
            slides_path.write_text(header + slides_md)
            print(f"    +slides {slides_path.name} ({slides_path.stat().st_size / 1024:.1f} KB)")
    print(f"\ndone: {written} pages")


if __name__ == "__main__":
    main()
