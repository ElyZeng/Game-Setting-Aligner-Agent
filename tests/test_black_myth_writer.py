from __future__ import annotations

from types import SimpleNamespace

import pytest

from config_manager.settings_parser import extract_key_settings, setting_options_for_game
from config_manager.settings_writer import write_settings
from config_manager.verification import backup_and_write


def test_black_myth_dynamic_resolution_is_not_available():
    assert setting_options_for_game(
        "Black Myth: Wukong", "dynamic_resolution", "N/A"
    ) == ["—"]


def test_black_myth_retail_upscaling_and_frame_generation_options():
    assert setting_options_for_game("Black Myth: Wukong", "upscaling") == [
        "—", "TSR", "NXSR", "FSR3", "XeSS",
    ]
    assert setting_options_for_game(
        "Black Myth: Wukong", "frame_generation", upscaling_method="XeSS"
    ) == ["—", "Off", "Auto"]
    for method in ("TSR", "NXSR", "FSR3"):
        assert setting_options_for_game(
            "Black Myth: Wukong", "frame_generation", upscaling_method=method
        ) == ["—", "Off"]


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


def test_black_myth_upscaling_mode_round_trip_uses_render_percentage(tmp_path):
    settings_path = tmp_path / "GameUserSettings.ini"
    content = """[ScalabilityGroups]
sg.ResolutionQuality=100
[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=1920
ResolutionSizeY=1080
DesiredScreenWidth=1920
DesiredScreenHeight=1080
LastUserConfirmedDesiredScreenWidth=1920
LastUserConfirmedDesiredScreenHeight=1080
UISettingData=(("ImageQuality", "1080"),("SuperResolutionSampling", "1"))
"""
    settings_path.write_text(content, encoding="utf-8")

    write_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": content}],
        {"upscaling_mode": "Balanced (66%)"},
    )

    written = settings_path.read_text(encoding="utf-8")
    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": written}],
    )
    assert "sg.ResolutionQuality=66" in written
    assert '("ImageQuality", "713")' in written
    assert "DesiredScreenWidth=1267" in written
    assert "DesiredScreenHeight=712" in written
    assert "LastUserConfirmedDesiredScreenWidth=1267" in written
    assert "LastUserConfirmedDesiredScreenHeight=712" in written
    assert parsed["upscaling_mode"] == "Balanced (66%)"


def test_black_myth_render_resolution_does_not_replace_output_resolution():
    content = """ResolutionSizeX=1920
ResolutionSizeY=1080
LastUserConfirmedDesiredScreenWidth=1267
LastUserConfirmedDesiredScreenHeight=712
sg.ResolutionQuality=66
UISettingData=(("ImageQuality", "713"),("SuperResolutionSampling", "0"))
"""

    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": "GameUserSettings.ini", "found": True, "content": content}],
    )

    assert parsed["resolution"] == "1920x1080"
    assert parsed["upscaling_mode"] == "Balanced (66%)"


@pytest.mark.parametrize(
    ("method", "stored_value"),
    [("FSR3", "0"), ("XeSS", "1"), ("TSR", "3"), ("NXSR", "5")],
)
def test_black_myth_upscaling_method_round_trip_updates_ui_setting_data(
    tmp_path, method, stored_value
):
    settings_path = tmp_path / "GameUserSettings.ini"
    content = """[ScalabilityGroups]
sg.ResolutionQuality=66
[/Script/GSGameSettings.GSGameUserSettings]
UISettingData=(("SuperResolutionSampling", "1"))
"""
    settings_path.write_text(content, encoding="utf-8")

    write_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": content}],
        {"upscaling": method},
    )

    written = settings_path.read_text(encoding="utf-8")
    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": written}],
    )
    assert f'("SuperResolutionSampling", "{stored_value}")' in written
    assert parsed["upscaling"] == method


def test_black_myth_non_xess_method_forces_frame_generation_off(tmp_path):
    settings_path = tmp_path / "GameUserSettings.ini"
    content = 'UISettingData=(("SuperResolutionSampling", "1"),("InsertFrame", "1"))\n'
    settings_path.write_text(content, encoding="utf-8")

    write_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": content}],
        {"upscaling": "FSR3"},
    )

    written = settings_path.read_text(encoding="utf-8")
    assert '("SuperResolutionSampling", "0")' in written
    assert '("InsertFrame", "0")' in written
    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": str(settings_path), "found": True, "content": written}],
    )
    assert parsed["frame_generation"] == "Off"


def test_black_myth_non_xess_parser_ignores_stale_frame_generation():
    content = 'UISettingData=(("SuperResolutionSampling", "3"),("InsertFrame", "1"))\n'

    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": "GameUserSettings.ini", "found": True, "content": content}],
    )

    assert parsed["upscaling"] == "TSR"
    assert parsed["frame_generation"] == "Off"


def test_black_myth_guarded_write_supports_all_writable_settings(tmp_path):
    settings_path = tmp_path / "GameUserSettings.ini"
    content = """[ScalabilityGroups]
sg.ResolutionQuality=100
sg.ViewDistanceQuality=0
sg.AntiAliasingQuality=0
sg.ShadowQuality=0
sg.GlobalIlluminationQuality=0
sg.RayTracingQuality=0
sg.ReflectionQuality=0
sg.PostProcessQuality=0
sg.TextureQuality=0
sg.EffectsQuality=0
sg.FoliageQuality=0
sg.ShadingQuality=0
[/Script/GSGameSettings.GSGameUserSettings]
bUseVSync=True
bUseDynamicResolution=False
FrameRateLimit=0.000000
ResolutionSizeX=1600
ResolutionSizeY=900
LastUserConfirmedResolutionSizeX=1600
LastUserConfirmedResolutionSizeY=900
LastUserConfirmedDesiredScreenWidth=1600
LastUserConfirmedDesiredScreenHeight=900
FullscreenMode=2
LastConfirmedFullscreenMode=2
PreferredFullscreenMode=1
UISettingData=(("ScreenMode", "2"),("Vsync", "1"),("SuperResolutionSampling", "1"),("InsertFrame", "1"),("QualityLevel", "1"))
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
            "rule": {"supported_settings": [
                "resolution", "screen_mode", "vsync", "frame_limit",
                "upscaling", "upscaling_mode",
                "frame_generation", "quick_preset",
            ]},
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
            "frame_limit": "60 FPS",
            "upscaling": "XeSS",
            "upscaling_mode": "Balanced (66%)",
            "frame_generation": "Off",
            "quick_preset": "High",
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
    assert parsed["frame_limit"] == "60 FPS"
    assert parsed["dynamic_resolution"] == "N/A"
    assert parsed["upscaling"] == "XeSS"
    assert parsed["upscaling_mode"] == "Balanced (66%)"
    assert parsed["frame_generation"] == "Off"
    assert parsed["quick_preset"] == "High"
    written = settings_path.read_text(encoding="utf-8")
    assert "sg.ResolutionQuality=66" in written
    for key in (
        "ViewDistance", "AntiAliasing", "Shadow", "GlobalIllumination",
        "Reflection", "PostProcess", "Texture", "Effects", "Foliage",
        "Shading",
    ):
        assert f"sg.{key}Quality=2" in written
    assert "sg.RayTracingQuality=0" in written


def test_black_myth_parser_rejects_preset_label_when_scalability_differs():
    content = """[ScalabilityGroups]
sg.ViewDistanceQuality=0
sg.AntiAliasingQuality=0
sg.ShadowQuality=0
sg.GlobalIlluminationQuality=0
sg.RayTracingQuality=0
sg.ReflectionQuality=0
sg.PostProcessQuality=0
sg.TextureQuality=0
sg.EffectsQuality=0
sg.FoliageQuality=0
sg.ShadingQuality=0
[/Script/GSGameSettings.GSGameUserSettings]
UISettingData=(("QualityLevel", "2"))
"""

    parsed = extract_key_settings(
        "Black Myth: Wukong",
        [{"expanded_path": "GameUserSettings.ini", "found": True, "content": content}],
    )

    assert parsed["quick_preset"] == "Custom"