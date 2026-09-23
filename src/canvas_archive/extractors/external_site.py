from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pypdf import PdfReader

from ..core.markdown import to_md
from .base import ExtractResult
from .canvas_only import PLACEHOLDER, CanvasOnlyExtractor

_WGET_USER_AGENT = "canvas-archive/personal-student-archive"
_DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _render_via_chrome(url: str, chrome_path: str | None = None) -> str | None:
    """Fetch a URL's post-JS DOM via headless Chrome. None on any failure.

    Exists because wget mirrors only the pre-render HTML stub for instructor
    sites that build the page with JavaScript at load time (see CMPT 328 in
    docs/UAT-wave-202-306-328.md: mirror reported 0 files, course root never
    found). This replaces the one-off scripts/render_chrome_pages.sh, which
    did the same fetch with a hardcoded "Homework N.M" filename pattern for a
    single course. Reusing to_md() here instead of that script's pandoc
    dependency keeps this to Chrome alone, already required for canvas-archive
    development, and keeps the HTML-to-Markdown behavior identical to every
    other content path in this codebase rather than a second, separately
    tuned conversion.
    """
    chrome = chrome_path or os.environ.get("CHROME") or _DEFAULT_CHROME
    if not Path(chrome).exists():
        return None
    try:
        proc = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--virtual-time-budget=6000",
                "--dump-dom",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout


def _get_base_url_http_status(base_url: str) -> tuple[int | None, str]:
    """Single GET for diagnostics when the mirror is empty (same UA as wget)."""
    req = urllib.request.Request(
        base_url,
        headers={"User-Agent": _WGET_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return int(getattr(resp, "status", 200) or 200), ""
    except urllib.error.HTTPError as e:
        return int(e.code), (e.reason or "").strip()
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        return None, str(reason)
    except Exception as e:
        return None, str(e)


def _mirror(base_url: str, out_dir: Path) -> tuple[int, int]:
    """Run wget mirror; return (file_count, total_bytes)."""
    domain = urlparse(base_url).netloc
    if not domain:
        raise SystemExit(f"could not parse domain from {base_url!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "wget",
        "--recursive", "--no-parent",
        "--convert-links", "--page-requisites",
        "--html-extension", "--adjust-extension",
        f"--domains={domain}",
        f"--user-agent={_WGET_USER_AGENT}",
        "--wait=0.5", "--random-wait", "--no-verbose",
        "--directory-prefix", str(out_dir),
        base_url,
    ]
    print(f"  mirroring {base_url} -> {out_dir}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"  (wget exited {e.returncode}; may still have downloaded usable content)")
    files = [p for p in out_dir.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    print(f"  mirrored {len(files)} files, {total / 1024**2:.2f} MB")
    return (len(files), total)


def _find_course_root(external: Path, base_url: str) -> Path | None:
    """Reconstruct the local path mirroring base_url's directory."""
    parsed = urlparse(base_url)
    candidate = external / parsed.netloc / parsed.path.lstrip("/").rstrip("/")
    if candidate.exists():
        return candidate
    # Fallback: walk for any dir matching the URL's last segment
    last = parsed.path.rstrip("/").split("/")[-1]
    for d in external.rglob("*"):
        if d.is_dir() and d.name == last:
            return d
    return None


def _derive_url(base_url: str, course_root: Path, target: Path) -> str:
    rel = target.relative_to(course_root).as_posix()
    return base_url.rstrip("/") + "/" + rel


def _pdf_to_text(pdf_path: Path) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"### Page {i}\n\n{text}")
        return "\n\n".join(pages)
    except Exception as e:
        return f"_(PDF text extraction failed: {e})_"


def _candidates_from_pattern(name: str, pattern: dict) -> list[str]:
    regex = pattern.get("regex", "")
    if not regex:
        return []
    m = re.match(regex, name.lower())
    if not m:
        return []
    n = m.group(1) if m.groups() else ""
    return [c.format(n=n) for c in pattern.get("candidates", [])]


def _starters_from_pattern(name: str, pattern: dict) -> list[str]:
    regex = pattern.get("regex", "")
    if not regex:
        return []
    m = re.match(regex, name.lower())
    if not m:
        return []
    n = m.group(1) if m.groups() else ""
    return [s.format(n=n) for s in pattern.get("starters", [])]


def _update_md(md_path: Path, external_md: str, source_url: str) -> None:
    existing = md_path.read_text()
    attribution = f"\n*Source: [{source_url}]({source_url})*\n\n"
    if PLACEHOLDER in existing:
        new_content = existing.replace(PLACEHOLDER, attribution + external_md)
    else:
        new_content = existing + f"\n\n## External content\n{attribution}{external_md}\n"
    md_path.write_text(new_content)


class ExternalSiteExtractor:
    """Canvas-only first, then mirror prof's external site, match assignments to URLs/PDFs,
    embed/copy content, copy lab starter code, extract handouts. Mirror is deleted at the end."""

    def extract(self, course, profile: dict[str, Any], out_dir: Path) -> ExtractResult:
        result = CanvasOnlyExtractor().extract(course, profile, out_dir)

        site = profile.get("external_site") or {}
        base_url = site.get("base_url")
        if not base_url:
            print("  [skip] external_site.base_url missing in profile")
            return result

        mirror_root = out_dir / "external_content"
        n_files, _n_bytes = _mirror(base_url, mirror_root)

        course_root = _find_course_root(mirror_root, base_url)
        patterns = site.get("assignment_patterns", [])

        if course_root is None:
            print("  [warn] could not locate course root in mirror")
            if n_files == 0:
                code, detail = _get_base_url_http_status(base_url)
                if code is not None:
                    extra = f" ({detail})" if detail else ""
                    print(
                        f"  [diag] GET {base_url} -> HTTP {code}{extra} "
                        "(empty mirror often means the seed URL is blocked or wrong)"
                    )
                else:
                    print(f"  [diag] GET {base_url} failed: {detail}")

            if not site.get("js_render_fallback"):
                print(
                    "  [skip] js_render_fallback not set on this profile; aborting enrich. "
                    "If the empty mirror above is because the instructor site renders "
                    "content with JavaScript, set external_site.js_render_fallback: true."
                )
                shutil.rmtree(mirror_root, ignore_errors=True)
                return result

            print("  [fallback] js_render_fallback set; rendering candidate URLs via headless Chrome")
            result.assignments_enriched += self._match_and_embed_via_chrome(base_url, out_dir, patterns)
            shutil.rmtree(mirror_root, ignore_errors=True)
            return result

        print(f"  course root: {course_root}")

        result.assignments_enriched += self._match_and_embed(course_root, base_url, out_dir, patterns)
        result.starters_copied = self._copy_starters(course_root, out_dir, patterns)

        handouts_dir = site.get("handouts_dir")
        if handouts_dir:
            h_md, h_pdf = self._archive_handouts(course_root / handouts_dir, out_dir / "handouts")
            result.handouts_html = h_md
            result.handouts_pdf = h_pdf

        shutil.rmtree(mirror_root, ignore_errors=True)
        print(f"  mirror deleted: {mirror_root}")
        return result

    def _match_and_embed_via_chrome(self, base_url: str, out_dir: Path, patterns: list[dict]) -> int:
        """Same name-to-content matching as _match_and_embed, but fetches each
        candidate live via headless Chrome instead of reading it from a wget
        mirror, for instructor sites wget cannot see content on at all."""
        n = 0
        for md in sorted((out_dir / "assignments").rglob("*.md")):
            name = re.sub(r"\s+\(\d+\)$", "", md.stem)

            candidate_url = None
            for pat in patterns:
                for rel in _candidates_from_pattern(name, pat):
                    if rel.lower().endswith(".pdf"):
                        continue  # Chrome dumps rendered DOM, not binary PDFs.
                    candidate_url = base_url.rstrip("/") + "/" + rel.lstrip("/")
                    dom = _render_via_chrome(candidate_url)
                    if dom:
                        break
                    candidate_url = None
                if candidate_url:
                    break

            if not candidate_url:
                continue

            external_md = to_md(dom)
            if not external_md:
                continue

            _update_md(md, external_md, candidate_url)
            print(f"    + {md.relative_to(out_dir)} <- {candidate_url}  (Chrome-rendered)")
            n += 1
        print(f"  enriched {n} assignments via Chrome render fallback")
        return n

    def _match_and_embed(self, course_root: Path, base_url: str, out_dir: Path, patterns: list[dict]) -> int:
        n = 0
        for md in sorted((out_dir / "assignments").rglob("*.md")):
            name = re.sub(r"\s+\(\d+\)$", "", md.stem)

            found = None
            for pat in patterns:
                for rel in _candidates_from_pattern(name, pat):
                    p = course_root / rel
                    if p.exists():
                        found = p
                        break
                if found:
                    break

            if not found:
                continue

            url = _derive_url(base_url, course_root, found)

            if found.suffix.lower() == ".pdf":
                pdf_dest = md.parent / f"{md.stem}.pdf"
                shutil.copy2(found, pdf_dest)
                external_md = f"_See companion PDF: [{pdf_dest.name}]({pdf_dest.name})_"
                label = f"PDF -> {pdf_dest.name}"
            else:
                html = found.read_text(errors="ignore")
                external_md = to_md(html)
                label = f"HTML ({len(external_md)} chars)"

            if not external_md:
                continue

            _update_md(md, external_md, url)
            print(f"    + {md.relative_to(out_dir)} <- {found.relative_to(course_root)}  ({label})")
            n += 1
        print(f"  enriched {n} assignments from external site")
        return n

    def _copy_starters(self, course_root: Path, out_dir: Path, patterns: list[dict]) -> int:
        n = 0
        for md in sorted((out_dir / "assignments").rglob("*.md")):
            name = re.sub(r"\s+\(\d+\)$", "", md.stem)
            for pat in patterns:
                for rel in _starters_from_pattern(name, pat):
                    src = course_root / rel
                    if src.exists():
                        dest = md.parent / f"{md.stem}{Path(rel).suffix if not rel.endswith('.tar.gz') else '.tar.gz'}"
                        shutil.copy2(src, dest)
                        print(f"    + starter {dest.relative_to(out_dir)}")
                        n += 1
                        break
        print(f"  copied {n} starter files")
        return n

    def _archive_handouts(self, src_dir: Path, dest_dir: Path) -> tuple[int, int]:
        if not src_dir.exists():
            return (0, 0)
        n_html = n_pdf = 0
        for path in sorted(src_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(src_dir)

            if path.suffix.lower() in (".html", ".htm"):
                html = path.read_text(errors="ignore")
                md = to_md(html)
                if not md:
                    continue
                dest = dest_dir / rel.with_suffix(".md")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(f"# {rel.stem}\n\n{md}\n")
                n_html += 1

            elif path.suffix.lower() == ".pdf":
                dest_pdf = dest_dir / rel
                dest_pdf.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest_pdf)
                n_pdf += 1
        print(f"  handouts extracted: {n_html} HTML->md, {n_pdf} PDFs (no .md companion)")
        return (n_html, n_pdf)
