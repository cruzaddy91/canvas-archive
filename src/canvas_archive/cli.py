from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .core.canvas import get_canvas
from .core.git_ops import push_and_verify
from .pipeline import EXTRACTS_ROOT, run_pipeline, resolve_meta
from .profiles import find_profile_by_id, list_profiles


def cmd_list(args: argparse.Namespace) -> None:
    canvas = get_canvas()
    rows = []
    for c in canvas.get_courses(include=["term"]):
        name = getattr(c, "name", "<unnamed>")
        code = getattr(c, "course_code", "")
        term = getattr(getattr(c, "term", None), "name", "") or ""
        state = getattr(c, "workflow_state", "")
        rows.append((term, code, c.id, state, name))
    rows.sort(key=lambda r: (r[0], r[1]))
    print(f"{'TERM':<22} {'CODE':<22} {'ID':>10}  {'STATE':<12} NAME")
    print("-" * 100)
    for term, code, cid, state, name in rows:
        print(f"{term:<22} {code:<22} {cid:>10}  {state:<12} {name}")
    print(f"\n{len(rows)} courses")


def cmd_run(args: argparse.Namespace) -> None:
    run_pipeline(args.canvas_id, push=args.push)


def cmd_run_all(args: argparse.Namespace) -> None:
    profiles = list_profiles()
    if not profiles:
        print("no profile files found in profiles/")
        return
    for profile_path in profiles:
        try:
            data = yaml.safe_load(profile_path.read_text()) or {}
        except yaml.YAMLError as e:
            print(f"  [skip] {profile_path.name}: {e}")
            continue
        cid = data.get("canvas_id")
        if not cid:
            print(f"  [skip] {profile_path.name}: no canvas_id")
            continue
        print(f"\n=== {profile_path.name} (canvas_id={cid}) ===")
        try:
            run_pipeline(cid, push=args.push)
        except Exception as e:
            print(f"  [error] {type(e).__name__}: {e}")


def cmd_show_profile(args: argparse.Namespace) -> None:
    profile = find_profile_by_id(args.canvas_id)
    if profile is None:
        print(json.dumps({"canvas_id": args.canvas_id, "strategy": "canvas_only", "_default": True}, indent=2))
        return
    print(yaml.safe_dump(profile, sort_keys=False))


def cmd_push(args: argparse.Namespace) -> None:
    canvas = get_canvas()
    course = canvas.get_course(args.canvas_id)
    profile = find_profile_by_id(args.canvas_id) or {"strategy": "canvas_only"}
    meta = resolve_meta(course, profile)
    local_dir = EXTRACTS_ROOT / meta["slug_camel"]
    if not (local_dir / ".git").exists():
        sys.exit(f"no git repo at {local_dir}. Run `canvas-archive run {args.canvas_id}` first.")
    push_and_verify(local_dir)


def main() -> None:
    parser = argparse.ArgumentParser(prog="canvas-archive")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list all Canvas courses")
    p_list.set_defaults(fn=cmd_list)

    p_run = sub.add_parser("run", help="provision + extract + commit (push optional)")
    p_run.add_argument("canvas_id", type=int)
    p_run.add_argument("--push", action="store_true", help="also push to remote")
    p_run.set_defaults(fn=cmd_run)

    p_run_all = sub.add_parser("run-all", help="run pipeline for every profile in profiles/")
    p_run_all.add_argument("--push", action="store_true")
    p_run_all.set_defaults(fn=cmd_run_all)

    p_show = sub.add_parser("show-profile", help="print resolved profile for a canvas_id")
    p_show.add_argument("canvas_id", type=int)
    p_show.set_defaults(fn=cmd_show_profile)

    p_push = sub.add_parser("push", help="push existing local commit to remote")
    p_push.add_argument("canvas_id", type=int)
    p_push.set_defaults(fn=cmd_push)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
