from __future__ import annotations

import datetime
import json
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from .core.canvas import get_canvas, parse_course
from .core.profile_lockdown import validate_profile_security_flags
from .core.git_ops import (
    capture,
    clone_or_pull,
    commit_if_changes,
    is_initial_archive,
    push_and_verify,
    run,
)
from .assignment_md_verify import verify_assignment_markdown
from .extractors import get_strategy
from .observability import StepTimer, log_event
from .profiles import find_profile_by_id, list_profiles

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = PROJECT_ROOT / "infra"
TFVARS_PATH = INFRA_DIR / "courses.auto.tfvars.json"
EXTRACTS_ROOT = Path.home() / "Workspace" / "school" / "canvas-extracts"


def github_owner() -> str:
    """GitHub user or org for clone URLs and Terraform provider owner (see .env.example)."""
    return os.environ.get("CANVAS_ARCHIVE_GITHUB_OWNER", "cruzaddy91")


def repo_prefix() -> str:
    """Prefix for private archive repos, must match Terraform var repo_prefix."""
    return os.environ.get("CANVAS_ARCHIVE_REPO_PREFIX", "canvas-archive")

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
        # Legacy CamelCase label from course name (unused for disk paths; kept for introspection)
        "slug_camel": profile.get("slug_camel") or derived["slug_camel"],
    }


def local_archive_path(meta: dict[str, Any]) -> Path:
    """Clone or extract target: same basename as the private GitHub repo (repo_prefix + slug_kebab)."""
    return EXTRACTS_ROOT / f"{repo_prefix()}-{meta['slug_kebab']}"


def _terraform_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GITHUB_TOKEN"] = capture(["gh", "auth", "token"])
    env["TF_VAR_github_owner"] = github_owner()
    env["TF_VAR_repo_prefix"] = repo_prefix()
    return env


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


def sync_tfvars_from_profiles(*, prune: bool = False) -> tuple[int, int, Path]:
    """
    Rebuild or merge `courses` in courses.auto.tfvars.json from every profile with a canvas_id.

    When prune is False, existing course entries that are not in any profile are kept.
    When prune is True, the file contains only courses referenced by profiles.

    Returns (profile_count_used, skipped_profile_files, path_written).
    """
    canvas = get_canvas()
    from_profiles: dict[str, dict[str, Any]] = {}
    skipped = 0
    for profile_path in list_profiles():
        try:
            data = yaml.safe_load(profile_path.read_text()) or {}
        except yaml.YAMLError as e:
            print(f"  [skip] {profile_path.name}: {e}")
            skipped += 1
            continue
        cid = data.get("canvas_id")
        if not cid:
            print(f"  [skip] {profile_path.name}: no canvas_id")
            skipped += 1
            continue
        course = canvas.get_course(cid)
        meta = resolve_meta(course, data)
        slug = meta["slug_kebab"]
        from_profiles[slug] = {
            "canvas_id": meta["canvas_id"],
            "code": meta["code"],
            "name": meta["name"],
            "term": meta["term"],
        }

    if TFVARS_PATH.exists():
        disk = json.loads(TFVARS_PATH.read_text())
        existing = disk.get("courses") or {}
    else:
        existing = {}

    if prune:
        merged = dict(sorted(from_profiles.items(), key=lambda kv: kv[0]))
    else:
        merged = {**existing, **from_profiles}
        merged = dict(sorted(merged.items(), key=lambda kv: kv[0]))

    payload = {"courses": merged}
    TFVARS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TFVARS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    return len(from_profiles), skipped, TFVARS_PATH


def terraform_init() -> None:
    run(["terraform", "init", "-input=false"], cwd=INFRA_DIR, env=_terraform_env())


def terraform_apply() -> None:
    run(["terraform", "apply", "-auto-approve"], cwd=INFRA_DIR, env=_terraform_env())


def run_pipeline(canvas_id: int, push: bool = False) -> None:
    canvas = get_canvas()
    profile = find_profile_by_id(canvas_id) or {"strategy": "canvas_only"}
    validate_profile_security_flags(profile)
    course_kwargs: dict[str, Any] = {}
    if profile.get("assignment_files_from_course_home_table"):
        course_kwargs["include"] = ["syllabus_body"]
    course = canvas.get_course(canvas_id, **course_kwargs)

    meta = resolve_meta(course, profile)

    rp = repo_prefix()
    go = github_owner()
    repo_name = f"{rp}-{meta['slug_kebab']}"
    repo_url = f"https://github.com/{go}/{repo_name}.git"
    local_dir = local_archive_path(meta)
    strategy_name = profile.get("strategy", "canvas_only")

    print(f"Course   : {meta['code']} ({meta['term']}) - {meta['name']}")
    print(f"Strategy : {strategy_name}")
    print(f"Repo     : {repo_name}")
    print(f"Local    : {local_dir}\n")

    run_timer = StepTimer()
    log_event(
        "pipeline",
        "run_start",
        canvas_id=int(course.id),
        slug_kebab=meta["slug_kebab"],
        strategy=strategy_name,
    )

    print("\n[1/7] Update tfvars")
    if update_tfvars(meta["slug_kebab"], meta):
        print(f"  added {meta['slug_kebab']} to tfvars")
    else:
        print("  tfvars already current")

    print("\n[2/7] Terraform init + apply")
    terraform_init()
    terraform_apply()

    print("\n[3/7] Clone/pull working copy")
    initial = is_initial_archive(local_dir)
    clone_or_pull(repo_url, local_dir)
    stale = wipe_stale_artifacts(local_dir)
    if stale:
        print(f"  wiped {stale} stale v1/v2 artifact(s) from remote")

    print("\n[4/7] Extract")
    extractor = get_strategy(strategy_name)
    result = extractor.extract(course, profile, local_dir)
    print(f"  result: {result.summary()}")

    print("\n[5/7] Verify assignment Markdown")
    md_issues = verify_assignment_markdown(local_dir)
    if md_issues:
        for line in md_issues:
            print(f"  [FAIL] {line}")
        log_event(
            "pipeline",
            "run_failed",
            canvas_id=int(course.id),
            slug_kebab=meta["slug_kebab"],
            phase="verify_assignments_md",
            errors=len(md_issues),
            latency_ms=run_timer.latency_ms(),
        )
        raise SystemExit(1)
    print("  verify-assignments-md: OK")

    print("\n[6/7] Commit (if changed)")
    today = datetime.date.today().isoformat()
    label = "Initial archive" if initial else "Re-archive"
    committed = commit_if_changes(local_dir, f"{label} {today}")

    print("\n[7/7] Push" + ("" if push else " (skipped, pass --push to enable)"))
    if push and committed:
        push_and_verify(local_dir)
    elif not push and committed:
        print("  local commit ready; not pushed")
    elif not committed:
        print("  nothing to push")

    print(f"\nDone -> {local_dir}")
    log_event(
        "pipeline",
        "run_complete",
        canvas_id=int(course.id),
        slug_kebab=meta["slug_kebab"],
        latency_ms=run_timer.latency_ms(),
        committed=bool(committed),
        push=bool(push),
        assignments_written=result.assignments_written,
        canvas_files_downloaded=result.canvas_files_downloaded,
        canvas_file_bytes_total=result.canvas_file_bytes_total,
        canvas_file_errors=result.canvas_file_errors,
        extract_duration_ms=result.extract_duration_ms,
        external_starters_downloaded=result.external_starters_downloaded,
        external_spec_follow_downloaded=result.external_spec_follow_downloaded,
        stage_home_table_canvas_assignments=result.stage_home_table_canvas_assignments,
        stage_home_table_external_assignments=result.stage_home_table_external_assignments,
        stage_assignments_with_canvas_downloads=result.stage_assignments_with_canvas_downloads,
        stage_assignments_with_external_downloads=result.stage_assignments_with_external_downloads,
    )
    if push:
        print(f"      -> https://github.com/{go}/{repo_name}")
