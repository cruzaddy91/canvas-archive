import pytest

from canvas_archive.extractors import STRATEGIES, get_strategy
from canvas_archive.extractors.canvas_only import CanvasOnlyExtractor
from canvas_archive.extractors.external_site import ExternalSiteExtractor


def test_known_strategies_are_registered():
    assert set(STRATEGIES) == {"canvas_only", "external_site"}


def test_get_strategy_returns_canvas_only_instance():
    strategy = get_strategy("canvas_only")
    assert isinstance(strategy, CanvasOnlyExtractor)


def test_get_strategy_returns_external_site_instance():
    strategy = get_strategy("external_site")
    assert isinstance(strategy, ExternalSiteExtractor)


def test_get_strategy_raises_systemexit_for_unknown_name():
    with pytest.raises(SystemExit, match="unknown strategy"):
        get_strategy("does_not_exist")
