import pytest

from canvas_archive import profiles


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "PROFILES_DIR", tmp_path)
    return tmp_path


def test_list_profiles_returns_empty_list_when_dir_missing(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(profiles, "PROFILES_DIR", missing)
    assert profiles.list_profiles() == []


def test_list_profiles_skips_underscore_prefixed_files(profiles_dir):
    (profiles_dir / "cmpt-201.yaml").write_text("canvas_id: 1\n")
    (profiles_dir / "_template.yaml").write_text("canvas_id: 0\n")
    result = profiles.list_profiles()
    assert [p.name for p in result] == ["cmpt-201.yaml"]


def test_load_profile_returns_matching_profile_with_default_strategy(profiles_dir):
    (profiles_dir / "cmpt-306.yaml").write_text(
        "canvas_id: 3506954\nslug_kebab: cmpt-306-algorithms\n"
    )
    result = profiles.load_profile(3506954)
    assert result["slug_kebab"] == "cmpt-306-algorithms"
    assert result["strategy"] == "canvas_only"
    assert result["_profile_path"].endswith("cmpt-306.yaml")


def test_load_profile_preserves_explicit_strategy(profiles_dir):
    (profiles_dir / "cmpt-328.yaml").write_text(
        "canvas_id: 42\nstrategy: external_site\n"
    )
    result = profiles.load_profile(42)
    assert result["strategy"] == "external_site"


def test_load_profile_falls_back_to_canvas_only_when_no_match(profiles_dir):
    result = profiles.load_profile(999)
    assert result == {
        "canvas_id": 999,
        "strategy": "canvas_only",
        "_profile_path": None,
    }


def test_load_profile_raises_systemexit_on_invalid_yaml(profiles_dir):
    (profiles_dir / "broken.yaml").write_text("canvas_id: [unclosed\n")
    with pytest.raises(SystemExit):
        profiles.load_profile(1)


def test_find_profile_by_id_returns_none_when_no_match(profiles_dir):
    assert profiles.find_profile_by_id(123) is None


def test_find_profile_by_id_skips_unparseable_files_instead_of_raising(profiles_dir):
    (profiles_dir / "broken.yaml").write_text("canvas_id: [unclosed\n")
    (profiles_dir / "good.yaml").write_text("canvas_id: 55\n")
    result = profiles.find_profile_by_id(55)
    assert result is not None
    assert result["canvas_id"] == 55
