from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from config_manager.settings_parser import ALL_KEYS, setting_options_for_game
from config_manager.verification import (
    builtin_manifest,
    VerificationError,
    VerificationRegistry,
    backup_and_write,
    game_structural_fingerprint,
    structural_fingerprint,
)


def _reviewed_rules():
    rules_path = Path(__file__).resolve().parents[1] / "release-assets" / "forza-write-candidate-rules.json"
    return json.loads(rules_path.read_text(encoding="utf-8"))


def test_reviewed_writable_upscaling_rules_allow_method_and_mode():
    for rule in _reviewed_rules():
        if rule["status"] not in {"write_candidate", "write_verified"}:
            continue
        supported = set(rule["supported_settings"])
        if supported & {"upscaling", "upscaling_mode"}:
            assert {"upscaling", "upscaling_mode"} <= supported, rule["game"]


def test_reviewed_rules_preserve_current_writable_games():
    writable_games = {
        rule["game"]
        for rule in _reviewed_rules()
        if rule["status"] in {"write_candidate", "write_verified"}
    }
    assert {"Cyberpunk 2077", "F1 25", "Forza Horizon 6"} <= writable_games


def test_reviewed_rules_enable_all_black_myth_retail_writer_settings():
    rules = [
        rule for rule in _reviewed_rules()
        if rule["game"] == "Black Myth: Wukong" and rule["platform"] == "Steam"
    ]
    assert {rule["fingerprint"] for rule in rules} == {
        "d4387b1827b144ce6b0fe8d8163f973268ee928d742276062f0924068dbc4843",
        "1198ec49c02647f504ab71f395df6d73ec36bfc650abad34094549c48a482dd1",
        "3bb9659ab9341d238ae74e2f5b96e148ff065b8e3fd76155fe3a74eef94221f9",
    }
    for rule in rules:
        assert rule["version"] == "Steam build 21393610"
        assert rule["status"] == "write_candidate"
        assert rule["supported_settings"] == [
            "resolution", "screen_mode", "vsync", "frame_limit",
            "upscaling", "upscaling_mode",
            "frame_generation", "quick_preset",
        ]
        assert rule["writer_id"] == "black-myth-ini-writer"


def test_reviewed_rules_only_allow_known_unique_setting_keys():
    for rule in _reviewed_rules():
        supported = rule["supported_settings"]
        assert len(supported) == len(set(supported)), rule["game"]
        assert set(supported) <= set(ALL_KEYS), rule["game"]


def test_reviewed_writable_settings_have_selectable_options():
    for rule in _reviewed_rules():
        if rule["status"] not in {"write_candidate", "write_verified"}:
            continue
        for key in rule["supported_settings"]:
            if key == "upscaling_mode":
                methods = setting_options_for_game(rule["game"], "upscaling")[1:]
                assert any(
                    len(setting_options_for_game(
                        rule["game"], key, upscaling_method=method,
                    )) > 1
                    for method in methods
                    if method != "Off"
                ), rule["game"]
            else:
                assert len(setting_options_for_game(rule["game"], key)) > 1, (
                    rule["game"], key
                )


class _Response:
    def __init__(self, payload=None, content=b"", text=""):
        self.payload = payload
        self.content = content
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_unknown_game_is_not_allowed_to_write(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.enable_test_writes()
    with pytest.raises(VerificationError, match="write_not_allowed:game_not_listed"):
        backup_and_write(
            "Unknown Game", "Steam", "1.0", [], {"vsync": "On"},
            lambda *_: [], registry,
        )


def test_write_rule_rejects_settings_not_in_supported_list(tmp_path):
    registry = VerificationRegistry("0.08.6", data_dir=tmp_path)
    registry.enable_test_writes()
    registry.status_for = lambda *_args: {
        "status": "write_candidate",
        "reason": "verified",
        "rule": {"supported_settings": ["resolution", "screen_mode"]},
    }
    writes = []

    with pytest.raises(VerificationError, match="write_setting_not_allowed:vsync"):
        backup_and_write(
            "Cyberpunk 2077", "Steam", "2.31", [], {"vsync": "On"},
            lambda *_args: writes.append(True), registry,
        )

    assert writes == []


def test_cyberpunk_upscaling_validation_accepts_method_and_mode_readback(tmp_path, monkeypatch):
    registry = VerificationRegistry("0.08.6", data_dir=tmp_path)
    registry.enable_test_writes()
    registry.status_for = lambda *_args: {
        "status": "write_candidate",
        "reason": "verified",
        "rule": {"supported_settings": ["upscaling", "upscaling_mode"]},
    }
    monkeypatch.setattr(
        "config_manager.verification.extract_key_settings",
        lambda *_args: {"upscaling": "XeSS", "upscaling_mode": "Auto"},
    )

    result = backup_and_write(
        "Cyberpunk 2077", "Steam", "2.31", [],
        {"upscaling": "XeSS", "upscaling_mode": "Auto"},
        lambda *_args: [], registry,
    )

    assert result == []


def test_cyberpunk_upscaling_validation_rejects_wrong_quality(tmp_path, monkeypatch):
    registry = VerificationRegistry("0.08.6", data_dir=tmp_path)
    registry.enable_test_writes()
    registry.status_for = lambda *_args: {
        "status": "write_candidate",
        "reason": "verified",
        "rule": {"supported_settings": ["upscaling", "upscaling_mode"]},
    }
    monkeypatch.setattr(
        "config_manager.verification.extract_key_settings",
        lambda *_args: {"upscaling": "XeSS", "upscaling_mode": "Performance"},
    )

    with pytest.raises(VerificationError, match="write_validation_failed_restored"):
        backup_and_write(
            "Cyberpunk 2077", "Steam", "2.31", [],
            {"upscaling": "XeSS", "upscaling_mode": "Quality"},
            lambda *_args: [], registry,
        )


def test_cyberpunk_frame_limit_validation_accepts_fps_label(tmp_path, monkeypatch):
    registry = VerificationRegistry("0.08.6", data_dir=tmp_path)
    registry.enable_test_writes()
    registry.status_for = lambda *_args: {
        "status": "write_candidate",
        "reason": "verified",
        "rule": {"supported_settings": ["frame_limit"]},
    }
    monkeypatch.setattr(
        "config_manager.verification.extract_key_settings",
        lambda *_args: {"frame_limit": "120"},
    )

    result = backup_and_write(
        "Cyberpunk 2077", "Steam", "2.31", [], {"frame_limit": "120 FPS"},
        lambda *_args: [], registry,
    )

    assert result == []


def test_verified_game_still_requires_test_write_consent(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    fingerprint = structural_fingerprint([])
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Example", "platform": "Steam", "version": "1.0", "fingerprint": fingerprint,
            "status": "write_verified", "config_patterns": [], "supported_settings": [],
            "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }), encoding="utf-8")
    with pytest.raises(VerificationError, match="test_write_consent_required"):
        backup_and_write("Example", "Steam", "1.0", [], {"vsync": "On"}, lambda *_: [], registry)


def test_guarded_write_rechecks_live_file_fingerprint(tmp_path):
    config_path = tmp_path / "GameUserSettings.ini"
    stale_content = "VSync=True\n"
    config_path.write_text("VSync=True\nNewGameGeneratedKey=1\n", encoding="utf-8")
    stale_files = [{
        "expanded_path": str(config_path),
        "found": True,
        "content": stale_content,
    }]
    registry = VerificationRegistry("0.08.8", data_dir=tmp_path / "app-data")
    registry.enable_test_writes()
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "test",
        "minimum_client_version": "0.08.8",
        "games": [{
            "game": "Example",
            "platform": "Steam",
            "version": "1.0",
            "fingerprint": structural_fingerprint(stale_files),
            "status": "write_candidate",
            "config_patterns": [],
            "supported_settings": ["vsync"],
            "reader_id": "example-parser",
            "writer_id": "example-writer",
        }],
    }), encoding="utf-8")
    writes = []

    with pytest.raises(VerificationError, match="write_not_allowed:fingerprint_mismatch"):
        backup_and_write(
            "Example", "Steam", "1.0", stale_files, {"vsync": "Off"},
            lambda *_args: writes.append(True) or [], registry,
        )

    assert writes == []


def test_guarded_write_rejects_file_removed_after_scan(tmp_path):
    config_path = tmp_path / "GameUserSettings.ini"
    stale_files = [{
        "expanded_path": str(config_path),
        "found": True,
        "content": "VSync=True\n",
    }]
    registry = VerificationRegistry("0.08.9", data_dir=tmp_path / "app-data")
    registry.enable_test_writes()
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "test",
        "minimum_client_version": "0.08.9",
        "games": [{
            "game": "Example",
            "platform": "Steam",
            "version": "1.0",
            "fingerprint": structural_fingerprint(stale_files),
            "status": "write_candidate",
            "config_patterns": [],
            "supported_settings": ["vsync"],
            "reader_id": "example-parser",
            "writer_id": "example-writer",
        }],
    }), encoding="utf-8")
    writes = []

    with pytest.raises(VerificationError, match="write_not_allowed:fingerprint_mismatch"):
        backup_and_write(
            "Example", "Steam", "1.0", stale_files, {"vsync": "Off"},
            lambda *_args: writes.append(True) or [], registry,
        )

    assert writes == []


def test_forza_rejects_vsync_on_with_unlimited_frame_limit_before_write(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.enable_test_writes()
    config_files = [{"expanded_path": "UserConfigSelections", "content": "<UserConfig/>"}]
    fingerprint = structural_fingerprint(config_files)
    registry.status_for = lambda *_args: {
        "status": "write_candidate",
        "reason": "verified",
        "rule": {},
    }
    writes = []

    with pytest.raises(VerificationError, match="forza_incompatible_settings:vsync_on_unlimited"):
        backup_and_write(
            "Forza Horizon 6",
            "Steam",
            "1.0",
            config_files,
            {"vsync": "On", "frame_limit": "Unlimited"},
            lambda *_args: writes.append(True),
            registry,
        )

    assert writes == []


def test_f1_rejects_frame_generation_with_fullscreen_before_write(tmp_path):
    registry = VerificationRegistry("0.08.2", data_dir=tmp_path)
    registry.enable_test_writes()
    config_files = [{"expanded_path": "hardware_settings_config.xml", "content": "<hardware_settings_config/>"}]
    registry.status_for = lambda *_args: {
        "status": "write_candidate",
        "reason": "verified",
        "rule": {},
    }
    writes = []

    with pytest.raises(VerificationError, match="f1_incompatible_settings:frame_generation_fullscreen"):
        backup_and_write(
            "F1® 25",
            "Steam",
            "1,0,141,2878",
            config_files,
            {"frame_generation": "XeFG", "screen_mode": "Fullscreen"},
            lambda *_args: writes.append(True),
            registry,
        )

    assert writes == []


def test_f1_accepts_custom_base_preset_when_frame_generation_is_enabled(tmp_path):
    registry = VerificationRegistry("0.08.3", data_dir=tmp_path)
    registry.enable_test_writes()
    config_files = [{"expanded_path": "hardware_settings_config.xml", "content": "<hardware_settings_config/>"}]
    registry.status_for = lambda *_args: {
        "status": "write_candidate",
        "reason": "verified",
        "rule": {},
    }

    def write_and_make_custom(*_args):
        return [{"path": "hardware_settings_config.xml", "status": "ok"}]

    from config_manager import verification as verification_module
    original_extract = verification_module.extract_key_settings
    verification_module.extract_key_settings = lambda *_args: {
        "quick_preset": "Custom (Medium)",
        "frame_generation": "AMD FSR3",
    }
    try:
        result = backup_and_write(
            "F1® 25",
            "Steam",
            "1,0,141,2878",
            config_files,
            {"quick_preset": "Medium", "frame_generation": "AMD FSR3"},
            write_and_make_custom,
            registry,
        )
    finally:
        verification_module.extract_key_settings = original_extract

    assert result[0]["status"] == "ok"


def test_structural_fingerprint_ignores_setting_values():
    one = structural_fingerprint([{"expanded_path": "GameUserSettings.ini", "content": "VSync=True\n"}])
    two = structural_fingerprint([{"expanded_path": "GameUserSettings.ini", "content": "VSync=False\n"}])
    assert one == two


def test_black_myth_fingerprint_ignores_unrelated_engine_keys():
    game_settings = {
        "expanded_path": "GameUserSettings.ini",
        "content": "ResolutionSizeX=1920\n",
    }
    before = [game_settings, {"expanded_path": "Engine.ini", "content": "r.Foo=1\n"}]
    after = [
        game_settings,
        {"expanded_path": "Engine.ini", "content": "r.Foo=1\nStickyKeysHotkey=False\n"},
    ]

    assert game_structural_fingerprint("Black Myth: Wukong", before) == (
        game_structural_fingerprint("Black Myth: Wukong", after)
    )
    assert game_structural_fingerprint("Other Unreal Game", before) != (
        game_structural_fingerprint("Other Unreal Game", after)
    )


def test_release_update_installs_manifest_and_keeps_previous(tmp_path):
    manifest = {
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [],
    }
    raw = json.dumps(manifest).encode("utf-8")
    checksum = hashlib.sha256(raw).hexdigest()
    responses = iter([
        _Response({"assets": [
            {"name": "verified-games.json", "browser_download_url": "manifest"},
            {"name": "verified-games.json.sha256", "browser_download_url": "checksum"},
        ]}),
        _Response(content=raw),
        _Response(text=checksum),
    ])
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path, http_get=lambda *_args, **_kwargs: next(responses))

    assert registry.update()["updated"] is True
    assert registry.load()["manifest_version"] == "1.0.0"


def test_status_uses_newly_installed_manifest_after_update(tmp_path):
    config_files = [{"expanded_path": "UserConfigSelections", "content": "VSync=On\n"}]
    fingerprint = structural_fingerprint(config_files)
    manifest = {
        "format_version": 1,
        "manifest_version": "2.0.0",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Forza Horizon 6", "platform": "Steam", "version": "1.0",
            "fingerprint": fingerprint, "status": "write_candidate", "config_patterns": [],
            "supported_settings": [], "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }
    raw = json.dumps(manifest).encode("utf-8")
    checksum = hashlib.sha256(raw).hexdigest()
    responses = iter([
        _Response({"assets": [
            {"name": "verified-games.json", "browser_download_url": "manifest"},
            {"name": "verified-games.json.sha256", "browser_download_url": "checksum"},
        ]}),
        _Response(content=raw),
        _Response(text=checksum),
    ])
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path, http_get=lambda *_args, **_kwargs: next(responses))

    assert registry.status_for("Forza Horizon 6", "Steam", "1.0", fingerprint)["reason"] == "game_not_listed"
    assert registry.update()["manifest_version"] == "2.0.0"
    assert registry.status_for("Forza Horizon 6", "Steam", "1.0", fingerprint)["status"] == "write_candidate"
    assert registry.status_for("Forza Horizon 6", "Steam", "2.0", fingerprint)["status"] == "candidate"
    assert registry.status_for("Forza Horizon 6", "Steam", "1.0", "other")["status"] == "candidate"


def test_specific_rule_overrides_builtin_wildcard_rule(tmp_path):
    registry = VerificationRegistry("0.07.8", data_dir=tmp_path)
    fingerprint = "f1-fingerprint"
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "f1-test",
        "minimum_client_version": "0.07.8",
        "games": [{
            "game": "F1 25", "platform": "Steam", "version": "unknown",
            "fingerprint": fingerprint, "status": "write_candidate",
            "config_patterns": [], "supported_settings": [],
            "reader_id": "f1-xml-parser", "writer_id": "f1-xml-writer",
        }],
    }), encoding="utf-8")

    status = registry.status_for("F1 25", "Steam", "unknown", fingerprint)

    assert status["status"] == "write_candidate"
    assert status["reason"] == "verified"


def test_failed_update_preserves_current_manifest_and_status(tmp_path):
    current = {
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Forza Horizon 6", "platform": "Steam", "version": "1.0",
            "fingerprint": "known", "status": "write_candidate", "config_patterns": [],
            "supported_settings": [], "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }
    replacement = {
        "format_version": 1,
        "manifest_version": "2.0.0",
        "minimum_client_version": "0.05.1",
        "games": [],
    }
    replacement_raw = json.dumps(replacement).encode("utf-8")
    responses = iter([
        _Response({"assets": [
            {"name": "verified-games.json", "browser_download_url": "manifest"},
            {"name": "verified-games.json.sha256", "browser_download_url": "checksum"},
        ]}),
        _Response(content=replacement_raw),
        _Response(text="0" * 64),
    ])
    registry = VerificationRegistry(
        "0.05.1", data_dir=tmp_path,
        http_get=lambda *_args, **_kwargs: next(responses),
    )
    registry.current_path.write_text(json.dumps(current), encoding="utf-8")
    original_bytes = registry.current_path.read_bytes()

    result = registry.update()

    assert result["updated"] is False
    assert result["error"] == "manifest_checksum_mismatch"
    assert result["manifest_version"] == "1.0.0"
    assert registry.current_path.read_bytes() == original_bytes
    status = registry.status_for("Forza Horizon 6", "Steam", "1.0", "known")
    assert status == {
        "status": "write_candidate",
        "reason": "verified",
        "rule": current["games"][0],
    }


def _write_rule_bundle(path, manifest, checksum=None, extra_files=None):
    raw = json.dumps(manifest, indent=2).encode("utf-8")
    digest = checksum or hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("verified-games.json", raw)
        archive.writestr("verified-games.json.sha256", f"{digest}  verified-games.json\n")
        for name, content in (extra_files or {}).items():
            archive.writestr(name, content)
    return raw


def _manifest(version="2.0.0", minimum="0.05.1"):
    return {
        "format_version": 1,
        "manifest_version": version,
        "published_at": "2026-09-14T00:00:00Z",
        "minimum_client_version": minimum,
        "games": [],
    }


def test_offline_bundle_preview_and_import_preserve_previous_manifest(tmp_path):
    registry = VerificationRegistry("0.07.7", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps(_manifest("1.0.0")), encoding="utf-8")
    bundle = tmp_path / "rules.gtrules"
    incoming_raw = _write_rule_bundle(bundle, _manifest("2.0.0"))

    preview = registry.preview_offline_bundle(bundle)
    result = registry.import_offline_bundle(bundle)

    assert preview["manifest_version"] == "2.0.0"
    assert preview["integrity"] == "sha256_verified"
    assert preview["source"] == "offline_bundle"
    assert result["installed"] is True
    assert registry.current_path.read_bytes() == incoming_raw
    assert json.loads(registry.previous_path.read_text(encoding="utf-8"))["manifest_version"] == "1.0.0"
    log = registry.log_path.read_text(encoding="utf-8")
    assert "source=offline_bundle" in log
    assert "incoming_version=2.0.0" in log
    assert "result=installed" in log


@pytest.mark.parametrize(
    ("bundle_factory", "error"),
    [
        (lambda path: path.write_bytes(b"not a zip"), "invalid_offline_bundle"),
        (lambda path: _write_rule_bundle(path, _manifest(), checksum="0" * 64), "manifest_checksum_mismatch"),
        (lambda path: _write_rule_bundle(path, _manifest(minimum="99.0.0")), "client_update_required"),
        (lambda path: _write_rule_bundle(path, {**_manifest(), "games": "invalid"}), "invalid_manifest_games"),
        (lambda path: _write_rule_bundle(path, _manifest(), extra_files={"private.txt": "secret"}), "invalid_offline_bundle_contents"),
    ],
)
def test_invalid_offline_bundle_does_not_change_caches(tmp_path, bundle_factory, error):
    registry = VerificationRegistry("0.07.7", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps(_manifest("1.0.0")), encoding="utf-8")
    registry.previous_path.write_text(json.dumps(_manifest("0.9.0")), encoding="utf-8")
    before_current = registry.current_path.read_bytes()
    before_previous = registry.previous_path.read_bytes()
    bundle = tmp_path / "rules.gtrules"
    bundle_factory(bundle)

    with pytest.raises(VerificationError, match=error):
        registry.import_offline_bundle(bundle)

    assert registry.current_path.read_bytes() == before_current
    assert registry.previous_path.read_bytes() == before_previous
    assert error in registry.log_path.read_text(encoding="utf-8")


def test_older_offline_bundle_requires_explicit_rollback(tmp_path):
    registry = VerificationRegistry("0.07.7", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps(_manifest("2.0.0")), encoding="utf-8")
    bundle = tmp_path / "rules.gtrules"
    _write_rule_bundle(bundle, _manifest("1.0.0"))

    with pytest.raises(VerificationError, match="offline_manifest_rollback_required"):
        registry.import_offline_bundle(bundle)

    result = registry.import_offline_bundle(bundle, allow_rollback=True)
    assert result["installed"] is True
    assert result["rollback"] is True
    assert registry.load()["manifest_version"] == "1.0.0"


def test_equivalent_manifest_version_is_not_a_rollback(tmp_path):
    registry = VerificationRegistry("0.07.7", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps(_manifest("1.0")), encoding="utf-8")
    bundle = tmp_path / "rules.gtrules"
    _write_rule_bundle(bundle, _manifest("1.0.0"))

    result = registry.import_offline_bundle(bundle)

    assert result["installed"] is True
    assert result["rollback"] is False


def test_offline_bundle_atomic_install_failure_preserves_caches(tmp_path, monkeypatch):
    registry = VerificationRegistry("0.07.7", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps(_manifest("1.0.0")), encoding="utf-8")
    registry.previous_path.write_text(json.dumps(_manifest("0.9.0")), encoding="utf-8")
    before_current = registry.current_path.read_bytes()
    before_previous = registry.previous_path.read_bytes()
    bundle = tmp_path / "rules.gtrules"
    _write_rule_bundle(bundle, _manifest("2.0.0"))
    monkeypatch.setattr(registry, "_replace_current", lambda raw: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(VerificationError, match="offline_bundle_install_failed"):
        registry.import_offline_bundle(bundle)

    assert registry.current_path.read_bytes() == before_current
    assert registry.previous_path.read_bytes() == before_previous


def test_empty_remote_manifest_preserves_builtin_rules(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [],
    }), encoding="utf-8")

    loaded = registry.load()

    assert loaded["manifest_version"] == "1.0.0"
    assert len(loaded["games"]) == len(builtin_manifest("0.05.1")["games"])
    assert registry.status_for("Counter-Strike 2", "Steam", "unknown", "anything")["status"] == "read_verified"


def test_remote_rule_overrides_builtin_rule(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Counter-Strike 2",
            "platform": "*",
            "version": "unknown",
            "fingerprint": "*",
            "status": "deprecated",
            "config_patterns": [],
            "supported_settings": [],
            "reader_id": "existing-parser",
            "writer_id": None,
        }],
    }), encoding="utf-8")

    assert registry.status_for("Counter-Strike 2", "Steam", "unknown", "anything")["status"] == "deprecated"


def test_exact_platform_fingerprint_mismatch_is_not_reported_as_version_mismatch(tmp_path):
    registry = VerificationRegistry("0.08.8", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "test",
        "minimum_client_version": "0.08.8",
        "games": [{
            "game": "Black Myth: Wukong",
            "platform": "Steam",
            "version": "Steam build 21393610",
            "fingerprint": "expected",
            "status": "write_candidate",
            "config_patterns": [],
            "supported_settings": ["vsync"],
            "reader_id": "black-myth-parser",
            "writer_id": "black-myth-ini-writer",
        }],
    }), encoding="utf-8")

    result = registry.status_for(
        "Black Myth: Wukong", "Steam", "Steam build 21393610", "actual"
    )

    assert result["status"] == "candidate"
    assert result["reason"] == "fingerprint_mismatch"
    assert result["rule"] is None


def test_multiple_exact_platform_fingerprint_variants_remain_matchable(tmp_path):
    registry = VerificationRegistry("0.08.10", data_dir=tmp_path)
    rules = []
    for fingerprint in ("before-game-normalization", "after-game-normalization"):
        rules.append({
            "game": "Black Myth: Wukong",
            "platform": "Steam",
            "version": "Steam build 21393610",
            "fingerprint": fingerprint,
            "status": "write_candidate",
            "config_patterns": [],
            "supported_settings": ["resolution", "screen_mode", "vsync"],
            "reader_id": "black-myth-parser",
            "writer_id": "black-myth-ini-writer",
        })
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "test",
        "minimum_client_version": "0.08.10",
        "games": rules,
    }), encoding="utf-8")

    before = registry.status_for(
        "Black Myth: Wukong", "Steam", "Steam build 21393610",
        "before-game-normalization",
    )
    after = registry.status_for(
        "Black Myth: Wukong", "Steam", "Steam build 21393610",
        "after-game-normalization",
    )

    assert before["reason"] == "verified"
    assert after["reason"] == "verified"


@pytest.mark.parametrize(
    ("declared_status", "expected_status"),
    [
        ("candidate", "candidate"),
        ("read_verified", "read_verified"),
        ("write_candidate", "candidate"),
        ("write_verified", "read_verified"),
        ("deprecated", "deprecated"),
    ],
)
def test_version_mismatch_preserves_or_safely_downgrades_status(
    tmp_path, declared_status, expected_status
):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "test",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Example", "platform": "Steam", "version": "1.0", "fingerprint": "*",
            "status": declared_status, "config_patterns": [], "supported_settings": [],
            "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }), encoding="utf-8")

    result = registry.status_for("Example", "Steam", "2.0", "anything")

    assert result["status"] == expected_status
    assert result["reason"] == "version_mismatch"


def test_write_candidate_allows_guarded_test_write(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.enable_test_writes()
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "test",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Example", "platform": "Steam", "version": "1.0",
            "fingerprint": structural_fingerprint([]), "status": "write_candidate",
            "config_patterns": [], "supported_settings": [],
            "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }), encoding="utf-8")

    called = []
    result = backup_and_write(
        "Example", "Steam", "1.0", [], {},
        lambda *_: called.append(True) or [], registry,
    )

    assert result == []
    assert called == [True]