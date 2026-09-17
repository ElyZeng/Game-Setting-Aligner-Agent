from __future__ import annotations

import json

import config_manager.settings_parser as settings_parser
from config_manager.settings_parser import (
    DYNAMIC_RESOLUTION,
    FRAME_LIMIT,
    FRAME_GENERATION,
    QUICK_PRESET,
    RESOLUTION,
    SCREEN_MODE,
    UPSCALING,
    UPSCALING_MODE,
    VSYNC,
    extract_key_settings,
    is_setting_writable_for_game,
    setting_options_for_game,
)
from config_manager.settings_writer import write_settings


def _config(options):
    return json.dumps({
        "data": [{
            "group_name": "/video/display",
            "options": options,
        }],
    })


def test_reads_current_string_window_mode_and_hides_internal_drs():
    content = _config([
        {"name": "WindowMode", "value": "BorderlessWindowed", "index": 1},
        {"name": "DynamicResolutionScaling", "value": False},
    ])

    settings = extract_key_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": "UserSettings.json"}],
    )

    assert settings["screen_mode"] == "Borderless Windowed"
    assert settings[DYNAMIC_RESOLUTION] == "N/A"


def test_reads_current_maximum_fps_value():
    content = _config([
        {"name": "MaximumFPS_OnOff", "value": True},
        {"name": "MaximumFPS_Value", "value": 114},
    ])

    settings = extract_key_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": "UserSettings.json"}],
    )

    assert settings["frame_limit"] == "114"


def test_cyberpunk_frame_limit_options_use_off_label():
    options = setting_options_for_game("Cyberpunk 2077", FRAME_LIMIT, "114")

    assert options == ["—", "Off", "30 FPS", "60 FPS", "120 FPS", "144 FPS", "240 FPS"]
    assert "Unlimited" not in options


def test_writes_current_maximum_fps_value(tmp_path):
    content = _config([
        {"name": "MaximumFPS_OnOff", "value": True},
        {"name": "MaximumFPS_Value", "value": 114},
    ])
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {"frame_limit": "120 FPS"},
    )

    options = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"]
    value = next(option for option in options if option["name"] == "MaximumFPS_Value")
    assert value["value"] == 120


def test_writes_frame_limit_off(tmp_path):
    content = _config([
        {"name": "MaximumFPS_OnOff", "value": True},
        {"name": "MaximumFPS_Value", "value": 114},
    ])
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {FRAME_LIMIT: "Off"},
    )

    options = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"]
    enabled = next(option for option in options if option["name"] == "MaximumFPS_OnOff")
    assert enabled["value"] is False


def test_exposes_only_verified_cyberpunk_controls():
    assert "Ray Tracing Medium" in setting_options_for_game("Cyberpunk 2077", QUICK_PRESET)
    assert is_setting_writable_for_game("Cyberpunk 2077", DYNAMIC_RESOLUTION) is False
    assert is_setting_writable_for_game("Cyberpunk 2077", FRAME_GENERATION) is False


def test_exposes_cyberpunk_upscaling_methods():
    assert setting_options_for_game("Cyberpunk 2077", UPSCALING) == [
        "—",
        "Off",
        "FSR 2.1",
        "FSR 3",
        "XeSS",
    ]


def test_exposes_modes_for_selected_cyberpunk_upscaler():
    assert setting_options_for_game(
        "Cyberpunk 2077", UPSCALING_MODE, upscaling_method="FSR 3"
    ) == ["—", "Auto", "Native AA", "Quality", "Balanced", "Performance", "Ultra Performance", "Dynamic"]
    assert setting_options_for_game(
        "Cyberpunk 2077", UPSCALING_MODE, upscaling_method="XeSS"
    ) == ["—", "Auto", "Ultra Quality Plus", "Ultra Quality", "Quality", "Balanced", "Performance", "Dynamic"]


def test_exposes_refresh_specific_cyberpunk_vsync_choices():
    assert setting_options_for_game("Cyberpunk 2077", VSYNC, "36", refresh_rate=144) == [
        "—", "Off", "144", "72", "48", "36",
    ]
    assert setting_options_for_game("Cyberpunk 2077", VSYNC, "30", refresh_rate=60) == [
        "—", "Off", "60", "30",
    ]
    assert setting_options_for_game("Cyberpunk 2077", VSYNC, "40", refresh_rate=120) == [
        "—", "Off", "120", "60", "40", "30",
    ]
    assert setting_options_for_game("Cyberpunk 2077", VSYNC, "55", refresh_rate=165) == [
        "—", "Off", "165", "82", "55", "41",
    ]


def test_cyberpunk_removes_fullscreen_and_labels_desktop_resolution():
    assert setting_options_for_game("Cyberpunk 2077", SCREEN_MODE) == [
        "—", "Windowed", "Borderless Windowed",
    ]
    assert setting_options_for_game(
        "Cyberpunk 2077", RESOLUTION, desktop_resolution="1920x1080"
    ) == [
        "—",
        "1920x1080 (recommended for proper scaling)",
        "2560x1440",
    ]


def test_cyberpunk_rechecks_desktop_resolution_on_each_refresh(monkeypatch):
    modes = iter([("1920x1080", 60), ("2560x1440", 144)])
    monkeypatch.setattr(settings_parser, "_query_desktop_display_mode", lambda: next(modes))

    first = setting_options_for_game("Cyberpunk 2077", RESOLUTION)
    second = setting_options_for_game("Cyberpunk 2077", RESOLUTION)

    assert "1920x1080 (recommended for proper scaling)" in first
    assert "2560x1440 (recommended for proper scaling)" in second


def test_writes_current_window_mode_value_and_index(tmp_path):
    content = _config([
        {"name": "WindowMode", "value": "BorderlessWindowed", "index": 1},
    ])
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {"screen_mode": "Windowed"},
    )

    option = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"][0]
    assert option["value"] == "Windowed"
    assert option["index"] == 0


def test_writes_1920x1080_value_and_index(tmp_path):
    content = _config([
        {"name": "Resolution", "value": "2560x1440", "index": 21},
    ])
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {"resolution": "1920x1080"},
    )

    option = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"][0]
    assert option["value"] == "1920x1080"
    assert option["index"] == 16


def test_writes_labeled_recommended_resolution_as_raw_value(tmp_path):
    content = _config([
        {"name": "Resolution", "value": "2560x1440", "index": 21},
    ])
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {"resolution": "1920x1080 (recommended for proper scaling)"},
    )

    option = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"][0]
    assert option["value"] == "1920x1080"
    assert option["index"] == 16


def test_writes_numeric_vsync_value_and_index(tmp_path):
    content = _config([
        {"name": "VSync", "value": "36", "index": 4},
    ])
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {"vsync": "72"},
    )

    option = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"][0]
    assert option["value"] == "72"
    assert option["index"] == 2


def test_writes_other_refresh_family_vsync_value_and_index(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "config_manager.settings_writer.desktop_display_mode",
        lambda: ("2560x1440", 165),
    )
    content = _config([
        {"name": "VSync", "value": "82", "index": 2},
    ])
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {"vsync": "41"},
    )

    option = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"][0]
    assert option["value"] == "41"
    assert option["index"] == 4


def test_writes_upscaling_method_and_index(tmp_path):
    content = json.dumps({
        "data": [{
            "group_name": "/graphics/presets",
            "options": [
                {"name": "ResolutionScaling", "value": "Off", "index": 0},
                {"name": "XESS", "value": "Auto", "index": 0},
            ],
        }],
    })
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {UPSCALING: "FSR 3"},
    )

    options = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"]
    method = next(option for option in options if option["name"] == "ResolutionScaling")
    assert method["value"] == "FSR3"
    assert method["index"] == 2


def test_writes_fsr_quality_value_and_index(tmp_path):
    content = json.dumps({
        "data": [{
            "group_name": "/graphics/presets",
            "options": [
                {"name": "ResolutionScaling", "value": "Off", "index": 0},
                {"name": "FSR2", "value": "Auto", "index": 0},
            ],
        }],
    })
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {UPSCALING: "FSR 2.1", UPSCALING_MODE: "Balanced"},
    )

    options = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"]
    method = next(option for option in options if option["name"] == "ResolutionScaling")
    quality = next(option for option in options if option["name"] == "FSR2")
    assert (method["value"], method["index"]) == ("FSR2", 1)
    assert (quality["value"], quality["index"]) == ("Balanced", 2)


def test_writes_xess_quality_value_and_index(tmp_path):
    content = json.dumps({
        "data": [{
            "group_name": "/graphics/presets",
            "options": [
                {"name": "ResolutionScaling", "value": "Off", "index": 0},
                {"name": "XESS", "value": "Auto", "index": 0},
            ],
        }],
    })
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {UPSCALING: "XeSS", UPSCALING_MODE: "Ultra Quality Plus"},
    )

    options = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"]
    method = next(option for option in options if option["name"] == "ResolutionScaling")
    quality = next(option for option in options if option["name"] == "XESS")
    assert (method["value"], method["index"]) == ("XeSS", 3)
    assert (quality["value"], quality["index"]) == ("Ultra Quality Plus", 1)


def test_reads_fsr_method_and_mode_separately():
    content = json.dumps({
        "data": [{
            "group_name": "/graphics/presets",
            "options": [
                {"name": "ResolutionScaling", "value": "FSR2", "index": 2},
                {"name": "FSR2", "value": "Quality", "index": 1},
            ],
        }],
    })

    settings = extract_key_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": "UserSettings.json"}],
    )

    assert settings[UPSCALING] == "FSR 2.1"
    assert settings[UPSCALING_MODE] == "Quality"


def test_reads_fsr3_native_aa_mode():
    content = json.dumps({
        "data": [{
            "group_name": "/graphics/presets",
            "options": [
                {"name": "ResolutionScaling", "value": "FSR3", "index": 2},
                {"name": "FSR3", "value": "NativeAA", "index": 1},
            ],
        }],
    })

    settings = extract_key_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": "UserSettings.json"}],
    )

    assert settings[UPSCALING] == "FSR 3"
    assert settings[UPSCALING_MODE] == "Native AA"


def test_writes_quick_preset_by_value(tmp_path):
    content = json.dumps({
        "data": [{
            "group_name": "/graphics/presets",
            "options": [
                {"name": "QuickPresets", "value": "Custom", "index": 0},
            ],
        }],
    })
    config_path = tmp_path / "UserSettings.json"
    config_path.write_text(content, encoding="utf-8")

    write_settings(
        "Cyberpunk 2077",
        [{"found": True, "content": content, "expanded_path": str(config_path)}],
        {QUICK_PRESET: "High"},
    )

    option = json.loads(config_path.read_text(encoding="utf-8"))["data"][0]["options"][0]
    assert option["value"] == "High"