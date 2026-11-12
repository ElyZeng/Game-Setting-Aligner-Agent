"""Unit tests for write_settings()'s profile-first dispatch branch with a
registry-shaped config_files entry (backlog item 1: fix the unguarded
``cfg["expanded_path"]`` KeyError and route registry-type entries through
registry_io instead of a plain filesystem write).

No shipped profile currently declares a non-null ``writer_fn`` for a
registry-shaped file (Horizon Zero Dawn Remastered / Shadow of the Tomb
Raider deliberately stay read-only, see tests/test_profile_registry_games.py).
So this test builds a synthetic in-memory Profile — not loaded from a JSON
file — with a registered test-only writer_fn, to exercise the fixed dispatch
logic end to end against a production-shaped registry config dict (no
"expanded_path" key at all, only type/registry_path/found/content/error,
exactly matching config_manager.config_exporter._read_registry_key()'s real
output).
"""

import json

import pytest

from config_manager import function_registry, profile_dispatch, registry_io
from config_manager.profiles.loader import ConfigFile, Profile
from config_manager.settings_writer import write_settings


class _FakeKey:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeWinreg:
    """Minimal stand-in for the winreg module (duplicated from
    tests/test_profile_registry_games.py's FakeWinreg — tests/ has no
    package __init__.py making a cross-file import fragile)."""

    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ, REG_EXPAND_SZ, REG_BINARY, REG_DWORD, REG_QWORD = 1, 2, 3, 4, 11

    def __init__(self, keys):
        self.keys = keys
        self.set_calls = []

    def OpenKey(self, hive, subkey, _reserved, _access):
        path = f"{hive}\\{subkey}"
        if path not in self.keys:
            raise FileNotFoundError(path)
        return _FakeKey(path)

    def EnumValue(self, key, index):
        items = list(self.keys[key.path].items())
        if index >= len(items):
            raise OSError("no more")
        name, (value, value_type) = items[index]
        return name, value, value_type

    def EnumKey(self, key, index):
        prefix = key.path + "\\"
        children = sorted({p[len(prefix):].split("\\")[0] for p in self.keys if p.startswith(prefix)})
        if index >= len(children):
            raise OSError("no more")
        return children[index]

    def QueryValueEx(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(name)
        return self.keys[key.path][name]

    def SetValueEx(self, key, name, _reserved, value_type, value):
        self.set_calls.append((key.path, name, value_type, value))
        self.keys[key.path][name] = (value, value_type)


GAME_NAME = "Test Registry Profile Game"
REGISTRY_PATH = "HKEY_CURRENT_USER\\Software\\Test\\Registry Profile Game\\"


def _test_registry_parser(content):
    return {}


def _test_registry_writer(content, settings):
    data = json.loads(content)
    if settings.get("vsync") is not None:
        data["Graphics"]["VSync"] = 1 if settings["vsync"] == "On" else 0
    return json.dumps(data)


@pytest.fixture(autouse=True)
def _register_test_functions():
    function_registry.register("parser_fn", "_test_registry_parser", _test_registry_parser, overwrite=True)
    function_registry.register("writer_fn", "_test_registry_writer", _test_registry_writer, overwrite=True)
    yield


def _synthetic_profile():
    return Profile(
        id="test-registry-profile-game",
        match_names=[GAME_NAME],
        match_steam_appid=None,
        engine=None,
        files={"main": ConfigFile(key="main", path=REGISTRY_PATH, codec="registry")},
        parser_fn="_test_registry_parser",
        writer_fn="_test_registry_writer",
    )


def _registry_content(vsync=0):
    return json.dumps({
        "Graphics": {"VSync": vsync, "FullscreenWidth": 3840, "FullscreenHeight": 2160},
    })


def _production_shaped_registry_files(content, *, found=True):
    """Mirrors config_exporter._read_registry_key()'s real output: no
    "expanded_path" key at all."""
    return [{
        "type": "registry",
        "registry_path": REGISTRY_PATH,
        "found": found,
        "content": content if found else None,
        "error": None if found else "key_not_found",
    }]


class TestProfileDispatchRegistryWrite:
    def test_no_keyerror_and_routes_to_registry_io(self, monkeypatch):
        """The core bug fix: with a profile that *does* declare a writer_fn
        for a registry-shaped main file, write_settings() must not KeyError
        on the missing "expanded_path" key, and must perform a real guarded
        registry write (via registry_io) rather than a silent/corrupting
        filesystem write."""
        monkeypatch.setattr(profile_dispatch, "find_profile", lambda name: _synthetic_profile())

        graphics_key = "HKCU\\Software\\Test\\Registry Profile Game\\\\Graphics"
        fake = FakeWinreg({
            graphics_key: {
                "VSync": (0, 4), "FullscreenWidth": (3840, 4), "FullscreenHeight": (2160, 4),
            },
        })
        monkeypatch.setattr(registry_io, "default_backend", lambda: fake)

        files = _production_shaped_registry_files(_registry_content(vsync=0))

        results = write_settings(GAME_NAME, files, {"vsync": "On"})

        assert results[0]["status"] == "ok", results
        assert results[0]["path"] == REGISTRY_PATH
        assert fake.set_calls == [(graphics_key, "VSync", 4, 1)]

    def test_non_registry_profile_unaffected(self, monkeypatch):
        """Regression guard: a profile whose main file is a normal
        filesystem file (the common case, e.g. Forza/F1 25) must still take
        the plain-file path and not be redirected into registry_io."""
        safe_writes = []

        def _file_writer(content, settings):
            return content + ";written"

        function_registry.register("writer_fn", "_test_file_writer", _file_writer, overwrite=True)
        profile = Profile(
            id="test-file-profile-game",
            match_names=["Test File Profile Game"],
            match_steam_appid=None,
            engine=None,
            files={"main": ConfigFile(key="main", path="C:/Games/config.ini", codec="ini")},
            parser_fn="_test_registry_parser",
            writer_fn="_test_file_writer",
        )
        monkeypatch.setattr(profile_dispatch, "find_profile", lambda name: profile)

        import config_manager.settings_writer as settings_writer_module
        monkeypatch.setattr(settings_writer_module, "_safe_write", lambda path, content: safe_writes.append((path, content)))

        files = [{
            "type": "file", "expanded_path": "C:/Games/config.ini",
            "found": True, "content": "orig", "error": None,
        }]

        results = write_settings("Test File Profile Game", files, {"vsync": "On"})

        assert results[0]["status"] == "ok", results
        assert safe_writes == [("C:/Games/config.ini", "orig;written")]

    def test_missing_expanded_path_on_non_registry_entry_is_skipped_not_keyerror(self, monkeypatch):
        """A malformed/unexpected non-registry config entry with no
        "expanded_path" must be skipped defensively, never crash the whole
        write with a raw KeyError."""
        monkeypatch.setattr(profile_dispatch, "find_profile", lambda name: _synthetic_profile())

        # type != "registry" (so it goes down the file branch) but has no
        # expanded_path at all.
        files = [{"type": "file", "found": True, "content": "x", "error": None}]

        results = write_settings(GAME_NAME, files, {"vsync": "On"})

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
