"""Named-function registry for game profiles (see proposal §3.3).

Profiles reference special-case logic (e.g. Forza's refresh-relative frame
rate, Black Myth's intertwined quality/upscaling fields) by *name* instead of
embedding code, so a profile stays declarative data. The actual Python
callables are registered here by ``config_manager.profile_functions`` (and,
over time, per-game registration modules) at import time.

Three independent namespaces are kept (``map_fn`` for a single setting,
``parser_fn``/``writer_fn`` for "read/write everything this profile covers in
one call" — the escape hatch used for games whose fields are too
interdependent to decompose yet) so the same short name can mean different
things in different roles without colliding.
"""

from __future__ import annotations

from typing import Callable, Dict

_registries: Dict[str, Dict[str, Callable]] = {
    "map_fn": {},
    "parser_fn": {},
    "writer_fn": {},
    "preset_fn": {},
}


class FunctionRegistryError(KeyError):
    """Raised when a profile references a function name that was never registered."""


def register(kind: str, name: str, fn: Callable, *, overwrite: bool = False) -> None:
    if kind not in _registries:
        raise ValueError(f"Unknown function registry kind: {kind!r} (known: {sorted(_registries)})")
    table = _registries[kind]
    if not overwrite and name in table and table[name] is not fn:
        raise FunctionRegistryError(
            f"{kind} function {name!r} is already registered to a different callable"
        )
    table[name] = fn


def get(kind: str, name: str) -> Callable:
    try:
        table = _registries[kind]
    except KeyError:
        raise ValueError(f"Unknown function registry kind: {kind!r} (known: {sorted(_registries)})") from None
    try:
        return table[name]
    except KeyError:
        raise FunctionRegistryError(
            f"No {kind} function registered as {name!r}. "
            f"Known: {sorted(table)}. Register it in config_manager/profile_functions.py."
        ) from None


def names(kind: str):
    return sorted(_registries.get(kind, {}))


def _reset_for_tests() -> None:
    """Test-only helper: clear all registrations."""
    for table in _registries.values():
        table.clear()
