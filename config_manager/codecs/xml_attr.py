"""XML-attribute codec: ``<tag ... attr="value" ...>`` patched via regex
(not a full XML parse/serialise round-trip, so unrelated formatting,
comments and attribute order are left untouched).

``key_spec`` is an ``(tag, attr)`` tuple.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

KeySpec = Tuple[str, str]


def read(content: str, key_spec: KeySpec) -> Optional[str]:
    tag, attr = key_spec
    pattern = re.compile(
        rf'<{re.escape(tag)}\b[^>]*\b{re.escape(attr)}="([^"]*)"'
    )
    match = pattern.search(content)
    return match.group(1) if match else None


def patch(content: str, key_spec: KeySpec, raw_value: str) -> str:
    tag, attr = key_spec
    pattern = re.compile(
        rf'(<{re.escape(tag)}\b[^>]*\b{re.escape(attr)}=")([^"]*)(")',
    )
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{raw_value}\g<3>", content)
    return content


def read_option(content: str, option_id: str) -> Optional[str]:
    """Read ``<option id="..." value="...">`` (Forza/F1-style option lists)."""
    pattern = re.compile(
        rf'<option\s+id="{re.escape(option_id)}"\s+value="([^"]*)"',
    )
    match = pattern.search(content)
    return match.group(1) if match else None


def patch_option(content: str, option_id: str, raw_value: str) -> str:
    pattern = re.compile(
        rf'(<option\s+id="{re.escape(option_id)}"\s+value=")([^"]*)(")',
    )
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{raw_value}\g<3>", content)
    return content
