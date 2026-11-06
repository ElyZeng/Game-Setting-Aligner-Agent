"""Parity tests for the Black Myth: Wukong profile migration (P1 step 1).

Per the handoff (§4.2): "新路徑與舊函式對同一份 fixture 的讀值和寫出 bytes 完全相同"
— these compare the profile-dispatch path (extract_key_settings /
write_settings going through config_manager.profile_dispatch) against the
pre-P1 functions (_parse_black_myth / _write_black_myth_ini) called directly,
on the same fixture content. They must be identical, because the profile's
parser_fn/writer_fn are thin wrappers around those exact functions (see
config_manager/profile_functions.py) — this test exists to catch the dispatch
wiring itself breaking, not the underlying parsing logic (which already has
its own coverage in tests/test_config_exporter.py).

Retail only: "Black Myth: Wukong Benchmark Tool" is a different, not-yet-
migrated profile and must keep going through the legacy dispatch.
"""

from config_manager.settings_parser import _parse_black_myth, extract_key_settings
from config_manager.settings_writer import _write_black_myth_ini, write_settings

RETAIL_WINDOWED = """[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=1600
ResolutionSizeY=900
LastUserConfirmedResolutionSizeX=1600
LastUserConfirmedResolutionSizeY=900
FullscreenMode=2
LastUserConfirmedDesiredScreenWidth=1600
LastUserConfirmedDesiredScreenHeight=900
UISettingData=(("ScreenMode", "2"),("ScreenRatio", "0"),("ScreenResolution", "1"),("WindowFullImageQuality", "0"),("ImageQuality", "1080"))
"""

RETAIL_UI_SETTINGS = """[/Script/Engine.GameUserSettings]
bUseDynamicResolution=False
ResolutionSizeX=3840
ResolutionSizeY=2160
FullscreenMode=1
FrameRateLimit=0.000000
UISettingData=(("ScreenMode", "1"),("Vsync", "0"),("Dlss", "1"),("SuperResolutionSampling", "1"),("InsertFrame", "1"),("QualityLevel", "1"))
"""


def _files(content, filename="GameUserSettings.ini"):
    return [{"found": True, "content": content, "expanded_path": filename}]


class TestReadParity:
    def test_retail_windowed(self):
        via_profile = extract_key_settings("Black Myth: Wukong", _files(RETAIL_WINDOWED))
        via_legacy = _parse_black_myth(RETAIL_WINDOWED, benchmark=False)
        assert via_profile == via_legacy
        assert via_profile["resolution"] == "1600x900"
        assert via_profile["screen_mode"] == "Windowed"

    def test_retail_ui_settings(self):
        via_profile = extract_key_settings("Black Myth: Wukong", _files(RETAIL_UI_SETTINGS))
        via_legacy = _parse_black_myth(RETAIL_UI_SETTINGS, benchmark=False)
        assert via_profile == via_legacy
        assert via_profile["upscaling"] == "XeSS"
        assert via_profile["frame_generation"] == "Auto"
        assert via_profile["quick_preset"] == "Low"

    def test_benchmark_variant_not_hijacked_by_profile(self):
        """Guards against the profile's exact-match accidentally widening to
        substring match and swallowing the not-yet-migrated Benchmark Tool."""
        benchmark_content = 'UISettingData=(("SuperResolutionSampling", "0"),("InsertFrame", "1"))\n'
        via_dispatch = extract_key_settings(
            "Black Myth: Wukong Benchmark Tool", _files(benchmark_content)
        )
        assert via_dispatch["upscaling"] == "FSR"
        assert via_dispatch["frame_generation"] == "On"


class TestWriteParity:
    def test_write_round_trip_matches_legacy_bytes(self, tmp_path):
        settings = {
            "resolution": None,
            "screen_mode": "Fullscreen",
            "vsync": "On",
            "frame_limit": None,
            "dynamic_resolution": None,
            "upscaling": None,
            "upscaling_mode": None,
            "frame_generation": None,
            "quick_preset": "High",
        }
        expected = _write_black_myth_ini(RETAIL_WINDOWED, settings, benchmark=False)

        path = tmp_path / "GameUserSettings.ini"
        path.write_text(RETAIL_WINDOWED, encoding="utf-8")
        results = write_settings(
            "Black Myth: Wukong",
            [{"found": True, "content": RETAIL_WINDOWED, "expanded_path": str(path)}],
            settings,
        )

        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert results[0]["detail"] == "Black Myth settings written"
        assert path.read_text(encoding="utf-8") == expected
