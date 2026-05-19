"""Post-extract checks for assignment Markdown (inline data URIs bloat archives)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Output .md should never contain raw data-URI payloads after to_md sanitization.
_DATA_URI_IN_MD = re.compile(r"data:(image|application)\s*;", re.I)
_MAX_LINE_LEN = 20_000


def verify_assignment_markdown(local_dir: Path) -> list[str]:
    """Return human-readable issues for any .md under assignments/ (all groups: homework, quiz, lab, …)."""
    assignments = local_dir / "assignments"
    if not assignments.is_dir():
        return [f"no assignments directory: {assignments}"]

    issues: list[str] = []
    for md in sorted(assignments.rglob("*.md")):
        text = md.read_text(errors="replace")
        if _DATA_URI_IN_MD.search(text):
            issues.append(f"{md.relative_to(local_dir)}: contains inline data: URI (image/application)")
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if len(line) > _MAX_LINE_LEN:
                issues.append(
                    f"{md.relative_to(local_dir)}:{i}: line length {len(line)} "
                    f"(exceeds {_MAX_LINE_LEN}; likely unsanitized binary or base64)"
                )
                break
    return issues


def exit_if_assignment_md_issues(local_dir: Path) -> None:
    problems = verify_assignment_markdown(local_dir)
    if problems:
        print("verify-assignments-md: FAILED", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(1)
    print(f"verify-assignments-md: OK ({local_dir})")
