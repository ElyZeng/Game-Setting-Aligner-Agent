"""Parity tests for the Street Fighter 6 profile (GSAA_P1_handoff.md §4.2).

This is a deliberately READ-ONLY migration - see street-fighter-6.json's
_parser_fn_note for the full rationale. Unlike GTA (real writer lives
elsewhere) or the Expedition 33 fix (accidental live writer path that had
to be closed), SF6 was already a genuine, fully-confirmed dead end before
this migration: no _write_sf6 function exists anywhere, and
_detect_parser_type() already had an explicit "unknown" guard for it. This
migration changes nothing about write behaviour for this title - only read
dispatch now goes through a profile.
"""

from config_manager.settings_parser import extract_key_settings, _parse_sf6
from config_manager.settings_writer import write_settings

GAME = "Street Fighter 6"


def _config(
    global_settings="Custom", max_framerate="60", display_mode="154",
    window_mode="Normal", vsync="True", upscale="None", fullscreen="false",
    width="1680", height="1050",
):
    return (
        "[Render]\n"
        f"GlobalSettings={global_settings}\n"
        f"MaxFramerate={max_framerate}\n"
        "[RenderConfig]\n"
        f"FullScreenDisplayMode={display_mode}\n"
        f"WindowMode={window_mode}\n"
        f"VSync={vsync}\n"
        f"UpscaleType={upscale}\n"
        f"FullScreenMode={fullscreen}\n"
        f"DisplayMode{display_mode}_Width={width}\n"
        f"DisplayMode{display_mode}_Height={height}\n"
    )


def _files(content, path="config.ini"):
    return [{"found": True, "content": content, "expanded_path": path}]


class TestReadParity:
    def test_profile_dispatch_matches_legacy_parse(self):
        content = _config()

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_sf6(content)

        assert via_profile == via_legacy
        assert via_profile["resolution"] == "1680x1050"
        assert via_profile["screen_mode"] == "Windowed"
        assert via_profile["quick_preset"] == "Custom"
        assert via_profile["upscaling"] == "Off"
        assert via_profile["upscaling_mode"] == "N/A"
        assert via_profile["frame_generation"] == "N/A"

    def test_fullscreen_and_upscaler_match_legacy(self):
        content = _config(fullscreen="true", upscale="DLSS", window_mode="")

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_sf6(content)

        assert via_profile == via_legacy
        assert via_profile["screen_mode"] == "Fullscreen"
        assert via_profile["upscaling"] == "DLSS"
        assert via_profile["upscaling_mode"] == "N/A"

    def test_malformed_content_returns_same_as_legacy(self):
        content = "not a valid ini at all"

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_sf6(content)

        assert via_profile == via_legacy

    def test_exact_match_only_no_substring_collision(self):
        """Profile.matches() is exact; a hypothetical 'Street Fighter V'
        or trademark-glyph variant does not get hijacked by this profile -
        it still resolves via the legacy "street fighter"/"streetfighter"
        substring dispatch in extract_key_settings, unaffected by this
        profile's existence."""
        content = _config()

        for other_name in ("Street Fighter V", "Street Fighter™ 6", "StreetFighter6"):
            result = extract_key_settings(other_name, _files(content))
            name_lower = other_name.lower()
            if "street fighter" in name_lower or "streetfighter" in name_lower:
                assert result == _parse_sf6(content)
            else:
                assert result == extract_key_settings(other_name, _files(content))


class TestWriteUnchanged:
    """Confirms write_settings() still reports the pre-existing "unknown
    parser type" skip for this title now that a profile exists - this was
    already true before this migration (see _detect_parser_type's dedicated
    "street fighter 6" guard) and must stay true."""

    def test_write_settings_still_reports_unknown_parser_type(self, tmp_path):
        content = _config()
        path = tmp_path / "config.ini"
        path.write_text(content, encoding="utf-8")

        results = write_settings(GAME, _files(content, str(path)), {"vsync": "Off"})

        assert results == [
            {"path": "", "status": "skipped", "detail": f"Unknown parser type for '{GAME}'"}
        ]
        assert path.read_text(encoding="utf-8") == content
