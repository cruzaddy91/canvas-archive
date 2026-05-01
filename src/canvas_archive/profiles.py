from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"


def list_profiles() -> list[Path]:
    if not PROFILES_DIR.exists():
        return []
    return sorted(p for p in PROFILES_DIR.glob("*.yaml") if not p.name.startswith("_"))


def load_profile(canvas_id: int) -> dict[str, Any]:
    """Load profile for canvas_id. Returns default canvas_only profile if no file matches."""
    for path in list_profiles():
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as e:
            raise SystemExit(f"invalid YAML in {path}: {e}")
        if data.get("canvas_id") == canvas_id:
            data.setdefault("strategy", "canvas_only")
            data["_profile_path"] = str(path)
            return data
    return {"canvas_id": canvas_id, "strategy": "canvas_only", "_profile_path": None}


def find_profile_by_id(canvas_id: int) -> dict[str, Any] | None:
    for path in list_profiles():
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        if data.get("canvas_id") == canvas_id:
            return data
    return None
