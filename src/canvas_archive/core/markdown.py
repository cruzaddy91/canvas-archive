from __future__ import annotations

import json

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown

# Embedded data: URIs (common on instructor pages for a single inline image) explode
# Markdown output when passed through markdownify. Replace bulky ones with a short note.
_MAX_DATA_URI_LEN = 500


def _strip_bulky_data_uri_sources(soup: BeautifulSoup) -> None:
    """Replace huge data: URLs on media tags so HTML-to-Markdown stays readable."""
    for tag in soup.find_all(["img", "embed", "object", "iframe"]):
        src = (tag.get("src") or "").strip()
        if src.startswith("data:") and len(src) > _MAX_DATA_URI_LEN:
            alt = (tag.get("alt") or tag.get("title") or "").strip() or "inline media"
            note = soup.new_tag("p")
            em = soup.new_tag("em")
            em.string = f"[Omitted embedded file ({len(src)} characters): {alt}]"
            note.append(em)
            tag.replace_with(note)


def _primary_content_fragment(soup: BeautifulSoup) -> str:
    """Prefer obvious main-markdown wrappers so TOC chrome and trailing bundles drop out."""
    for sel in ("#markdown_content", "main", "article", '[role="main"]'):
        node = soup.select_one(sel)
        if node is not None:
            return str(node)
    body = soup.find("body")
    return str(body) if body else str(soup)


def to_md(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "link", "meta", "noscript"]):
        tag.decompose()
    _strip_bulky_data_uri_sources(soup)
    cleaned = _primary_content_fragment(soup)
    return html_to_markdown(cleaned, heading_style="ATX", bullets="-").strip()


def yaml_value(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, (int, float, bool)):
        return json.dumps(v)
    if isinstance(v, list):
        return json.dumps(v)
    return json.dumps(str(v))


def frontmatter(d: dict) -> str:
    lines = ["---"]
    for k, v in d.items():
        if v is None:
            continue
        lines.append(f"{k}: {yaml_value(v)}")
    lines.append("---")
    return "\n".join(lines)
