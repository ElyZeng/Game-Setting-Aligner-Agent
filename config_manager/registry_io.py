"""Guarded Windows-registry access for games that keep settings in the registry.

Rules enforced here:

* Only values that actually change are written; everything else in the key
  is left untouched.
* A value is only written if it already exists, and it keeps its original
  registry type.  Only ``REG_DWORD`` / ``REG_QWORD`` (integers) and
  ``REG_SZ`` / ``REG_EXPAND_SZ`` (strings) can be written; binary and other
  types are refused.
* Before a write the affected keys are snapshotted (values *and* types) so the
  exact previous state can be restored and verified.

The ``winreg`` module is injected as *backend* so the logic can be unit-tested
on any platform with a fake implementation.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional, Tuple

_HIVE_NAMES = {
    "HKEY_CURRENT_USER": "HKEY_CURRENT_USER",
    "HKCU": "HKEY_CURRENT_USER",
    "HKEY_LOCAL_MACHINE": "HKEY_LOCAL_MACHINE",
    "HKLM": "HKEY_LOCAL_MACHINE",
}


class RegistryWriteError(ValueError):
    """A registry write was refused or could not be verified."""


def default_backend() -> Any:
    try:
        import winreg  # type: ignore
    except ImportError as exc:  # pragma: no cover - non-Windows
        raise RegistryWriteError("registry_not_available") from exc
    return winreg


def split_path(reg_path: str, backend: Any) -> Tuple[Any, str]:
    parts = str(reg_path).replace("/", "\\").split("\\", 1)
    hive_name = _HIVE_NAMES.get(parts[0].upper())
    if hive_name is None:
        raise RegistryWriteError(f"registry_unknown_hive:{parts[0]}")
    return getattr(backend, hive_name), (parts[1] if len(parts) > 1 else "")


def _join(subkey: str, child: str) -> str:
    return f"{subkey}\\{child}" if child else subkey


def _serialise(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return {"bytes_b64": base64.b64encode(bytes(value)).decode("ascii")}
    return value


def _deserialise(value: Any) -> Any:
    if isinstance(value, dict) and "bytes_b64" in value:
        return base64.b64decode(value["bytes_b64"])
    return value


def _read_values(backend: Any, hive: Any, subkey: str) -> Dict[str, Tuple[Any, int]]:
    values: Dict[str, Tuple[Any, int]] = {}
    with backend.OpenKey(hive, subkey, 0, backend.KEY_READ) as key:
        index = 0
        while True:
            try:
                name, value, value_type = backend.EnumValue(key, index)
            except OSError:
                break
            values[name or "(Default)"] = (value, value_type)
            index += 1
    return values


def _subkeys(backend: Any, hive: Any, subkey: str) -> List[str]:
    names: List[str] = []
    with backend.OpenKey(hive, subkey, 0, backend.KEY_READ) as key:
        index = 0
        while True:
            try:
                names.append(backend.EnumKey(key, index))
            except OSError:
                break
            index += 1
    return names


def read_key_as_json(reg_path: str, backend: Any = None) -> Dict[str, Any]:
    """Same shape as ``config_exporter._read_registry_key`` (values + one level of sub-keys)."""
    backend = backend or default_backend()
    entry: Dict[str, Any] = {
        "type": "registry", "registry_path": reg_path, "expanded_path": reg_path,
        "found": False, "content": None, "error": None,
    }
    hive, subkey = split_path(reg_path, backend)
    try:
        data: Dict[str, Any] = {name: value for name, (value, _t) in _read_values(backend, hive, subkey).items()}
        for child in _subkeys(backend, hive, subkey):
            try:
                child_values = _read_values(backend, hive, _join(subkey, child))
            except OSError:
                continue
            if child_values:
                data[child] = {name: value for name, (value, _t) in child_values.items()}
    except FileNotFoundError:
        entry["error"] = "key_not_found"
        return entry
    entry["found"] = True
    entry["content"] = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    return entry


def snapshot(reg_path: str, backend: Any = None) -> Dict[str, Any]:
    """Values and types of the key and its immediate sub-keys."""
    backend = backend or default_backend()
    hive, subkey = split_path(reg_path, backend)
    keys: Dict[str, Dict[str, List[Any]]] = {}
    keys[""] = {n: [_serialise(v), t] for n, (v, t) in _read_values(backend, hive, subkey).items()}
    for child in _subkeys(backend, hive, subkey):
        try:
            keys[child] = {
                n: [_serialise(v), t] for n, (v, t) in _read_values(backend, hive, _join(subkey, child)).items()
            }
        except OSError:
            continue
    return {"format_version": 1, "path": reg_path, "keys": keys}


def diff_changes(original_json: str, new_json: str) -> Dict[str, Dict[str, Any]]:
    """Changed scalar values, grouped by relative sub-key (``""`` = the key itself)."""
    before = json.loads(original_json)
    after = json.loads(new_json)
    changes: Dict[str, Dict[str, Any]] = {}

    def _scan(relative: str, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        for name, value in new.items():
            if isinstance(value, dict):
                if relative:
                    raise RegistryWriteError("registry_nesting_too_deep")
                _scan(name, old.get(name) if isinstance(old.get(name), dict) else {}, value)
                continue
            if name not in old:
                raise RegistryWriteError(f"registry_value_missing:{_join(relative, name)}")
            if old[name] != value:
                changes.setdefault(relative, {})[name] = value

    _scan("", before, after)
    return changes


_INT_TYPES = ("REG_DWORD", "REG_QWORD")
_STR_TYPES = ("REG_SZ", "REG_EXPAND_SZ")


def write_changes(reg_path: str, changes: Dict[str, Dict[str, Any]], backend: Any = None) -> List[str]:
    """Write only *changes*, keeping each value's existing type. Returns written names."""
    backend = backend or default_backend()
    hive, subkey = split_path(reg_path, backend)
    int_types = {getattr(backend, name) for name in _INT_TYPES}
    str_types = {getattr(backend, name) for name in _STR_TYPES}
    limits = {backend.REG_DWORD: 0xFFFFFFFF, backend.REG_QWORD: 0xFFFFFFFFFFFFFFFF}

    # Validate everything first so a refused value cannot leave a partial write.
    plan: List[Tuple[str, str, Any, int]] = []
    for relative, values in changes.items():
        target = _join(subkey, relative)
        with backend.OpenKey(hive, target, 0, backend.KEY_READ) as key:
            for name, value in values.items():
                try:
                    _current, value_type = backend.QueryValueEx(key, name)
                except FileNotFoundError as exc:
                    raise RegistryWriteError(f"registry_value_missing:{_join(relative, name)}") from exc
                if value_type in int_types:
                    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limits[value_type]:
                        raise RegistryWriteError(f"registry_bad_value:{_join(relative, name)}")
                elif value_type in str_types:
                    if not isinstance(value, str):
                        raise RegistryWriteError(f"registry_bad_value:{_join(relative, name)}")
                else:
                    raise RegistryWriteError(f"registry_type_not_writable:{_join(relative, name)}")
                plan.append((target, name, value, value_type))

    written: List[str] = []
    for target, name, value, value_type in plan:
        with backend.OpenKey(hive, target, 0, backend.KEY_SET_VALUE) as key:
            backend.SetValueEx(key, name, 0, value_type, value)
        written.append(name)
    return written


def restore_snapshot(snap: Dict[str, Any], backend: Any = None) -> List[str]:
    """Put back every value that differs from *snap* (same value and type). Returns mismatches left."""
    backend = backend or default_backend()
    hive, subkey = split_path(snap["path"], backend)
    for relative, values in snap.get("keys", {}).items():
        target = _join(subkey, relative)
        try:
            current = _read_values(backend, hive, target)
        except OSError:
            continue
        for name, (raw, value_type) in values.items():
            value = _deserialise(raw)
            if current.get(name) != (value, value_type):
                with backend.OpenKey(hive, target, 0, backend.KEY_SET_VALUE) as key:
                    backend.SetValueEx(key, "" if name == "(Default)" else name, 0, value_type, value)
    return snapshot_differences(snap, backend)


def snapshot_differences(snap: Dict[str, Any], backend: Any = None) -> List[str]:
    backend = backend or default_backend()
    hive, subkey = split_path(snap["path"], backend)
    mismatches: List[str] = []
    for relative, values in snap.get("keys", {}).items():
        try:
            current = _read_values(backend, hive, _join(subkey, relative))
        except OSError:
            mismatches.append(relative or "(key)")
            continue
        for name, (raw, value_type) in values.items():
            if current.get(name) != (_deserialise(raw), value_type):
                mismatches.append(_join(relative, name))
    return mismatches
