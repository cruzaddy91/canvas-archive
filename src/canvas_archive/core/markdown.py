from __future__ import annotations

import json

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown


def to_md(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "link", "meta", "noscript"]):
        tag.decompose()
    body = soup.find("body")
    cleaned = str(body) if body else str(soup)
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
