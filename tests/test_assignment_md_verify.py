from canvas_archive.assignment_md_verify import verify_not_empty


def test_verify_not_empty_flags_zero_assignments():
    issues = verify_not_empty(0)
    assert len(issues) == 1
    assert "0 assignment files" in issues[0]


def test_verify_not_empty_passes_when_assignments_written():
    assert verify_not_empty(1) == []
    assert verify_not_empty(53) == []
