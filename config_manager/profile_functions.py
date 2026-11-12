"""Registers the named functions that game profiles reference by name
(``parser_fn`` / ``writer_fn`` / ``map_fn`` / ``preset_fn``).

Importing this module has the side effect of populating
``config_manager.function_registry``. ``profiles.loader`` imports it before
validating any profile so a profile that names an unregistered function fails
fast (at load time, not at first use) — see the "profile 寫錯時要在啟動和測試時
就失敗" requirement in the P1 handoff.

P1 step 1 (Black Myth: Wukong migration): the profile does not yet decompose
Black Myth's fields into per-setting ``key``/``map`` entries — its resolution,
quality-level and upscaling-mode logic are too interdependent (see
``settings_parser._parse_black_myth`` / ``settings_writer._write_black_myth_ini``)
to safely split up in one pass. Instead the profile's ``parser_fn``/``writer_fn``
point at thin wrappers around those *existing* functions below, so behaviour
is guaranteed byte-identical to the pre-profile code (it IS the pre-profile
code) — only the profile's ``match``/``verified``/``anticheat``/``fingerprint``
metadata is new. Decomposing the Black Myth logic into pure declarative
fields is left for a follow-up pass once the loader/dispatch plumbing is
proven out.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from . import function_registry as _registry


def _black_myth_parse(content: str) -> Dict[str, Optional[str]]:
    from .settings_parser import _parse_black_myth

    return _parse_black_myth(content, benchmark=False)


def _black_myth_write(content: str, settings: Dict[str, Optional[str]]) -> str:
    from .settings_writer import _write_black_myth_ini

    return _write_black_myth_ini(content, settings, benchmark=False)


def _black_myth_benchmark_parse(content: str) -> Dict[str, Optional[str]]:
    from .settings_parser import _parse_black_myth

    return _parse_black_myth(content, benchmark=True)


def _black_myth_benchmark_write(content: str, settings: Dict[str, Optional[str]]) -> str:
    from .settings_writer import _write_black_myth_ini

    return _write_black_myth_ini(content, settings, benchmark=True)


def _f1_25_parse(content: str) -> Dict[str, Optional[str]]:
    from .settings_parser import _parse_f1_xml

    return _parse_f1_xml(content)


def _f1_25_write(content: str, settings: Dict[str, Optional[str]]) -> str:
    from .settings_writer import _write_f1_xml

    return _write_f1_xml(content, settings)


def _cs2_parse(config_files: Any) -> Dict[str, Optional[str]]:
    """Note: receives the *full* config-file list (``parse_mode:
    "multi_file"``), not a single file's content — CS2's settings are split
    across ``cs2_video.txt`` (resolution/vsync/upscaling) and a separate
    convars file (``fps_max`` for frame_limit), see
    ``settings_parser._parse_cs2`` and the CS2 profile's ``_parser_fn_note``.
    """
    from .settings_parser import _parse_cs2

    return _parse_cs2(config_files)


def _cs2_write(content: str, settings: Dict[str, Optional[str]]) -> str:
    from .settings_writer import _write_cs2_video

    return _write_cs2_video(content, settings)


def _forza_parse(content: str) -> Dict[str, Optional[str]]:
    from .settings_parser import _parse_forza_xml

    return _parse_forza_xml(content)


def _forza_write(content: str, settings: Dict[str, Optional[str]]) -> str:
    from .settings_writer import _write_forza_xml

    return _write_forza_xml(content, settings)


def _forza_fullscreen_sidecar(config_files: Any, settings: Dict[str, Optional[str]]) -> list:
    """Mirrors the legacy write_settings() 'forza_xml' branch's sidecar
    write: when screen_mode is part of what's being written, also persist a
    single raw byte (1=Fullscreen, else 0) to the sibling 'fullscreen_choice'
    file located via settings_writer.forza_auxiliary_paths. See
    forza-horizon-6.json's _write_side_effect_fn_note for the full rationale.
    """
    from .safe_io import atomic_write_bytes
    from .settings_parser import SCREEN_MODE
    from .settings_writer import forza_auxiliary_paths

    results = []
    if SCREEN_MODE in settings:
        fullscreen_value = bytes([1 if settings[SCREEN_MODE] == "Fullscreen" else 0])
        for auxiliary_path in forza_auxiliary_paths(config_files):
            atomic_write_bytes(auxiliary_path, fullscreen_value)
            results.append({"path": auxiliary_path, "status": "ok", "detail": "Forza fullscreen choice written"})
    return results


def _cyberpunk_parse(content: str) -> Dict[str, Optional[str]]:
    from .settings_parser import _parse_cyberpunk

    return _parse_cyberpunk(content)


def _cyberpunk_write(content: str, settings: Dict[str, Optional[str]]) -> str:
    from .settings_writer import _write_cyberpunk

    return _write_cyberpunk(content, settings)


def _gta_enhanced_parse(content: str) -> Dict[str, Optional[str]]:
    """Read-only: no _gta_enhanced_write wrapper exists on purpose. See
    grand-theft-auto-v-enhanced.json's _parser_fn_note for why this profile
    does not (and must not) declare a writer_fn.
    """
    from .settings_parser import _parse_gta_enhanced_xml

    return _parse_gta_enhanced_xml(content)


def _expedition_33_parse(content: str) -> Dict[str, Optional[str]]:
    """Read-only: no writer wrapper exists on purpose. See
    clair-obscur-expedition-33.json's _parser_fn_note - this title's real
    writer_fn gap (it used to fall through to the generic "unreal_ini"
    writer by accident) was fixed in settings_writer._detect_parser_type()
    as part of this same migration, not papered over here.
    """
    from .settings_parser import _parse_expedition_33

    return _parse_expedition_33(content)


def _sf6_parse(content: str) -> Dict[str, Optional[str]]:
    """Read-only: no _write_sf6 function exists anywhere in the codebase,
    by design. See street-fighter-6.json's _parser_fn_note.
    """
    from .settings_parser import _parse_sf6

    return _parse_sf6(content)


def _registry_parse(config_files: Any) -> Dict[str, Optional[str]]:
    """Shared multi_file parser_fn for the registry-based titles (Horizon Zero
    Dawn (TM) Remastered, Shadow of the Tomb Raider). Receives the *full*
    config-file list (``parse_mode: "multi_file"``, the CS2 mechanism) and
    filters it for the one entry with ``type == "registry"`` itself, mirroring
    _cs2_parse's established pattern - extract_key_settings()'s filename-based
    _content_for() helper has no registry-path-shaped candidate to match
    against, so this bypasses it entirely, same as CS2 does for its split
    files. _parse_registry_json's ``game_hint`` parameter is accepted but
    never branched on anywhere in its body (confirmed by reading it in full),
    so this single wrapper is correct for both titles rather than two
    near-duplicate ones. Read-only: no writer wrapper exists on purpose - see
    horizon-zero-dawn-remastered.json / shadow-of-the-tomb-raider.json's
    _parser_fn_note for the full rationale (an unguarded ``cfg["expanded_path"]``
    bracket access in settings_writer.write_settings()'s profile-first write
    dispatch would KeyError against config_exporter._read_registry_key()-shaped
    production entries, which never set expanded_path at all).
    """
    from .settings_parser import _empty_result, _parse_registry_json

    for cfg in config_files:
        if cfg.get("type") == "registry" and cfg.get("content"):
            return _parse_registry_json(cfg["content"])
    return _empty_result()


def register_all() -> None:
    _registry.register("parser_fn", "black_myth_parse", _black_myth_parse)
    _registry.register("writer_fn", "black_myth_write", _black_myth_write)
    _registry.register("parser_fn", "black_myth_benchmark_parse", _black_myth_benchmark_parse)
    _registry.register("writer_fn", "black_myth_benchmark_write", _black_myth_benchmark_write)
    _registry.register("parser_fn", "f1_25_parse", _f1_25_parse)
    _registry.register("writer_fn", "f1_25_write", _f1_25_write)
    _registry.register("parser_fn", "cs2_parse", _cs2_parse)
    _registry.register("writer_fn", "cs2_write", _cs2_write)
    _registry.register("parser_fn", "forza_parse", _forza_parse)
    _registry.register("writer_fn", "forza_write", _forza_write)
    _registry.register("write_side_effect_fn", "forza_fullscreen_sidecar", _forza_fullscreen_sidecar)
    _registry.register("parser_fn", "cyberpunk_parse", _cyberpunk_parse)
    _registry.register("writer_fn", "cyberpunk_write", _cyberpunk_write)
    _registry.register("parser_fn", "gta_enhanced_parse", _gta_enhanced_parse)
    _registry.register("parser_fn", "expedition_33_parse", _expedition_33_parse)
    _registry.register("parser_fn", "sf6_parse", _sf6_parse)
    _registry.register("parser_fn", "registry_parse", _registry_parse)


register_all()
