"""Tests for config_manager/profiles/loader.py (P1 schema validation + loading)."""

import json

import pytest

from config_manager.profiles.loader import ProfileError, load_all, load_profile


def test_load_all_real_profiles_succeeds():
    """All checked-in profiles must validate — this is the "fails at load/test
    time, not production" guarantee from the P1 handoff."""
    profiles = load_all()
    assert "black-myth-wukong" in profiles
    profile = profiles["black-myth-wukong"]
    assert profile.matches("Black Myth: Wukong")
    assert not profile.matches("Black Myth: Wukong Benchmark Tool")
    assert not profile.matches("Some Other Game")


def _write_profile(tmp_path, data):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


MINIMAL_VALID = {
    "id": "test-game",
    "match": {"names": ["Test Game"]},
    "engine": "unreal",
    "files": {"main": {"path": "GameUserSettings.ini", "codec": "unreal_ini"}},
    "parser_fn": "black_myth_parse",
    "writer_fn": "black_myth_write",
}


def test_minimal_valid_profile_loads(tmp_path):
    path = _write_profile(tmp_path, MINIMAL_VALID)
    profile = load_profile(path)
    assert profile.id == "test-game"
    assert profile.version_policy == "exact"
    assert profile.anticheat["review"] == "n/a"


def test_missing_required_field_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    del data["match"]
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="match"):
        load_profile(path)


def test_unknown_codec_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    data["files"] = {"main": {"path": "x.ini", "codec": "not_a_real_codec"}}
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="not_a_real_codec"):
        load_profile(path)


def test_unregistered_parser_fn_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    data["parser_fn"] = "no_such_function"
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="no_such_function"):
        load_profile(path)


def test_profile_without_settings_or_parser_writer_fn_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    del data["parser_fn"]
    del data["writer_fn"]
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="settings"):
        load_profile(path)


def test_invalid_level_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    data["verified"] = [{"platform": "Steam", "version": "1.0", "levels": {"resolution": "L9"}}]
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="L9"):
        load_profile(path)


def test_invalid_json_raises(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProfileError, match="invalid JSON"):
        load_profile(path)


def test_required_keys_reference_unknown_file_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    data["required_keys"] = {"aux": ["SomeKey"]}
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="aux"):
        load_profile(path)
