"""Parity tests for the Black Myth: Wukong Benchmark Tool profile migration
(P1 step 2 — second game migrated after the retail Black Myth profile).

Same purpose as tests/test_profile_black_myth.py: compare the profile-dispatch
path against the pre-P1 functions (_parse_black_myth/_write_black_myth_ini
called with benchmark=True) on the same fixture content — this exists to
catch the dispatch wiring itself breaking, not the underlying parsing logic
(already covered in tests/test_config_exporter.py and
tests/test_black_myth_writer.py).

Also guards the reverse direction of the exact-match safety check already
covered for the retail game: the Benchmark Tool's own profile must not widen
to also swallow the retail "Black Myth: Wukong" title.
"""

from config_manager.settings_parser import _parse_black_myth, extract_key_settings
from config_manager.settings_writer import _write_black_myth_ini, write_settings

BENCHMARK_BORDERLESS = """[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=1920
ResolutionSizeY=1080
LastUserConfirmedResolutionSizeX=1600
LastUserConfirmedResolutionSizeY=900
LastUserConfirmedDesiredScreenWidth=1516
LastUserConfirmedDesiredScreenHeight=853
UISettingData=(("ImageQuality", "853"),("ScreenMode", "1"),("ScreenRatio", "2"),("ScreenResolution", "1"),("WindowFullImageQuality", "833333"),("Vsync", "1"),("SuperResolutionSampling", "3"),("InsertFrame", "1"),("QualityLevel", "5"))
"""

BENCHMARK_FULL = """[ScalabilityGroups]
sg.ResolutionQuality=65
sg.ViewDistanceQuality=4
sg.AntiAliasingQuality=4
sg.ShadowQuality=4
sg.GlobalIlluminationQuality=4
sg.RayTracingQuality=0
sg.ReflectionQuality=4
sg.PostProcessQuality=4
sg.TextureQuality=4
sg.EffectsQuality=4
sg.FoliageQuality=4
sg.ShadingQuality=4
[/Script/GSGameSettings.GSGameUserSettings]
bUseVSync=True
FrameRateLimit=120.000000
ResolutionSizeX=1920
ResolutionSizeY=1080
LastUserConfirmedResolutionSizeX=1920
LastUserConfirmedResolutionSizeY=1080
FullscreenMode=1
LastConfirmedFullscreenMode=1
PreferredFullscreenMode=1
UISettingData=(("ScreenMode", "1"),("WindowFullImageQuality", "1000000"),("Vsync", "1"),("SuperResolutionSampling", "3"),("InsertFrame", "1"),("QualityLevel", "5"))
"""


def _files(content, filename="GameUserSettings.ini"):
    return [{"found": True, "content": content, "expanded_path": filename}]


class TestReadParity:
    def test_borderless_resolution(self):
        via_profile = extract_key_settings("Black Myth: Wukong Benchmark Tool", _files(BENCHMARK_BORDERLESS))
        via_legacy = _parse_black_myth(BENCHMARK_BORDERLESS, benchmark=True)
        assert via_profile == via_legacy
        assert via_profile["resolution"] == "1600x900"
        assert via_profile["screen_mode"] == "Borderless Windowed"
        assert via_profile["upscaling"] == "TSR"
        assert via_profile["frame_generation"] == "On"

    def test_full_fixture(self):
        via_profile = extract_key_settings("Black Myth: Wukong Benchmark Tool", _files(BENCHMARK_FULL))
        via_legacy = _parse_black_myth(BENCHMARK_FULL, benchmark=True)
        assert via_profile == via_legacy

    def test_retail_variant_not_hijacked_by_benchmark_profile(self):
        """Reverse of the guard in test_profile_black_myth.py: the Benchmark
        Tool's own exact-match profile must not also swallow the retail
        "Black Myth: Wukong" title."""
        retail_content = 'UISettingData=(("SuperResolutionSampling", "0"),("InsertFrame", "1"))\n'
        via_dispatch = extract_key_settings("Black Myth: Wukong", _files(retail_content))
        # Retail (benchmark=False) mapping: "0" -> FSR3, not benchmark's "FSR".
        assert via_dispatch["upscaling"] == "FSR3"
        assert via_dispatch["frame_generation"] == "Off"


class TestWriteParity:
    def test_write_round_trip_matches_legacy_bytes(self, tmp_path):
        settings = {
            "resolution": "1600x900",
            "screen_mode": "Windowed",
            "vsync": "Off",
            "frame_limit": "60 FPS",
            "upscaling": "FSR",
            "upscaling_mode": "50%",
            "frame_generation": "Off",
            "quick_preset": "High",
        }
        expected = _write_black_myth_ini(BENCHMARK_FULL, settings, benchmark=True)

        path = tmp_path / "GameUserSettings.ini"
        path.write_text(BENCHMARK_FULL, encoding="utf-8")
        results = write_settings(
            "Black Myth: Wukong Benchmark Tool",
            [{"found": True, "content": BENCHMARK_FULL, "expanded_path": str(path)}],
            settings,
        )

        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert results[0]["detail"] == "Black Myth settings written"
        assert path.read_text(encoding="utf-8") == expected
