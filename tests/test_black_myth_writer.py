from __future__ import annotations

from types import SimpleNamespace

from config_manager.settings_parser import extract_key_settings
from config_manager.settings_writer import write_settings
from config_manager.verification import backup_and_write


def test_black_myth_vsync_round_trip_only_writes_game_user_settings(tmp_path):
    engine_path = tmp_path / "Engine.ini"
    engine_content = "[SystemSettings]\nr.Foo=1\n"
    engine_path.write_text(engine_content, encoding="utf-8")

    settings_path = tmp_path / "GameUserSettings.ini"
    settings_content = """[/Script/GSGameSettings.GSGameUserSettings]
bUseVSync=True
ResolutionSizeX=1600
ResolutionSizeY=900
UISettingData=(("ScreenMode", "2"),("Vsync", "1"),("SuperResolutionSampling", "1"),("InsertFrame", "1"),("QualityLevel", "1"))
"""
    settings_path.write_text(settings_content, encoding="utf-8")
    config_files = [
        {"expanded_path": str(engine_path), "found": True, "content": engine_content},
        {"expanded_path": str(settings_path), "found": True, "content": settings_content},
    ]

    result = write_settings("Black Myth: Wukong", config_files, {"vsync": "Off"})

    written = settings_path.read_text(encoding="utf-8")
    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": written}],
    )
    assert result == [{
        "path": str(settings_path),
        "status": "ok",
        "detail": "Black Myth settings written",
    }]
    assert parsed["vsync"] == "Off"
    assert "bUseVSync=False" in written
    assert '("Vsync", "0")' in written
    assert engine_path.read_text(encoding="utf-8") == engine_content


def test_black_myth_resolution_round_trip_updates_desired_dimensions(tmp_path):
    settings_path = tmp_path / "GameUserSettings.ini"
    content = """[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=1600
ResolutionSizeY=900
LastUserConfirmedResolutionSizeX=1600
LastUserConfirmedResolutionSizeY=900
LastUserConfirmedDesiredScreenWidth=1600
LastUserConfirmedDesiredScreenHeight=900
UISettingData=(("ScreenMode", "2"),("ImageQuality", "1080"))
"""
    settings_path.write_text(content, encoding="utf-8")

    write_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": content}],
        {"resolution": "1920x1080"},
    )

    written = settings_path.read_text(encoding="utf-8")
    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": written}],
    )
    assert parsed["resolution"] == "1920x1080"
    assert "LastUserConfirmedDesiredScreenWidth=1920" in written
    assert "LastUserConfirmedDesiredScreenHeight=1080" in written


def test_black_myth_screen_mode_round_trip_updates_ui_setting_data(tmp_path):
    settings_path = tmp_path / "GameUserSettings.ini"
    content = """[/Script/GSGameSettings.GSGameUserSettings]
FullscreenMode=2
LastConfirmedFullscreenMode=2
PreferredFullscreenMode=1
UISettingData=(("ScreenMode", "2"),("Vsync", "1"))
"""
    settings_path.write_text(content, encoding="utf-8")

    write_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": content}],
        {"screen_mode": "Fullscreen"},
    )

    written = settings_path.read_text(encoding="utf-8")
    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": written}],
    )
    assert parsed["screen_mode"] == "Fullscreen"
    assert '("ScreenMode", "0")' in written


def test_black_myth_guarded_write_supports_all_writable_settings(tmp_path):
    settings_path = tmp_path / "GameUserSettings.ini"
    content = """[/Script/GSGameSettings.GSGameUserSettings]
bUseVSync=True
ResolutionSizeX=1600
ResolutionSizeY=900
LastUserConfirmedResolutionSizeX=1600
LastUserConfirmedResolutionSizeY=900
LastUserConfirmedDesiredScreenWidth=1600
LastUserConfirmedDesiredScreenHeight=900
FullscreenMode=2
LastConfirmedFullscreenMode=2
PreferredFullscreenMode=1
UISettingData=(("ScreenMode", "2"),("Vsync", "1"))
"""
    settings_path.write_text(content, encoding="utf-8")
    config_files = [{
        "expanded_path": str(settings_path),
        "found": True,
        "content": content,
    }]
    registry = SimpleNamespace(
        data_dir=tmp_path / "app-data",
        test_write_enabled=lambda: True,
        status_for=lambda *_args: {
            "status": "write_candidate",
            "reason": "verified",
            "rule": {"supported_settings": ["resolution", "screen_mode", "vsync"]},
        },
    )

    result = backup_and_write(
        "Black Myth: Wukong",
        "Steam",
        "Steam build 21393610",
        config_files,
        {
            "resolution": "1920x1080",
            "screen_mode": "Fullscreen",
            "vsync": "Off",
        },
        write_settings,
        registry,
    )

    backup = registry.data_dir / "backups" / "Black_Myth_Wukong" / "0-GameUserSettings.ini"
    assert result[0]["status"] == "ok"
    assert backup.read_text(encoding="utf-8") == content
    parsed = extract_key_settings("Black Myth: Wukong", [{
        "expanded_path": str(settings_path),
        "found": True,
        "content": settings_path.read_text(encoding="utf-8"),
    }])
    assert parsed["resolution"] == "1920x1080"
    assert parsed["screen_mode"] == "Fullscreen"
    assert parsed["vsync"] == "Off"