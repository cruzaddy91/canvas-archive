from .base import ExtractResult, ExtractStrategy
from .canvas_only import CanvasOnlyExtractor
from .external_site import ExternalSiteExtractor

STRATEGIES: dict[str, type[ExtractStrategy]] = {
    "canvas_only": CanvasOnlyExtractor,
    "external_site": ExternalSiteExtractor,
}


def get_strategy(name: str) -> ExtractStrategy:
    cls = STRATEGIES.get(name)
    if cls is None:
        raise SystemExit(f"unknown strategy {name!r}; known: {sorted(STRATEGIES)}")
    return cls()


__all__ = ["ExtractResult", "ExtractStrategy", "STRATEGIES", "get_strategy"]
