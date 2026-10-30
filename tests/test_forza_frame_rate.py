"""Forza Horizon 6 FrameRate is a fraction of the display refresh rate.

Measured in Forza Horizon 6 6.461.691.0 on a 144 Hz display: the Video > Frame Rate menu offers
36 / 48 / 72 / 144 FPS with VSync On and adds "Unlocked (variable)" with VSync Off; saving each choice wrote
FrameRate 0 / 2 / 3 / 4 (48 FPS = 1 by the same rule), and turning VSync On changed Unlocked to 144 FPS.
"""
import pytest

from config_manager.settings_parser import (
    FRAME_LIMIT,
    extract_key_settings,
    forza_refresh_rate,
    forza_v52_frame_rate_labels,
    setting_options_for_game,
)
from config_manager.settings_writer import _write_forza_xml

GAME = "Forza Horizon 6"


def _config(frame_rate="2", vsync="1", period="0.006944"):
    refresh = f'<MonitorRefreshPeriod value="{period}"/>' if period is not None else ""
    return (
        '<UserConfig Version="52" HardwareHash="0">\n  <settings>\n'
        f'    <PresentInterval value="1"/>\n    {refresh}\n'
        '    <ResolutionWidth value="2560"/>\n    <ResolutionHeight value="1440"/>\n'
        '    <Fullscreen value="1"/>\n  </settings>\n  <selections>\n'
        f'    <option id="FrameRate" value="{frame_rate}"/>\n'
        f'    <option id="VSync" value="{vsync}"/>\n'
        '  </selections>\n</UserConfig>\n'
    )


def _read(content):
    return extract_key_settings(GAME, [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}])


def test_refresh_rate_comes_from_monitor_refresh_period():
    assert forza_refresh_rate(_config(period="0.006944")) == 144
    assert forza_refresh_rate(_config(period="0.016667")) == 60
    assert forza_refresh_rate(_config(period="0.008333")) == 120
    assert forza_refresh_rate(_config(period=None)) == 60
    assert forza_refresh_rate(_config(period="0")) == 60


def test_labels_are_refresh_fractions():
    assert forza_v52_frame_rate_labels(144) == ["36 FPS", "48 FPS", "72 FPS", "144 FPS", "Unlimited"]
    assert forza_v52_frame_rate_labels(60) == ["15 FPS", "20 FPS", "30 FPS", "60 FPS", "Unlimited"]
    assert forza_v52_frame_rate_labels(None) == forza_v52_frame_rate_labels(60)


@pytest.mark.parametrize(("enum_value", "expected"), [
    ("0", "36 FPS"), ("1", "48 FPS"), ("2", "72 FPS"), ("3", "144 FPS"), ("4", "Unlimited"),
])
def test_reads_frame_rate_at_144_hz(enum_value, expected):
    vsync = "0" if enum_value == "4" else "1"
    assert _read(_config(enum_value, vsync))["frame_limit"] == expected


def test_reads_legacy_60_hz_labels_without_refresh_period():
    assert _read(_config("2", period=None))["frame_limit"] == "30 FPS"
    assert _read(_config("0", period=None))["frame_limit"] == "15 FPS"


def test_options_follow_the_refresh_rate():
    assert setting_options_for_game(GAME, FRAME_LIMIT, refresh_rate=144)[1:] == [
        "36 FPS", "48 FPS", "72 FPS", "144 FPS", "Unlimited",
    ]
    assert setting_options_for_game(GAME, FRAME_LIMIT, refresh_rate=60)[1:] == [
        "15 FPS", "20 FPS", "30 FPS", "60 FPS", "Unlimited",
    ]


@pytest.mark.parametrize(("label", "enum_value"), [
    ("36 FPS", "0"), ("48 FPS", "1"), ("72 FPS", "2"), ("144 FPS", "3"),
])
def test_writes_frame_rate_at_144_hz(label, enum_value):
    result = _write_forza_xml(_config("2"), {"frame_limit": label})
    assert f'<option id="FrameRate" value="{enum_value}"/>' in result
    assert '<option id="VSync" value="1"/>' in result
    assert _read(result)["frame_limit"] == label


def test_rejects_a_label_the_display_does_not_offer():
    with pytest.raises(ValueError):
        _write_forza_xml(_config("2"), {"frame_limit": "30 FPS"})


def test_unlimited_turns_vsync_off_like_the_game():
    result = _write_forza_xml(_config("2", vsync="1"), {"frame_limit": "Unlimited"})
    assert '<option id="FrameRate" value="4"/>' in result
    assert '<option id="VSync" value="0"/>' in result
    settings = _read(result)
    assert settings["frame_limit"] == "Unlimited"
    assert settings["vsync"] == "Off"


def test_unlimited_with_vsync_on_is_rejected():
    with pytest.raises(ValueError):
        _write_forza_xml(_config("2"), {"frame_limit": "Unlimited", "vsync": "On"})


def test_vsync_on_changes_unlocked_to_the_refresh_rate_like_the_game():
    result = _write_forza_xml(_config("4", vsync="0"), {"vsync": "On"})
    assert '<option id="FrameRate" value="3"/>' in result
    assert _read(result)["frame_limit"] == "144 FPS"


def test_vsync_on_keeps_a_capped_frame_rate():
    result = _write_forza_xml(_config("2", vsync="0"), {"vsync": "On"})
    assert '<option id="FrameRate" value="2"/>' in result
