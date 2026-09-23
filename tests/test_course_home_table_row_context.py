from bs4 import BeautifulSoup

from canvas_archive.core.course_home_table import (
    HomeTableRefs,
    _header_labels,
    _leading_number,
    _match_assignment_id_by_leading_number,
    _numeric_match_enabled,
    _parse_table,
    _row_context_text,
    _row_text_context_enabled,
)


def test_row_text_context_enabled_reads_profile_flag():
    assert _row_text_context_enabled({}) is False
    assert _row_text_context_enabled({"course_home_row_text_context": False}) is False
    assert _row_text_context_enabled({"course_home_row_text_context": True}) is True


def _cells(html: str) -> list:
    return BeautifulSoup(html, "html.parser").find_all(["td", "th"])


def test_row_context_text_labels_each_non_empty_cell():
    cells = _cells(
        "<tr><td>1</td><td>Topic A</td><td>Slides here</td><td><a href='/x'>Assignment 1</a></td></tr>"
    )
    headers = ["Index", "Topics", "Slides/Material", "Assignments"]
    ctx = _row_context_text(cells, headers, assignments_col=3)
    assert "**Topics:** Topic A" in ctx
    assert "**Slides/Material:** Slides here" in ctx
    # The assignments column itself is excluded, its links are captured elsewhere.
    assert "Assignment 1" not in ctx
    # Index is noise, skipped.
    assert "Index" not in ctx


def test_row_context_text_skips_empty_cells():
    cells = _cells("<tr><td>Topic A</td><td></td></tr>")
    headers = ["Topics", "Notes"]
    ctx = _row_context_text(cells, headers, assignments_col=99)
    assert ctx == "**Topics:** Topic A"


def test_header_labels_reads_th_and_td_text():
    row = BeautifulSoup("<tr><th>Week</th><td>Topics</td></tr>", "html.parser").tr
    assert _header_labels(row) == ["Week", "Topics"]


# ---------------------------------------------------------------------------
# _parse_table integration: the shapes actually found during the 2026-09-23
# read-only audit of Jingsai's courses.
# ---------------------------------------------------------------------------

_DATA_220_SHAPE = """
<table>
  <tr><th>Index</th><th>Topics</th><th>Assignments/Tests</th></tr>
  <tr>
    <td>1</td>
    <td>Intro to R</td>
    <td><a href="https://westminster.instructure.com/courses/1/assignments/501">R Module 1</a></td>
  </tr>
</table>
"""


def test_parse_table_captures_row_context_for_canvas_only_link_when_enabled():
    """DATA 220's shape: the Assignments column links straight back to Canvas,
    nothing for file-discovery to find, but the row's own Topics text is real
    content and should be captured when the profile opts in."""
    table = BeautifulSoup(_DATA_220_SHAPE, "html.parser").table
    profile = {"course_home_row_text_context": True}
    result = _parse_table(table, {}, profile)
    assert result.canvas_by_assignment == {}
    assert result.row_context_by_assignment == {501: "**Topics:** Intro to R"}


def test_parse_table_skips_row_context_when_flag_not_set():
    table = BeautifulSoup(_DATA_220_SHAPE, "html.parser").table
    result = _parse_table(table, {}, {})
    assert result.row_context_by_assignment == {}


_CMPT_311_ACTIVITY_SHAPE = """
<table>
  <tr><th>Week</th><th>Topics</th><th>Activities</th><th>Assignments</th></tr>
  <tr>
    <td>3</td>
    <td>Decision Trees</td>
    <td>Activity 12 - Decision Tree</td>
    <td></td>
  </tr>
</table>
"""


def test_parse_table_falls_back_to_activities_cell_text_match(tmp_path=None):
    """CMPT 311's shape: some rows have nothing in the Assignments cell at all,
    the row is entirely an in-class Activity. Falls back to matching the
    Activities cell's own text against known assignment names. The context
    includes the Activities cell itself, only the (empty) Assignments cell is
    excluded."""
    table = BeautifulSoup(_CMPT_311_ACTIVITY_SHAPE, "html.parser").table
    slug_map = {"activity-12-decision-tree": 777}
    profile = {"course_home_row_text_context": True}
    result = _parse_table(table, slug_map, profile)
    assert result.row_context_by_assignment == {
        777: "**Topics:** Decision Trees\n**Activities:** Activity 12 - Decision Tree"
    }


def test_parse_table_activities_fallback_requires_single_match():
    """Ambiguous matches are left alone rather than guessing. An exact literal
    name match would short-circuit this (see _all_assignment_ids_for_file_label),
    so this uses two names that both partially, and equally, resemble the
    Activities cell text without exactly matching either."""
    table = BeautifulSoup(_CMPT_311_ACTIVITY_SHAPE, "html.parser").table
    slug_map = {
        "Decision-Tree": 777,
        "Decision:Tree": 778,
    }
    profile = {"course_home_row_text_context": True}
    result = _parse_table(table, slug_map, profile)
    assert result.row_context_by_assignment == {}


def test_home_table_refs_row_context_defaults_to_empty_dict():
    assert HomeTableRefs().row_context_by_assignment == {}


# ---------------------------------------------------------------------------
# The stale-link safety check: a course-home page can be a reused/static
# document whose embedded Canvas links point at a different course offering
# entirely (confirmed on DATA 220, see profiles/data-220-*.yaml). An id this
# course's own roster does not contain must never be trusted.
# ---------------------------------------------------------------------------

_STALE_LINK_SHAPE = """
<table>
  <tr><th>Index</th><th>Topics</th><th>Assignments</th></tr>
  <tr>
    <td>1</td>
    <td>Intro to R</td>
    <td><a href="https://westminster.instructure.com/courses/1/assignments/999999">R Module 1</a></td>
  </tr>
</table>
"""


def test_parse_table_discards_link_id_not_in_known_roster():
    """The link points at assignment id 999999, which is not in slug_map's
    values, so it must not be trusted even though a link was found."""
    table = BeautifulSoup(_STALE_LINK_SHAPE, "html.parser").table
    slug_map = {"some-other-assignment": 501}
    profile = {"course_home_row_text_context": True}
    result = _parse_table(table, slug_map, profile)
    assert result.row_context_by_assignment == {}


def test_parse_table_trusts_link_id_when_no_roster_to_check_against():
    """With no slug_map at all, there is nothing to validate the link id
    against, so the original link-trusting behavior is preserved."""
    table = BeautifulSoup(_STALE_LINK_SHAPE, "html.parser").table
    profile = {"course_home_row_text_context": True}
    result = _parse_table(table, {}, profile)
    assert result.row_context_by_assignment == {999999: "**Topics:** Intro to R"}


def test_parse_table_falls_back_to_cell_text_name_match_when_link_discarded():
    """Once the stale link id is discarded, matching falls through to the
    Assignments cell's own text ("R Module 1")."""
    table = BeautifulSoup(_STALE_LINK_SHAPE, "html.parser").table
    slug_map = {"R Module 1": 501}
    profile = {"course_home_row_text_context": True}
    result = _parse_table(table, slug_map, profile)
    assert result.row_context_by_assignment == {501: "**Topics:** Intro to R"}


# ---------------------------------------------------------------------------
# Numeric fallback: DATA 220's calendar says "05 R module (due 10/1)", Canvas
# says "5. Manipulating data", nothing in common but the leading number.
# ---------------------------------------------------------------------------


def test_leading_number_strips_padding_zeros_and_trailing_punctuation():
    assert _leading_number("05 R module (due 10/1)") == 5
    assert _leading_number("5. Manipulating data") == 5
    assert _leading_number("12) Something") == 12


def test_leading_number_requires_number_in_leading_position():
    # "Test 1" and "Test 5" would otherwise collide with an unrelated
    # differently-numbered series that also starts at 1.
    assert _leading_number("Test 1") is None
    assert _leading_number("") is None


def test_numeric_match_enabled_reads_profile_flag():
    assert _numeric_match_enabled({}) is False
    assert _numeric_match_enabled({"course_home_row_numeric_match": True}) is True


def test_match_assignment_id_by_leading_number_single_match():
    slug_map = {"5. Manipulating data": 501, "6. Correlation": 502}
    assert _match_assignment_id_by_leading_number("05 R module (due 10/1)", slug_map) == 501


def test_match_assignment_id_by_leading_number_no_number_returns_none():
    slug_map = {"5. Manipulating data": 501}
    assert _match_assignment_id_by_leading_number("Test 1", slug_map) is None


def test_match_assignment_id_by_leading_number_ambiguous_returns_none():
    """Two different series that both happen to number their 5th item "5."
    would otherwise collide; leaving it unmatched is correct, not a bug."""
    slug_map = {"5. Manipulating data": 501, "5. Midterm review": 502}
    assert _match_assignment_id_by_leading_number("05 R module (due 10/1)", slug_map) is None


_NUMERIC_FALLBACK_SHAPE = """
<table>
  <tr><th>Index</th><th>Topics</th><th>Assignments</th></tr>
  <tr>
    <td>5</td>
    <td>Manipulating Data in R</td>
    <td>05 R module (due 10/1)</td>
  </tr>
</table>
"""


def test_parse_table_numeric_fallback_requires_its_own_flag():
    """course_home_row_text_context alone is not enough, the numeric fallback
    is a separate, riskier opt-in (see _numeric_match_enabled)."""
    table = BeautifulSoup(_NUMERIC_FALLBACK_SHAPE, "html.parser").table
    slug_map = {"5. Manipulating data": 501}
    profile = {"course_home_row_text_context": True}
    result = _parse_table(table, slug_map, profile)
    assert result.row_context_by_assignment == {}


_NO_ASSIGNMENT_WORD_SHAPE = """
<table>
  <tr><th>Index</th><th>Topics</th><th>Labs/Homework/Project</th></tr>
  <tr>
    <td>1</td>
    <td>Intro</td>
    <td><a href="https://westminster.instructure.com/courses/1/assignments/501">Lab 1</a></td>
  </tr>
</table>
"""


def test_assignments_column_index_finds_nothing_without_override_or_keyword():
    """DATA 370's real header, "Labs/Homework/Project", never says the word
    "assignment" at all. Auto-detection alone must not match it."""
    table = BeautifulSoup(_NO_ASSIGNMENT_WORD_SHAPE, "html.parser").table
    result = _parse_table(table, {}, {"course_home_row_text_context": True})
    assert result.row_context_by_assignment == {}


def test_assignments_column_index_uses_declared_header_override():
    table = BeautifulSoup(_NO_ASSIGNMENT_WORD_SHAPE, "html.parser").table
    profile = {
        "course_home_row_text_context": True,
        "course_home_assignments_column_header": "Labs/Homework/Project",
    }
    result = _parse_table(table, {}, profile)
    assert result.row_context_by_assignment == {501: "**Topics:** Intro"}


def test_assignments_column_index_override_is_case_insensitive():
    table = BeautifulSoup(_NO_ASSIGNMENT_WORD_SHAPE, "html.parser").table
    profile = {
        "course_home_row_text_context": True,
        "course_home_assignments_column_header": "labs/homework/project",
    }
    result = _parse_table(table, {}, profile)
    assert result.row_context_by_assignment == {501: "**Topics:** Intro"}


def test_parse_table_numeric_fallback_matches_when_enabled():
    table = BeautifulSoup(_NUMERIC_FALLBACK_SHAPE, "html.parser").table
    slug_map = {"5. Manipulating data": 501}
    profile = {
        "course_home_row_text_context": True,
        "course_home_row_numeric_match": True,
    }
    result = _parse_table(table, slug_map, profile)
    assert result.row_context_by_assignment == {
        501: "**Topics:** Manipulating Data in R"
    }
