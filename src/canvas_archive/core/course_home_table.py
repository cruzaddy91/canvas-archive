"""Map starter files from the course home wiki schedule table (Assignments column)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag
from canvasapi.exceptions import CanvasException

from .assignment_canvas_files import _dedupe_pairs, canvas_file_refs_from_html
from .fetch_403_cache import is_forbidden_cached, record_forbidden_403
from .follow_spec_links import USER_AGENT, _host_allowed, _normalize_hosts
from .slug import slug

# YAML-derived course extract settings (keys are strings, values vary by key).
Profile = dict[str, object]

_ASSIGN_RE = re.compile(r"/courses/\d+/assignments/(\d+)", re.I)
_FILE_HREF_RE = re.compile(r"/courses/(\d+)/files/(\d+)", re.I)


def _href_attr(tag: Tag) -> str:
    """Normalize ``Tag.get("href")`` to ``str`` (BeautifulSoup types allow list-like values)."""
    raw = tag.get("href")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list) and raw:
        return str(raw[0])
    return str(raw) if raw is not None else ""


def _external_download_hosts(profile: Profile) -> list[str]:
    h = profile.get("course_home_external_download_hosts")
    if isinstance(h, list) and h:
        return [str(x).strip() for x in h if str(x).strip()]
    follow = profile.get("follow_description_links")
    if isinstance(follow, dict):
        inner = follow.get("host_allowlist")
        if isinstance(inner, list) and inner:
            return [str(x).strip() for x in inner if str(x).strip()]
    return []


def _external_extensions(profile: Profile) -> tuple[str, ...]:
    ex = profile.get("course_home_external_file_extensions")
    if isinstance(ex, list) and ex:
        out: list[str] = []
        for x in ex:
            s = str(x).strip().lower()
            if not s:
                continue
            out.append(s if s.startswith(".") else f".{s}")
        return tuple(out) if out else (".ipynb", ".py", ".zip")
    return (".ipynb", ".py", ".zip")


def _normalize_http_href(href: str) -> str | None:
    h = (href or "").strip().replace("&amp;", "&")
    if not h:
        return None
    if h.startswith("//"):
        h = "https:" + h
    if h.startswith(("http://", "https://")):
        return h.split("#", 1)[0]
    return None


_SUPPLEMENT_HTML_MAX_BYTES = 3 * 1024 * 1024


def _developer_mode(profile: Profile) -> bool:
    """When true, relax schedule-table external host checks (see README). Turn off when the archive is done."""
    return bool(profile.get("developer_mode"))


def _external_starters_trust_any_https_host(profile: Profile) -> bool:
    """True if schedule-column ``.ipynb`` / ``.py`` / ``.zip`` links may use any http(s) host (extension filter still applies)."""
    if _developer_mode(profile):
        return True
    return bool(profile.get("course_home_external_starters_allow_any_https_host"))


def _supplement_html_url_allowed(url: str, profile: Profile) -> bool:
    full = _normalize_http_href(url)
    if not full or not full.startswith(("http://", "https://")):
        return False
    hosts = _normalize_hosts(_external_download_hosts(profile))
    host = urlparse(full).hostname
    if hosts and _host_allowed(host, hosts):
        return True
    if _developer_mode(profile):
        return True
    return False


def _fetch_supplement_html(url: str) -> str | None:
    u = _normalize_http_href(url)
    if not u or not u.startswith(("http://", "https://")):
        return None
    if is_forbidden_cached(u):
        return None
    try:
        req = Request(u, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=120) as resp:
            total = 0
            parts: list[bytes] = []
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > _SUPPLEMENT_HTML_MAX_BYTES:
                    return None
                parts.append(chunk)
            raw = b"".join(parts)
            charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")
    except HTTPError as e:
        if e.code == 403:
            record_forbidden_403(u)
        return None
    except (URLError, TimeoutError, ValueError, OSError, TypeError):
        return None


def _supplement_html_base_for_relative_resolution(profile: Profile) -> str | None:
    """First ``course_home_supplement_html_urls`` entry, used as base for relative ``href`` values."""
    raw = profile.get("course_home_supplement_html_urls")
    if not isinstance(raw, list) or not raw:
        return None
    return _normalize_http_href(str(raw[0]).strip())


def _absolute_http_href(href: str, profile: Profile) -> str | None:
    """Resolve ``href`` to an absolute http(s) URL (direct, or via supplement page base)."""
    raw = (href or "").strip().replace("&amp;", "&")
    if not raw:
        return None
    direct = _normalize_http_href(raw)
    if direct:
        return direct
    base = _supplement_html_base_for_relative_resolution(profile)
    if not base or raw.startswith("#"):
        return None
    joined = urljoin(base, raw)
    return _normalize_http_href(joined)


def _external_starter_match_resolved(full: str, profile: Profile) -> bool:
    if not full.startswith(("http://", "https://")):
        return False
    if "/courses/" in full and "/files/" in full:
        return False
    path = (urlparse(full).path or "").lower()
    if not any(path.endswith(ext) for ext in _external_extensions(profile)):
        return False
    if _external_starters_trust_any_https_host(profile):
        return True
    hosts = _normalize_hosts(_external_download_hosts(profile))
    if not hosts:
        return False
    host = urlparse(full).hostname
    return _host_allowed(host, hosts)


def _resolved_external_starter_url(href: str, profile: Profile) -> str | None:
    full = _absolute_http_href(href, profile)
    if not full or not _external_starter_match_resolved(full, profile):
        return None
    return full


def _list_external_starter_hrefs_in_snippet(html: str, profile: Profile) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        u = _resolved_external_starter_url(_href_attr(a), profile)
        if u:
            out.append(u)
    return out


def _cell_starter_score(cell_html: str, profile: Profile) -> int:
    return len(canvas_file_refs_from_html(cell_html)) + len(_list_external_starter_hrefs_in_snippet(cell_html, profile))


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _match_assignment_id_for_file_label(label: str, slug_to_id: dict[str, int]) -> int | None:
    ids = _all_assignment_ids_for_file_label(label, slug_to_id)
    return ids[0] if ids else None


def _all_assignment_ids_for_file_label(hint: str, slug_to_id: dict[str, int]) -> list[int]:
    """All Canvas assignment ids whose slug matches ``hint`` (exact, or substring with score >= 4)."""
    stem = Path(hint.strip()).stem if hint else ""
    if not stem:
        return []
    al = _alnum(stem)
    if len(al) < 4:
        return []
    exact = slug(stem)
    if exact in slug_to_id:
        return [slug_to_id[exact]]
    matches: list[tuple[int, int]] = []
    for asn_slug, aid in slug_to_id.items():
        asn = _alnum(asn_slug.replace("-", ""))
        if not asn:
            continue
        if al == asn:
            matches.append((10_000, aid))
            continue
        if al in asn or asn in al:
            score = min(len(al), len(asn))
            if score >= 4:
                matches.append((score, aid))
    if not matches:
        return []
    best = max(m[0] for m in matches)
    return sorted({aid for sc, aid in matches if sc == best})


_PATH_HINT_SKIP = frozenset(
    {
        "assignments",
        "project",
        "courses",
        "course",
        "www",
        "static",
        "public",
        "dist",
        "download",
        "downloads",
        "agent",
    }
)


def _activity_row_priority_filename_stems(profile: Profile | None) -> frozenset[str]:
    """Filename stems that should use the schedule **Activities** cell before the file name (same row)."""
    if not profile:
        return frozenset()
    raw = profile.get("course_home_activity_row_priority_filename_stems")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(x).strip().lower() for x in raw if str(x).strip())


def _starter_match_hints(
    label: str,
    resolved_url: str,
    activity_row_text: str = "",
    *,
    profile: Profile | None = None,
) -> list[str]:
    """Ordered strings to map a schedule external starter link to Canvas assignment ids (strongest first)."""
    prio = _activity_row_priority_filename_stems(profile)
    art = (activity_row_text or "").strip()
    lab = (label or "").strip()
    path = Path(urlparse(resolved_url).path)
    path_stem = path.stem if (path.name and path.name != "/") else ""
    label_stem = Path(lab).stem if lab else ""
    weak = bool(
        prio
        and art
        and len(art) >= 3
        and (
            (label_stem and label_stem.lower() in prio)
            or (path_stem and path_stem.lower() in prio)
        )
    )

    raw_hints: list[str] = []
    if weak:
        raw_hints.append(art)
    # URL file stem before link text so names such as ``pacman_project_step2`` win over the week Activities cell.
    if path_stem and len(_alnum(path_stem)) >= 4:
        if not weak or path_stem.lower() not in prio:
            raw_hints.append(path_stem)
    if lab:
        if not weak or label_stem.lower() not in prio:
            raw_hints.append(label_stem)
            if lab != label_stem:
                raw_hints.append(lab)
    elif path_stem and len(_alnum(path_stem)) < 4:
        raw_hints.append(path_stem)
    parent = path.parent.name
    if parent and parent.lower() not in _PATH_HINT_SKIP:
        raw_hints.append(parent)
        for piece in parent.replace("-", "_").split("_"):
            p2 = piece.strip()
            if len(p2) >= 3 and p2.lower() not in _PATH_HINT_SKIP:
                raw_hints.append(p2)
    if not weak and art and len(art) >= 3:
        raw_hints.append(art)

    out: list[str] = []
    seen: set[str] = set()
    for h in raw_hints:
        h = h.strip()
        if len(h) < 3 or h.lower() in seen:
            continue
        seen.add(h.lower())
        out.append(h)
    return out


def _match_assignment_ids_for_starter_link(
    label: str,
    resolved_url: str,
    slug_map: dict[str, int],
    *,
    activity_row_text: str = "",
    profile: Profile | None = None,
) -> list[int]:
    """Stop at the first hint that matches any assignment; optional filename-stem fallback when activity-led hints miss."""
    prio = _activity_row_priority_filename_stems(profile)
    lab = (label or "").strip()
    label_stem = Path(lab).stem if lab else ""
    path_stem = Path(urlparse(resolved_url).path).stem
    weak = bool(
        prio
        and (activity_row_text or "").strip()
        and (
            (label_stem and label_stem.lower() in prio)
            or (path_stem and path_stem.lower() in prio)
        )
    )

    def _walk(hint_list: list[str]) -> list[int] | None:
        for hint in hint_list:
            ids = _all_assignment_ids_for_file_label(hint, slug_map)
            if ids:
                return ids
        return None

    primary = _starter_match_hints(
        label, resolved_url, activity_row_text, profile=profile
    )
    got = _walk(primary)
    if got is not None:
        return got
    if weak:
        fallback = _starter_match_hints(
            label, resolved_url, activity_row_text, profile=cast(Profile, {})
        )
        got2 = _walk(fallback)
        if got2 is not None:
            return got2
    return []


def _fetch_home_html(course: Any, profile: Profile) -> str | None:
    chunks: list[str] = []
    page_slug = profile.get("course_home_file_table_page_slug")
    try:
        if page_slug:
            page = course.get_page(str(page_slug))
        else:
            page = course.show_front_page()
        body = getattr(page, "body", None) or ""
        if str(body).strip():
            chunks.append(str(body))
    except CanvasException:
        pass

    if profile.get("course_home_merge_syllabus_body", True):
        sb = getattr(course, "syllabus_body", None) or ""
        if str(sb).strip():
            chunks.append(str(sb))

    raw_supp = profile.get("course_home_supplement_html_urls")
    if isinstance(raw_supp, list):
        for item in raw_supp:
            url = str(item).strip()
            if not url:
                continue
            if not _supplement_html_url_allowed(url, profile):
                print(f"  course_home_supplement: skipped (host not allowlisted, set developer_mode or hosts): {url}")
                continue
            html = _fetch_supplement_html(url)
            if html and str(html).strip():
                chunks.append(str(html))
                print(f"  course_home_supplement: merged {len(html)} chars from {url}")
            else:
                print(f"  course_home_supplement: fetch failed, empty, or over cap: {url}")

    if not chunks:
        return None
    return "\n".join(chunks)


def _activities_column_index(header_row: Tag) -> int | None:
    """Column index for **Activities** (same-week context for assignment starter links)."""
    cells = header_row.find_all(["th", "td"])
    for i, cell in enumerate(cells):
        t = cell.get_text(" ", strip=True).lower()
        if "assignment" in t and "activity" not in t:
            continue
        if "activities" in t or (t.startswith("activity") and "assign" not in t):
            return i
    return None


def _assignments_column_index(header_row: Tag) -> int | None:
    cells = header_row.find_all(["th", "td"])
    for i, cell in enumerate(cells):
        text = cell.get_text(" ", strip=True).lower()
        if "activities" in text and "assignment" not in text:
            continue
        if "activity" in text and "assignment" not in text:
            continue
        if "assignment" in text:
            return i
    return None


def _assignments_column_index_by_starter_density(table: Tag, profile: Profile) -> int | None:
    rows = table.find_all("tr")
    if not rows:
        return None
    max_cols = 0
    for r in rows:
        max_cols = max(max_cols, len(r.find_all(["td", "th"])))
    if max_cols == 0:
        return None
    counts = [0] * max_cols
    for r in rows:
        cells = r.find_all(["td", "th"])
        for i, c in enumerate(cells):
            if i >= max_cols:
                break
            counts[i] += _cell_starter_score(str(c), profile)
    if max(counts) == 0:
        return None
    return max(range(len(counts)), key=lambda j: counts[j])


@dataclass
class HomeTableRefs:
    canvas_by_assignment: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
    external_urls_by_assignment: dict[int, list[str]] = field(default_factory=dict)


def _dedupe_url_map(m: dict[int, list[str]]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for aid, urls in m.items():
        seen: set[str] = set()
        lst: list[str] = []
        for u in urls:
            k = u.split("#", 1)[0]
            if k not in seen:
                seen.add(k)
                lst.append(u)
        out[aid] = lst
    return out


def _parse_table(table: Tag, assignment_slug_to_id: dict[str, int] | None, profile: Profile) -> HomeTableRefs:
    result = HomeTableRefs()
    out_c = result.canvas_by_assignment
    out_e = result.external_urls_by_assignment
    rows = table.find_all("tr")
    if not rows:
        return result
    col_idx: int | None = None
    data_start = 0
    header_row_for_activities: Tag | None = None
    for i, row in enumerate(rows):
        col_idx = _assignments_column_index(row)
        if col_idx is not None:
            data_start = i + 1
            header_row_for_activities = row
            break
    if col_idx is None:
        col_idx = _assignments_column_index_by_starter_density(table, profile)
        if col_idx is None:
            return result
        data_start = 0
        if rows[0].find_all("th") and not rows[0].find_all("td"):
            data_start = 1
        header_row_for_activities = rows[0]

    act_col_idx = (
        _activities_column_index(header_row_for_activities)
        if header_row_for_activities is not None
        else None
    )

    slug_map = assignment_slug_to_id or {}

    for row in rows[data_start:]:
        cells = row.find_all(["td", "th"])
        activity_text = ""
        if act_col_idx is not None and act_col_idx < len(cells):
            activity_text = cells[act_col_idx].get_text(" ", strip=True)
        if col_idx >= len(cells):
            continue
        cell = cells[col_idx]
        cell_html = str(cell)
        if _cell_starter_score(cell_html, profile) == 0:
            continue

        assigned_hrefs: set[str] = set()
        assigned_external: set[str] = set()
        current_aid: int | None = None
        for node in cell.descendants:
            if not isinstance(node, Tag):
                continue
            if node.name != "a" or not node.get("href"):
                continue
            href = _href_attr(node).replace("&amp;", "&")
            if not href:
                continue
            am = _ASSIGN_RE.search(href)
            if am:
                current_aid = int(am.group(1))
                continue
            m = _FILE_HREF_RE.search(href)
            if m:
                pair = (int(m.group(1)), int(m.group(2)))
                if current_aid is not None:
                    out_c.setdefault(current_aid, []).append(pair)
                    assigned_hrefs.add(href.split("#", 1)[0])
                continue
            full = _resolved_external_starter_url(href, profile)
            if full:
                aids: list[int] = []
                if current_aid is not None:
                    aids = [current_aid]
                elif slug_map:
                    lbl = (node.get_text() or "").strip()
                    aids = _match_assignment_ids_for_starter_link(
                        lbl,
                        full,
                        slug_map,
                        activity_row_text=activity_text,
                        profile=profile,
                    )
                if aids:
                    ukey = full.split("#", 1)[0]
                    for aid in aids:
                        out_e.setdefault(aid, []).append(full)
                    assigned_external.add(ukey)
                continue

        if slug_map:
            for a in cell.find_all("a", href=True):
                href = _href_attr(a).replace("&amp;", "&")
                key = href.split("#", 1)[0]
                label = (a.get_text() or "").strip()
                m = _FILE_HREF_RE.search(href)
                if m:
                    if key in assigned_hrefs:
                        continue
                    pair = (int(m.group(1)), int(m.group(2)))
                    aid_m = _match_assignment_id_for_file_label(label, slug_map)
                    if aid_m is not None:
                        out_c.setdefault(aid_m, []).append(pair)
                    continue
                full = _resolved_external_starter_url(href, profile)
                if full:
                    if full.split("#", 1)[0] in assigned_external:
                        continue
                    for aid_m in _match_assignment_ids_for_starter_link(
                        label,
                        full,
                        slug_map,
                        activity_row_text=activity_text,
                        profile=profile,
                    ):
                        out_e.setdefault(aid_m, []).append(full)
                    assigned_external.add(full.split("#", 1)[0])

    for aid in list(out_c.keys()):
        out_c[aid] = _dedupe_pairs(out_c[aid])
    result.external_urls_by_assignment = _dedupe_url_map(out_e)
    return result


def parse_course_home_tables(
    course: Any,
    profile: Profile,
    *,
    assignment_slug_to_id: dict[str, int] | None = None,
) -> HomeTableRefs:
    html = _fetch_home_html(course, profile)
    if not html:
        return HomeTableRefs()

    soup = BeautifulSoup(html, "html.parser")
    merged = HomeTableRefs()
    for table in soup.find_all("table"):
        part = _parse_table(table, assignment_slug_to_id, profile)
        for aid, pairs in part.canvas_by_assignment.items():
            merged.canvas_by_assignment.setdefault(aid, []).extend(pairs)
        for aid, urls in part.external_urls_by_assignment.items():
            merged.external_urls_by_assignment.setdefault(aid, []).extend(urls)
    for aid in list(merged.canvas_by_assignment.keys()):
        merged.canvas_by_assignment[aid] = _dedupe_pairs(merged.canvas_by_assignment[aid])
    merged.external_urls_by_assignment = _dedupe_url_map(merged.external_urls_by_assignment)
    return merged


def external_starter_downloads_allowed(profile: Profile) -> bool:
    """True when the profile allowlists hosts or explicitly opts in to any https starter URLs."""
    if _external_starters_trust_any_https_host(profile):
        return True
    return bool(_external_download_hosts(profile))


def file_refs_by_assignment_from_course_home(
    course: Any,
    profile: Profile,
    *,
    assignment_slug_to_id: dict[str, int] | None = None,
) -> dict[int, list[tuple[int, int]]]:
    """Backward-compatible: only Canvas ``/files/`` id pairs from the home schedule table."""
    return parse_course_home_tables(course, profile, assignment_slug_to_id=assignment_slug_to_id).canvas_by_assignment
