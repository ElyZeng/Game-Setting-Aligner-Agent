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

    assert "black-myth-wukong-benchmark" in profiles
    benchmark_profile = profiles["black-myth-wukong-benchmark"]
    assert benchmark_profile.matches("Black Myth: Wukong Benchmark Tool")
    assert not benchmark_profile.matches("Black Myth: Wukong")

    assert "f1-25" in profiles
    f1_profile = profiles["f1-25"]
    assert f1_profile.matches("F1® 25")
    assert not f1_profile.matches("F1 25")

    assert "cs2" in profiles
    cs2_profile = profiles["cs2"]
    assert cs2_profile.matches("Counter-Strike 2")
    assert not cs2_profile.matches("CS2")
    assert cs2_profile.parse_mode == "multi_file"

    assert "forza-horizon-6" in profiles
    forza_profile = profiles["forza-horizon-6"]
    assert forza_profile.matches("Forza Horizon 6")
    assert not forza_profile.matches("Forza Horizon 5")
    assert not forza_profile.matches("Forza")
    assert forza_profile.write_side_effect_fn == "forza_fullscreen_sidecar"

    assert "cyberpunk-2077" in profiles
    cyberpunk_profile = profiles["cyberpunk-2077"]
    assert cyberpunk_profile.matches("Cyberpunk 2077")
    assert not cyberpunk_profile.matches("Cyberpunk 2077: Phantom Liberty")
    assert cyberpunk_profile.parse_mode == "single_file"
    assert cyberpunk_profile.write_side_effect_fn is None

    assert "grand-theft-auto-v-enhanced" in profiles
    gta_profile = profiles["grand-theft-auto-v-enhanced"]
    assert gta_profile.matches("Grand Theft Auto V Enhanced")
    assert not gta_profile.matches("Grand Theft Auto V")
    assert not gta_profile.matches("GTA V Enhanced")
    assert gta_profile.parser_fn == "gta_enhanced_parse"
    assert gta_profile.writer_fn is None

    assert "clair-obscur-expedition-33" in profiles
    expedition_profile = profiles["clair-obscur-expedition-33"]
    assert expedition_profile.matches("Clair Obscur: Expedition 33")
    assert not expedition_profile.matches("Clair Obscur")
    assert not expedition_profile.matches("Expedition 33")
    assert expedition_profile.parser_fn == "expedition_33_parse"
    assert expedition_profile.writer_fn is None

    assert "street-fighter-6" in profiles
    sf6_profile = profiles["street-fighter-6"]
    assert sf6_profile.matches("Street Fighter 6")
    assert not sf6_profile.matches("Street Fighter V")
    assert sf6_profile.parser_fn == "sf6_parse"
    assert sf6_profile.writer_fn is None

    assert "horizon-zero-dawn-remastered" in profiles
    hzd_profile = profiles["horizon-zero-dawn-remastered"]
    assert hzd_profile.matches("Horizon Zero Dawn™ Remastered")
    assert not hzd_profile.matches("Horizon Zero Dawn™ Complete Edition")
    assert not hzd_profile.matches("Horizon Zero Dawn")
    assert hzd_profile.parser_fn == "registry_parse"
    assert hzd_profile.writer_fn is None
    assert hzd_profile.parse_mode == "multi_file"

    assert "shadow-of-the-tomb-raider" in profiles
    sottr_profile = profiles["shadow-of-the-tomb-raider"]
    assert sottr_profile.matches("Shadow of the Tomb Raider")
    assert not sottr_profile.matches("Shadow of the Tomb Raider Trial")
    assert sottr_profile.parser_fn == "registry_parse"
    assert sottr_profile.writer_fn is None
    assert sottr_profile.parse_mode == "multi_file"


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


def test_invalid_parse_mode_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    data["parse_mode"] = "not_a_real_mode"
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="not_a_real_mode"):
        load_profile(path)


def test_multi_file_parse_mode_without_parser_fn_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    del data["parser_fn"]
    del data["writer_fn"]
    data["settings"] = {"resolution": {"file": "main"}}
    data["parse_mode"] = "multi_file"
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="multi_file"):
        load_profile(path)


def test_write_side_effect_fn_without_writer_fn_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    del data["writer_fn"]
    data["settings"] = {"resolution": {"file": "main"}}
    data["write_side_effect_fn"] = "forza_fullscreen_sidecar"
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="write_side_effect_fn"):
        load_profile(path)


def test_unregistered_write_side_effect_fn_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    data["write_side_effect_fn"] = "no_such_side_effect_fn"
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="no_such_side_effect_fn"):
        load_profile(path)


def test_required_keys_reference_unknown_file_raises(tmp_path):
    data = dict(MINIMAL_VALID)
    data["required_keys"] = {"aux": ["SomeKey"]}
    path = _write_profile(tmp_path, data)
    with pytest.raises(ProfileError, match="aux"):
        load_profile(path)
