"""Profile-first dispatch helper (P1 handoff §4.2): "先找 profile，找不到才走舊路徑".

``settings_parser.extract_key_settings`` and ``settings_writer.write_settings``
call :func:`find_profile` before falling back to their hard-coded
``if "name" in game_name`` chains, so games can be migrated to profiles one
at a time without a single big-bang rewrite. Profiles are loaded once and
cached; call :func:`reset_cache` after editing profile files in a test.
"""

from __future__ import annotations

from typing import Dict, Optional

from .profiles.loader import Profile, load_all

_cache: Optional[Dict[str, Profile]] = None


def _profiles() -> Dict[str, Profile]:
    global _cache
    if _cache is None:
        _cache = load_all()
    return _cache


def find_profile(game_name: str) -> Optional[Profile]:
    for profile in _profiles().values():
        if profile.matches(game_name):
            return profile
    return None


def reset_cache() -> None:
    global _cache
    _cache = None
