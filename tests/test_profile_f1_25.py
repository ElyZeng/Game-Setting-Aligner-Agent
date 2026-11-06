"""Parity tests for the F1® 25 profile migration (P1 step 3).

Same purpose as tests/test_profile_black_myth.py: compare the
profile-dispatch path against the pre-P1 functions
(_parse_f1_xml/_write_f1_xml) called directly on the same fixture content.
Detailed behavior coverage already exists in tests/test_config_exporter.py
(TestF1Parser) and tests/test_f1_writer.py; this file only proves the
dispatch wiring itself is correct.

Note: some existing tests call extract_key_settings with the informal name
"F1 25" (no trademark symbol) and still expect correct results — that's
deliberately NOT covered by this exact-match profile (only the canonical
"F1® 25" title from pcgamingwiki/Steam is registered), so "F1 25" keeps
falling through to the legacy substring-based dispatch. That's not a
regression: the legacy path still handles it exactly as before.
"""

from config_manager.settings_parser import _parse_f1_xml, extract_key_settings
from config_manager.settings_writer import _write_f1_xml, write_settings

F1_XML = """<hardware_settings_config>
  <resolution width="1920" height="1080" displayMode="1" vsync="false" frameRateLimiterEnabled="true" frameRateLimiterValue="120" />
  <antialiasing taa="false" cas="1" dlss="false" fsr3="0" xess="true" />
  <aa_quality value="1" />
    <frame_gen mode="0" />
    <multi_frame_gen value="0" />
    <ssrt enabled="true" quality="4" />
    <lighting quality="3" />
    <shadows enabled="true" skyShadowMapSize="2048" sampling="3" />
    <weather_effects proceduralCloudQuality="1" />
    <texture_streaming sizeInMiB="2048" />
    <particles enabled="true" distanceScale="1.0" rate="1.0" high="true" />
    <vehicle_reflections envMapScale="2.0" />
    <ground_cover enabled="true" />
</hardware_settings_config>"""

F1_XML_PRESET_SIGNATURE = """<hardware_settings_config>
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


def _files(content, filename="hardware_settings_config.xml"):
    return [{"found": True, "content": content, "expanded_path": filename}]


class TestReadParity:
    def test_full_fixture(self):
        via_profile = extract_key_settings("F1® 25", _files(F1_XML))
        via_legacy = _parse_f1_xml(F1_XML)
        assert via_profile == via_legacy
        assert via_profile["upscaling"] == "XeSS"

    def test_preset_signature_fixture(self):
        via_profile = extract_key_settings("F1® 25", _files(F1_XML_PRESET_SIGNATURE))
        via_legacy = _parse_f1_xml(F1_XML_PRESET_SIGNATURE)
        assert via_profile == via_legacy
        assert via_profile["quick_preset"] == "Medium"
        assert via_profile["frame_generation"] == "Off"

    def test_informal_name_without_trademark_symbol_uses_legacy_fallback(self):
        """"F1 25" (no ®) is not in this profile's exact match list, so it
        must still resolve via the legacy substring dispatch, unchanged."""
        via_dispatch = extract_key_settings("F1 25", _files(F1_XML_PRESET_SIGNATURE))
        assert via_dispatch == _parse_f1_xml(F1_XML_PRESET_SIGNATURE)


class TestWriteParity:
    def test_write_round_trip_matches_legacy_bytes(self, tmp_path):
        settings = {
            "resolution": "2560x1440",
            "screen_mode": "Borderless Windowed",
            "vsync": "On",
            "frame_limit": "60 FPS",
            "upscaling": "FSR3 (Quality)",
            "frame_generation": "On",
        }
        expected = _write_f1_xml(F1_XML, settings)

        path = tmp_path / "hardware_settings_config.xml"
        path.write_text(F1_XML, encoding="utf-8")
        results = write_settings(
            "F1® 25",
            [{"found": True, "content": F1_XML, "expanded_path": str(path)}],
            settings,
        )

        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert results[0]["detail"] == "F1 25 XML settings written"
        assert path.read_text(encoding="utf-8") == expected
