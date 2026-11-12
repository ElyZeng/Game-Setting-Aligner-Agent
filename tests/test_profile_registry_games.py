"""Parity tests for the two registry-based profiles (GSAA_P1_handoff.md §4.2):
Horizon Zero Dawn™ Remastered and Shadow of the Tomb Raider.

This is a deliberately READ-ONLY migration for this round - see
horizon-zero-dawn-remastered.json / shadow-of-the-tomb-raider.json's
_parser_fn_note for the full rationale, including the unguarded
``cfg["expanded_path"]`` KeyError risk in settings_writer.write_settings()'s
profile-first write dispatch that omitting writer_fn sidesteps entirely (a
risk that does not exist for any previously-migrated game, because only
registry-typed config dicts - as actually produced by
config_manager/config_exporter.py's _read_registry_key() - lack an
expanded_path key at all).

These tests prove three things:

1. The read side (extract_key_settings) goes through the new profiles'
   shared _registry_parse parser_fn (parse_mode="multi_file", the CS2
   mechanism) and produces results identical to calling the legacy
   _parse_registry_json directly on the matched registry entry.

2. Profile.matches() is exact, so neither profile hijacks a same-family but
   distinct title (Horizon Zero Dawn™ Complete Edition, Shadow of the Tomb
   Raider Trial).

3. write_settings() still reaches the EXISTING, UNMODIFIED legacy
   "registry_json" write branch (real, working, registry_io-based - not a
   skip, unlike GTA/SF6/Expedition33) now that a profile exists but has no
   writer_fn, using a production-shaped config dict (no "expanded_path" key,
   matching config_exporter._read_registry_key()'s real output) that would
   KeyError if the profile-first branch were ever mistakenly reached for
   this title.
"""

import json

from config_manager.settings_parser import extract_key_settings, _parse_registry_json
from config_manager.settings_writer import write_settings


class _FakeKey:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeWinreg:
    """Minimal stand-in for the winreg module, mirroring
    tests/test_write_safety.py's FakeWinreg exactly (duplicated locally
    rather than imported cross-file, since tests/ has no package __init__.py
    making that import path fragile)."""

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

HZD = "Horizon Zero Dawn™ Remastered"
SOTTR = "Shadow of the Tomb Raider"


def _hzd_registry_content(width=3840, height=2160, fullscreen=1, vsync=1, xess=1):
    return json.dumps({
        "Graphics": {
            "FullscreenWidth": width, "FullscreenHeight": height,
            "Fullscreen": fullscreen, "ExclusiveFullscreen": 1,
            "VSync": vsync, "DynamicResolutionTargetFPS": 60,
            "UpscaleMethod": 4, "UpscaleQuality": 3,
            "XESS": xess, "FrameGen": 0, "DLSSG": 0,
        }
    })


def _hzd_files(found=True, registry_content=None):
    registry_entry = {
        "type": "registry",
        "registry_path": "HKEY_CURRENT_USER\\Software\\Guerrilla Games\\Horizon Zero Dawn Remastered\\",
        "found": found,
        "content": registry_content if found else None,
        "error": None if found else "key_not_found",
    }
    profile_dat = {
        "type": "file", "expanded_path": "profile.dat",
        "found": False, "content": None, "error": "binary_file",
    }
    return [profile_dat, registry_entry]


def _sottr_registry_content(vsync=0, fullscreen=1, exclusive=1, xess=1):
    return json.dumps({
        "Graphics": {
            "Fullscreen": fullscreen, "ExclusiveFullscreen": exclusive,
            "FullscreenWidth": 3840, "FullscreenHeight": 2160,
            "RefreshRate": 144, "VSync": vsync, "ResolutionModifier": 1000,
            "DLSS": 0, "XESS": xess, "CAS": 0,
        }
    })


def _sottr_files_production_shape(content):
    """Mirrors config_manager/config_exporter.py's _read_registry_key()
    output exactly - no "expanded_path" key at all - the real shape that
    triggers the KeyError risk this profile's missing writer_fn sidesteps.
    """
    return [{
        "type": "registry",
        "registry_path": "HKEY_CURRENT_USER\\Software\\Eidos Montreal\\Shadow of the Tomb Raider\\",
        "found": True,
        "content": content,
        "error": None,
    }]


class TestReadParityHZD:
    def test_profile_dispatch_matches_legacy_parse(self):
        content = _hzd_registry_content()
        files = _hzd_files(registry_content=content)

        via_profile = extract_key_settings(HZD, files)
        via_legacy = _parse_registry_json(content)

        assert via_profile == via_legacy
        assert via_profile["resolution"] == "3840x2160"
        assert via_profile["screen_mode"] == "Exclusive Fullscreen"
        assert via_profile["vsync"] == "On"
        assert via_profile["upscaling"] == "XeSS"

    def test_key_not_found_returns_empty_result_like_legacy(self):
        """Matches this workstation's real observed state in
        validation/workstation.json: the registry key has never been
        populated (game not yet launched), found=false/content=null."""
        files = _hzd_files(found=False)

        from config_manager.settings_parser import _empty_result

        via_profile = extract_key_settings(HZD, files)
        via_legacy = extract_key_settings("Some Unmigrated Registry Game", files)

        assert via_profile == via_legacy == _empty_result()

    def test_exact_match_only_no_substring_collision(self):
        """The real, distinct, non-registry 'Complete Edition' title (empty
        config_files in validation/workstation.json) must never be routed
        through this profile - Profile.matches() is an exact
        (case-insensitive) title match, confirmed directly here."""
        from config_manager import profile_dispatch

        profile = profile_dispatch.find_profile(HZD)
        assert profile is not None
        assert not profile.matches("Horizon Zero Dawn™ Complete Edition")
        assert not profile.matches("Horizon Zero Dawn")


class TestReadParitySOTTR:
    def test_profile_dispatch_matches_legacy_parse(self):
        content = _sottr_registry_content()
        files = _sottr_files_production_shape(content)

        via_profile = extract_key_settings(SOTTR, files)
        via_legacy = _parse_registry_json(content)

        assert via_profile == via_legacy
        assert via_profile["resolution"] == "3840x2160"
        assert via_profile["screen_mode"] == "Exclusive Fullscreen"
        assert via_profile["vsync"] == "Off"
        assert via_profile["upscaling"] == "XeSS"

    def test_real_workstation_content_matches_legacy(self):
        """Exact byte-for-byte registry value blob copied from this
        checkout's validation/workstation.json "Shadow of the Tomb Raider"
        entry (confirmed found=true, error=null on this workstation)."""
        content = (
            "{\"Graphics\": {\"Fullscreen\": 1, \"ExclusiveFullscreen\": 1, "
            "\"FullscreenWidth\": 3840, \"FullscreenHeight\": 2160, "
            "\"RefreshRate\": 144, \"ForceHalfRefreshRate\": 0, \"VSync\": 0, "
            "\"ResolutionModifier\": 1000, \"DLSS\": 0, \"XESS\": 1, \"CAS\": 0}}"
        )
        files = _sottr_files_production_shape(content)

        via_profile = extract_key_settings(SOTTR, files)
        via_legacy = _parse_registry_json(content)

        assert via_profile == via_legacy

    def test_exact_match_only_no_substring_collision(self):
        from config_manager import profile_dispatch

        profile = profile_dispatch.find_profile(SOTTR)
        assert profile is not None
        assert not profile.matches("Shadow of the Tomb Raider Trial")
        assert not profile.matches("Shadow of the Tomb Raider: Definitive Edition")


class TestWriteStillReachesLegacyRegistryPath:
    """Confirms write_settings() does NOT crash and still reaches the
    existing, unmodified legacy "registry_json" write branch - real,
    registry_io-based, working writes, unlike GTA/SF6/Expedition33's "skip"
    outcome - now that a profile exists for these titles but declares no
    writer_fn. Uses the same FakeWinreg pattern as
    tests/test_write_safety.py's S7 registry tests."""

    def test_write_settings_succeeds_with_production_shaped_config(self, monkeypatch):
        from config_manager import registry_io

        # registry_path (from the production config dict, see
        # _sottr_files_production_shape) ends with a trailing backslash, so
        # registry_io.split_path/_join produces a *double* backslash before
        # the "Graphics" sub-key - matched here exactly as write_changes()
        # will actually compute it.
        graphics_key = "HKCU\\Software\\Eidos Montreal\\Shadow of the Tomb Raider\\\\Graphics"
        fake = FakeWinreg({
            graphics_key: {
                "VSync": (0, 4), "FullscreenWidth": (3840, 4), "FullscreenHeight": (2160, 4),
                "Fullscreen": (1, 4),
            },
        })
        monkeypatch.setattr(registry_io, "default_backend", lambda: fake)

        content = _sottr_registry_content(vsync=0)
        # Production shape: NO "expanded_path" key at all - this is the exact
        # shape that would KeyError in write_settings()'s profile-first branch
        # if this profile ever declared a writer_fn.
        files = _sottr_files_production_shape(content)

        results = write_settings(SOTTR, files, {"vsync": "On"})

        assert results[0]["status"] == "ok", results
        assert fake.set_calls == [(graphics_key, "VSync", 4, 1)]

    def test_profile_has_no_writer_fn_so_profile_first_branch_is_never_entered(self):
        """Direct confirmation of the mechanism: profile.writer_fn is None,
        so write_settings()'s 'if profile is not None and profile.writer_fn'
        guard is False and the cfg["expanded_path"] bracket access is never
        reached for this title at all."""
        from config_manager import profile_dispatch

        for name in (HZD, SOTTR):
            profile = profile_dispatch.find_profile(name)
            assert profile is not None
            assert profile.writer_fn is None
