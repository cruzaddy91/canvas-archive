from __future__ import annotations

from pathlib import Path
from typing import Any

from canvasapi.exceptions import CanvasException

from ..core.assignment_canvas_files import download_assignment_linked_canvas_files
from ..core.assignment_external_download import download_external_starter_files
from ..core.course_home_table import (
    HomeTableRefs,
    external_starter_downloads_allowed,
    parse_course_home_tables,
)
from ..core.fetch_403_cache import reset_run_forbidden_cache
from ..core.follow_spec_links import append_followed_spec
from ..core.markdown import to_md
from ..core.slug import dir_slug, slug
from ..observability import StepTimer, log_event
from .base import ExtractResult, reset_dir, write_text


PLACEHOLDER = "_No description provided in Canvas._"

_APPENDIX_MARKERS = (
    "## Canvas file attachments",
    "## External starter files (instructor host)",
)


def _strip_assignment_appendices(text: str) -> str:
    """Remove prior download appendix sections so re-runs do not stack duplicates."""
    cut = len(text)
    for m in _APPENDIX_MARKERS:
        i = text.find(m)
        if i != -1:
            cut = min(cut, i)
    if cut >= len(text):
        return text
    return text[:cut].rstrip() + "\n"


# Global skip-list for assignment names (matched case-insensitive on full name).
# Canvas auto-creates "Roll Call Attendance" when a prof uses the attendance roll-call tool;
# it carries no real assignment content and clutters the archive.
SKIP_NAMES: set[str] = {"roll call attendance"}


def assignment_md(a, group_name: str, profile: dict[str, Any]) -> tuple[str, bool]:
    raw = getattr(a, "description", "") or ""
    body = to_md(raw).strip()
    merged, enriched = append_followed_spec(
        body=body,
        raw_description_html=raw,
        assignment_name=a.name or "",
        group_name=group_name,
        profile=profile,
    )
    if merged.strip():
        fragment = merged
    elif body:
        fragment = body
    else:
        fragment = PLACEHOLDER
    return (f"# {a.name}\n\n{fragment}\n", enriched)


def _slug_map_for_home_table(assignments: list[Any]) -> dict[str, int]:
    return {slug(a.name): int(a.id) for a in assignments if a.name and getattr(a, "id", None)}


def _parse_course_home_table_stage(
    course: Any,
    profile: dict[str, Any],
    assignments: list[Any],
) -> HomeTableRefs | None:
    """Stage D: merge and parse course home / supplement HTML for schedule starters (once per run)."""
    if not profile.get("assignment_files_from_course_home_table"):
        return None
    slug_map = _slug_map_for_home_table(assignments)
    try:
        home = parse_course_home_tables(course, profile, assignment_slug_to_id=slug_map)
    except (CanvasException, TypeError, ValueError, OSError) as e:
        print(f"  course_home_table: skipped ({e})")
        return None
    if home and (home.canvas_by_assignment or home.external_urls_by_assignment):
        nc = len(home.canvas_by_assignment)
        ne = len(home.external_urls_by_assignment)
        print(
            f"  course_home_table: Canvas file refs for {nc} assignment id(s); "
            f"external starter URLs for {ne} assignment id(s)"
        )
    elif home is not None:
        print(
            "  course_home_table: no starter links parsed (no <table> in visible HTML, "
            "no Assignments column match, or empty syllabus or front page for this token; "
            "set course_home_file_table_page_slug if the schedule is on another wiki page)"
        )
    return home


def _stage_download_canvas_files(
    *,
    course: Any,
    assignment_id: int,
    assignment_dir: Path,
    raw_description_html: str,
    profile: dict[str, Any],
    home_table_refs: dict[int, list[tuple[int, int]]] | None,
) -> tuple[int, str, int, int]:
    """Stages A–C plus merge: Canvas files from description, modules, and optional home table."""
    return download_assignment_linked_canvas_files(
        course=course,
        assignment_id=assignment_id,
        assignment_dir=assignment_dir,
        raw_description_html=raw_description_html,
        profile=profile,
        home_table_refs=home_table_refs,
    )


def _stage_download_external_starters(
    *,
    urls: list[str],
    assignment_dir: Path,
    profile: dict[str, Any],
    shared_external_url_cache: dict[str, Path] | None,
) -> tuple[int, str, int, int, int]:
    """Stage F–G: instructor-host URLs plus optional follow-from-htm."""
    return download_external_starter_files(
        urls=urls,
        assignment_dir=assignment_dir,
        profile=profile,
        shared_external_url_cache=shared_external_url_cache,
    )


class CanvasOnlyExtractor:
    """Default strategy. Writes ``assignments/<group>/<assignment-dir>/<name>.md`` and optional ``canvas/``, ``external/`` siblings."""

    def extract(self, course, profile: dict[str, Any], out_dir: Path) -> ExtractResult:
        result = ExtractResult()
        ext_timer = StepTimer()
        reset_run_forbidden_cache()
        out_dir.mkdir(parents=True, exist_ok=True)
        spec_follow_total = 0

        d = out_dir / "assignments"
        reset_dir(d)

        try:
            groups = {g.id: g.name.strip() for g in course.get_assignment_groups()}
        except CanvasException:
            groups = {}

        raw_assignments = list(course.get_assignments())
        assignments = [
            a for a in raw_assignments
            if (a.name or "").strip().lower() not in SKIP_NAMES
        ]
        skipped_count = len(raw_assignments) - len(assignments)
        if skipped_count:
            print(f"  filtered {skipped_count} skip-list assignment(s)")

        home = _parse_course_home_table_stage(course, profile, assignments)
        if home:
            result.stage_home_table_canvas_assignments = len(home.canvas_by_assignment)
            result.stage_home_table_external_assignments = len(home.external_urls_by_assignment)

        shared_external_url_cache: dict[str, Path] | None = (
            {} if profile.get("dedupe_external_download_urls") else None
        )

        name_buckets: dict[tuple[str, str], int] = {}
        for a in assignments:
            group_id = getattr(a, "assignment_group_id", None)
            group_name = groups.get(group_id, "_ungrouped")
            key = (group_name, slug(a.name))
            name_buckets[key] = name_buckets.get(key, 0) + 1

        counts: dict[str, int] = {}
        for a in assignments:
            group_id = getattr(a, "assignment_group_id", None)
            group_name = groups.get(group_id, "_ungrouped")
            group_dir = d / dir_slug(group_name)
            s = slug(a.name)
            if name_buckets[(group_name, s)] > 1:
                filename = f"{s} ({a.id}).md"
            else:
                filename = f"{s}.md"
            a_desc = a
            if profile.get("refetch_assignment_description"):
                try:
                    a_desc = course.get_assignment(a.id)
                except CanvasException:
                    a_desc = a
            raw = getattr(a_desc, "description", "") or ""
            md_stem = Path(filename).stem
            assignment_dir = group_dir / dir_slug(md_stem)
            assignment_dir.mkdir(parents=True, exist_ok=True)
            home_table_refs = home.canvas_by_assignment if (home and home.canvas_by_assignment) else None
            n_dl, appendix, dl_bytes, dl_err = _stage_download_canvas_files(
                course=course,
                assignment_id=a.id,
                assignment_dir=assignment_dir,
                raw_description_html=raw,
                profile=profile,
                home_table_refs=home_table_refs,
            )
            if n_dl > 0:
                result.stage_assignments_with_canvas_downloads += 1
            ext_appendix = ""
            ex_bytes = 0
            ex_err = 0
            n_ex = 0
            if home and external_starter_downloads_allowed(profile):
                ex_urls = home.external_urls_by_assignment.get(int(a.id), [])
                if ex_urls:
                    n_ex, ext_appendix, ex_bytes, ex_err, n_spec_follow = _stage_download_external_starters(
                        urls=ex_urls,
                        assignment_dir=assignment_dir,
                        profile=profile,
                        shared_external_url_cache=shared_external_url_cache,
                    )
                    spec_follow_total += n_spec_follow
                    if n_ex > 0:
                        result.stage_assignments_with_external_downloads += 1
            text, enriched = assignment_md(a_desc, group_name, profile)
            pieces = [p for p in (appendix, ext_appendix) if p]
            if pieces:
                text = _strip_assignment_appendices(text.rstrip()) + "".join(pieces)
                if not text.endswith("\n"):
                    text += "\n"
            write_text(assignment_dir / filename, text)
            counts[group_name] = counts.get(group_name, 0) + 1
            result.assignments_written += 1
            if enriched:
                result.assignments_enriched += 1
            result.canvas_files_downloaded += n_dl
            result.canvas_file_bytes_total += dl_bytes + ex_bytes
            result.canvas_file_errors += dl_err + ex_err
            result.external_starters_downloaded += n_ex

        result.extract_duration_ms = ext_timer.latency_ms()
        result.external_spec_follow_downloaded = spec_follow_total
        log_event(
            "extractor.canvas_only",
            "extract_complete",
            canvas_id=int(course.id),
            assignments_written=result.assignments_written,
            assignments_enriched=result.assignments_enriched,
            canvas_files_downloaded=result.canvas_files_downloaded,
            canvas_file_bytes_total=result.canvas_file_bytes_total,
            canvas_file_errors=result.canvas_file_errors,
            external_starters_downloaded=result.external_starters_downloaded,
            external_spec_follow_downloaded=spec_follow_total,
            extract_duration_ms=result.extract_duration_ms,
            stage_home_table_canvas_assignments=result.stage_home_table_canvas_assignments,
            stage_home_table_external_assignments=result.stage_home_table_external_assignments,
            stage_assignments_with_canvas_downloads=result.stage_assignments_with_canvas_downloads,
            stage_assignments_with_external_downloads=result.stage_assignments_with_external_downloads,
        )
        summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
        print(f"  assignments: {result.assignments_written} .md files  [{summary}]")
        if profile.get("follow_description_links") and result.assignments_enriched:
            print(f"  follow_description_links: merged instructor pages for {result.assignments_enriched} assignment(s)")
        n_starter = result.canvas_files_downloaded + result.external_starters_downloaded
        if n_starter:
            print(
                f"  starter files: {n_starter} saved "
                f"({result.canvas_files_downloaded} Canvas, {result.external_starters_downloaded} instructor host)"
            )
        return result
