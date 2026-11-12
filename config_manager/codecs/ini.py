"""``Key=Value`` INI-style codec (used by Unreal Engine's GameUserSettings.ini
and similar line-oriented config files).

``key_spec`` is the bare key name, e.g. ``"ResolutionSizeX"``.
"""

from __future__ import annotations

import re
from typing import Optional


def read(content: str, key_spec: str) -> Optional[str]:
    pattern = re.compile(rf"^\s*{re.escape(key_spec)}\s*=\s*(.*)$", re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return None
    return match.group(1).rstrip("\r\n")


def patch(content: str, key_spec: str, raw_value: str) -> str:
    pattern = re.compile(rf"^(\s*{re.escape(key_spec)}\s*=\s*)(.*)$", re.MULTILINE)
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{raw_value}", content)
    return content
