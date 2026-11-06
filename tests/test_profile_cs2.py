"""Parity tests for the Counter-Strike 2 profile migration (P1 step 4).

CS2 is the first game whose profile needs `parse_mode: "multi_file"`
(see config_manager/profiles/loader.py Profile.parse_multi and the
profile-first dispatch block in settings_parser.extract_key_settings):
resolution/screen_mode/vsync/upscaling live in cs2_video.txt, but
frame_limit (fps_max) only lives in a separate convars file, and the legacy
_parse_cs2() has always taken the whole config-file list for that reason.

Writing only ever touches cs2_video.txt, so writer_fn still goes through the
ordinary single-"main"-file write dispatch path, unchanged from the other
profiles.

As with tests/test_profile_f1_25.py, detailed settings-value coverage
already exists in tests/test_upscaling_split.py; this file only proves the
new profile-dispatch wiring (including the multi-file read path) is correct.
"""

from config_manager.settings_parser import _parse_cs2, extract_key_settings
from config_manager.settings_writer import _write_cs2_video, write_settings

CS2_VIDEO = """"video.cfg"
{
\t"setting.defaultres"\t\t"3840"
\t"setting.defaultresheight"\t\t"2160"
\t"setting.refreshrate_numerator"\t\t"0"
\t"setting.refreshrate_denominator"\t\t"0"
\t"setting.fullscreen"\t\t"0"
\t"setting.mat_vsync"\t\t"0"
\t"setting.monitor_index"\t\t"0"
\t"Version"\t\t"16"
\t"VendorID"\t\t"32902"
\t"DeviceID"\t\t"57867"
\t"setting.cpu_level"\t\t"3"
\t"setting.gpu_mem_level"\t\t"3"
\t"setting.gpu_level"\t\t"3"
\t"setting.knowndevice"\t\t"0"
\t"setting.nowindowborder"\t\t"1"
\t"setting.fullscreen_min_on_focus_loss"\t\t"1"
\t"setting.high_dpi"\t\t"0"
\t"setting.coop_fullscreen"\t\t"0"
\t"Autoconfig"\t\t"2"
\t"setting.shaderquality"\t\t"1"
\t"setting.r_texturefilteringquality"\t\t"2"
\t"setting.msaa_samples"\t\t"4"
\t"setting.r_csgo_cmaa_enable"\t\t"0"
\t"setting.videocfg_shadow_quality"\t\t"2"
\t"setting.videocfg_dynamic_shadows"\t\t"1"
\t"setting.videocfg_texture_detail"\t\t"2"
\t"setting.videocfg_particle_detail"\t\t"2"
\t"setting.videocfg_ao_detail"\t\t"2"
\t"setting.videocfg_hdr_detail"\t\t"-1"
\t"setting.videocfg_fsr_detail"\t\t"2"
}
"""

CS2_CONVARS = """"machine_convars"
{
\t"fps_max"\t\t"400.000000"
}
"""


def _config(content: str, path: str):
    return {"found": True, "content": content, "expanded_path": path}


class TestReadParity:
    def test_video_file_only_matches_legacy(self):
        files = [_config(CS2_VIDEO, "cs2_video.txt")]
        via_profile = extract_key_settings("Counter-Strike 2", files)
        readable = [c for c in files if c.get("content") and c.get("found")]
        via_legacy = _parse_cs2(readable)
        assert via_profile == via_legacy
        assert via_profile["resolution"] == "3840x2160"
        assert via_profile["screen_mode"] == "Borderless Windowed"
        assert via_profile["vsync"] == "Off"
        assert via_profile["upscaling"] == "FSR"
        assert via_profile["upscaling_mode"] == "Quality"
        # Not in cs2_video.txt — unmatched without the convars file.
        assert via_profile["frame_limit"] is None

    def test_video_plus_convars_fills_in_frame_limit(self):
        """This is the whole point of parse_mode='multi_file': frame_limit
        only shows up once the convars file is also passed through."""
        files = [
            _config(CS2_VIDEO, "cs2_video.txt"),
            _config(CS2_CONVARS, "cs2_machine_convars.vcfg"),
        ]
        via_profile = extract_key_settings("Counter-Strike 2", files)
        readable = [c for c in files if c.get("content") and c.get("found")]
        via_legacy = _parse_cs2(readable)
        assert via_profile == via_legacy
        assert via_profile["frame_limit"] == "400 FPS"

    def test_informal_name_without_exact_title_uses_legacy_fallback(self):
        """"CS2" alone (not the exact canonical "Counter-Strike 2") is not in
        this profile's match list, so it must still resolve via the legacy
        substring dispatch ("cs2" in name_lower), unchanged."""
        files = [_config(CS2_VIDEO, "cs2_video.txt")]
        via_dispatch = extract_key_settings("CS2", files)
        readable = [c for c in files if c.get("content") and c.get("found")]
        assert via_dispatch == _parse_cs2(readable)


class TestWriteParity:
    def test_write_round_trip_matches_legacy_bytes(self, tmp_path):
        settings = {
            "resolution": "2560x1440",
            "screen_mode": "Fullscreen",
            "vsync": "On",
            "upscaling": "FSR",
            "upscaling_mode": "Balanced",
        }
        expected = _write_cs2_video(CS2_VIDEO, settings)

        path = tmp_path / "cs2_video.txt"
        path.write_text(CS2_VIDEO, encoding="utf-8")
        results = write_settings(
            "Counter-Strike 2",
            [{"found": True, "content": CS2_VIDEO, "expanded_path": str(path)}],
            settings,
        )

        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert results[0]["detail"] == "CS2 video settings written"
        assert path.read_text(encoding="utf-8") == expected
