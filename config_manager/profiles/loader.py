"""Game profile loader and schema validator (P1, proposal §3.3).

Profiles are JSON (not YAML — see the P1 handoff §4.1: avoids a new runtime
dependency and keeps PyInstaller packaging unchanged). A profile is the
single source of truth for one game's: file locations/codecs, how each
setting maps to raw file content, structural-compatibility checks
(``required_keys``), anti-cheat review status, and verified version/levels
(replacing the old remote ``verified-games.json`` rule file — see proposal
§3.8).

Validation is deliberately strict and fails at *load* time (not first use):
a broken profile should break ``pytest`` and app startup, never silently
degrade a game to "unsupported" in production. See handoff §4.1: "profile
寫錯時要在啟動和測試時就失敗".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import function_registry
from ..codecs import CODECS

# Importing this registers the named parser_fn/writer_fn/map_fn callables
# profiles are allowed to reference. Must happen before any profile is
# validated, so a profile naming an unregistered function fails immediately.
from .. import profile_functions  # noqa: F401  (import for side effect)

_VALID_VERSION_POLICIES = {"exact", "schema_compatible"}
_VALID_ANTICHEAT_REVIEW = {"approved", "blocked", "n/a"}
_VALID_LEVELS = {"L0", "L1", "L2", "L3", "L4"}
_VALID_PARSE_MODES = {"single_file", "multi_file"}


class ProfileError(ValueError):
    """A profile file is missing a required field or references something unknown."""

    def __init__(self, profile_path: Path, message: str):
        super().__init__(f"{profile_path.name}: {message}")
        self.profile_path = profile_path


@dataclass
class ConfigFile:
    key: str
    path: str
    codec: str


@dataclass
class Setting:
    key: str
    file: str
    raw_key: Optional[str] = None
    raw_keys: Optional[List[str]] = None
    map: Optional[Dict[str, str]] = None
    map_fn: Optional[str] = None


@dataclass
class VerifiedEntry:
    platform: str
    version: str
    levels: Dict[str, str]
    fingerprint: Optional[str] = None


@dataclass
class Profile:
    id: str
    match_names: List[str]
    match_steam_appid: Optional[int]
    engine: Optional[str]
    files: Dict[str, ConfigFile]
    settings: Dict[str, Setting] = field(default_factory=dict)
    parser_fn: Optional[str] = None
    writer_fn: Optional[str] = None
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    readback_aliases: Dict[str, str] = field(default_factory=dict)
    fingerprint_scope: List[str] = field(default_factory=list)
    verified: List[VerifiedEntry] = field(default_factory=list)
    version_policy: str = "exact"
    required_keys: Dict[str, List[str]] = field(default_factory=dict)
    anticheat: Dict[str, Any] = field(default_factory=dict)
    process_ignore: List[str] = field(default_factory=list)
    write_detail: Optional[str] = None
    parse_mode: str = "single_file"
    write_side_effect_fn: Optional[str] = None
    writer_id: Optional[str] = None
    supported_values: Dict[str, List[str]] = field(default_factory=dict)
    source_path: Optional[Path] = None

    def matches(self, game_name: str) -> bool:
        """Exact (case-insensitive) match against ``match.names``.

        Deliberately not a substring match: "Black Myth: Wukong" must not
        also match "Black Myth: Wukong Benchmark Tool" (a different,
        not-yet-migrated profile/legacy path) just because one title
        contains the other.
        """
        name_lower = game_name.strip().lower()
        return any(candidate.strip().lower() == name_lower for candidate in self.match_names)

    def parse(self, content: str) -> Dict[str, Optional[str]]:
        """Read all settings this profile covers from *content* (main file)."""
        if self.parser_fn:
            return function_registry.get("parser_fn", self.parser_fn)(content)
        raise ProfileError(
            self.source_path or Path(self.id), "per-field declarative read not implemented yet; profile needs parser_fn"
        )

    def parse_multi(self, config_files: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
        """Read settings from the *full* list of config file entries.

        For ``parse_mode: "multi_file"`` profiles only (e.g. CS2, whose
        settings are split across ``cs2_video.txt`` and a separate convars
        file) — the registered ``parser_fn`` receives the raw config-file
        list exactly as the pre-P1 legacy function did, so this is still a
        zero-behavior-change wrapper, just over multiple files instead of one.
        """
        if self.parser_fn:
            return function_registry.get("parser_fn", self.parser_fn)(config_files)
        raise ProfileError(
            self.source_path or Path(self.id), "per-field declarative read not implemented yet; profile needs parser_fn"
        )

    def write(self, content: str, settings: Dict[str, Optional[str]]) -> str:
        """Write *settings* into *content* (main file)."""
        if self.writer_fn:
            return function_registry.get("writer_fn", self.writer_fn)(content, settings)
        raise ProfileError(
            self.source_path or Path(self.id), "per-field declarative write not implemented yet; profile needs writer_fn"
        )

    def write_side_effects(
        self, config_files: List[Dict[str, Any]], settings: Dict[str, Optional[str]]
    ) -> List[Dict[str, str]]:
        """Run any extra writes this profile needs beyond the main file.

        Optional (most profiles have none — returns ``[]``). For games like
        Forza Horizon 6, a successful main-file write has an extra side
        effect (a sibling ``fullscreen_choice`` sidecar byte-file write) that
        the pre-P1 legacy code performed inline in the write-dispatch branch
        rather than inside the main writer function itself. ``write_side_effect_fn``
        wraps that *existing* logic verbatim so the migration stays
        zero-behavior-change; it receives the full config-file list (it may
        need files other than "main") and the settings being written, and
        returns extra ``{"path", "status", "detail"}`` result dicts to append
        after the main-file write result.
        """
        if not self.write_side_effect_fn:
            return []
        return function_registry.get("write_side_effect_fn", self.write_side_effect_fn)(config_files, settings)


def _require(data: Dict[str, Any], key: str, path: Path, expected_type: type) -> Any:
    if key not in data:
        raise ProfileError(path, f"missing required field {key!r}")
    value = data[key]
    if not isinstance(value, expected_type):
        raise ProfileError(path, f"field {key!r} must be {expected_type.__name__}, got {type(value).__name__}")
    return value


def _parse_files(raw: Dict[str, Any], path: Path) -> Dict[str, ConfigFile]:
    if not raw:
        raise ProfileError(path, "'files' must declare at least one entry")
    files: Dict[str, ConfigFile] = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            raise ProfileError(path, f"files.{key} must be an object")
        file_path = entry.get("path")
        codec = entry.get("codec")
        if not file_path or not isinstance(file_path, str):
            raise ProfileError(path, f"files.{key}.path is required")
        if codec not in CODECS and codec != "registry":
            raise ProfileError(
                path, f"files.{key}.codec={codec!r} is not a known codec ({sorted(CODECS)} + 'registry')"
            )
        files[key] = ConfigFile(key=key, path=file_path, codec=codec)
    return files


def _parse_settings(raw: Dict[str, Any], files: Dict[str, ConfigFile], path: Path) -> Dict[str, Setting]:
    settings: Dict[str, Setting] = {}
    for key, entry in (raw or {}).items():
        if not isinstance(entry, dict):
            raise ProfileError(path, f"settings.{key} must be an object")
        file_key = entry.get("file")
        if file_key not in files:
            raise ProfileError(path, f"settings.{key}.file={file_key!r} is not declared in 'files'")
        map_fn = entry.get("map_fn")
        if map_fn is not None:
            # Fail fast: the name must already be registered.
            try:
                function_registry.get("map_fn", map_fn)
            except function_registry.FunctionRegistryError as exc:
                raise ProfileError(path, str(exc)) from exc
        settings[key] = Setting(
            key=key,
            file=file_key,
            raw_key=entry.get("key"),
            raw_keys=entry.get("keys"),
            map=entry.get("map"),
            map_fn=map_fn,
        )
    return settings


def _parse_verified(raw: List[Any], path: Path) -> List[VerifiedEntry]:
    entries: List[VerifiedEntry] = []
    for i, item in enumerate(raw or []):
        if not isinstance(item, dict):
            raise ProfileError(path, f"verified[{i}] must be an object")
        for required in ("platform", "version", "levels"):
            if required not in item:
                raise ProfileError(path, f"verified[{i}] missing {required!r}")
        levels = item["levels"]
        if not isinstance(levels, dict) or not levels:
            raise ProfileError(path, f"verified[{i}].levels must be a non-empty object")
        for setting_key, level in levels.items():
            if level not in _VALID_LEVELS:
                raise ProfileError(
                    path, f"verified[{i}].levels.{setting_key}={level!r} is not one of {sorted(_VALID_LEVELS)}"
                )
        entries.append(
            VerifiedEntry(
                platform=item["platform"],
                version=item["version"],
                levels=levels,
                fingerprint=item.get("fingerprint"),
            )
        )
    return entries


def _parse_anticheat(raw: Dict[str, Any], path: Path) -> Dict[str, Any]:
    raw = raw or {"detected": [], "review": "n/a"}
    review = raw.get("review", "n/a")
    if review not in _VALID_ANTICHEAT_REVIEW:
        raise ProfileError(path, f"anticheat.review={review!r} is not one of {sorted(_VALID_ANTICHEAT_REVIEW)}")
    return raw


def _parse_supported_values(raw: Any, path: Path) -> Dict[str, List[str]]:
    """Optional per-setting allow-lists for games with a dedicated legacy
    write gate keyed on an exact value list (see verification.py's
    ``_check_write_rule`` Forza Horizon 6 ``quick_preset`` block — it
    requires ``rule["supported_values"]["quick_preset"]`` to be a concrete
    allow-list, not just a setting name in ``supported_settings``). Most
    profiles leave this empty; ``_status_from_profile`` copies it verbatim
    into the synthesized rule dict next to ``writer_id``, same pattern as
    ``anticheat``.
    """
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ProfileError(path, "supported_values must be an object mapping setting key -> list of allowed values")
    for key, values in raw.items():
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ProfileError(path, f"supported_values.{key} must be a list of strings")
    return raw


def load_profile(path: Path) -> Profile:
    """Parse and validate one profile JSON file. Raises ProfileError on any problem."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(path, f"invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProfileError(path, "profile root must be a JSON object")

    profile_id = _require(raw, "id", path, str)
    match = _require(raw, "match", path, dict)
    match_names = match.get("names", [])
    if not isinstance(match_names, list) or not all(isinstance(n, str) for n in match_names):
        raise ProfileError(path, "match.names must be a list of strings")
    steam_appid = match.get("steam_appid")
    if not match_names and steam_appid is None:
        raise ProfileError(path, "match must declare at least one of names/steam_appid")

    files = _parse_files(_require(raw, "files", path, dict), path)
    settings = _parse_settings(raw.get("settings", {}), files, path)
    parser_fn = raw.get("parser_fn")
    writer_fn = raw.get("writer_fn")
    if parser_fn is not None:
        try:
            function_registry.get("parser_fn", parser_fn)
        except function_registry.FunctionRegistryError as exc:
            raise ProfileError(path, str(exc)) from exc
    if writer_fn is not None:
        try:
            function_registry.get("writer_fn", writer_fn)
        except function_registry.FunctionRegistryError as exc:
            raise ProfileError(path, str(exc)) from exc
    write_side_effect_fn = raw.get("write_side_effect_fn")
    if write_side_effect_fn is not None:
        if not writer_fn:
            raise ProfileError(path, "write_side_effect_fn requires writer_fn")
        try:
            function_registry.get("write_side_effect_fn", write_side_effect_fn)
        except function_registry.FunctionRegistryError as exc:
            raise ProfileError(path, str(exc)) from exc
    if not settings and not (parser_fn and writer_fn):
        raise ProfileError(
            path, "profile must declare either per-field 'settings' or both 'parser_fn' and 'writer_fn'"
        )

    version_policy = raw.get("version_policy", "exact")
    if version_policy not in _VALID_VERSION_POLICIES:
        raise ProfileError(path, f"version_policy={version_policy!r} is not one of {sorted(_VALID_VERSION_POLICIES)}")

    parse_mode = raw.get("parse_mode", "single_file")
    if parse_mode not in _VALID_PARSE_MODES:
        raise ProfileError(path, f"parse_mode={parse_mode!r} is not one of {sorted(_VALID_PARSE_MODES)}")
    if parse_mode == "multi_file" and not parser_fn:
        raise ProfileError(path, "parse_mode='multi_file' requires parser_fn")

    required_keys = raw.get("required_keys", {})
    if not isinstance(required_keys, dict):
        raise ProfileError(path, "required_keys must be an object mapping file key -> list of keys")
    for file_key in required_keys:
        if file_key not in files:
            raise ProfileError(path, f"required_keys references unknown file {file_key!r}")

    writer_id = raw.get("writer_id")
    if writer_id is not None and not isinstance(writer_id, str):
        raise ProfileError(path, "writer_id must be a string")
    supported_values = _parse_supported_values(raw.get("supported_values"), path)

    return Profile(
        id=profile_id,
        match_names=match_names,
        match_steam_appid=steam_appid,
        engine=raw.get("engine"),
        files=files,
        settings=settings,
        parser_fn=parser_fn,
        writer_fn=writer_fn,
        constraints=raw.get("constraints", []),
        readback_aliases=raw.get("readback_aliases", {}),
        fingerprint_scope=raw.get("fingerprint_scope", []),
        verified=_parse_verified(raw.get("verified", []), path),
        version_policy=version_policy,
        required_keys=required_keys,
        anticheat=_parse_anticheat(raw.get("anticheat", {}), path),
        process_ignore=raw.get("process_ignore", []),
        write_detail=raw.get("write_detail"),
        parse_mode=parse_mode,
        write_side_effect_fn=write_side_effect_fn,
        writer_id=writer_id,
        supported_values=supported_values,
        source_path=path,
    )


def load_all(profiles_dir: Optional[Path] = None) -> Dict[str, Profile]:
    """Load every ``*.json`` profile in *profiles_dir* (default: this package's dir).

    Raises on the first invalid profile — callers (app startup, pytest) are
    expected to let this propagate rather than catch it, per the "fail at
    load time" requirement.
    """
    profiles_dir = Path(profiles_dir) if profiles_dir else Path(__file__).parent
    profiles: Dict[str, Profile] = {}
    for file_path in sorted(profiles_dir.glob("*.json")):
        profile = load_profile(file_path)
        if profile.id in profiles:
            raise ProfileError(file_path, f"duplicate profile id {profile.id!r} (also in {profiles[profile.id].source_path})")
        profiles[profile.id] = profile
    return profiles


def find_profile(game_name: str, profiles: Optional[Dict[str, Profile]] = None) -> Optional[Profile]:
    """Return the profile matching *game_name*, or None (caller falls back to legacy code)."""
    if profiles is None:
        profiles = load_all()
    for profile in profiles.values():
        if profile.matches(game_name):
            return profile
    return None
