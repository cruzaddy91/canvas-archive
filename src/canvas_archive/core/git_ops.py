from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, env=env, check=True, text=True)


def capture(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd, env=env, text=True).strip()


def clone_or_pull(repo_url: str, local_dir: Path) -> None:
    if (local_dir / ".git").exists():
        run(["git", "pull", "--ff-only", "origin", "main"], cwd=local_dir)
    else:
        local_dir.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", repo_url, str(local_dir)])


def commit_if_changes(local_dir: Path, message: str) -> bool:
    run(["git", "add", "-A"], cwd=local_dir)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=local_dir
    )
    if diff.returncode == 0:
        print("  No changes to commit.")
        return False
    full = f"{message}\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
    run(["git", "commit", "-m", full], cwd=local_dir)
    return True


def push_and_verify(local_dir: Path) -> None:
    run(["git", "push", "origin", "main"], cwd=local_dir)
    local_head = capture(["git", "rev-parse", "HEAD"], cwd=local_dir)
    remote_ls = capture(["git", "ls-remote", "origin", "main"], cwd=local_dir)
    remote_head = remote_ls.split()[0] if remote_ls else ""
    if local_head != remote_head:
        sys.exit(f"VERIFY FAIL: local {local_head} != remote {remote_head}")
    print(f"  Verified: local HEAD = remote main = {local_head[:8]}")


def is_initial_archive(local_dir: Path) -> bool:
    """True if this archive has no prior assignment content (initial archive)."""
    if not local_dir.exists():
        return True
    return not (local_dir / "assignments").exists()
