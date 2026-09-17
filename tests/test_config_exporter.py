"""Tests for config_manager.config_exporter module."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager.config_exporter import ConfigExporter, _MAX_FILE_BYTES, _try_read_file
from config_manager.anonymizer import anonymize_package


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeGame:
    """Minimal game object compatible with ConfigExporter.export()."""

    def __init__(self, name: str, install_path: str = "", platform: str = "Steam") -> None:
        self.name = name
        self.install_path = install_path
        self.platform = platform


def _make_wiki_mock(raw_paths=None, expanded_paths=None, error=None):
    """Return a mock wiki client whose get_config_info() returns given values."""
    mock = MagicMock()
    mock.get_config_info.return_value = {
        "page_title": "FakeGame",
        "url": "https://www.pcgamingwiki.com/wiki/FakeGame",
        "raw_paths": raw_paths or [],
        "expanded_paths": expanded_paths or [],
        "error": error,
    }
    return mock


# ---------------------------------------------------------------------------
# _try_read_file tests
# ---------------------------------------------------------------------------

class TestTryReadFile:
    def test_reads_existing_file(self, tmp_path):
        cfg = tmp_path / "settings.cfg"
        cfg.write_text("setting=1\nresolution=1080p", encoding="utf-8")
        result = _try_read_file(str(cfg))

        assert result["found"] is True
        assert result["content"] == "setting=1\nresolution=1080p"
        assert result["truncated"] is False
        assert result["error"] is None


class TestAnonymizer:
    def test_anonymizes_paths_ids_and_sensitive_lines(self):
        package = {
            "path": r"C:\Users\Alice\AppData\Local\Steam\userdata\123456\730\cfg",
            "config_files": [{"content": '"accountid" "123456"\npassword=secret'}],
            "api_token": "secret-value",
        }

        result = anonymize_package(package)
        text = json.dumps(result, ensure_ascii=False)

        assert "Alice" not in text
        assert "123456" not in text
        assert "secret-value" not in text
        assert result["privacy"]["anonymized"] is True

    def test_preserves_non_sensitive_settings(self):
        result = anonymize_package({"parsed_settings": {"resolution": "1920x1080"}})

        assert result["parsed_settings"]["resolution"] == "1920x1080"

    def test_missing_file_returns_not_found(self, tmp_path):
        result = _try_read_file(str(tmp_path / "nonexistent.cfg"))

        assert result["found"] is False
        assert result["error"] == "path_not_found"
        assert result["content"] is None

    def test_truncates_large_file(self, tmp_path):
        large_file = tmp_path / "big.cfg"
        # Write slightly more than the limit
        large_file.write_bytes(b"x" * (_MAX_FILE_BYTES + 100))
        result = _try_read_file(str(large_file))

        assert result["found"] is True
        assert result["truncated"] is True
        assert result["content"] is not None
        assert len(result["content"].encode("utf-8")) <= _MAX_FILE_BYTES

    def test_expanded_path_is_recorded(self, tmp_path):
        cfg = tmp_path / "config.ini"
        cfg.write_text("[s]\nk=v", encoding="utf-8")
        result = _try_read_file(str(cfg))

        assert result["expanded_path"] == str(cfg)

    def test_file_within_size_limit_not_truncated(self, tmp_path):
        cfg = tmp_path / "small.json"
        cfg.write_text('{"key": "value"}', encoding="utf-8")
        result = _try_read_file(str(cfg))

        assert result["truncated"] is False


# ---------------------------------------------------------------------------
# ConfigExporter tests
# ---------------------------------------------------------------------------

class TestConfigExporterNoWiki:
    def test_export_creates_json_file(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("MyGame", "/games/mygame")], output)

        assert os.path.isfile(output)

    def test_export_format_version(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("MyGame")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == ConfigExporter.FORMAT_VERSION

    def test_export_game_entry_structure(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("MyGame", "/games/mygame", "Steam")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        assert "MyGame" in data["games"]
        game = data["games"]["MyGame"]
        assert game["detected_install_path"] == "/games/mygame"
        assert game["platform"] == "Steam"
        assert game["pcgamingwiki"] is None
        assert game["config_files"] == []

    def test_export_multiple_games(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "out.json")
        games = [_FakeGame("GameA"), _FakeGame("GameB")]
        exporter.export(games, output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert set(data["games"].keys()) == {"GameA", "GameB"}

    def test_export_includes_parsed_settings(self, tmp_path):
        cfg_file = tmp_path / "UserSettings.json"
        cfg_file.write_text(json.dumps({
            "data": [{
                "group_name": "/video/display",
                "options": [
                    {"name": "Resolution", "value": "1920x1080"},
                    {"name": "WindowMode", "value": 0},
                    {"name": "VSync", "value": "UI-Settings-Video-QualitySetting-Off"},
                    {"name": "MaximumFPS_OnOff", "value": True},
                    {"name": "MaximumFPS", "value": 120},
                    {"name": "DynamicResolutionScaling", "value": False},
                    {"name": "ResolutionScaling", "value": "DLSS"},
                    {"name": "FrameGeneration", "value": False},
                ],
            }],
        }), encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[r"%USERPROFILE%\Saved Games\Cyberpunk 2077\UserSettings.json"],
            expanded_paths=[str(cfg_file)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Cyberpunk 2077")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        settings = data["games"]["Cyberpunk 2077"]["parsed_settings"]
        assert settings["resolution"] == "1920x1080"
        assert settings["screen_mode"] == "Fullscreen"
        assert settings["vsync"] == "Off"

    def test_export_creates_parent_dirs(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "nested" / "dir" / "out.json")
        exporter.export([_FakeGame("GameA")], output)

        assert os.path.isfile(output)


class TestStreetFighterParser:
    def test_parse_config_ini(self):
        from config_manager.settings_parser import extract_key_settings

        content = """[Render]
GlobalSettings=Custom
MaxFramerate=60
[RenderConfig]
FullScreenDisplayMode=154
WindowMode=Normal
VSync=True
UpscaleType=None
FullScreenMode=false
DisplayMode154_Width=1680
DisplayMode154_Height=1050
"""
        result = extract_key_settings(
            "Street Fighter 6",
            [{"found": True, "content": content, "expanded_path": "config.ini"}],
        )

        assert result["resolution"] == "1680x1050"
        assert result["screen_mode"] == "Windowed"
        assert result["quick_preset"] == "Custom"
        assert result["upscaling"] == "Off"
        assert result["frame_generation"] == "N/A"


class TestF1Parser:
    def test_registered_scanner_name_uses_f1_parser(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <ssrt quality="2" />
  <lighting quality="1" />
  <shadows sampling="1" />
  <weather_effects proceduralCloudQuality="1" />
  <texture_streaming sizeInMiB="1024" />
  <particles enabled="true" distanceScale="1.0" high="false" />
  <vehicle_reflections envMapScale="1.0" />
  <ground_cover enabled="true" />
  <frame_gen mode="0" />
  <multi_frame_gen value="0" />
</hardware_settings_config>"""

        result = extract_key_settings(
            "F1® 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["quick_preset"] == "Medium"
        assert result["frame_generation"] == "Off"

    def test_f1_options_include_upscaling_quality_modes(self):
        from config_manager.settings_parser import UPSCALING, setting_options_for_game

        options = setting_options_for_game("F1® 25", UPSCALING)

        assert "FSR3 (Quality)" in options
        assert "FSR3 (Ultra Performance)" in options
        assert "XeSS (Balanced)" in options
        assert "XeSS (Ultra Quality)" in options

    def test_parse_hardware_settings_config(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <resolution width="1920" height="1080" displayMode="1" vsync="false" frameRateLimiterEnabled="false" frameRateLimiterValue="120" />
  <antialiasing taa="true" cas="1" dlss="true" fsr3="0" xess="false" />
  <frame_gen mode="0" />
  <multi_frame_gen value="0" />
  <dynamicresolution_enabled value="false" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["resolution"] == "1920x1080"
        assert result["screen_mode"] == "Fullscreen"
        assert result["vsync"] == "Off"
        assert result["frame_limit"] == "Unlimited"
        assert result["upscaling"] == "DLSS"
        assert result["frame_generation"] == "Off"
        assert result["dynamic_resolution"] == "Off"
        assert result["quick_preset"] == "N/A"

    def test_parse_xess_balanced_quality(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <antialiasing taa="false" cas="1" dlss="false" fsr3="0" xess="true" />
    <aa_quality value="1" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["upscaling"] == "XeSS (Balanced)"

    def test_parse_xess_quality(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <antialiasing taa="false" cas="1" dlss="false" fsr3="0" xess="true" />
  <aa_quality value="0" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["upscaling"] == "XeSS (Quality)"

    def test_parse_xess_performance_quality(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <antialiasing taa="false" cas="1" dlss="false" fsr3="0" xess="true" />
  <aa_quality value="2" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["upscaling"] == "XeSS (Performance)"

    def test_parse_xess_ultra_quality(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <antialiasing taa="false" cas="1" dlss="false" fsr3="0" xess="true" />
  <aa_quality value="4" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["upscaling"] == "XeSS (Ultra Quality)"

    def test_parse_fsr3_ultra_performance(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <antialiasing taa="false" cas="1" dlss="false" fsr3="1" xess="false" />
  <aa_quality value="3" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["upscaling"] == "FSR (Ultra Performance)"

    def test_parse_fsr3_performance(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <antialiasing taa="false" cas="1" dlss="false" fsr3="1" xess="false" />
  <aa_quality value="2" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["upscaling"] == "FSR (Performance)"

    def test_parse_fsr3_balanced(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <antialiasing taa="false" cas="1" dlss="false" fsr3="1" xess="false" />
  <aa_quality value="1" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["upscaling"] == "FSR (Balanced)"

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [("0", "Off"), ("3", "AMD FSR3"), ("4", "XeFG")],
    )
    def test_parse_f1_frame_generation_provider(self, mode, expected):
        from config_manager.settings_parser import extract_key_settings

        content = f"""<hardware_settings_config>
  <frame_gen mode="{mode}" />
  <multi_frame_gen value="0" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1® 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["frame_generation"] == expected

    def test_dynamic_resolution_preserves_auto_target(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <dynamicresolution_enabled value="true" />
  <dynamicresolution_target_fps value="AUTO" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["dynamic_resolution"] == "On (Target: AUTO)"

    def test_dynamic_resolution_zero_target_maps_to_auto(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <dynamicresolution_enabled value="true" />
  <dynamicresolution_target_fps value="0" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["dynamic_resolution"] == "On (Target: AUTO)"


class TestForzaPresetInference:
    def test_forza_horizon_6_screen_mode_uses_game_full_screen_semantics(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<UserConfig Version="52">
    <settings><Fullscreen value="1" /></settings>
</UserConfig>"""

        result = extract_key_settings(
            "Forza Horizon 6",
            [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}],
        )

        assert result["screen_mode"] == "Fullscreen"

        def test_forza_reports_unavailable_independent_frame_generation_as_na(self):
                from config_manager.settings_parser import extract_key_settings

                content = """<UserConfig Version="52">
    <settings>
        <UseDynamicOptimization value="1" />
    </settings>
    <selections>
        <option id="FSR3Mode" value="1" />
        <option id="DLSSGMode" value="0" />
        <option id="UseDynamicOptimization" value="0" />
    </selections>
</UserConfig>"""

                result = extract_key_settings(
                        "Forza Horizon 6",
                        [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}],
                )

                assert result["upscaling"] == "FSR3 (preset 1)"
                assert result["dynamic_resolution"] == "N/A"
                assert result["frame_generation"] == "N/A"

        def test_forza_horizon_6_frame_rate_value_three_is_60_fps(self):
                from config_manager.settings_parser import extract_key_settings

                content = """<UserConfig Version="52">
    <settings>
        <ResolutionWidth value="1920" />
        <ResolutionHeight value="1080" />
        <Fullscreen value="1" />
    </settings>
    <selections>
        <option id="VSync" value="1" />
        <option id="FrameRate" value="3" />
        <option id="UseDynamicOptimization" value="0" />
        <option id="DLSSMode" value="0" />
        <option id="FSR3Mode" value="0" />
        <option id="XeSSMode" value="0" />
        <option id="CarLOD" value="3" />
        <option id="GeometryQuality" value="4" />
    </selections>
</UserConfig>"""

                result = extract_key_settings(
                        "Forza Horizon 6",
                        [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}],
                )

                assert result["frame_limit"] == "60 FPS"
                assert result["quick_preset"] == "Custom"

        @pytest.mark.parametrize(
            ("enum_value", "expected"),
            [("1", "20 FPS"), ("2", "30 FPS"), ("3", "60 FPS"), ("4", "Unlimited")],
        )
        def test_forza_version_52_reads_all_frame_rate_enums(self, enum_value, expected):
            from config_manager.settings_parser import extract_key_settings

            content = f'<UserConfig Version="52"><selections><option id="FrameRate" value="{enum_value}" /></selections></UserConfig>'
            result = extract_key_settings(
                "Forza Horizon 6",
                [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}],
            )

            assert result["frame_limit"] == expected

        def test_mixed_quality_options_are_custom(self):
                from config_manager.settings_parser import extract_key_settings

                content = """<UserConfig>
    <settings>
        <ResolutionWidth value="1920" />
        <ResolutionHeight value="1080" />
        <Fullscreen value="1" />
    </settings>
    <selections>
        <option id="GeometryQuality" value="5" />
        <option id="ReflectionQuality" value="4" />
        <option id="ShadowQuality" value="4" />
        <option id="VolumetricFogQuality" value="5" />
    </selections>
</UserConfig>"""
                result = extract_key_settings(
                        "Forza Horizon 6",
                        [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}],
                )

                assert result["quick_preset"] == "Custom"



class TestForzaWriter:
    def test_forza_writes_high_preset_quality_signature(self):
        from config_manager.settings_writer import _write_forza_xml

        content = '<UserConfig Version="52"><selections><option id="CarLOD" value="0" /><option id="GeometryQuality" value="0" /><option id="ShadowQuality" value="0" /></selections></UserConfig>'
        result = _write_forza_xml(content, {"quick_preset": "High"})

        assert '<option id="CarLOD" value="2" />' in result
        assert '<option id="GeometryQuality" value="3" />' in result
        assert '<option id="ShadowQuality" value="2" />' in result

    def test_forza_writes_high_preset_quality_signature(self):
        from config_manager.settings_writer import _write_forza_xml

        content = '<UserConfig Version="52"><selections><option id="CarLOD" value="0" /><option id="GeometryQuality" value="0" /><option id="ShadowQuality" value="0" /></selections></UserConfig>'
        result = _write_forza_xml(content, {"quick_preset": "High"})

        assert '<option id="CarLOD" value="2" />' in result
        assert '<option id="GeometryQuality" value="3" />' in result
        assert '<option id="ShadowQuality" value="2" />' in result

    def test_forza_reads_xess_quality_names(self):
        from config_manager.settings_parser import extract_key_settings

        content = '<UserConfig Version="52"><selections><option id="XeSSMode" value="3" /></selections></UserConfig>'
        result = extract_key_settings(
            "Forza Horizon 6",
            [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}],
        )

        assert result["upscaling"] == "XeSS Quality"

    def test_forza_reads_xess_ultra_performance(self):
        from config_manager.settings_parser import extract_key_settings

        content = '<UserConfig Version="52"><selections><option id="XeSSMode" value="6" /></selections></UserConfig>'
        result = extract_key_settings("Forza Horizon 6", [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}])

        assert result["upscaling"] == "XeSS Ultra Performance"

    def test_forza_reads_fsr_quality_names(self):
        from config_manager.settings_parser import extract_key_settings

        content = '<UserConfig Version="52"><selections><option id="FSR3Mode" value="4" /></selections></UserConfig>'
        result = extract_key_settings(
            "Forza Horizon 6",
            [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}],
        )

        assert result["upscaling"] == "FSR Ultra Performance"

    def test_forza_infers_high_preset_from_captured_signature(self):
        from config_manager.settings_parser import extract_key_settings

        values = ["2", "2", "3", "3", "3", "0", "2", "0", "1", "0", "2", "3", "2", "2", "3", "3", "2"]
        ids = ["CarLOD", "EnvStreamingTex", "GeometryQuality", "ReflectionQuality", "SSRQuality", "RTReflectionQuality", "ShadowQuality", "NightShadows", "SSGIQuality", "RTGIQuality", "ShaderQuality", "AudioQuality", "DeformableSnowQuality", "ParticlesSettings", "VolumetricFogQuality", "LensEffects", "MotionBlurQuality"]
        content = '<UserConfig Version="52"><selections>' + ''.join(f'<option id="{key}" value="{value}" />' for key, value in zip(ids, values)) + '</selections></UserConfig>'
        result = extract_key_settings("Forza Horizon 6", [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}])

        assert result["quick_preset"] == "High"

    @pytest.mark.parametrize("preset_name, values", [
        ("Extreme", ["4", "4", "5", "4", "5", "0", "4", "2", "2", "0", "4", "4", "4", "4", "5", "4", "3"]),
        ("Very Low", ["0"] * 17),
    ])
    def test_forza_infers_extreme_and_very_low_presets(self, preset_name, values):
        from config_manager.settings_parser import extract_key_settings

        ids = ["CarLOD", "EnvStreamingTex", "GeometryQuality", "ReflectionQuality", "SSRQuality", "RTReflectionQuality", "ShadowQuality", "NightShadows", "SSGIQuality", "RTGIQuality", "ShaderQuality", "AudioQuality", "DeformableSnowQuality", "ParticlesSettings", "VolumetricFogQuality", "LensEffects", "MotionBlurQuality"]
        content = '<UserConfig Version="52"><selections>' + ''.join(f'<option id="{key}" value="{value}" />' for key, value in zip(ids, values)) + '</selections></UserConfig>'
        result = extract_key_settings("Forza Horizon 6", [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}])

        assert result["quick_preset"] == preset_name

    def test_forza_writes_xess_and_fsr_quality_enums(self):
        from config_manager.settings_writer import _write_forza_xml

        content = '<UserConfig Version="52"><selections><option id="FSR3Mode" value="0" /><option id="XeSSMode" value="0" /></selections></UserConfig>'
        xess = _write_forza_xml(content, {"upscaling": "XeSS Balanced"})
        fsr = _write_forza_xml(content, {"upscaling": "FSR Performance"})

        assert '<option id="XeSSMode" value="4" />' in xess
        assert '<option id="FSR3Mode" value="3" />' in fsr

        ultra_performance = _write_forza_xml(content, {"upscaling": "XeSS Ultra Performance"})
        assert '<option id="XeSSMode" value="6" />' in ultra_performance

    def test_forza_screen_mode_writes_fullscreen_choice_sidecar(self, tmp_path):
        from config_manager.settings_writer import write_settings

        game_root = tmp_path / "ForzaHorizon6"
        config_path = game_root / "LocalStorage_Shared" / "ForzaUserConfigSelections" / "UserConfigSelections"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('<UserConfig Version="52"><settings><Fullscreen value="0" /></settings></UserConfig>', encoding="utf-8")

        result = write_settings(
            "Forza Horizon 6",
            [{"expanded_path": str(config_path), "content": config_path.read_text(encoding="utf-8"), "found": True}],
            {"screen_mode": "Fullscreen"},
        )

        assert (game_root / "fullscreen_choice").read_bytes() == bytes([1])
        assert any(item["detail"] == "Forza fullscreen choice written" for item in result)

    def test_forza_horizon_6_writes_fullscreen_using_version_52_semantics(self):
        from config_manager.settings_writer import _write_forza_xml

        content = '<UserConfig Version="52"><settings><Fullscreen value="1" /></settings></UserConfig>'
        result = _write_forza_xml(content, {"screen_mode": "Fullscreen"})

        assert '<Fullscreen value="1" />' in result

    def test_forza_horizon_6_writes_60_fps_as_frame_rate_three(self):
        from config_manager.settings_writer import _write_forza_xml

        content = '<UserConfig Version="52"><selections><option id="FrameRate" value="0" /></selections></UserConfig>'
        result = _write_forza_xml(content, {"frame_limit": "60 FPS"})

        assert '<option id="FrameRate" value="3" />' in result

    def test_forza_horizon_6_writes_30_fps_as_frame_rate_one(self):
        from config_manager.settings_writer import _write_forza_xml

        content = '<UserConfig Version="52"><selections><option id="FrameRate" value="3" /></selections></UserConfig>'
        result = _write_forza_xml(content, {"frame_limit": "30 FPS"})

        assert '<option id="FrameRate" value="2" />' in result

    def test_forza_horizon_6_does_not_write_borderless_windowed(self):
        from config_manager.settings_writer import _write_forza_xml

        content = '<UserConfig Version="52"><settings><Fullscreen value="1" /></settings></UserConfig>'
        result = _write_forza_xml(content, {"screen_mode": "Borderless Windowed"})

        assert '<Fullscreen value="1" />' in result



class TestF1PresetInference:
    @pytest.mark.parametrize(
        ("name", "content"),
        [
            (
                "Ultra Low",
                '<ssrt quality="0"/><lighting quality="0"/><shadows sampling="1" skyShadowMapSize="512"/><weather_effects proceduralCloudQuality="1"/><texture_streaming sizeInMiB="256"/><particles enabled="false" high="true"/><vehicle_reflections envMapScale="0.25"/><ground_cover enabled="false"/>',
            ),
            (
                "Low",
                '<ssrt quality="0"/><lighting quality="0"/><shadows sampling="1" skyShadowMapSize="1024"/><weather_effects proceduralCloudQuality="1"/><texture_streaming sizeInMiB="512"/><particles enabled="true" distanceScale="3.0" high="false"/><vehicle_reflections envMapScale="0.5"/>',
            ),
            (
                "Medium",
                '<ssrt quality="2"/><lighting quality="1"/><shadows sampling="1"/><weather_effects proceduralCloudQuality="1"/><texture_streaming sizeInMiB="1024"/><particles enabled="true" distanceScale="1.0" high="false"/><vehicle_reflections envMapScale="1.0"/><ground_cover enabled="true"/>',
            ),
        ],
    )
    def test_base_preset_signatures_are_recognized(self, name, content):
        from config_manager.settings_parser import extract_key_settings

        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": f"<hardware_settings_config>{content}</hardware_settings_config>", "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["quick_preset"] == name

    def test_high_signature_is_recognized(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <ssrt quality="3" />
  <lighting quality="2" />
  <shadows sampling="2" />
    <weather_effects proceduralCloudQuality="1" />
    <texture_streaming sizeInMiB="1536" />
    <particles high="true" />
    <rt_pathtrace enabled="false" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["quick_preset"] == "High"

    def test_ultra_high_signature_is_recognized(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <lighting quality="3" />
  <ssrt quality="4" />
  <shadows sampling="3" />
    <weather_effects proceduralCloudQuality="1" />
    <texture_streaming sizeInMiB="2048" />
    <particles high="true" />
    <rt_pathtrace enabled="false" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["quick_preset"] == "Ultra High"

    def test_ultra_max_signature_is_recognized(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <lighting quality="3" />
  <ssrt quality="4" />
  <shadows sampling="3" />
  <weather_effects proceduralCloudQuality="1" />
  <texture_streaming sizeInMiB="2048" />
    <particles high="true" />
  <rt_pathtrace enabled="true" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["quick_preset"] == "Ultra Max"

    def test_frame_generation_makes_matching_base_preset_custom(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <ssrt quality="0" />
  <lighting quality="0" />
  <shadows sampling="1" skyShadowMapSize="512" />
  <weather_effects proceduralCloudQuality="1" />
  <texture_streaming sizeInMiB="256" />
  <particles enabled="false" high="true" />
  <vehicle_reflections envMapScale="0.25" />
  <ground_cover enabled="false" />
  <frame_gen mode="3" />
  <multi_frame_gen value="0" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["quick_preset"] == "Custom (Ultra Low)"
        assert result["frame_generation"] == "AMD FSR3"

    def test_frame_generation_preserves_medium_base_preset_name(self):
        from config_manager.settings_parser import extract_key_settings

        content = """<hardware_settings_config>
  <ssrt quality="2" />
  <lighting quality="1" />
  <shadows sampling="1" />
  <weather_effects proceduralCloudQuality="1" />
  <texture_streaming sizeInMiB="1024" />
  <particles enabled="true" distanceScale="1.0" high="false" />
  <vehicle_reflections envMapScale="1.0" />
  <ground_cover enabled="true" />
  <frame_gen mode="4" />
  <multi_frame_gen value="0" />
</hardware_settings_config>"""
        result = extract_key_settings(
            "F1 25",
            [{"found": True, "content": content, "expanded_path": "hardware_settings_config.xml"}],
        )

        assert result["quick_preset"] == "Custom (Medium)"
        assert result["frame_generation"] == "XeFG"


class TestGameSpecificUnrealParsers:
    def test_parse_black_myth_retail_keeps_explicit_windowed_resolution(self):
        from config_manager.settings_parser import extract_key_settings

        content = """[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=1600
ResolutionSizeY=900
LastUserConfirmedResolutionSizeX=1600
LastUserConfirmedResolutionSizeY=900
FullscreenMode=2
LastUserConfirmedDesiredScreenWidth=1600
LastUserConfirmedDesiredScreenHeight=900
UISettingData=(("ScreenMode", "2"),("ScreenRatio", "0"),("ScreenResolution", "1"),("WindowFullImageQuality", "0"),("ImageQuality", "1080"))
"""

        result = extract_key_settings(
            "Black Myth: Wukong",
            [{"found": True, "content": content, "expanded_path": "GameUserSettings.ini"}],
        )

        assert result["resolution"] == "1600x900"
        assert result["screen_mode"] == "Windowed"

    def test_parse_black_myth_retail_keeps_explicit_borderless_resolution(self):
        from config_manager.settings_parser import extract_key_settings

        content = """[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=1600
ResolutionSizeY=900
LastUserConfirmedResolutionSizeX=1600
LastUserConfirmedResolutionSizeY=900
FullscreenMode=1
LastUserConfirmedDesiredScreenWidth=1600
LastUserConfirmedDesiredScreenHeight=900
UISettingData=(("ScreenMode", "1"),("ScreenRatio", "0"),("ScreenResolution", "1"),("ImageQuality", "1080"))
"""

        result = extract_key_settings(
            "Black Myth: Wukong",
            [{"found": True, "content": content, "expanded_path": "GameUserSettings.ini"}],
        )

        assert result["resolution"] == "1600x900"
        assert result["screen_mode"] == "Borderless Windowed"

    def test_black_myth_benchmark_options_match_game_capabilities(self):
        from config_manager.settings_parser import setting_options_for_game

        game = "Black Myth: Wukong Benchmark Tool"

        assert setting_options_for_game(game, "screen_mode") == [
            "—", "Borderless Windowed", "Windowed",
        ]
        assert setting_options_for_game(game, "upscaling") == [
            "—", "TSR", "FSR", "XeSS",
        ]
        assert setting_options_for_game(game, "frame_generation", upscaling_method="TSR") == [
            "—", "Off", "On",
        ]
        assert setting_options_for_game(game, "frame_generation", upscaling_method="FSR") == [
            "—", "Off", "On",
        ]
        assert setting_options_for_game(game, "frame_generation", upscaling_method="XeSS") == ["—"]

    def test_parse_black_myth_benchmark_borderless_uses_effective_resolution(self):
        from config_manager.settings_parser import extract_key_settings

        content = """[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=1920
ResolutionSizeY=1080
LastUserConfirmedResolutionSizeX=1600
LastUserConfirmedResolutionSizeY=900
LastUserConfirmedDesiredScreenWidth=1516
LastUserConfirmedDesiredScreenHeight=853
UISettingData=(("ImageQuality", "853"),("ScreenMode", "1"),("ScreenRatio", "2"),("ScreenResolution", "1"),("WindowFullImageQuality", "833333"),("Vsync", "1"),("SuperResolutionSampling", "3"),("InsertFrame", "1"),("QualityLevel", "5"))
"""

        result = extract_key_settings(
            "Black Myth: Wukong Benchmark Tool",
            [{"found": True, "content": content, "expanded_path": "GameUserSettings.ini"}],
        )

        assert result["resolution"] == "1600x900"
        assert result["screen_mode"] == "Borderless Windowed"
        assert result["vsync"] == "On"
        assert result["upscaling"] == "XeSS"
        assert result["frame_generation"] == "N/A"
        assert result["quick_preset"] == "Cinematic"

    def test_parse_black_myth_benchmark_windowed_uses_confirmed_resolution(self):
        from config_manager.settings_parser import extract_key_settings

        content = """[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=1920
ResolutionSizeY=1080
LastUserConfirmedResolutionSizeX=1280
LastUserConfirmedResolutionSizeY=720
UISettingData=(("ScreenMode", "2"),("ScreenResolution", "0"))
"""

        result = extract_key_settings(
            "Black Myth: Wukong Benchmark Tool",
            [{"found": True, "content": content, "expanded_path": "GameUserSettings.ini"}],
        )

        assert result["resolution"] == "1280x720"

    def test_parse_black_myth_benchmark_uses_confirmed_resolution(self):
        from config_manager.settings_parser import extract_key_settings

        content = """[/Script/GSGameSettings.GSGameUserSettings]
ResolutionSizeX=3840
ResolutionSizeY=2160
FullscreenMode=1
LastUserConfirmedDesiredScreenWidth=1920
LastUserConfirmedDesiredScreenHeight=1080
UISettingData=((\"ScreenMode\", \"2\"),(\"ScreenRatio\", \"2\"),(\"ScreenResolution\", \"1\"),(\"Vsync\", \"0\"),(\"Dlss\", \"1\"),(\"SuperResolutionSampling\", \"1\"),(\"InsertFrame\", \"0\"),(\"QualityLevel\", \"3\"))
"""

        result = extract_key_settings(
            "Black Myth: Wukong Benchmark Tool",
            [{"found": True, "content": content, "expanded_path": "GameUserSettings.ini"}],
        )

        assert result["resolution"] == "1920x1080"

    def test_parse_black_myth_ui_settings(self):
        from config_manager.settings_parser import extract_key_settings

        content = """[/Script/Engine.GameUserSettings]
bUseDynamicResolution=False
ResolutionSizeX=3840
ResolutionSizeY=2160
FullscreenMode=1
FrameRateLimit=0.000000
UISettingData=(("ScreenMode", "1"),("Vsync", "0"),("Dlss", "1"),("SuperResolutionSampling", "1"),("InsertFrame", "1"),("QualityLevel", "1"))
"""
        result = extract_key_settings(
            "Black Myth: Wukong",
            [{"found": True, "content": content, "expanded_path": "GameUserSettings.ini"}],
        )

        assert result["resolution"] == "3840x2160"
        assert result["screen_mode"] == "Borderless Windowed"
        assert result["vsync"] == "Off"
        assert result["upscaling"] == "XeSS"
        assert result["frame_generation"] == "Auto"
        assert result["quick_preset"] == "Low"

    def test_parse_expedition_selected_upscaler_and_frame_generation(self):
        from config_manager.settings_parser import extract_key_settings

        content = """ResolutionSizeX=3840
ResolutionSizeY=2160
FullscreenMode=1
bUseVSync=False
FrameRateLimit=0.000000
    sg.ViewDistanceQuality=1
    sg.ShadowQuality=1
    sg.TextureQuality=1
    sg.EffectsQuality=1
CurrentSelectedUpscaler=XeSS
CurrentSelectedUpscalerQualityMode=5
CurrentSelectedFrameGenerationMode=1
"""
        result = extract_key_settings(
            "Clair Obscur: Expedition 33",
            [{"found": True, "content": content, "expanded_path": "GameUserSettings.ini"}],
        )

        assert result["upscaling"] == "XeSS (mode 5)"
        assert result["frame_generation"] == "On (mode 1)"
        assert result["quick_preset"] == "Medium"

    def test_black_myth_picks_named_file_over_earlier_empty_candidates(self):
        from config_manager.settings_parser import extract_key_settings

        content = """[/Script/Engine.GameUserSettings]
ResolutionSizeX=3840
ResolutionSizeY=2160
FullscreenMode=1
"""
        # Alphabetically-earlier decoy files (as produced by a directory scan
        # of Unreal Engine's Saved\Config\Windows\) must not be parsed instead
        # of the real GameUserSettings.ini.
        config_files = [
            {"found": True, "content": "\n", "expanded_path": "ApexDestruction.ini"},
            {"found": True, "content": "\n", "expanded_path": "Compat.ini"},
            {"found": True, "content": content, "expanded_path": "GameUserSettings.ini"},
            {"found": True, "content": "\n", "expanded_path": "Wwise.ini"},
        ]

        result = extract_key_settings("Black Myth: Wukong", config_files)

        assert result["resolution"] == "3840x2160"
        assert result["screen_mode"] == "Borderless Windowed"


class TestConfigExporterWithWiki:
    def test_export_pcgamingwiki_section_populated(self, tmp_path):
        mock_wiki = _make_wiki_mock(
            raw_paths=[r"%USERPROFILE%\Saved Games\Game\settings.cfg"],
            expanded_paths=[os.path.join(os.path.expanduser("~"), "Saved Games", "Game", "settings.cfg")],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        wiki = data["games"]["Game"]["pcgamingwiki"]
        assert wiki is not None
        assert wiki["error"] is None
        assert len(wiki["raw_paths"]) == 1
        assert len(wiki["expanded_paths"]) == 1

    def test_export_config_files_not_found(self, tmp_path):
        expanded = os.path.join(os.path.expanduser("~"), "Saved Games", "Game", "settings.cfg")
        mock_wiki = _make_wiki_mock(
            raw_paths=[r"%USERPROFILE%\Saved Games\Game\settings.cfg"],
            expanded_paths=[expanded],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        assert len(cfg_files) == 1
        entry = cfg_files[0]
        assert entry["found"] is False
        assert entry["error"] == "path_not_found"

    def test_export_config_file_read_when_exists(self, tmp_path):
        cfg_file = tmp_path / "settings.cfg"
        cfg_file.write_text("volume=80\nresolution=1920x1080", encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[r"%USERPROFILE%\Game\settings.cfg"],
            expanded_paths=[str(cfg_file)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        assert len(cfg_files) == 1
        entry = cfg_files[0]
        assert entry["found"] is True
        assert "volume=80" in entry["content"]
        assert entry["error"] is None
        assert entry["truncated"] is False

    def test_wiki_error_recorded_in_json(self, tmp_path):
        mock_wiki = MagicMock()
        mock_wiki.get_config_info.side_effect = Exception("network error")

        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)  # must not raise

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        wiki = data["games"]["Game"]["pcgamingwiki"]
        assert wiki["error"] is not None
        assert data["games"]["Game"]["config_files"] == []

    def test_wiki_error_field_propagated(self, tmp_path):
        mock_wiki = _make_wiki_mock(error="API quota exceeded")
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        assert data["games"]["Game"]["pcgamingwiki"]["error"] == "API quota exceeded"

    def test_get_config_info_called_with_game_name(self, tmp_path):
        mock_wiki = _make_wiki_mock()
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Apex Legends")], output)

        mock_wiki.get_config_info.assert_called_once_with("Apex Legends", install_path="")


# ---------------------------------------------------------------------------
# Imports for new helpers
# ---------------------------------------------------------------------------

from config_manager.config_exporter import (
    _is_steam_userdata_path,
    _scan_directory,
    _DIR_SCAN_DEPTH,
    _CONFIG_EXTENSIONS,
    detect_config_files,
)


# ---------------------------------------------------------------------------
# _is_steam_userdata_path tests
# ---------------------------------------------------------------------------

class TestIsSteamUserdataPath:
    def test_userdata_windows_backslash(self):
        path = r"C:\Program Files (x86)\Steam\userdata\12345\553850\remote\input.config"
        assert _is_steam_userdata_path(path) is True

    def test_userdata_forward_slash(self):
        path = "/home/user/.steam/steam/userdata/12345/553850/remote/input.config"
        assert _is_steam_userdata_path(path) is True

    def test_non_userdata_path(self):
        path = r"C:\Users\user\AppData\Roaming\App\settings.cfg"
        assert _is_steam_userdata_path(path) is False

    def test_empty_path(self):
        assert _is_steam_userdata_path("") is False

    def test_path_contains_userdata_word_not_as_segment(self):
        # 'userdata' not flanked by slashes should still be caught if surrounded
        path = r"C:\Steam\userdata\123\game\file.cfg"
        assert _is_steam_userdata_path(path) is True


# ---------------------------------------------------------------------------
# _scan_directory tests
# ---------------------------------------------------------------------------

class TestScanDirectory:
    def test_finds_config_file_at_depth_0(self, tmp_path):
        cfg = tmp_path / "settings.cfg"
        cfg.write_text("k=v", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=0)
        assert str(cfg) in found

    def test_ignores_unknown_extension(self, tmp_path):
        (tmp_path / "readme.md").write_text("hello", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=0)
        assert found == []

    def test_scans_depth_1(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        cfg = sub / "options.ini"
        cfg.write_text("[s]\nk=v", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=1)
        assert str(cfg) in found

    def test_does_not_exceed_max_depth(self, tmp_path):
        """Files at depth 3 must NOT appear when max_depth=2."""
        d1 = tmp_path / "a"
        d2 = d1 / "b"
        d3 = d2 / "c"
        d3.mkdir(parents=True)
        deep_cfg = d3 / "deep.cfg"
        deep_cfg.write_text("deep", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=2)
        assert str(deep_cfg) not in found

    def test_depth_2_default_finds_two_levels_deep(self, tmp_path):
        """Files at depth ≤ 2 must be found with the default depth."""
        d1 = tmp_path / "a"
        d2 = d1 / "b"
        d2.mkdir(parents=True)
        cfg = d2 / "game.cfg"
        cfg.write_text("cfg", encoding="utf-8")
        found = _scan_directory(str(tmp_path))  # uses default _DIR_SCAN_DEPTH == 2
        assert str(cfg) in found

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        found = _scan_directory(str(tmp_path / "nonexistent"))
        assert found == []

    def test_all_config_extensions_found(self, tmp_path):
        for ext in _CONFIG_EXTENSIONS:
            (tmp_path / f"file{ext}").write_text("x", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=0)
        assert len(found) == len(_CONFIG_EXTENSIONS)

    def test_default_depth_constant(self):
        assert _DIR_SCAN_DEPTH == 2


# ---------------------------------------------------------------------------
# ConfigExporter – userdata exclusion and directory scanning
# ---------------------------------------------------------------------------

class TestConfigExporterUserdataInclusion:
    def test_userdata_path_included_in_config_files(self, tmp_path):
        """Steam userdata path must now appear in config_files."""
        userdata_cfg = tmp_path / "userdata" / "12345" / "input.config"
        userdata_cfg.parent.mkdir(parents=True)
        userdata_cfg.write_text("bind=x", encoding="utf-8")
        normal_path = str(tmp_path / "settings.cfg")
        (tmp_path / "settings.cfg").write_text("v=1", encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[str(userdata_cfg), normal_path],
            expanded_paths=[str(userdata_cfg), normal_path],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        game = data["games"]["Game"]
        cfg_paths = [e["expanded_path"] for e in game["config_files"]]
        assert str(userdata_cfg) in cfg_paths
        assert normal_path in cfg_paths

    def test_userdata_path_present_in_expanded_paths(self, tmp_path):
        """Steam userdata path must remain in pcgamingwiki.expanded_paths."""
        userdata_cfg = tmp_path / "userdata" / "12345" / "input.config"
        userdata_cfg.parent.mkdir(parents=True)
        userdata_cfg.write_text("bind=y", encoding="utf-8")
        mock_wiki = _make_wiki_mock(
            raw_paths=[str(userdata_cfg)],
            expanded_paths=[str(userdata_cfg)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        game = data["games"]["Game"]
        assert str(userdata_cfg) in game["pcgamingwiki"]["expanded_paths"]
        assert len(game["config_files"]) == 1

    def test_non_userdata_path_included_in_config_files(self, tmp_path):
        """Non-userdata expanded path must still be read into config_files."""
        cfg = tmp_path / "settings.cfg"
        cfg.write_text("volume=80", encoding="utf-8")
        mock_wiki = _make_wiki_mock(
            raw_paths=[str(cfg)],
            expanded_paths=[str(cfg)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        assert len(cfg_files) == 1
        assert cfg_files[0]["found"] is True


class TestConfigExporterDirectoryScan:
    def test_directory_path_triggers_scan(self, tmp_path):
        """When an expanded path is a directory, its config files are included."""
        game_dir = tmp_path / "GameProfile"
        game_dir.mkdir()
        (game_dir / "settings.ini").write_text("[s]\nk=v", encoding="utf-8")
        (game_dir / "save.sav").write_text("binary", encoding="utf-8")  # ignored ext

        mock_wiki = _make_wiki_mock(
            raw_paths=[str(game_dir)],
            expanded_paths=[str(game_dir)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        assert len(cfg_files) == 1
        assert "settings.ini" in cfg_files[0]["expanded_path"]

    def test_directory_scan_depth_2(self, tmp_path):
        """Files two levels deep inside a directory path are found."""
        profile = tmp_path / "Profile"
        nested = profile / "sub1" / "sub2"
        nested.mkdir(parents=True)
        (nested / "options.cfg").write_text("opt=1", encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[str(profile)],
            expanded_paths=[str(profile)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        paths = [e["expanded_path"] for e in cfg_files]
        assert any("options.cfg" in p for p in paths)

    def test_directory_scan_beyond_depth_2_excluded(self, tmp_path):
        """Files 3 levels deep must NOT appear in config_files."""
        profile = tmp_path / "Profile"
        deep = profile / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.cfg").write_text("d=1", encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[str(profile)],
            expanded_paths=[str(profile)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        paths = [e["expanded_path"] for e in cfg_files]
        assert not any("deep.cfg" in p for p in paths)


# ---------------------------------------------------------------------------
# detect_config_files tests
# ---------------------------------------------------------------------------

class TestDetectConfigFiles:
    def test_empty_input_returns_empty(self):
        assert detect_config_files([]) == []

    def test_existing_file_returned(self, tmp_path):
        cfg = tmp_path / "settings.cfg"
        cfg.write_text("k=v", encoding="utf-8")
        result = detect_config_files([str(cfg)])
        assert str(cfg) in result

    def test_nonexistent_file_not_returned(self, tmp_path):
        result = detect_config_files([str(tmp_path / "missing.cfg")])
        assert result == []

    def test_directory_path_scanned_recursively(self, tmp_path):
        game_dir = tmp_path / "GameData"
        game_dir.mkdir()
        cfg = game_dir / "options.ini"
        cfg.write_text("[s]\nk=v", encoding="utf-8")
        result = detect_config_files([str(game_dir)])
        assert str(cfg) in result

    def test_steam_userdata_path_excluded(self, tmp_path):
        userdata_path = r"C:\Steam\userdata\12345\553850\remote\input.config"
        cfg = tmp_path / "settings.cfg"
        cfg.write_text("v=1", encoding="utf-8")
        result = detect_config_files([userdata_path, str(cfg)])
        # Windows userdata path must not appear; the real config file must appear
        assert userdata_path not in result
        assert str(cfg) in result

    def test_directory_ignores_non_config_extensions(self, tmp_path):
        game_dir = tmp_path / "GameData"
        game_dir.mkdir()
        (game_dir / "save.sav").write_text("binary", encoding="utf-8")
        result = detect_config_files([str(game_dir)])
        assert result == []

    def test_mixed_file_and_directory(self, tmp_path):
        cfg_file = tmp_path / "prefs.json"
        cfg_file.write_text("{}", encoding="utf-8")
        sub_dir = tmp_path / "sub"
        sub_dir.mkdir()
        sub_cfg = sub_dir / "extra.ini"
        sub_cfg.write_text("[x]\n", encoding="utf-8")
        result = detect_config_files([str(cfg_file), str(sub_dir)])
        assert str(cfg_file) in result
        assert str(sub_cfg) in result


class TestForzaVersion52FrameRateEnums:
    @pytest.mark.parametrize(
        ("enum_value", "expected"),
        [
            ("1", "20 FPS"),
            ("2", "30 FPS"),
            ("3", "60 FPS"),
            ("4", "Unlimited"),
        ],
    )
    def test_reads_all_frame_rate_enums(self, enum_value, expected):
        from config_manager.settings_parser import extract_key_settings

        content = f'<UserConfig Version="52"><selections><option id="FrameRate" value="{enum_value}" /></selections></UserConfig>'
        result = extract_key_settings(
            "Forza Horizon 6",
            [{"found": True, "content": content, "expanded_path": "UserConfigSelections"}],
        )

        assert result["frame_limit"] == expected


def test_forza_quick_preset_is_read_only_derived_value():
    from config_manager.settings_parser import QUICK_PRESET, is_setting_writable_for_game

    assert QUICK_PRESET == "quick_preset"
    assert is_setting_writable_for_game("Forza Horizon 6", QUICK_PRESET) is True
    assert is_setting_writable_for_game("Cyberpunk 2077", QUICK_PRESET) is True
