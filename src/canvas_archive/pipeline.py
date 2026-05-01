from __future__ import annotations

import datetime
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .core.canvas import get_canvas, parse_course
from .core.git_ops import (
    capture,
    clone_or_pull,
    commit_if_changes,
    is_initial_archive,
    push_and_verify,
    run,
)
from .extractors import get_strategy
from .profiles import find_profile_by_id

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = PROJECT_ROOT / "infra"
TFVARS_PATH = INFRA_DIR / "courses.auto.tfvars.json"
EXTRACTS_ROOT = Path.home() / "Workspace" / "school" / "canvas-extracts"
REPO_PREFIX = "canvas-archive"
GITHUB_OWNER = "cruzaddy91"

# Files/dirs from the deprecated v1/v2 archive format. The current extractors never
# produce these, but they can persist in remote repos from earlier runs and leak in
# via clone. Wipe them after clone, before extract.
STALE_ARTIFACTS = (
    "course.json",
    "modules.json",
    "external_links.json",
    "syllabus.md",
    "front_page.md",
    "files_unfetchable.json",
    "pages",
    "quizzes",
    "files",
    "external_content",
)


def wipe_stale_artifacts(local_dir: Path) -> int:
    n = 0
    for name in STALE_ARTIFACTS:
        target = local_dir / name
        if not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        print(f"  removed stale: {name}")
        n += 1
    return n


def resolve_meta(course, profile: dict[str, Any]) -> dict[str, Any]:
    """Profile values override auto-derived ones."""
    derived = parse_course(course)
    return {
        "canvas_id": course.id,
        "code": derived["code"],
        "name": derived["name"],
        "term": derived["term"],
        "slug_kebab": profile.get("slug_kebab") or derived["slug_kebab"],
        "slug_camel": profile.get("slug_camel") or derived["slug_camel"],
    }


def update_tfvars(slug: str, meta: dict[str, Any]) -> bool:
    if TFVARS_PATH.exists():
        data = json.loads(TFVARS_PATH.read_text())
    else:
        data = {"courses": {}}
    courses = data.setdefault("courses", {})
    entry = {
        "canvas_id": meta["canvas_id"],
        "code": meta["code"],
        "name": meta["name"],
        "term": meta["term"],
    }
    if courses.get(slug) == entry:
        return False
    courses[slug] = entry
    TFVARS_PATH.write_text(json.dumps(data, indent=2) + "\n")
    return True


def terraform_apply() -> None:
    env = os.environ.copy()
    env["GITHUB_TOKEN"] = capture(["gh", "auth", "token"])
    run(["terraform", "apply", "-auto-approve"], cwd=INFRA_DIR, env=env)


def run_pipeline(canvas_id: int, push: bool = False) -> None:
    canvas = get_canvas()
    course = canvas.get_course(canvas_id)

    profile = find_profile_by_id(canvas_id) or {"strategy": "canvas_only"}
    meta = resolve_meta(course, profile)

    repo_name = f"{REPO_PREFIX}-{meta['slug_kebab']}"
    repo_url = f"https://github.com/{GITHUB_OWNER}/{repo_name}.git"
    local_dir = EXTRACTS_ROOT / meta["slug_camel"]
    strategy_name = profile.get("strategy", "canvas_only")

    print(f"Course   : {meta['code']} ({meta['term']}) - {meta['name']}")
    print(f"Strategy : {strategy_name}")
    print(f"Repo     : {repo_name}")
    print(f"Local    : {local_dir}\n")

    print("[1/6] Update tfvars")
    if update_tfvars(meta["slug_kebab"], meta):
        print(f"  added {meta['slug_kebab']} to tfvars")
    else:
        print("  tfvars already current")

    print("\n[2/6] Terraform apply")
    terraform_apply()

    print("\n[3/6] Clone/pull working copy")
    initial = is_initial_archive(local_dir)
    clone_or_pull(repo_url, local_dir)
    stale = wipe_stale_artifacts(local_dir)
    if stale:
        print(f"  wiped {stale} stale v1/v2 artifact(s) from remote")

    print("\n[4/6] Extract")
    extractor = get_strategy(strategy_name)
    result = extractor.extract(course, profile, local_dir)
    print(f"  result: {result.summary()}")

    print("\n[5/6] Commit (if changed)")
    today = datetime.date.today().isoformat()
    label = "Initial archive" if initial else "Re-archive"
    committed = commit_if_changes(local_dir, f"{label} {today}")

    print("\n[6/6] Push" + ("" if push else " (skipped, pass --push to enable)"))
    if push and committed:
        push_and_verify(local_dir)
    elif not push and committed:
        print("  local commit ready; not pushed")
    elif not committed:
        print("  nothing to push")

    print(f"\nDone -> {local_dir}")
    if push:
        print(f"      -> https://github.com/{GITHUB_OWNER}/{repo_name}")
