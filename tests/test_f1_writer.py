"""Regression tests for F1 25 XML writer behavior."""

from __future__ import annotations

from config_manager.settings_writer import write_settings


F1_XML = """<hardware_settings_config>
  <resolution width="1920" height="1080" displayMode="1" vsync="false" frameRateLimiterEnabled="true" frameRateLimiterValue="120" />
  <antialiasing taa="false" cas="1" dlss="false" fsr3="0" xess="true" />
  <aa_quality value="1" />
</hardware_settings_config>"""


def _write(tmp_path, settings):
    path = tmp_path / "hardware_settings_config.xml"
    path.write_text(F1_XML, encoding="utf-8")
    result = write_settings(
        "F1® 25",
        [{"expanded_path": str(path), "content": F1_XML, "found": True}],
        settings,
    )
    return result, path.read_text(encoding="utf-8")


def test_writes_resolution_screen_mode_vsync_and_frame_limit(tmp_path):
    result, content = _write(tmp_path, {
        "resolution": "2560x1440",
        "screen_mode": "Borderless Windowed",
        "vsync": "On",
        "frame_limit": "60 FPS",
    })

    assert result[0]["status"] == "ok"
    assert 'width="2560"' in content
    assert 'height="1440"' in content
    assert 'displayMode="2"' in content
    assert 'vsync="true"' in content
    assert 'frameRateLimiterEnabled="true"' in content
    assert 'frameRateLimiterValue="60"' in content


def test_writes_fsr_quality(tmp_path):
    result, content = _write(tmp_path, {"upscaling": "FSR3 (Quality)"})

    assert result[0]["status"] == "ok"
    assert 'fsr3="1"' in content
    assert 'xess="false"' in content
    assert '<aa_quality value="0"' in content


def test_writes_xess_balanced(tmp_path):
    result, content = _write(tmp_path, {"upscaling": "XeSS (Balanced)"})

    assert result[0]["status"] == "ok"
    assert 'fsr3="0"' in content
    assert 'xess="true"' in content
    assert '<aa_quality value="1"' in content
