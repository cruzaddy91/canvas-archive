from __future__ import annotations

import re

_SAFE = re.compile(r"[^\w\-. ]+")


def slug(s: str, maxlen: int = 80) -> str:
    cleaned = _SAFE.sub("_", s).strip().strip(".")
    return cleaned[:maxlen] or "untitled"


def dir_slug(s: str) -> str:
    cleaned = re.sub(r"[^\w]+", "_", s).strip("_")
    return cleaned or "untitled"
