from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from canvasapi import Canvas
from dotenv import load_dotenv

_TERM_SUFFIX = re.compile(r"\s+(\d{2}[A-Z]+)\s*$")
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(_PROJECT_ROOT / ".env")


def get_canvas() -> Canvas:
    url = os.environ.get("CANVAS_URL")
    token = os.environ.get("CANVAS_TOKEN")
    if not url or not token:
        sys.exit("CANVAS_URL and CANVAS_TOKEN must be set in .env")
    return Canvas(url, token)


def get_token() -> str:
    token = os.environ.get("CANVAS_TOKEN")
    if not token:
        sys.exit("CANVAS_TOKEN must be set in .env")
    return token


def derive_course_meta(course) -> tuple[str, str]:
    """Returns (code_short, term) e.g. ('CMPT-306', '24FA')."""
    raw_code = (getattr(course, "course_code", None) or "").replace("*", "-")
    parts = [p for p in raw_code.split("-") if p]
    code_short = "-".join(parts[:2]).upper() if len(parts) >= 2 else raw_code.upper()
    name = course.name or ""
    m = _TERM_SUFFIX.search(name)
    term = m.group(1) if m else ""
    return code_short, term


def parse_course(course) -> dict:
    """Parses a Canvas course object into the dict used by tfvars + repo naming."""
    raw_code = (getattr(course, "course_code", None) or "").replace("*", "-")
    parts = [p for p in raw_code.split("-") if p]
    dept = parts[0].upper() if parts else "UNKNOWN"
    num = parts[1] if len(parts) >= 2 else "000"

    raw_name = course.name or ""
    name = re.sub(r"\s+Sect\.\s+\d+\s*", " ", raw_name).strip()
    m = re.search(r"\s+(\d{2}[A-Z]+)\s*$", name)
    if m:
        term = m.group(1)
        name = name[:m.start()].strip()
    else:
        term = ""

    kebab = re.sub(r"[^\w]+", "-", name.lower()).strip("-") or "course"
    camel = "".join(w[:1].upper() + w[1:] for w in re.split(r"\W+", name) if w) or "Course"

    return {
        "canvas_id": course.id,
        "code": f"{dept}-{num}-01",
        "name": name,
        "term": term,
        "slug_kebab": f"{dept.lower()}-{num.lower()}-{kebab}",
        "slug_camel": f"{dept}{num}_{camel}",
    }
