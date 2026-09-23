import subprocess
from unittest.mock import patch

from canvas_archive.extractors.external_site import (
    ExternalSiteExtractor,
    _render_via_chrome,
)


def _mock_status(code):
    return patch(
        "canvas_archive.extractors.external_site._get_base_url_http_status",
        return_value=(code, ""),
    )


def test_render_via_chrome_returns_none_when_binary_missing():
    with _mock_status(200):
        result = _render_via_chrome("https://example.edu/hw1", chrome_path="/nowhere/chrome")
    assert result is None


def test_render_via_chrome_returns_stdout_on_success(tmp_path):
    fake_chrome = tmp_path / "chrome.sh"
    fake_chrome.write_text("#!/bin/sh\necho '<html><body>rendered</body></html>'\n")
    fake_chrome.chmod(0o755)
    with _mock_status(200):
        result = _render_via_chrome("https://example.edu/hw1", chrome_path=str(fake_chrome))
    assert result is not None
    assert "rendered" in result


def test_render_via_chrome_returns_none_on_nonzero_exit(tmp_path):
    fake_chrome = tmp_path / "chrome.sh"
    fake_chrome.write_text("#!/bin/sh\nexit 1\n")
    fake_chrome.chmod(0o755)
    with _mock_status(200):
        result = _render_via_chrome("https://example.edu/hw1", chrome_path=str(fake_chrome))
    assert result is None


def test_render_via_chrome_returns_none_on_timeout(tmp_path):
    fake_chrome = tmp_path / "chrome.sh"
    fake_chrome.write_text("#!/bin/sh\nexit 0\n")
    fake_chrome.chmod(0o755)
    with _mock_status(200), patch(
        "canvas_archive.extractors.external_site.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="chrome", timeout=30),
    ):
        result = _render_via_chrome("https://example.edu/hw1", chrome_path=str(fake_chrome))
    assert result is None


def test_render_via_chrome_rejects_non_200_status_without_launching_chrome():
    """The actual bug this guards against: Chrome happily renders a server's
    403 page as valid, non-empty HTML. cmpt-307's homework pages did exactly
    this, "You don't have permission to access this resource" landed in the
    archive dressed up as real content. A non-200 status must short-circuit
    before Chrome ever launches."""
    with _mock_status(403), patch(
        "canvas_archive.extractors.external_site.subprocess.run"
    ) as mock_run:
        result = _render_via_chrome("https://example.edu/forbidden", chrome_path="/bin/echo")
    assert result is None
    mock_run.assert_not_called()


def test_match_and_embed_via_chrome_writes_rendered_content(tmp_path):
    out_dir = tmp_path
    assignments = out_dir / "assignments"
    assignments.mkdir()
    md_path = assignments / "Homework 1.1.md"
    md_path.write_text("# Homework 1.1\n\n_placeholder_\n")

    patterns = [
        {
            "regex": r"^homework (\d+\.\d+)$",
            "candidates": ["homework{n}.html"],
        }
    ]

    with patch(
        "canvas_archive.extractors.external_site._render_via_chrome",
        return_value="<html><body><p>Real content</p></body></html>",
    ):
        n = ExternalSiteExtractor()._match_and_embed_via_chrome(
            "https://example.edu/course/", out_dir, patterns
        )

    assert n == 1
    updated = md_path.read_text()
    assert "Real content" in updated
    assert "Source: [https://example.edu/course/homework1.1.html]" in updated


def test_match_and_embed_via_chrome_skips_pdf_candidates(tmp_path):
    out_dir = tmp_path
    assignments = out_dir / "assignments"
    assignments.mkdir()
    md_path = assignments / "Homework 2.1.md"
    md_path.write_text("# Homework 2.1\n\n_placeholder_\n")

    patterns = [
        {
            "regex": r"^homework (\d+\.\d+)$",
            "candidates": ["homework{n}.pdf"],
        }
    ]

    with patch("canvas_archive.extractors.external_site._render_via_chrome") as mock_render:
        n = ExternalSiteExtractor()._match_and_embed_via_chrome(
            "https://example.edu/course/", out_dir, patterns
        )

    mock_render.assert_not_called()
    assert n == 0


def test_extractor_is_still_the_documented_public_entrypoint():
    # Sanity check that the class itself (used by the STRATEGIES registry)
    # is unaffected by the module-level fallback helpers added alongside it.
    assert hasattr(ExternalSiteExtractor, "extract")
