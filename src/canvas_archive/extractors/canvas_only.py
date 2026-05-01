from __future__ import annotations

from pathlib import Path
from typing import Any

from canvasapi.exceptions import CanvasException

from ..core.canvas import derive_course_meta
from ..core.markdown import to_md
from ..core.slug import dir_slug, slug
from .base import ExtractResult, reset_dir, write_text


PLACEHOLDER = "_No description provided in Canvas._"

# Global skip-list for assignment names (matched case-insensitive on full name).
# Canvas auto-creates "Roll Call Attendance" when a prof uses the attendance roll-call tool;
# it carries no real assignment content and clutters the archive.
SKIP_NAMES: set[str] = {"roll call attendance"}


def assignment_md(a, code: str, term: str, group_name: str) -> str:
    body = to_md(getattr(a, "description", "") or "")
    out = [f"# {a.name}", ""]
    if body:
        out.append(body)
    else:
        out.append(PLACEHOLDER)
    return "\n".join(out) + "\n"


class CanvasOnlyExtractor:
    """Default strategy. Writes assignments/<group>/<name>.md from Canvas description fields."""

    def extract(self, course, profile: dict[str, Any], out_dir: Path) -> ExtractResult:
        result = ExtractResult()
        out_dir.mkdir(parents=True, exist_ok=True)

        d = out_dir / "assignments"
        reset_dir(d)

        code, term = derive_course_meta(course)

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

        # Detect collisions per (group, slug) to disambiguate filenames.
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
            write_text(group_dir / filename, assignment_md(a, code, term, group_name))
            counts[group_name] = counts.get(group_name, 0) + 1
            result.assignments_written += 1

        summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
        print(f"  assignments: {result.assignments_written} .md files  [{summary}]")
        return result
