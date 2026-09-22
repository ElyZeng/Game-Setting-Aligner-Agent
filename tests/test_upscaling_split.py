import json

import pytest

from config_manager.settings_parser import extract_key_settings, setting_options_for_game
from config_manager.settings_writer import _write_cyberpunk, _write_f1_xml, _write_forza_xml


def _config(content: str, path: str, **extra):
    return {"found": True, "content": content, "expanded_path": path, **extra}


def test_unreal_upscaling_method_and_mode_are_separate():
    result = extract_key_settings(
        "ARC Raiders",
        [_config("ResolutionSizeX=1920\nResolutionSizeY=1080\nResolutionScalingMethod=DLSS\nDLSSMode=Quality\n", "GameUserSettings.ini")],
    )

    assert result["upscaling"] == "DLSS"
    assert result["upscaling_mode"] == "Quality"


def test_forza_upscaling_method_and_mode_are_separate():
    result = extract_key_settings(
        "Forza Horizon 6",
        [_config('<UserConfig Version="52"><selections><option id="XeSSMode" value="4" /></selections></UserConfig>', "UserConfigSelections")],
    )

    assert result["upscaling"] == "XeSS"
    assert result["upscaling_mode"] == "Balanced"


def test_f1_upscaling_method_and_mode_are_separate():
    result = extract_key_settings(
        "F1 25",
        [_config('<hardware_settings_config><antialiasing dlss="false" fsr3="1" xess="false" /><aa_quality value="1" /></hardware_settings_config>', "hardware_settings_config.xml")],
    )

    assert result["upscaling"] == "FSR"
    assert result["upscaling_mode"] == "Balanced"


def test_registry_upscaling_method_and_mode_are_separate():
    result = extract_key_settings(
        "Horizon Zero Dawn",
        [_config('{"Graphics":{"UpscaleMethod":4,"UpscaleQuality":3}}', "registry.json", type="registry")],
    )

    assert result["upscaling"] == "XeSS"
    assert result["upscaling_mode"] == "Quality"


def test_cs2_upscaling_method_and_mode_are_separate():
    result = extract_key_settings(
        "Counter-Strike 2",
        [_config('"setting.videocfg_fsr_detail" "2"\n', "cs2_video.txt")],
    )

    assert result["upscaling"] == "FSR"
    assert result["upscaling_mode"] == "Quality"


def test_games_without_upscaling_mode_report_not_available():
    sf6 = extract_key_settings(
        "Street Fighter 6",
        [_config("UpscaleType=DLSS\n", "config.ini")],
    )

    assert sf6["upscaling"] == "DLSS"
    assert sf6["upscaling_mode"] == "N/A"


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [
        ("50", "Performance (50%)"),
        ("66", "Balanced (66%)"),
        ("71", "Quality (71%)"),
        ("100", "Native AA (100%)"),
    ],
)
def test_black_myth_reports_percentage_upscaling_mode(percentage, expected):
    result = extract_key_settings(
        "Black Myth: Wukong",
        [_config(
            f'sg.ResolutionQuality={percentage}\nUISettingData=(("SuperResolutionSampling", "1"))',
            "GameUserSettings.ini",
        )],
    )

    assert result["upscaling"] == "XeSS"
    assert result["upscaling_mode"] == expected


def test_black_myth_exposes_percentage_upscaling_modes():
    assert setting_options_for_game("Black Myth: Wukong", "upscaling") == [
        "—", "TSR", "NXSR", "FSR3", "XeSS",
    ]
    assert setting_options_for_game(
        "Black Myth: Wukong", "upscaling_mode", upscaling_method="XeSS",
    ) == [
        "—",
        "Ultra Performance (33%)",
        "Performance (50%)",
        "Balanced (66%)",
        "Quality (75%)",
        "Native AA (100%)",
    ]


@pytest.mark.parametrize("method", ["TSR", "NXSR", "FSR3", "XeSS"])
def test_black_myth_exposes_percentage_modes_for_each_method(method):
    assert "Balanced (66%)" in setting_options_for_game(
        "Black Myth: Wukong", "upscaling_mode", upscaling_method=method,
    )


def test_black_myth_exposes_retail_frame_generation_and_preset_options():
    assert setting_options_for_game(
        "Black Myth: Wukong", "frame_generation", upscaling_method="XeSS",
    ) == ["—", "Off", "Auto"]
    assert setting_options_for_game("Black Myth: Wukong", "quick_preset") == [
        "—", "Custom", "Low", "Medium", "High", "Very High", "Cinematic",
    ]


def test_forza_exposes_separate_method_and_mode_options():
    assert setting_options_for_game("Forza Horizon 6", "upscaling") == [
        "—", "Off", "DLSS", "FSR", "XeSS",
    ]
    assert setting_options_for_game(
        "Forza Horizon 6", "upscaling_mode", upscaling_method="XeSS",
    ) == [
        "—", "Ultra Quality Plus", "Ultra Quality", "Quality", "Balanced",
        "Performance", "Ultra Performance",
    ]


def test_f1_exposes_separate_method_and_mode_options():
    assert setting_options_for_game("F1 25", "upscaling") == [
        "—", "Off", "DLSS", "FSR", "XeSS",
    ]
    assert setting_options_for_game(
        "F1 25", "upscaling_mode", upscaling_method="FSR",
    ) == ["—", "Quality", "Balanced", "Performance", "Ultra Performance"]


def test_cs2_exposes_fsr_modes_only():
    assert setting_options_for_game("Counter-Strike 2", "upscaling") == ["—", "Off", "FSR"]
    assert setting_options_for_game(
        "Counter-Strike 2", "upscaling_mode", upscaling_method="FSR",
    ) == ["—", "Ultra Quality", "Quality", "Balanced", "Performance"]


def test_unreal_writer_accepts_separate_method_and_mode():
    from config_manager.settings_writer import _write_unreal_ini

    content = "ResolutionScalingMethod=FSR\nDLSSMode=Quality\nFSRMode=Balanced\n"
    result = _write_unreal_ini(content, {"upscaling": "DLSS", "upscaling_mode": "Performance"})

    assert "ResolutionScalingMethod=DLSS" in result
    assert "DLSSMode=Performance" in result


def test_forza_writer_accepts_separate_method_and_mode():
    from config_manager.settings_writer import _write_forza_xml

    content = '<selections><option id="DLSSMode" value="0" /><option id="FSR3Mode" value="0" /><option id="XeSSMode" value="0" /></selections>'
    result = _write_forza_xml(content, {"upscaling": "XeSS", "upscaling_mode": "Balanced"})

    assert '<option id="XeSSMode" value="4" />' in result
    assert '<option id="DLSSMode" value="0" />' in result
    assert '<option id="FSR3Mode" value="0" />' in result


def test_forza_writer_can_change_mode_without_changing_method():
    from config_manager.settings_writer import _write_forza_xml

    content = '<selections><option id="DLSSMode" value="0" /><option id="FSR3Mode" value="1" /><option id="XeSSMode" value="0" /></selections>'
    result = _write_forza_xml(content, {"upscaling_mode": "Performance"})

    assert '<option id="FSR3Mode" value="3" />' in result


def test_f1_writer_accepts_separate_method_and_mode():
    from config_manager.settings_writer import _write_f1_xml

    content = '<hardware_settings_config><antialiasing dlss="false" fsr3="1" xess="false" /><aa_quality value="0" /></hardware_settings_config>'
    result = _write_f1_xml(content, {"upscaling": "XeSS", "upscaling_mode": "Ultra Quality"})

    assert '<antialiasing dlss="false" fsr3="0" xess="true" />' in result
    assert '<aa_quality value="4" />' in result


def test_registry_writer_accepts_separate_method_and_mode():
    from config_manager.settings_writer import _write_registry_json

    result = _write_registry_json(
        '{"Graphics":{"UpscaleMethod":1,"UpscaleQuality":0}}',
        {"upscaling": "XeSS", "upscaling_mode": "Quality"},
    )

    assert '"UpscaleMethod": 4' in result
    assert '"UpscaleQuality": 3' in result


def test_cs2_writer_accepts_separate_method_and_mode():
    from config_manager.settings_writer import _write_cs2_video

    content = '"setting.videocfg_fsr_detail" "0"\n'
    result = _write_cs2_video(content, {"upscaling": "FSR", "upscaling_mode": "Balanced"})

    assert '"setting.videocfg_fsr_detail" "3"' in result


@pytest.mark.parametrize("game", ["Forza Horizon 6", "F1 25"])
def test_verified_xml_games_round_trip_every_upscaling_option(game):
    if game == "Forza Horizon 6":
        content = '<UserConfig Version="52"><selections><option id="DLSSMode" value="0" /><option id="FSR3Mode" value="0" /><option id="XeSSMode" value="0" /></selections></UserConfig>'
        writer = _write_forza_xml
        path = "UserConfigSelections"
    else:
        content = '<hardware_settings_config><antialiasing dlss="false" fsr3="0" xess="false" /><aa_quality value="0" /></hardware_settings_config>'
        writer = _write_f1_xml
        path = "hardware_settings_config.xml"

    for method in setting_options_for_game(game, "upscaling")[1:]:
        if method == "Off":
            continue
        for mode in setting_options_for_game(game, "upscaling_mode", upscaling_method=method)[1:]:
            written = writer(content, {"upscaling": method, "upscaling_mode": mode})
            parsed = extract_key_settings(game, [_config(written, path)])
            assert (parsed["upscaling"], parsed["upscaling_mode"]) == (method, mode)


def test_verified_cyberpunk_round_trips_every_upscaling_option():
    methods = setting_options_for_game("Cyberpunk 2077", "upscaling")[1:]
    for method in methods:
        if method == "Off":
            continue
        for mode in setting_options_for_game("Cyberpunk 2077", "upscaling_mode", upscaling_method=method)[1:]:
            stored_method = {"FSR 2.1": "FSR2", "FSR 3": "FSR3", "XeSS": "XeSS"}[method]
            content = json.dumps({"data": [{
                "group_name": "/graphics/presets",
                "options": [
                    {"name": "ResolutionScaling", "value": "Off", "index": 0},
                    {"name": "XESS" if method == "XeSS" else stored_method, "value": "Auto", "index": 0},
                ],
            }]})
            written = _write_cyberpunk(content, {"upscaling": method, "upscaling_mode": mode})
            parsed = extract_key_settings("Cyberpunk 2077", [_config(written, "UserSettings.json")])
            assert (parsed["upscaling"], parsed["upscaling_mode"]) == (method, mode)