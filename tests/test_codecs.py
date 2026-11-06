"""Unit tests for the P1 codec layer (config_manager/codecs/).

These also serve as the parity proof for the settings_writer.py re-exports
(_replace_ini_value / _replace_xml_attr / _replace_valve_kv_value /
_replace_xml_option): they must behave exactly like the inline regexes they
replaced.
"""

from config_manager.codecs import ini, raw_text, valve_kv, xml_attr
from config_manager.settings_writer import (
    _replace_ini_value,
    _replace_valve_kv_value,
    _replace_xml_attr,
    _replace_xml_option,
)


class TestIniCodec:
    def test_read_existing_key(self):
        content = "ResolutionSizeX=1920\nResolutionSizeY=1080\n"
        assert ini.read(content, "ResolutionSizeX") == "1920"

    def test_read_missing_key_returns_none(self):
        assert ini.read("Foo=1\n", "Bar") is None

    def test_patch_existing_key(self):
        content = "ResolutionSizeX=1920\nResolutionSizeY=1080\n"
        patched = ini.patch(content, "ResolutionSizeX", "2560")
        assert patched == "ResolutionSizeX=2560\nResolutionSizeY=1080\n"
        assert ini.read(patched, "ResolutionSizeX") == "2560"

    def test_patch_missing_key_is_noop(self):
        content = "Foo=1\n"
        assert ini.patch(content, "Bar", "2") == content

    def test_patch_preserves_surrounding_whitespace_and_indentation(self):
        content = "[Section]\n    sg.ShadowQuality=2\nOther=1\n"
        patched = ini.patch(content, "sg.ShadowQuality", "3")
        assert patched == "[Section]\n    sg.ShadowQuality=3\nOther=1\n"

    def test_matches_settings_writer_reexport(self):
        content = "ResolutionSizeX=1920\nFoo=bar\n"
        assert ini.patch(content, "ResolutionSizeX", "1600") == _replace_ini_value(
            content, "ResolutionSizeX", "1600"
        )


class TestXmlAttrCodec:
    def test_read_and_patch_attribute(self):
        content = '<Resolution Width="1920" Height="1080" />'
        assert xml_attr.read(content, ("Resolution", "Width")) == "1920"
        patched = xml_attr.patch(content, ("Resolution", "Width"), "2560")
        assert patched == '<Resolution Width="2560" Height="1080" />'

    def test_patch_missing_tag_is_noop(self):
        content = '<Other Width="1" />'
        assert xml_attr.patch(content, ("Resolution", "Width"), "9") == content

    def test_read_and_patch_option(self):
        content = '<option id="quick_preset" value="Medium" />'
        assert xml_attr.read_option(content, "quick_preset") == "Medium"
        patched = xml_attr.patch_option(content, "quick_preset", "High")
        assert patched == '<option id="quick_preset" value="High" />'

    def test_matches_settings_writer_reexport(self):
        content = '<VSync value="0" />'
        assert xml_attr.patch(content, ("VSync", "value"), "1") == _replace_xml_attr(
            content, "VSync", "value", "1"
        )

    def test_option_matches_settings_writer_reexport(self):
        content = '<option id="vsync" value="0" />'
        assert xml_attr.patch_option(content, "vsync", "1") == _replace_xml_option(
            content, "vsync", "1"
        )


class TestValveKvCodec:
    def test_read_and_patch(self):
        content = '"fullscreen" "1"\n"width" "1920"\n'
        assert valve_kv.read(content, "fullscreen") == "1"
        patched = valve_kv.patch(content, "fullscreen", "0")
        assert patched == '"fullscreen" "0"\n"width" "1920"\n'

    def test_patch_missing_key_is_noop(self):
        content = '"foo" "1"\n'
        assert valve_kv.patch(content, "bar", "2") == content

    def test_matches_settings_writer_reexport(self):
        content = '"width" "1920"\n'
        assert valve_kv.patch(content, "width", "2560") == _replace_valve_kv_value(
            content, "width", "2560"
        )


class TestRawTextCodec:
    def test_read_returns_whole_content(self):
        assert raw_text.read("fullscreen") == "fullscreen"

    def test_patch_replaces_whole_content(self):
        assert raw_text.patch("fullscreen", None, "windowed") == "windowed"
