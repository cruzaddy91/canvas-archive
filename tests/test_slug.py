from canvas_archive.core.slug import dir_slug, slug


def test_slug_replaces_unsafe_characters():
    assert slug("Lab 1: Intro / Setup?") == "Lab 1_ Intro _ Setup_"


def test_slug_strips_trailing_dot_and_space():
    assert slug("trailing.dot. ") == "trailing.dot"


def test_slug_truncates_to_maxlen():
    result = slug("a" * 200, maxlen=10)
    assert result == "a" * 10


def test_slug_empty_input_falls_back_to_untitled():
    assert slug("") == "untitled"
    assert slug("...") == "untitled"


def test_dir_slug_collapses_non_word_runs_to_single_underscore():
    assert dir_slug("Lab 1: Intro / Setup?") == "Lab_1_Intro_Setup"


def test_dir_slug_strips_leading_and_trailing_underscores():
    assert dir_slug("  hello world  ") == "hello_world"


def test_dir_slug_empty_input_falls_back_to_untitled():
    assert dir_slug("///") == "untitled"
