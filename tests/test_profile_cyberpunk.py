"""Parity tests for the Cyberpunk 2077 profile (GSAA_P1_handoff.md §4.2).

These prove the profile-dispatch path (extract_key_settings/write_settings
going through config_manager/profiles/cyberpunk-2077.json) produces results
identical to calling the legacy _parse_cyberpunk/_write_cyberpunk functions
directly — the "profile wraps the existing function verbatim" guarantee.

Detailed value-mapping coverage (resolution/index bookkeeping, vsync
refresh-rate options, upscaling method+mode split, frame generation,
quick_preset member rewrites) already exists in test_cyberpunk_231.py and
test_cyberpunk_frame_generation.py; this file only needs to prove the
dispatch wiring is correct, not re-test every value mapping.
"""

import json

from config_manager.settings_parser import extract_key_settings, _parse_cyberpunk
from config_manager.settings_writer import _write_cyberpunk, write_settings

GAME = "Cyberpunk 2077"


def _config(options, group_name="/video/display"):
    return json.dumps({"data": [{"group_name": group_name, "options": options}]})


def _files(content, path="UserSettings.json"):
    return [{"found": True, "content": content, "expanded_path": path}]


class TestReadParity:
    def test_profile_dispatch_matches_legacy_parse(self):
        content = _config([
            {"name": "Resolution", "value": "2560x1440"},
            {"name": "WindowMode", "value": "BorderlessWindowed", "index": 1},
            {"name": "VSync", "value": "UI-Settings-Video-QualitySetting-Off"},
            {"name": "MaximumFPS_OnOff", "value": True},
            {"name": "MaximumFPS_Value", "value": 114},
        ])

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_cyberpunk(content)

        assert via_profile == via_legacy
        assert via_profile["resolution"] == "2560x1440"
        assert via_profile["screen_mode"] == "Borderless Windowed"
        assert via_profile["frame_limit"] == "114 FPS"

    def test_informal_variant_name_without_exact_title_uses_legacy_fallback(self):
        """'Cyberpunk 2077: Phantom Liberty' is NOT in the profile's exact
        match list (no evidence any such DLC-suffixed variant is handled
        differently in this checkout) — it must keep resolving through the
        legacy "cyberpunk" in name_lower substring dispatch unchanged
        (Profile.matches() is exact, case-insensitive match only)."""
        content = _config([{"name": "Resolution", "value": "1920x1080"}])

        result = extract_key_settings("Cyberpunk 2077: Phantom Liberty", _files(content))

        assert result == _parse_cyberpunk(content)


class TestWriteParity:
    def test_write_round_trip_matches_legacy_bytes(self, tmp_path):
        content = _config([
            {"name": "Resolution", "value": "2560x1440", "index": 21},
            {"name": "MaximumFPS_OnOff", "value": False},
            {"name": "MaximumFPS_Value", "value": 60},
        ])
        path = tmp_path / "UserSettings.json"
        path.write_text(content, encoding="utf-8")

        settings = {"resolution": "1920x1080", "frame_limit": "60 FPS"}
        legacy_bytes = _write_cyberpunk(content, settings)

        results = write_settings(GAME, _files(content, str(path)), settings)

        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert results[0]["detail"] == "Cyberpunk settings written"
        assert path.read_text(encoding="utf-8") == legacy_bytes
        assert json.loads(legacy_bytes)["data"][0]["options"][0]["value"] == "1920x1080"

    def test_quick_preset_write_round_trip_matches_legacy(self, tmp_path):
        """Quick preset writes also rewrite ~32 member settings across
        multiple groups — the single most interdependent part of Cyberpunk's
        write logic. Prove the profile dispatch reproduces it byte-for-byte
        rather than only checking the simple single-field case above."""
        content = json.dumps({
            "data": [
                {"group_name": "/graphics/presets", "options": [
                    {"name": "QuickPresets", "value": "Low", "index": 1},
                    {"name": "ResolutionScaling", "value": "DLSS"},
                ]},
                {"group_name": "/graphics/advanced", "options": [
                    {"name": "AmbientOcclusion", "value": "Low"},
                ]},
            ],
        })
        path = tmp_path / "UserSettings.json"
        path.write_text(content, encoding="utf-8")

        settings = {"quick_preset": "Ultra"}
        legacy_bytes = _write_cyberpunk(content, settings)

        results = write_settings(GAME, _files(content, str(path)), settings)

        assert results[0]["status"] == "ok"
        assert path.read_text(encoding="utf-8") == legacy_bytes
        written = json.loads(legacy_bytes)
        presets_group = next(g for g in written["data"] if g["group_name"] == "/graphics/presets")
        quick_opt = next(o for o in presets_group["options"] if o["name"] == "QuickPresets")
        assert quick_opt["value"] == "Ultra"
        # the upscaler must be left alone by a preset write, per legacy behavior
        resolution_scaling = next(o for o in presets_group["options"] if o["name"] == "ResolutionScaling")
        assert resolution_scaling["value"] == "DLSS"
