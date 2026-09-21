from __future__ import annotations

import json
import zipfile

from config_manager.diagnostic_package import (
    build_preview,
    config_file_id,
    default_file_selection,
    export_diagnostic_package,
)


def test_preview_anonymizes_paths_and_excludes_content_by_default():
    preview = build_preview([{
        "name": "Example", "platform": "Steam", "config_files": [{
            "expanded_path": r"C:\Users\Alice\settings.ini", "found": True,
            "content": "VSync=True\n",
        }],
    }], include_content=False)
    file_data = preview["games"][0]["files"][0]
    assert "Alice" not in file_data["path"]
    assert file_data["preview"] is None
    assert file_data["included"] is True


def test_default_file_selection_excludes_private_or_empty_files():
    assert default_file_selection({"found": True, "content": "x", "expanded_path": "cs2_user_keys.vcfg"}) == {
        "selected": False,
        "reason": "excluded_name:key",
    }
    assert default_file_selection({"found": True, "content": "\n", "expanded_path": "GameUserSettings.ini"}) == {
        "selected": False,
        "reason": "empty_file",
    }
    assert default_file_selection({"found": True, "content": "VSync=True", "expanded_path": "GameUserSettings.ini"}) == {
        "selected": True,
        "reason": "default_selected",
    }


def test_black_myth_recommends_only_game_user_settings():
    preview = build_preview([{
        "name": "Black Myth: Wukong",
        "platform": "Steam",
        "config_files": [
            {"expanded_path": "Engine.ini", "found": True, "content": "r.Foo=1\n"},
            {"expanded_path": "GameUserSettings.ini", "found": True, "content": "VSync=True\n"},
        ],
    }], include_content=False)

    files = {item["path"]: item for item in preview["games"][0]["files"]}
    assert files["Engine.ini"]["default_selected"] is False
    assert files["Engine.ini"]["selection_reason"] == "not_game_settings"
    assert files["GameUserSettings.ini"]["default_selected"] is True


def test_export_writes_anonymous_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("config_manager.diagnostic_package.collect_windows_hardware", lambda: {"os_version": "test"})
    path = export_diagnostic_package([{
        "name": "Example", "platform": "Steam", "config_files": [], "parsed_settings": {},
    }], tmp_path)
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["privacy"]["device_name_collected"] is False
    assert path.name.startswith("game-tuner-report-")


def test_content_export_writes_anonymized_config_copy(tmp_path, monkeypatch):
    monkeypatch.setattr("config_manager.diagnostic_package.collect_windows_hardware", lambda: {})
    path = export_diagnostic_package([{
        "name": "Example", "platform": "Steam", "config_files": [{
            "expanded_path": r"C:\Users\Alice\settings.ini", "found": True,
            "content": "VSync=True\n",
        }], "parsed_settings": {},
    }], tmp_path, include_content=True)
    with zipfile.ZipFile(path) as archive:
        copy = archive.read("configs/0-0.txt").decode("utf-8")
    assert "Alice" not in copy
    assert copy == "VSync=True\n"


def test_content_export_uses_selected_file_ids(tmp_path, monkeypatch):
    monkeypatch.setattr("config_manager.diagnostic_package.collect_windows_hardware", lambda: {})
    selected = {"expanded_path": "GameUserSettings.ini", "found": True, "content": "VSync=True\n"}
    excluded = {"expanded_path": "input.ini", "found": True, "content": "secret-input\n"}
    path = export_diagnostic_package([{
        "name": "Example", "platform": "Steam", "config_files": [selected, excluded], "parsed_settings": {},
    }], tmp_path, include_content=True, selected_file_ids=[config_file_id(selected)])
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
    assert "configs/0-0.txt" in names
    assert "configs/0-1.txt" not in names
    assert [item["included"] for item in manifest["games"][0]["files"]] == [True, False]