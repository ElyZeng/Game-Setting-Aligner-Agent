"""Regression tests for Cyberpunk 2077 Frame Generation state handling."""

from __future__ import annotations

import json

import pytest

from config_manager.settings_parser import FRAME_GENERATION, extract_key_settings
from config_manager.settings_writer import _write_cyberpunk


def _cyberpunk_settings(frame_generation, multi_frame_generation="missing"):
    options = [{"name": "FrameGeneration", "value": frame_generation}]
    if multi_frame_generation != "missing":
        options.append({"name": "DLSS_MultiFrameGeneration", "value": multi_frame_generation})
    return json.dumps({"data": [{"group_name": "/video/display", "options": options}]})


def _parse_frame_generation(frame_generation, multi_frame_generation="missing"):
    return extract_key_settings(
        "Cyberpunk 2077",
        [{
            "found": True,
            "expanded_path": "UserSettings.json",
            "content": _cyberpunk_settings(frame_generation, multi_frame_generation),
        }],
    )[FRAME_GENERATION]


def test_off_ignores_stale_multi_frame_generation_multiplier():
    assert _parse_frame_generation(False, "x2") == "Off"


def test_on_displays_active_multi_frame_generation_multiplier():
    assert _parse_frame_generation(True, "x2") == "On / MFG: x2"


@pytest.mark.parametrize("multiplier", ["missing", None, "", "Off"])
def test_on_without_active_multi_frame_generation_multiplier_is_on(multiplier):
    assert _parse_frame_generation(True, multiplier) == "On"


def test_unknown_frame_generation_value_is_not_advertised_as_writable():
    assert _parse_frame_generation("Auto", "x2") == "N/A"


@pytest.mark.parametrize("value", ["Off", "On"])
def test_toggling_frame_generation_preserves_stored_multi_frame_multiplier(value):
    updated = json.loads(_write_cyberpunk(_cyberpunk_settings(True, "x2"), {FRAME_GENERATION: value}))
    options = updated["data"][0]["options"]
    option_values = {option["name"]: option["value"] for option in options}

    assert option_values["FrameGeneration"] is (value == "On")
    assert option_values["DLSS_MultiFrameGeneration"] == "x2"