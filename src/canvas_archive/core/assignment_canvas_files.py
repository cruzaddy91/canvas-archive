"""Download Canvas-hosted files linked from assignment HTML (starter .ipynb, .py, etc.)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from typing import Any

from canvasapi.exceptions import CanvasException, ResourceDoesNotExist

from .canvas import get_canvas
from .slug import slug


# Match course file URLs in rich content (absolute or scheme-relative).
_FILE_URL_RE = re.compile(
    r"(?:https?:)?//[^/\"\s>]+/courses/(\d+)/files/(\d+)(?:/download)?(?:[?#\"'\s>]|$)",
    re.I,
)
# data-api-endpoint="https://.../files/12345"
_API_EP_RE = re.compile(
    r"data-api-endpoint=\"https?:[^\"]+/courses/(\d+)/files/(\d+)(?:/download)?\"",
    re.I,
)


def _dedupe_pairs(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    out: list[tuple[int, int]] = []
    for c, f in pairs:
        key = (c, f)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def canvas_file_refs_from_html(html: str) -> list[tuple[int, int]]:
    """Return (course_id, file_id) pairs referenced in assignment description HTML."""
    if not html:
        return []
    pairs: list[tuple[int, int]] = []
    for rx in (_FILE_URL_RE, _API_EP_RE):
        for m in rx.finditer(html):
            pairs.append((int(m.group(1)), int(m.group(2))))
    return _dedupe_pairs(pairs)


def module_file_refs_before_assignment(
    course: Any,
    assignment_id: int,
    *,
    lookback_items: int = 15,
    max_files: int = 12,
) -> list[tuple[int, int]]:
    """
    Find Canvas File module items placed immediately before an Assignment item in the same module.

    Some courses keep assignment descriptions empty but attach starter .ipynb / .py as module Files
    above the assignment row.
    """
    cid = int(course.id)
    aid = int(assignment_id)
    out: list[tuple[int, int]] = []
    try:
        modules = list(course.get_modules())
    except CanvasException:
        return []

    for mod in modules:
        try:
            items = list(mod.get_module_items())
        except CanvasException:
            continue
        for i, item in enumerate(items):
            if getattr(item, "type", None) != "Assignment":
                continue
            if int(getattr(item, "content_id", 0) or 0) != aid:
                continue
            j = i - 1
            scanned = 0
            files_here = 0
            while j >= 0 and scanned < lookback_items and files_here < max_files:
                it = items[j]
                typ = getattr(it, "type", None)
                scanned += 1
                j -= 1
                if typ == "File":
                    fid = getattr(it, "content_id", None)
                    if fid is not None:
                        out.append((cid, int(fid)))
                        files_here += 1
                    continue
                if typ == "SubHeader":
                    continue
                break

    return _dedupe_pairs(out)


def _safe_disk_name(display_name: str, file_id: int) -> str:
    name = (display_name or "").strip() or f"file_{file_id}"
    name = unquote(name)
    p = Path(name)
    stem = slug(p.stem)
    ext = p.suffix.lower() if p.suffix else ""
    base = f"{stem}{ext}" if stem else f"file{ext}"
    return f"{file_id}_{base}"


def download_assignment_linked_canvas_files(
    *,
    course: Any | None,
    assignment_id: int | None,
    assignment_dir: Path,
    raw_description_html: str,
    profile: dict,
    home_table_refs: dict[int, list[tuple[int, int]]] | None = None,
) -> tuple[int, str, int, int]:
    """
    If profile['download_linked_canvas_files'] is truthy, download each Canvas file
    linked from the description into ``assignment_dir/canvas/``.

    When profile['module_files_before_assignment'] is truthy, also download File module items
    that appear above this assignment in a module (see module_file_refs_before_assignment).

    When ``home_table_refs`` is provided (from the course home wiki table Assignments column),
    merge those (course_id, file_id) pairs for this ``assignment_id``.

    Returns (download_count, markdown_appendix, bytes_on_disk, fetch_error_count).
    """
    if not profile.get("download_linked_canvas_files"):
        return 0, "", 0, 0

    refs = canvas_file_refs_from_html(raw_description_html)
    if profile.get("module_files_before_assignment") and course is not None and assignment_id is not None:
        lb = profile.get("module_file_lookback_items")
        mx = profile.get("module_files_max_per_assignment")
        try:
            lb_i = int(lb) if lb is not None else 15
        except (TypeError, ValueError):
            lb_i = 15
        try:
            mx_i = int(mx) if mx is not None else 12
        except (TypeError, ValueError):
            mx_i = 12
        refs = _dedupe_pairs(
            refs
            + module_file_refs_before_assignment(
                course,
                assignment_id,
                lookback_items=max(1, lb_i),
                max_files=max(1, mx_i),
            )
        )

    if home_table_refs and assignment_id is not None:
        refs = _dedupe_pairs(refs + home_table_refs.get(int(assignment_id), []))

    if not refs:
        return 0, "", 0, 0

    dest_root = assignment_dir / "canvas"
    dest_root.mkdir(parents=True, exist_ok=True)

    canvas = get_canvas()
    lines: list[str] = ["", "## Canvas file attachments", ""]
    n_ok = 0
    any_note = False
    bytes_total = 0
    n_err = 0
    expected_disk: set[str] = set()

    for ref_course_id, file_id in refs:
        try:
            c = canvas.get_course(ref_course_id)
            fobj = c.get_file(file_id)
            display = getattr(fobj, "display_name", None) or getattr(fobj, "filename", None) or str(file_id)
            disk_name = _safe_disk_name(str(display), file_id)
            expected_disk.add(disk_name)
            out_path = dest_root / disk_name
            if not out_path.exists():
                fobj.download(str(out_path))
            if out_path.exists():
                bytes_total += out_path.stat().st_size
            rel = f"canvas/{disk_name}"
            lines.append(f"- [{display}]({rel})")
            n_ok += 1
        except (CanvasException, ResourceDoesNotExist, OSError, TypeError, ValueError) as e:
            lines.append(f"- _(skipped file id {file_id} from course {ref_course_id}: {e})_")
            any_note = True
            n_err += 1

    if profile.get("prune_orphan_canvas_files", True) and dest_root.is_dir() and expected_disk:
        for p in list(dest_root.iterdir()):
            if p.is_file() and p.name not in expected_disk:
                try:
                    p.unlink()
                except OSError:
                    pass

    if n_ok == 0 and not any_note:
        return 0, "", 0, 0

    return n_ok, "\n".join(lines).rstrip() + "\n", bytes_total, n_err
