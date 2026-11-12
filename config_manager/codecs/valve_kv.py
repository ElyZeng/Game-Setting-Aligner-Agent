"""Valve KeyValues (VDF-lite) codec: ``"key" "value"`` lines, one per line.

``key_spec`` is the bare key name, e.g. ``"fullscreen"``.
"""

from __future__ import annotations

import re
from typing import Optional


def read(content: str, key_spec: str) -> Optional[str]:
    pattern = re.compile(
        rf'^\s*"{re.escape(key_spec)}"\s+"([^"]*)"$', re.MULTILINE
    )
    match = pattern.search(content)
    return match.group(1) if match else None


def patch(content: str, key_spec: str, raw_value: str) -> str:
    pattern = re.compile(
        rf'^(\s*"{re.escape(key_spec)}"\s+")([^"]*)(")$', re.MULTILINE
    )
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{raw_value}\g<3>", content)
    return content
