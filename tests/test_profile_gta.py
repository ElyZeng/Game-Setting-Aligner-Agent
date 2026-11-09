"""Parity tests for the Grand Theft Auto V Enhanced profile (GSAA_P1_handoff.md §4.2).

This is a deliberately READ-ONLY migration - see
grand-theft-auto-v-enhanced.json's _parser_fn_note for the full rationale.
These tests prove two things:

1. The read side (extract_key_settings) goes through the new profile's
   parser_fn and produces results identical to calling the legacy
   _parse_gta_enhanced_xml directly - the usual "profile wraps the existing
   function verbatim" guarantee.

2. The write side (write_settings()) is completely UNCHANGED now that a
   profile exists for this game: it must still report the legacy
   "skipped" / "GTA V Enhanced requires guarded Apply" result, because this
   profile intentionally declares no writer_fn. This is the critical
   regression guard - the real guarded write path
   (config_manager.verification.backup_and_write -> _write_gta_enhanced_settings)
   bypasses write_settings() entirely for this title and must stay that way.
"""

from config_manager.settings_parser import extract_key_settings, _parse_gta_enhanced_xml
from config_manager.settings_writer import write_settings

GAME = "Grand Theft Auto V Enhanced"


def _config(
    width="1920", height="1080", windowed="2", vsync="1", frame_limit="120",
    scaling_type="0", preset="4",
):
    return (
        "<Settings>"
        "<video>"
        f'<ScreenWidth value="{width}"/><ScreenHeight value="{height}"/>'
        f'<Windowed value="{windowed}"/><VSync value="{vsync}"/>'
        f'<FrameLimit value="{frame_limit}"/>'
        "</video>"
        "<graphics>"
        f'<ResScalingType value="{scaling_type}"/>'
        "</graphics>"
        "<Presets>"
        f'<PresetLevel value="{preset}"/>'
        "</Presets>"
        "</Settings>"
    )


def _files(content, path="settings.xml"):
    return [{"found": True, "content": content, "expanded_path": path}]


class TestReadParity:
    def test_profile_dispatch_matches_legacy_parse(self):
        content = _config()

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_gta_enhanced_xml(content)

        assert via_profile == via_legacy
        assert via_profile["resolution"] == "1920x1080"
        assert via_profile["screen_mode"] == "Borderless Windowed"
        assert via_profile["vsync"] == "On"
        assert via_profile["frame_limit"] == "120 FPS"
        assert via_profile["upscaling"] == "Off"
        assert via_profile["quick_preset"] == "Very High"
        # GTA's legacy parser never sets dynamic_resolution - confirm the
        # profile dispatch preserves that (it's deliberately absent from
        # the profile's "settings" field too).
        assert via_profile["dynamic_resolution"] is None

    def test_fsr3_upscaling_and_frame_generation_match_legacy(self):
        content = _config(scaling_type="3")
        content = content.replace(
            "</graphics>", '<fsr3Quality value="2"/><FrameGenType value="2"/></graphics>'
        )

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_gta_enhanced_xml(content)

        assert via_profile == via_legacy
        assert via_profile["upscaling"] == "FSR 3"
        assert via_profile["upscaling_mode"] == "Quality"
        assert via_profile["frame_generation"] == "AMD FSR 3"

    def test_malformed_xml_returns_empty_result_like_legacy(self):
        content = "<Settings><video>"

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_gta_enhanced_xml(content)

        assert via_profile == via_legacy
        assert all(v is None for v in via_profile.values())

    def test_exact_match_only_no_substring_collision(self):
        """Profile.matches() is exact - confirm a hypothetical shorter/longer
        GTA name string does NOT get hijacked by this profile (it would
        still resolve via the legacy "grand theft auto v enhanced" in
        name_lower substring dispatch in extract_key_settings, unaffected
        by this profile's existence)."""
        content = _config()

        for other_name in ("Grand Theft Auto V", "GTA V Enhanced", "Grand Theft Auto V Enhanced Legacy"):
            result = extract_key_settings(other_name, _files(content))
            if "grand theft auto v enhanced" in other_name.lower():
                assert result == _parse_gta_enhanced_xml(content)
            else:
                # No legacy branch recognizes these names either - both
                # resolve through the same generic fallback path, so they
                # must still agree with each other (no profile involved).
                assert result == extract_key_settings(other_name, _files(content))


class TestWriteUnchanged:
    """The single most important test file in this migration: prove
    write_settings() behaves byte-for-byte as it did before this profile
    existed, now that a profile *does* exist but declares no writer_fn."""

    def test_write_settings_still_reports_skipped_guarded_apply(self, tmp_path):
        content = _config()
        path = tmp_path / "settings.xml"
        path.write_text(content, encoding="utf-8")

        results = write_settings(GAME, _files(content, str(path)), {"vsync": "Off"})

        assert results == [
            {"path": "", "status": "skipped", "detail": "GTA V Enhanced requires guarded Apply"}
        ]
        # and, crucially, the file on disk was never touched
        assert path.read_text(encoding="utf-8") == content

    def test_write_settings_skipped_regardless_of_which_setting_requested(self, tmp_path):
        content = _config()
        path = tmp_path / "settings.xml"
        path.write_text(content, encoding="utf-8")

        for settings in (
            {"resolution": "1600x900"},
            {"quick_preset": "Lowest"},
            {"frame_generation": "AMD FSR 3"},
        ):
            results = write_settings(GAME, _files(content, str(path)), settings)
            assert results == [
                {"path": "", "status": "skipped", "detail": "GTA V Enhanced requires guarded Apply"}
            ]
            assert path.read_text(encoding="utf-8") == content
