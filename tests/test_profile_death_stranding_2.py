"""Parity tests for the Death Stranding 2: On the Beach profile (Stage 3 of
[[reference_new_game_onboarding_workflow]] - see
validation-evidence/20 - Death Stranding 2/COLLECT.txt for the full
discovery trail).

This is a deliberately READ-ONLY migration for this round - see
death-stranding-2.json's ``_parser_fn_note`` for the full rationale,
including why the initial discovery pass concluded (wrongly) that this
title had no readable settings store at all, and how a second,
``-Recurse`` registry read corrected that.

These tests mirror tests/test_profile_registry_games.py's structure for the
two existing registry-based titles (Horizon Zero Dawn (TM) Remastered,
Shadow of the Tomb Raider) and prove the same three things for this title:

1. The read side (extract_key_settings) goes through this title's own
   _death_stranding_2_registry_parse parser_fn (parse_mode="multi_file"),
   which is _parse_registry_json's existing generic registry-JSON parser
   called with game_hint="death stranding 2" - no new parsing logic, just a
   per-game override of two values this generic path got wrong for THIS
   title (screen_mode and UpscaleMethod/UpscaleQuality), live-confirmed via
   VLM/OCR against the real in-game Display Settings tab
   (validation-evidence/20 - Death Stranding 2/COLLECT.txt round 2/3,
   2026-11-12). Calling _parse_registry_json directly without that
   game_hint (as HZD/SotTR's shared _registry_parse wrapper still does)
   reproduces the old, pre-fix generic values - that's intentional, not a
   discrepancy, since HZD/SotTR's own COLLECT.txt logs never actually
   live-validated these same fields and so are deliberately left untouched.

2. Profile.matches() is exact, so a hypothetical differently-punctuated or
   related title string does not get silently routed through this profile.

3. write_settings() still reaches the EXISTING, UNMODIFIED legacy
   "registry_json" write branch (shape-based dispatch on
   cfg["type"] == "registry", not a name check) now that a profile exists
   for this title but declares no writer_fn - same mechanism already
   exercised by HZD Remastered / Shadow of the Tomb Raider.
"""

import json

from config_manager.settings_parser import extract_key_settings, _parse_registry_json
from config_manager.settings_writer import write_settings

GAME = "DEATH STRANDING 2: ON THE BEACH"
REGISTRY_PATH = "HKEY_CURRENT_USER\\SOFTWARE\\KOJIMA PRODUCTIONS\\DEATH STRANDING 2 - ON THE BEACH\\"


def _ds2_registry_content(
    width=1920, height=1080, fullscreen=1, exclusive=0, vsync=1,
    dynamic_res_fps=60, upscale_method=1, upscale_quality=3, frame_gen=0,
):
    """Field names/shape and these exact default values are copied from the
    real registry dump taken on the .9 test-machine after the user manually
    saved Graphics/Video settings in-game (see death-stranding-2.json's
    _parser_fn_note and [[gsaa_death_stranding2_onboarding]])."""
    return json.dumps({
        "Graphics": {
            "Monitor": 0, "Version": 6,
            "Fullscreen": fullscreen, "ExclusiveFullscreen": exclusive,
            "WindowWidth": 1920, "WindowHeight": 1080,
            "FullscreenWidth": width, "FullscreenHeight": height,
            "RefreshRate": 144, "VSync": vsync,
            "FOVCorrection": 1000, "Sharpness": 500,
            "DynamicResolutionTargetFPS": dynamic_res_fps,
            "FrameGen": frame_gen, "MaxGeneratedFrame": 256,
            "TextureQuality": 1, "ShadowQuality": 2,
            "UpscaleMethod": upscale_method, "UpscaleQuality": upscale_quality,
            "HDR": 0, "HDRMaxNits": 565711,
        },
        "Audio": {"Main Output Device": 0},
        "Input": {"MouseHorizontalSensitivity": 40000},
    })


def _ds2_files_production_shape(content):
    """Mirrors config_manager/config_exporter.py's _read_registry_key()
    output exactly - no "expanded_path" key at all - matching the
    production shape used by the two existing registry-profile tests."""
    return [{
        "type": "registry",
        "registry_path": REGISTRY_PATH,
        "found": True,
        "content": content,
        "error": None,
    }]


class TestReadParity:
    def test_profile_dispatch_matches_legacy_parse(self):
        content = _ds2_registry_content()
        files = _ds2_files_production_shape(content)

        via_profile = extract_key_settings(GAME, files)
        via_legacy = _parse_registry_json(content, game_hint="death stranding 2")

        assert via_profile == via_legacy
        assert via_profile["resolution"] == "1920x1080"
        assert via_profile["screen_mode"] == "Fullscreen"
        assert via_profile["vsync"] == "On"
        assert via_profile["upscaling"] == "PICO"
        assert via_profile["upscaling_mode"] == "Dynamic"
        assert via_profile["frame_generation"] == "Off"
        # quick_preset: no discrete preset-name field exists anywhere in this
        # title's registry (confirmed during discovery - presets just bulk-set
        # several quality keys at once) - _parse_registry_json hard-codes N/A
        # for every registry-based title, this one included.
        assert via_profile["quick_preset"] == "N/A"

    def test_exclusive_fullscreen_and_frame_gen_on(self):
        content = _ds2_registry_content(exclusive=1, frame_gen=1)
        files = _ds2_files_production_shape(content)

        via_profile = extract_key_settings(GAME, files)
        via_legacy = _parse_registry_json(content, game_hint="death stranding 2")

        assert via_profile == via_legacy
        assert via_profile["screen_mode"] == "Exclusive Fullscreen"
        assert via_profile["frame_generation"] == "Frame Gen: On"

    def test_windowed_mode(self):
        content = _ds2_registry_content(fullscreen=0)
        files = _ds2_files_production_shape(content)

        via_profile = extract_key_settings(GAME, files)
        via_legacy = _parse_registry_json(content, game_hint="death stranding 2")

        assert via_profile == via_legacy
        assert via_profile["screen_mode"] == "Windowed"

    def test_real_dot9_observed_content_matches_legacy(self):
        """Byte-for-byte-equivalent (field names/values) to the real dump
        taken on the .9 test-machine's HKCU Graphics sub-key after the
        user's third preset switch (M = Medium) - see
        [[gsaa_death_stranding2_onboarding]] for the raw dump this was
        transcribed from."""
        content = json.dumps({
            "Graphics": {
                "Monitor": 0, "Version": 6, "Fullscreen": 1, "ExclusiveFullscreen": 0,
                "WindowLeft": 240, "WindowTop": 135, "WindowWidth": 1920, "WindowHeight": 1080,
                "UserWindowWidth": 1440, "UserWindowHeight": 810, "WindowMaximized": 0,
                "MultiMonitorEnabled": 0, "AspectRatio": 0, "ForcedAspectRatio": 0,
                "CorrectForNonSquarePixels": 1, "FullscreenWidth": 1920, "FullscreenHeight": 1080,
                "RefreshRate": 144, "VSync": 1, "FOVCorrection": 1000, "Sharpness": 500,
                "Brightness": 5000, "Contrast": 1000, "DynamicResolutionTargetFPS": 60,
                "LatencyReductionMode": 0, "FrameGen": 0, "MaxGeneratedFrame": 256,
                "TextureQuality": 1, "TextureFiltering": 2, "ShadowQuality": 2,
                "ShadowResolution": 2, "DOFQuality": 1, "MotionBlurScale": 500,
                "AmbientOcclusionQuality": 1, "Vignette": 1, "LevelOfDetail": 2,
                "ScreenSpaceReflections": 1, "AA": 3, "ScreenSpaceShadows": 1,
                "Lighting": 1, "TranslucencyQuality": 0, "TerrainQuality": 1,
                "CloudsQuality": 1, "AsyncCompute": 1, "UpscaleMethod": 1,
                "UpscaleQuality": 3, "HDR": 0, "HDRMaxNits": 565711,
                "HDRGamma": 5000, "HDRBrightness": 50000, "ProcessWorkingSetSize": 0,
                "IncreasedMemoryStreamingCache": 1,
            }
        })
        files = _ds2_files_production_shape(content)

        via_profile = extract_key_settings(GAME, files)
        via_legacy = _parse_registry_json(content, game_hint="death stranding 2")

        assert via_profile == via_legacy
        assert via_profile["resolution"] == "1920x1080"
        assert via_profile["screen_mode"] == "Fullscreen"
        assert via_profile["vsync"] == "On"
        assert via_profile["dynamic_resolution"] == "On (Target: 60 FPS)"
        assert via_profile["upscaling"] == "PICO"
        assert via_profile["upscaling_mode"] == "Dynamic"

    def test_without_game_hint_reproduces_old_generic_values(self):
        """Documents the intentional divergence: calling the shared generic
        parser with no game_hint (what HZD/SotTR's _registry_parse wrapper
        still does) reproduces the old, now-known-wrong-for-DS2 values. This
        is not a bug in the generic path for HZD/SotTR - it's just evidence
        that the DS2 profile's own dedicated parser_fn (which does pass
        game_hint) is what actually fixes this title."""
        content = _ds2_registry_content()

        generic = _parse_registry_json(content)

        assert generic["screen_mode"] == "Borderless Fullscreen"
        assert generic["upscaling"] == "DLSS"
        assert generic["upscaling_mode"] == "Quality"

    def test_profile_uses_its_own_parser_fn_not_the_shared_one(self):
        from config_manager import profile_dispatch

        profile = profile_dispatch.find_profile(GAME)
        assert profile is not None
        assert profile.parser_fn == "death_stranding_2_registry_parse"

    def test_exact_match_only_no_substring_collision(self):
        from config_manager import profile_dispatch

        profile = profile_dispatch.find_profile(GAME)
        assert profile is not None
        assert not profile.matches("DEATH STRANDING 2")
        assert not profile.matches("DEATH STRANDING")
        # The install-folder-shaped name variant must match too (both are
        # declared in match.names - Steam's display name uses ": ", the
        # on-disk folder/registry key uses " - ").
        assert profile.matches("DEATH STRANDING 2 - ON THE BEACH")


class TestWriteStillReachesLegacyRegistryPath:
    """Confirms write_settings() does NOT crash and still reaches the
    existing, unmodified legacy "registry_json" write branch now that a
    profile exists for this title but declares no writer_fn - same
    mechanism as HZD Remastered / Shadow of the Tomb Raider
    (tests/test_profile_registry_games.py), exercised here with this
    title's own registry path."""

    def test_write_settings_succeeds_with_production_shaped_config(self, monkeypatch):
        from config_manager import registry_io
        from tests.test_profile_registry_games import FakeWinreg

        # registry_io.split_path() resolves the hive name to the backend's
        # HKEY_CURRENT_USER attribute (= FakeWinreg.HKEY_CURRENT_USER = "HKCU"
        # here) before OpenKey ever sees it, so the fake key dict must be
        # keyed on "HKCU", not the literal "HKEY_CURRENT_USER" prefix used in
        # REGISTRY_PATH - confirmed against tests/test_profile_registry_games.py's
        # SOTTR fixture, which uses the same "HKCU\\...\\\\Graphics" shape.
        graphics_key = "HKCU\\" + REGISTRY_PATH.split("\\", 1)[1] + "\\Graphics"
        fake = FakeWinreg({
            graphics_key: {
                "VSync": (0, 4), "FullscreenWidth": (1920, 4), "FullscreenHeight": (1080, 4),
                "Fullscreen": (1, 4),
            },
        })
        monkeypatch.setattr(registry_io, "default_backend", lambda: fake)

        content = _ds2_registry_content(vsync=0)
        files = _ds2_files_production_shape(content)

        results = write_settings(GAME, files, {"vsync": "On"})

        assert results[0]["status"] == "ok", results
        assert fake.set_calls == [(graphics_key, "VSync", 4, 1)]

    def test_profile_has_no_writer_fn_so_profile_first_branch_is_never_entered(self):
        from config_manager import profile_dispatch

        profile = profile_dispatch.find_profile(GAME)
        assert profile is not None
        assert profile.writer_fn is None
