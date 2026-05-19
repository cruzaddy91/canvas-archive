"""Optional enrichment: fetch instructor-hosted pages linked from Canvas HTML descriptions."""

from __future__ import annotations

import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .fetch_403_cache import is_forbidden_cached, record_forbidden_403
from .markdown import to_md

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
USER_AGENT = "canvas-archive/personal-student-archive (private course archive)"


class FetchSkipped403(Exception):
    """URL is in the 403 cache; caller should not append an error note or retry."""


def _normalize_hosts(host_allowlist: list[str]) -> set[str]:
    out: set[str] = set()
    for h in host_allowlist:
        s = (h or "").strip().lower().removeprefix("*.")
        if s:
            out.add(s)
    return out


def _host_allowed(hostname: str | None, allowed: set[str]) -> bool:
    if not hostname:
        return False
    hl = hostname.lower()
    for a in allowed:
        if hl == a or hl.endswith("." + a):
            return True
    return False


def first_allowlisted_http_url(html: str, host_allowlist: list[str]) -> str | None:
    """Return the first http(s) URL in description HTML whose host is on the allowlist."""
    allowed = _normalize_hosts(host_allowlist)
    if not html or not allowed:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href.startswith(("http://", "https://")):
            continue
        host = urlparse(href).hostname
        if _host_allowed(host, allowed):
            return href.split("#", 1)[0]

    for m in re.finditer(r"https?://[^\s\"'<>)\]]+", html):
        url = m.group(0).rstrip(".,;")
        host = urlparse(url).hostname
        if _host_allowed(host, allowed):
            return url.split("#", 1)[0]

    return None


def _trim_duplicate_leading_heading(ext_md: str, assignment_name: str) -> str:
    lines = ext_md.splitlines()
    if not lines:
        return ext_md
    first = lines[0].strip()
    if not first.startswith("#"):
        return ext_md
    title = first.lstrip("#").strip().lower()
    an = (assignment_name or "").strip().lower()
    if not an:
        return ext_md
    if title == an or title in an or an in title:
        return "\n".join(lines[1:]).lstrip("\n")
    return ext_md


def _canvas_plaintext_len(raw_html: str) -> int:
    if not raw_html:
        return 0
    soup = BeautifulSoup(raw_html, "html.parser")
    return len(soup.get_text("\n", strip=True))


def fetch_page_as_markdown(url: str) -> str:
    if is_forbidden_cached(url):
        raise FetchSkipped403(url)
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as resp:
        chunk = resp.read(MAX_RESPONSE_BYTES + 1)
    if len(chunk) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response larger than {MAX_RESPONSE_BYTES} bytes")
    html = chunk.decode("utf-8", errors="replace")
    return to_md(html).strip()


def append_followed_spec(
    *,
    body: str,
    raw_description_html: str,
    assignment_name: str,
    group_name: str,
    profile: dict,
) -> tuple[str, bool]:
    """If profile requests link following and a matching URL exists, append fetched Markdown."""
    cfg = profile.get("follow_description_links")
    if not isinstance(cfg, dict) or not cfg:
        return body, False

    hosts = cfg.get("host_allowlist") or []
    if not isinstance(hosts, list) or not hosts:
        return body, False

    only = cfg.get("only_assignment_groups")

    if only is None:
        # All assignment groups: only follow when the Canvas HTML body is short (submission shell + link).
        # Set follow_max_canvas_plaintext_chars to false to disable that ceiling.
        max_plain = cfg.get("follow_max_canvas_plaintext_chars")
        if max_plain is not False:
            if max_plain is None:
                limit = 900
            else:
                try:
                    limit = int(max_plain)
                except (TypeError, ValueError):
                    limit = 900
            if _canvas_plaintext_len(raw_description_html) > limit:
                return body, False
        group_ok = True
    elif isinstance(only, list) and len(only) == 0:
        group_ok = False
    elif isinstance(only, list):
        gl = (group_name or "").lower()
        group_ok = any(str(sub).lower() in gl for sub in only)
    else:
        return body, False

    if not group_ok:
        return body, False

    url = first_allowlisted_http_url(raw_description_html, hosts)
    if not url:
        return body, False

    try:
        ext_md = fetch_page_as_markdown(url)
    except FetchSkipped403:
        return body, False
    except HTTPError as e:
        if e.code == 403:
            record_forbidden_403(url)
        note = f"\n\n_(Could not fetch instructor-hosted instructions from [{url}]({url}): {e})_\n"
        return (body + note if body else note.strip()), False
    except (URLError, TimeoutError, ValueError, OSError) as e:
        note = f"\n\n_(Could not fetch instructor-hosted instructions from [{url}]({url}): {e})_\n"
        return (body + note if body else note.strip()), False

    ext_md = _trim_duplicate_leading_heading(ext_md, assignment_name)
    title = cfg.get("merged_section_title") or "Instructor-hosted description"
    sep = f"\n\n---\n\n## {title}\n\n"
    attr = f"*Source: [{url}]({url})*\n\n"
    merged = f"{body.rstrip()}{sep}{attr}{ext_md}\n".strip() + "\n"
    pause = float(cfg.get("pause_seconds_between_requests") or 0.25)
    if pause > 0:
        time.sleep(pause)
    return merged, True


__all__ = [
    "FetchSkipped403",
    "append_followed_spec",
    "fetch_page_as_markdown",
    "first_allowlisted_http_url",
]
