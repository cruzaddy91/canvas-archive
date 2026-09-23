from canvas_archive.core.markdown import frontmatter, to_md, yaml_value


def test_to_md_empty_html_returns_empty_string():
    assert to_md("") == ""
    assert to_md(None) == ""  # type: ignore[arg-type]


def test_to_md_converts_basic_html_to_markdown():
    result = to_md("<p>Hello <strong>world</strong></p>")
    assert "Hello" in result
    assert "**world**" in result


def test_to_md_prefers_markdown_content_wrapper_over_full_page():
    html = (
        "<html><body>"
        '<nav>skip this</nav><div id="markdown_content"><p>Keep this</p></div>'
        "</body></html>"
    )
    result = to_md(html)
    assert "Keep this" in result
    assert "skip this" not in result


def test_to_md_strips_scripts_and_style_tags():
    html = "<p>Visible</p><script>alert('x')</script><style>.a{}</style>"
    result = to_md(html)
    assert "Visible" in result
    assert "alert" not in result

    assert ".a{}" not in result


def test_to_md_omits_bulky_inline_data_uris():
    long_data_uri = "data:image/png;base64," + "A" * 600
    html = f'<img src="{long_data_uri}" alt="diagram">'
    result = to_md(html)
    assert "base64" not in result
    assert "Omitted embedded file" in result
    assert "diagram" in result


def test_to_md_keeps_short_data_uris_untouched():
    short_data_uri = "data:image/png;base64,AAAA"
    html = f'<img src="{short_data_uri}" alt="tiny">'
    result = to_md(html)
    assert "Omitted embedded file" not in result


def test_yaml_value_formats_scalars_and_collections():
    assert yaml_value(None) == "null"
    assert yaml_value(True) == "true"
    assert yaml_value(3) == "3"
    assert yaml_value([1, 2]) == "[1, 2]"
    assert yaml_value("plain") == '"plain"'
    assert yaml_value("has: colon") == '"has: colon"'


def test_frontmatter_skips_none_values_and_wraps_in_rules():
    result = frontmatter({"title": "Lab 1", "due": None, "points": 10})
    lines = result.splitlines()
    assert lines[0] == "---"
    assert lines[-1] == "---"
    assert "due" not in result
    assert 'title: "Lab 1"' in result
    assert "points: 10" in result
