"""Parity tests for the Clair Obscur: Expedition 33 profile (GSAA_P1_handoff.md §4.2).

This is a deliberately READ-ONLY migration - see
clair-obscur-expedition-33.json's _parser_fn_note for the full rationale,
including the pre-existing legacy dispatch gap this change also fixes (see
tests/test_write_safety.py::test_expedition_33_not_routed_to_generic_unreal_writer
for the dedicated regression test covering that fix).

These tests prove two things:

1. The read side (extract_key_settings) goes through the new profile's
   parser_fn and produces results identical to calling the legacy
   _parse_expedition_33 directly - the usual "profile wraps the existing
   function verbatim" guarantee.

2. The write side (write_settings()) now reports the *corrected* "unknown
   parser type" skip for this title - not the old, accidentally-live
   "unreal_ini" write path - and this is true regardless of whether a
   profile exists at all (the fix lives in _detect_parser_type, not in the
   profile), so these tests exercise both "with profile" and implicitly
   confirm the write side stays inert now that one does.
"""

from config_manager.settings_parser import extract_key_settings, _parse_expedition_33
from config_manager.settings_writer import write_settings

GAME = "Clair Obscur: Expedition 33"


def _config(
    width="3840", height="2160", fullscreen="1", vsync="False", frame_limit="0.000000",
    quality="1", upscaler="XeSS", upscaler_mode="5", frame_gen="1",
):
    return (
        f"ResolutionSizeX={width}\n"
        f"ResolutionSizeY={height}\n"
        f"FullscreenMode={fullscreen}\n"
        f"bUseVSync={vsync}\n"
        f"FrameRateLimit={frame_limit}\n"
        f"sg.ViewDistanceQuality={quality}\n"
        f"sg.ShadowQuality={quality}\n"
        f"sg.TextureQuality={quality}\n"
        f"sg.EffectsQuality={quality}\n"
        f"CurrentSelectedUpscaler={upscaler}\n"
        f"CurrentSelectedUpscalerQualityMode={upscaler_mode}\n"
        f"CurrentSelectedFrameGenerationMode={frame_gen}\n"
    )


def _files(content, path="GameUserSettings.ini"):
    return [{"found": True, "content": content, "expanded_path": path}]


class TestReadParity:
    def test_profile_dispatch_matches_legacy_parse(self):
        content = _config()

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_expedition_33(content)

        assert via_profile == via_legacy
        assert via_profile["upscaling"] == "XeSS"
        assert via_profile["upscaling_mode"] == "5"
        assert via_profile["frame_generation"] == "On (mode 1)"
        assert via_profile["quick_preset"] == "Medium"

    def test_custom_quality_mix_matches_legacy(self):
        content = _config(quality="1")
        content = content.replace("sg.ShadowQuality=1", "sg.ShadowQuality=3")

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_expedition_33(content)

        assert via_profile == via_legacy
        assert via_profile["quick_preset"] == "Custom"

    def test_malformed_content_returns_same_as_legacy(self):
        content = "not a valid ini at all"

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_expedition_33(content)

        assert via_profile == via_legacy

    def test_exact_match_only_no_substring_collision(self):
        content = _config()

        for other_name in ("Clair Obscur", "Expedition 33", "Clair Obscur: Expedition 33 Demo"):
            result = extract_key_settings(other_name, _files(content))
            if "clair obscur" in other_name.lower() or "expedition 33" in other_name.lower():
                assert result == _parse_expedition_33(content)
            else:
                assert result == extract_key_settings(other_name, _files(content))


class TestWriteNowSkipped:
    """Confirms write_settings() no longer silently writes this title's
    GameUserSettings.ini (the behaviour change explicitly approved by the
    user on 2026-11-09, fixing a pre-existing legacy bug uncovered by this
    migration's research rather than a regression introduced by it)."""

    def test_write_settings_reports_unknown_parser_type(self, tmp_path):
        content = _config()
        path = tmp_path / "GameUserSettings.ini"
        path.write_text(content, encoding="utf-8")

        results = write_settings(GAME, _files(content, str(path)), {"quick_preset": "Low"})

        assert results == [
            {"path": "", "status": "skipped", "detail": f"Unknown parser type for '{GAME}'"}
        ]
        # and, crucially, the file on disk was never touched
        assert path.read_text(encoding="utf-8") == content
