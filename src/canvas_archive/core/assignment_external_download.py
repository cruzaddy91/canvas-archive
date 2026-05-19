"""Download starter files from allowlisted instructor HTTP(S) URLs (for example cs.westminstercollege.edu)."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .course_home_table import (
    _external_download_hosts,
    _external_starters_trust_any_https_host,
)
from .fetch_403_cache import is_forbidden_cached, record_forbidden_403
from .follow_spec_links import USER_AGENT, _host_allowed, _normalize_hosts
from .slug import slug

_MAX_BYTES = 25 * 1024 * 1024
_MAX_FOLLOW_LINKS_PER_HTML = 48


def _safe_disk_name_from_url(url: str) -> str:
    path = (urlparse(url).path or "").rstrip("/") or "download"
    base = Path(path).name or "download"
    base = re.sub(r"[^\w.\-]+", "_", base, flags=re.I).strip("._") or "download"
    stem, dot, ext = base.partition(".")
    if not ext:
        ext = "bin"
    stem_safe = slug(stem) or "file"
    return f"{stem_safe}.{ext.lower()}"


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        key = u.split("#", 1)[0].strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _external_disk_names_by_url(urls: list[str]) -> dict[str, str]:
    """Map each URL to a filename under ``external/``. Use the URL path basename; add a short hash
    suffix only when two URLs in this batch would otherwise share the same name.
    """
    pairs = [(u, _safe_disk_name_from_url(u)) for u in urls]
    buckets: dict[str, list[str]] = {}
    for u, fn in pairs:
        buckets.setdefault(fn, []).append(u)
    out: dict[str, str] = {}
    for fn, ulist in buckets.items():
        if len(ulist) == 1:
            out[ulist[0]] = fn
            continue
        sfx = Path(fn).suffix.lower() or ".bin"
        stem = Path(fn).stem or "file"
        for u in ulist:
            short = hashlib.sha256(u.encode()).hexdigest()[:8]
            out[u] = f"{stem}_{short}{sfx}"
    return out


def _html_follow_extensions(profile: dict) -> frozenset[str]:
    """Extensions to pull from ``<a href>`` inside downloaded external ``.htm`` / ``.html`` starters."""
    raw = profile.get("course_home_external_html_follow_extensions")
    if isinstance(raw, list) and raw:
        out: set[str] = set()
        for x in raw:
            s = str(x).strip().lower()
            if not s:
                continue
            out.add(s if s.startswith(".") else f".{s}")
        return frozenset(out) if out else frozenset({".zip", ".ipynb", ".py"})
    return frozenset({".zip", ".ipynb", ".py"})


def _follow_host_ok(url: str, parent_url: str, profile: dict) -> bool:
    child = urlparse(url)
    parent = urlparse(parent_url)
    ch, ph = child.hostname, parent.hostname
    if not ch:
        return False
    if ph and ch.lower() == ph.lower():
        return True
    if _external_starters_trust_any_https_host(profile) and url.startswith("https://"):
        return True
    hosts = _normalize_hosts(_external_download_hosts(profile))
    return bool(hosts) and _host_allowed(ch, hosts)


def _discover_follow_urls_from_html(
    html_path: Path,
    base_url: str,
    profile: dict,
    ext_allow: frozenset[str],
    already: set[str],
) -> list[str]:
    """Resolve ``<a href>`` targets under ``base_url`` (schedule download URL of the saved page)."""
    try:
        text = html_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    soup = BeautifulSoup(text, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        if len(out) >= _MAX_FOLLOW_LINKS_PER_HTML:
            break
        raw = (a.get("href") or "").strip()
        if not raw or raw.startswith(("#", "javascript:", "mailto:")):
            continue
        abs_u = urljoin(base_url, raw)
        abs_u = abs_u.split("#", 1)[0].strip()
        if not abs_u.startswith(("http://", "https://")):
            continue
        ext = Path(urlparse(abs_u).path).suffix.lower()
        if ext not in ext_allow:
            continue
        if abs_u in already:
            continue
        if not _follow_host_ok(abs_u, base_url, profile):
            continue
        out.append(abs_u)
    return out


def download_external_starter_files(
    *,
    urls: list[str],
    assignment_dir: Path,
    profile: dict,
    shared_external_url_cache: dict[str, Path] | None = None,
) -> tuple[int, str, int, int, int]:
    """
    Download allowlisted HTTP(S) starter URLs into ``assignment_dir/external/``.

    When ``profile['dedupe_external_download_urls']`` is true and ``shared_external_url_cache`` is a
    dict shared across assignments in one extract run, the first successful download for a URL is
    stored and later hits use ``shutil.copy2`` instead of another HTTP GET.

    Returns (download_count, markdown_appendix, bytes_total, error_count, spec_follow_ok_count).
    """
    if not urls:
        return 0, "", 0, 0, 0

    uniq = _dedupe_urls(urls)
    if not uniq:
        return 0, "", 0, 0, 0

    dest_root = assignment_dir / "external"
    dest_root.mkdir(parents=True, exist_ok=True)

    url_to_disk = _external_disk_names_by_url(uniq)

    use_url_cache = bool(profile.get("dedupe_external_download_urls")) and shared_external_url_cache is not None

    lines: list[str] = ["", "## External starter files (instructor host)", ""]
    n_ok = 0
    n_err = 0
    bytes_total = 0
    any_note = False
    expected: set[str] = set()
    html_sources: list[tuple[str, Path]] = []
    seen_urls: set[str] = {u.split("#", 1)[0].strip() for u in uniq}
    n_spec_follow_ok = 0

    def _download_one(url: str, disk_name: str, *, is_follow: bool) -> None:
        nonlocal n_ok, n_err, bytes_total, any_note, n_spec_follow_ok
        out_path = dest_root / disk_name
        expected.add(disk_name)
        url_key = url.split("#", 1)[0].strip()
        if use_url_cache and url_key in shared_external_url_cache:
            try:
                shutil.copy2(shared_external_url_cache[url_key], out_path)
                bytes_total += out_path.stat().st_size
                label = Path(urlparse(url).path).name or url
                rel = f"external/{disk_name}"
                prefix = "_(from spec page)_ " if is_follow else ""
                lines.append(f"- {prefix}[{label}]({rel})")
                n_ok += 1
                if is_follow:
                    n_spec_follow_ok += 1
            except OSError as e:
                if out_path.exists():
                    try:
                        out_path.unlink()
                    except OSError:
                        pass
                expected.discard(disk_name)
                lines.append(f"- _(skipped copy from cache [{url}]({url}): {e})_")
                any_note = True
                n_err += 1
            return
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=120) as resp:
                total = 0
                with open(out_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > _MAX_BYTES:
                            raise ValueError(f"response larger than {_MAX_BYTES} bytes")
                        f.write(chunk)
            bytes_total += out_path.stat().st_size
            label = Path(urlparse(url).path).name or url
            rel = f"external/{disk_name}"
            prefix = "_(from spec page)_ " if is_follow else ""
            lines.append(f"- {prefix}[{label}]({rel})")
            n_ok += 1
            if is_follow:
                n_spec_follow_ok += 1
            if use_url_cache:
                shared_external_url_cache[url_key] = out_path.resolve()
        except HTTPError as e:
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            expected.discard(disk_name)
            if e.code == 403:
                record_forbidden_403(url)
            lines.append(f"- _(skipped [{url}]({url}): {e})_")
            any_note = True
            n_err += 1
        except (URLError, TimeoutError, ValueError, OSError, TypeError) as e:
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            expected.discard(disk_name)
            lines.append(f"- _(skipped [{url}]({url}): {e})_")
            any_note = True
            n_err += 1

    for raw_url in uniq:
        url = raw_url.strip()
        if not url.startswith(("http://", "https://")):
            n_err += 1
            any_note = True
            lines.append(f"- _(skipped non-http URL: {url})_")
            continue
        if is_forbidden_cached(url):
            lines.append(f"- _(403 cached, skipped: {url})_")
            any_note = True
            n_err += 1
            continue
        disk_name = url_to_disk[url]
        out_path = dest_root / disk_name
        before_ok = n_ok
        _download_one(url, disk_name, is_follow=False)
        if n_ok > before_ok and out_path.suffix.lower() in (".htm", ".html"):
            html_sources.append((url, out_path))

    if profile.get("course_home_follow_links_in_external_html"):
        ext_allow = _html_follow_extensions(profile)
        follow_candidates: list[str] = []
        for base_url, html_path in html_sources:
            follow_candidates.extend(
                _discover_follow_urls_from_html(
                    html_path, base_url, profile, ext_allow, seen_urls
                )
            )
        follow_uniq = _dedupe_urls(follow_candidates)
        if follow_uniq:
            lines.append("")
            lines.append("### Linked from external spec pages")
            lines.append("")
        follow_map = _external_disk_names_by_url(follow_uniq)
        for fu in follow_uniq:
            key = fu.split("#", 1)[0].strip()
            if key in seen_urls:
                continue
            seen_urls.add(key)
            disk_name = follow_map[fu]
            stem, sfx = Path(disk_name).stem, Path(disk_name).suffix.lower()
            if disk_name in expected:
                short = hashlib.sha256(fu.encode()).hexdigest()[:8]
                disk_name = f"{stem}_{short}{sfx or '.bin'}"
            _download_one(fu, disk_name, is_follow=True)

    if profile.get("prune_orphan_external_files", True) and dest_root.is_dir() and expected:
        for p in list(dest_root.iterdir()):
            if p.is_file() and p.name not in expected:
                try:
                    p.unlink()
                except OSError:
                    pass

    if n_ok == 0 and not any_note:
        return 0, "", 0, 0, 0

    return n_ok, "\n".join(lines).rstrip() + "\n", bytes_total, n_err, n_spec_follow_ok
