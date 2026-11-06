"""Whole-file raw-text codec, for files that hold a single value with no
key/value structure (e.g. Forza's ``fullscreen_choice`` sidecar file).

``key_spec`` is ignored (``None``); the entire file content is the value.
"""

from __future__ import annotations

from typing import Optional


def read(content: str, key_spec: object = None) -> Optional[str]:
    return content


def patch(content: str, key_spec: object, raw_value: str) -> str:
    return raw_value
