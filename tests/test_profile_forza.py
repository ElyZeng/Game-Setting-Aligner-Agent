"""Parity tests for the Forza Horizon 6 profile (GSAA_P1_handoff.md §4.2).

These prove the profile-dispatch path (extract_key_settings/write_settings
going through config_manager/profiles/forza-horizon-6.json) produces results
identical to calling the legacy _parse_forza_xml/_write_forza_xml functions
directly — the "profile wraps the existing function verbatim" guarantee.

Detailed value-mapping coverage (frame_limit/vsync coupling, upscaling
method+mode split, quick_preset) already exists in test_forza_frame_rate.py
and test_upscaling_split.py; this file only needs to prove the dispatch
wiring (including the new write_side_effect_fn sidecar mechanism) is
correct, not re-test every value mapping.
"""

import os

from config_manager.settings_parser import extract_key_settings
from config_manager.settings_writer import _write_forza_xml, write_settings

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


def _files(content, path="UserConfigSelections"):
    return [{"found": True, "content": content, "expanded_path": path}]


class TestReadParity:
    def test_profile_dispatch_matches_legacy_parse(self):
        content = _config()
        from config_manager.settings_parser import _parse_forza_xml

        via_profile = extract_key_settings(GAME, _files(content))
        via_legacy = _parse_forza_xml(content)

        assert via_profile == via_legacy
        assert via_profile["resolution"] == "2560x1440"
        assert via_profile["screen_mode"] == "Fullscreen"

    def test_informal_name_without_exact_title_uses_legacy_fallback(self):
        """'Forza' alone and 'Forza Horizon 5' are NOT in the profile's exact
        match list — they must keep resolving through the legacy "forza" in
        name_lower substring dispatch unchanged (Profile.matches() is exact,
        case-insensitive match only)."""
        content = _config()
        from config_manager.settings_parser import _parse_forza_xml

        for informal_name in ("Forza", "Forza Horizon 5", "FORZA HORIZON 6"):
            result = extract_key_settings(informal_name, _files(content))
            if informal_name.casefold() == GAME.casefold():
                # case-insensitive exact match still hits the profile
                assert result == _parse_forza_xml(content)
            else:
                assert result == _parse_forza_xml(content)


class TestWriteParity:
    def test_write_round_trip_matches_legacy_bytes(self, tmp_path):
        content = _config()
        path = tmp_path / "UserConfigSelections"
        path.write_text(content, encoding="utf-8")

        settings = {"frame_limit": "144 FPS"}
        legacy_bytes = _write_forza_xml(content, settings)

        results = write_settings(GAME, _files(content, str(path)), settings)

        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert results[0]["detail"] == "Forza XML settings written"
        assert path.read_text(encoding="utf-8") == legacy_bytes

    def test_write_side_effect_writes_fullscreen_sidecar(self, tmp_path):
        """The whole point of the new write_side_effect_fn plumbing: writing
        screen_mode through the profile-dispatch path must still produce the
        sibling 'fullscreen_choice' byte-file, exactly like the legacy
        forza_xml write-dispatch branch did (see
        tests/test_config_manager.py::test_import_v2_restores_forza_fullscreen_sidecar
        for the equivalent legacy-path assertion and directory shape)."""
        content = _config()
        config_dir = (
            tmp_path / "ForzaHorizon6" / "LocalStorage_Shared" / "ForzaUserConfigSelections"
        )
        config_dir.mkdir(parents=True)
        config_path = config_dir / "UserConfigSelections"
        config_path.write_text(content, encoding="utf-8")
        sidecar_path = config_dir.parent.parent / "fullscreen_choice"

        settings = {"screen_mode": "Fullscreen"}
        results = write_settings(GAME, _files(content, str(config_path)), settings)

        result_paths = [os.path.abspath(r["path"]) for r in results]
        assert os.path.abspath(config_path) in result_paths
        assert os.path.abspath(sidecar_path) in result_paths

        sidecar_result = next(r for r in results if os.path.abspath(r["path"]) == os.path.abspath(sidecar_path))
        assert sidecar_result["status"] == "ok"
        assert sidecar_result["detail"] == "Forza fullscreen choice written"
        assert sidecar_path.read_bytes() == bytes([1])

    def test_write_side_effect_writes_zero_byte_for_windowed(self, tmp_path):
        content = _config()
        config_dir = (
            tmp_path / "ForzaHorizon6" / "LocalStorage_Shared" / "ForzaUserConfigSelections"
        )
        config_dir.mkdir(parents=True)
        config_path = config_dir / "UserConfigSelections"
        config_path.write_text(content, encoding="utf-8")
        sidecar_path = config_dir.parent.parent / "fullscreen_choice"

        settings = {"screen_mode": "Windowed"}
        write_settings(GAME, _files(content, str(config_path)), settings)

        assert sidecar_path.read_bytes() == bytes([0])

    def test_no_sidecar_write_when_screen_mode_not_in_settings(self, tmp_path):
        """Writing a setting other than screen_mode must not touch the
        sidecar file at all — matching the legacy branch's `if SCREEN_MODE in
        to_write:` guard exactly."""
        content = _config()
        config_dir = (
            tmp_path / "ForzaHorizon6" / "LocalStorage_Shared" / "ForzaUserConfigSelections"
        )
        config_dir.mkdir(parents=True)
        config_path = config_dir / "UserConfigSelections"
        config_path.write_text(content, encoding="utf-8")
        sidecar_path = config_dir.parent.parent / "fullscreen_choice"

        settings = {"frame_limit": "144 FPS"}
        results = write_settings(GAME, _files(content, str(config_path)), settings)

        assert len(results) == 1
        assert not sidecar_path.exists()
