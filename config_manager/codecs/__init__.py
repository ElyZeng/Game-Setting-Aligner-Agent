"""Generic file-format codecs used by game profiles (P1, see GSAA_support_expansion_proposal.md §3.3).

Each codec module exposes two functions operating on whole file *content*
(not paths — callers are responsible for I/O via ``safe_io``):

``read(content, key_spec) -> raw value or None``
    Extract the raw string value addressed by *key_spec* (codec-specific:
    an INI key name, an ``(tag, attr)`` pair, a Valve KV key, ...).

``patch(content, key_spec, raw_value) -> new content``
    Replace only the targeted fragment, leaving everything else (including
    byte-for-byte formatting of untouched lines) unchanged. If the key is
    not present, ``patch`` returns *content* unchanged — callers that need
    to know whether a write took effect should call ``read`` first.

These wrap logic that used to be duplicated per-game in
``settings_writer.py`` (``_replace_ini_value``, ``_replace_xml_attr``,
``_replace_valve_kv_value``); those names are kept in ``settings_writer.py``
as thin re-exports for backward compatibility.
"""

from __future__ import annotations

from . import ini, raw_text, valve_kv, xml_attr

CODECS = {
    "ini": ini,
    "unreal_ini": ini,  # same `Key=Value` line format; engine-specific keys live in profiles, not the codec
    "xml_attr": xml_attr,
    "valve_kv": valve_kv,
    "raw_text": raw_text,
}


def get_codec(name: str):
    try:
        return CODECS[name]
    except KeyError:
        raise ValueError(f"Unknown codec: {name!r} (known: {sorted(CODECS)})") from None


__all__ = ["CODECS", "get_codec", "ini", "xml_attr", "valve_kv", "raw_text"]
