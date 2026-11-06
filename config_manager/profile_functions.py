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


def register_all() -> None:
    _registry.register("parser_fn", "black_myth_parse", _black_myth_parse)
    _registry.register("writer_fn", "black_myth_write", _black_myth_write)
    _registry.register("parser_fn", "black_myth_benchmark_parse", _black_myth_benchmark_parse)
    _registry.register("writer_fn", "black_myth_benchmark_write", _black_myth_benchmark_write)


register_all()
