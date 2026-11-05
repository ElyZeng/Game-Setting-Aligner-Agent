"""Detect anti-cheat components shipped with a game.

Policy (see DISCLAIMER.md): if any anti-cheat component is detected in the
game's install folder, writes are refused unless the matching rule carries an
approved per-game review whose recorded components are exactly the ones found
now, and every setting being written is inside the reviewed scope.  A game
update that adds a new component therefore drops back to read-only until it
is reviewed again.

Detection is a bounded walk of the install folder looking for well-known
folder and file names.  Kernel-level systems installed outside the game folder
(for example Riot Vanguard) are not covered by this check.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

# Lower-case folder names -> vendor
_DIR_MARKERS: Dict[str, str] = {
    "easyanticheat": "EasyAntiCheat",
    "easyanticheat_eos": "EasyAntiCheat",
    "battleye": "BattlEye",
    "eaanticheat": "EA Javelin",
    "gameguard": "nProtect GameGuard",
    "xigncode": "XIGNCODE3",
    "xigncode3": "XIGNCODE3",
    "anticheatexpert": "Anti-Cheat Expert",
    "pb": "PunkBuster",
}

# Lower-case file-name prefixes -> vendor
_FILE_PREFIXES: Dict[str, str] = {
    "easyanticheat": "EasyAntiCheat",
    "start_protected_game": "EasyAntiCheat",
    "beservice": "BattlEye",
    "beclient": "BattlEye",
    "eaanticheat": "EA Javelin",
    "gameguard": "nProtect GameGuard",
    "x3.xem": "XIGNCODE3",
    "pnkbstr": "PunkBuster",
    "pbsvc": "PunkBuster",
    "ace-base": "Anti-Cheat Expert",
    "mhyprot": "mhyprot",
}

# "pb" is too generic on its own; only count it with a PunkBuster binary inside.
_REQUIRES_CONFIRMATION = {"pb"}

MAX_DEPTH = 3
MAX_ENTRIES = 20000

Detector = Callable[[str], Sequence[str]]


def detect_anticheat(install_path: str, max_depth: int = MAX_DEPTH, max_entries: int = MAX_ENTRIES) -> List[str]:
    """Sorted vendor names of anti-cheat components found under *install_path*."""
    if not install_path or not Path(install_path).is_dir():
        return []
    root = Path(install_path)
    found = set()
    seen = 0
    stack = [(root, 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if seen > max_entries:
                return sorted(found)
            name = entry.name.lower()
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                vendor = _DIR_MARKERS.get(name)
                if vendor and name in _REQUIRES_CONFIRMATION:
                    try:
                        children = [child.lower() for child in os.listdir(entry.path)]
                    except OSError:
                        children = []
                    if not any(child.startswith(("pnkbstr", "pbsvc", "pbcl")) for child in children):
                        vendor = None
                if vendor:
                    found.add(vendor)
                if depth < max_depth:
                    stack.append((Path(entry.path), depth + 1))
            else:
                for prefix, vendor in _FILE_PREFIXES.items():
                    if name.startswith(prefix):
                        found.add(vendor)
                        break
    return sorted(found)


def check_write_allowed(
    detected: Iterable[str], rule: Optional[Dict], settings: Iterable[str]
) -> Optional[str]:
    """Return a refusal reason, or ``None`` if the write may proceed."""
    detected_set = set(detected)
    if not detected_set:
        return None
    names = ",".join(sorted(detected_set))
    review = (rule or {}).get("anticheat")
    if not isinstance(review, dict) or review.get("review") != "approved":
        return f"anticheat_not_reviewed:{names}"
    if set(review.get("detected") or []) != detected_set:
        return f"anticheat_changed_since_review:{names}"
    scope = review.get("scope")
    if not isinstance(scope, list):
        return f"anticheat_scope_missing:{names}"
    outside = sorted(set(settings) - set(scope))
    if outside:
        return f"anticheat_scope:{','.join(outside)}"
    return None
