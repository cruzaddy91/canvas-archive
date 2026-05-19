"""Remember instructor URLs that returned HTTP 403 so we do not hammer them on later items or runs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, urlunparse

_CACHE_DIR = Path.home() / ".cache" / "canvas-archive"
_CACHE_FILE = _CACHE_DIR / "fetch_403_urls.txt"

# In-process set for the current extract run (cleared when extract starts).
_run_forbidden: set[str] = set()

# Lazily loaded from disk.
_disk_forbidden: set[str] | None = None


def reset_run_forbidden_cache() -> None:
    _run_forbidden.clear()


def _canonical_key(url: str) -> str:
    u = url.strip().split("#", 1)[0].strip()
    p = urlparse(u)
    path = (p.path or "/").rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", "", ""))


def _load_disk_forbidden() -> set[str]:
    global _disk_forbidden
    if _disk_forbidden is not None:
        return _disk_forbidden
    out: set[str] = set()
    if _CACHE_FILE.is_file():
        try:
            out = {ln.strip() for ln in _CACHE_FILE.read_text().splitlines() if ln.strip()}
        except OSError:
            out = set()
    _disk_forbidden = out
    return out


def is_forbidden_cached(url: str) -> bool:
    key = _canonical_key(url)
    if key in _run_forbidden:
        return True
    return key in _load_disk_forbidden()


def record_forbidden_403(url: str) -> None:
    key = _canonical_key(url)
    _run_forbidden.add(key)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        disk = _load_disk_forbidden()
        if key not in disk:
            with _CACHE_FILE.open("a", encoding="utf-8") as f:
                f.write(key + "\n")
            disk.add(key)
    except OSError:
        pass
