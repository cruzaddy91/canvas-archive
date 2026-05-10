"""One-off: run canvas_only extractor against an existing local course dir.

Skips terraform provisioning and git clone — used when the course already has
its own repo and directory layout that we don't want to disturb. Only touches
<target>/assignments/ (the extractor reset_dirs that subtree before writing).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from canvas_archive.core.canvas import get_canvas
from canvas_archive.extractors import get_strategy
from canvas_archive.profiles import find_profile_by_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("canvas_id", type=int)
    ap.add_argument("target_dir", type=Path)
    args = ap.parse_args()

    target: Path = args.target_dir.expanduser().resolve()
    if not target.exists():
        sys.exit(f"target dir does not exist: {target}")

    canvas = get_canvas()
    course = canvas.get_course(args.canvas_id)
    profile = find_profile_by_id(args.canvas_id) or {"strategy": "canvas_only"}
    strategy_name = profile.get("strategy", "canvas_only")

    print(f"Course   : {course.course_code} - {course.name}")
    print(f"Strategy : {strategy_name}")
    print(f"Target   : {target}")
    print(f"Writes   : {target / 'assignments'}/  (existing siblings untouched)\n")

    extractor = get_strategy(strategy_name)
    result = extractor.extract(course, profile, target)
    print(f"\nresult: {result.summary()}")


if __name__ == "__main__":
    main()
