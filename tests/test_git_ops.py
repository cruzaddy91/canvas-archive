from canvas_archive.core.git_ops import is_initial_archive


def test_is_initial_archive_true_when_dir_missing(tmp_path):
    assert is_initial_archive(tmp_path / "not-cloned-yet") is True


def test_is_initial_archive_true_when_no_assignments_dir(tmp_path):
    (tmp_path / "README.md").write_text("hello")
    assert is_initial_archive(tmp_path) is True


def test_is_initial_archive_false_when_assignments_dir_exists(tmp_path):
    (tmp_path / "assignments").mkdir()
    assert is_initial_archive(tmp_path) is False
