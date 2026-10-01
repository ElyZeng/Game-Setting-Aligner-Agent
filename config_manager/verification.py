"""Verification rules, local cache management, and guarded config writes."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests

from .package import ConfigPackage
from .settings_parser import extract_key_settings
from .settings_writer import GTA_ENHANCED_WRITE_CODES, _detect_parser_type, _write_gta_enhanced_settings, _write_gta_enhanced_xml, forza_auxiliary_paths

logger = logging.getLogger(__name__)

MANIFEST_FORMAT_VERSION = 1
STATUSES = frozenset({"candidate", "read_verified", "write_candidate", "write_verified", "deprecated"})
DEFAULT_RELEASE_API = "https://api.github.com/repos/ElyZeng/Game-Setting-Aligner-Agent/releases/latest"
OFFLINE_BUNDLE_FILES = frozenset({"verified-games.json", "verified-games.json.sha256"})
MAX_OFFLINE_MANIFEST_BYTES = 5 * 1024 * 1024
_BUILTIN_GAMES = (
    "Black Myth: Wukong",
    "Clair Obscur: Expedition 33",
    "Counter-Strike 2",
    "Street Fighter 6",
    "F1 25",
    "Forza Horizon",
)


class VerificationError(RuntimeError):
    """Raised when a verification policy prevents an operation."""


def app_data_dir() -> Path:
    """Return the per-user directory used for private Game Tuner data."""
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    path = Path(root) / "GameTuner"
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_file_logging(data_dir: Path) -> Path:
    """Attach a file handler (once) so update failures can be diagnosed offline."""
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "verification.log"
    already_attached = any(
        isinstance(handler, logging.FileHandler) and handler.baseFilename == str(log_path)
        for handler in logger.handlers
    )
    if not already_attached:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return log_path


def _normalise_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def version_at_least(current: str, minimum: str) -> bool:
    """Compare ordinary dotted client version strings without extra packages."""
    def parts(value: str) -> List[int]:
        return [int(part) for part in re.findall(r"\d+", value)] or [0]

    left, right = parts(current), parts(minimum)
    length = max(len(left), len(right))
    return (left + [0] * (length - len(left))) >= (right + [0] * (length - len(right)))


def _manifest_version_key(value: str) -> tuple[int, ...]:
    if value.startswith("builtin-"):
        return (0,)
    parts = [int(part) for part in re.findall(r"\d+", value)]
    if not parts:
        raise VerificationError("invalid_manifest_version")
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def structural_fingerprint(config_files: Iterable[Dict[str, Any]]) -> str:
    """Hash paths and setting keys, deliberately excluding user setting values."""
    parts: List[str] = []
    for config_file in config_files:
        content = config_file.get("content")
        if not isinstance(content, str):
            continue
        path = os.path.basename(str(config_file.get("expanded_path", ""))).lower()
        keys = sorted(set(re.findall(r"(?m)^\s*([A-Za-z][A-Za-z0-9_.-]*)\s*=", content)))
        xml_keys = sorted(set(re.findall(r"\b(?:name|id)=[\"']([^\"']+)", content)))
        json_keys = sorted(set(re.findall(r"[\"']([A-Za-z][A-Za-z0-9_.-]*)[\"']\s*:", content)))
        parts.append("|".join([path] + keys + xml_keys + json_keys))
    digest_input = "\n".join(sorted(parts)).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()


def game_structural_fingerprint(
    game: str, config_files: Iterable[Dict[str, Any]]
) -> str:
    files = list(config_files)
    if "grand theft auto v enhanced" in game.casefold():
        signatures: List[str] = []
        for config_file in files:
            content = config_file.get("content")
            filename = Path(str(config_file.get("expanded_path", ""))).name.casefold()
            if filename != "settings.xml" or not isinstance(content, str):
                continue
            try:
                root = ET.fromstring(content)
            except (ET.ParseError, ValueError):
                signatures.append(f"{filename}:invalid:{content_hash(content)}")
                continue
            stack = [(root, "")]
            while stack:
                element, parent = stack.pop()
                path = f"{parent}/{element.tag}"
                signatures.append(f"{filename}:{path}:{','.join(sorted(element.attrib))}")
                stack.extend((child, path) for child in element)
        return hashlib.sha256(
            (structural_fingerprint(files) + "\n" + "\n".join(sorted(signatures))).encode("utf-8")
        ).hexdigest()
    if "black myth" in game.casefold() or "wukong" in game.casefold():
        files = [
            config_file for config_file in files
            if Path(str(config_file.get("expanded_path", ""))).name.casefold()
            == "gameusersettings.ini"
        ]
    return structural_fingerprint(files)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def builtin_manifest(client_version: str) -> Dict[str, Any]:
    """Return the conservative offline baseline shipped with the application."""
    return {
        "format_version": MANIFEST_FORMAT_VERSION,
        "manifest_version": "builtin-1",
        "published_at": "2026-09-02T00:00:00Z",
        "generator_version": client_version,
        "minimum_client_version": "0.05.1",
        "games": [
            {
                "game": game,
                "platform": "*",
                "version": "unknown",
                "fingerprint": "*",
                "status": "read_verified",
                "config_patterns": [],
                "supported_settings": [],
                "reader_id": "existing-parser",
                "writer_id": None,
            }
            for game in _BUILTIN_GAMES
        ],
    }


def validate_manifest(manifest: Dict[str, Any], client_version: str) -> None:
    """Validate a downloaded manifest before it can replace a local cache."""
    if manifest.get("format_version") != MANIFEST_FORMAT_VERSION:
        raise VerificationError("unsupported_manifest_format")
    if not version_at_least(client_version, str(manifest.get("minimum_client_version", "0"))):
        raise VerificationError("client_update_required")
    games = manifest.get("games")
    if not isinstance(games, list):
        raise VerificationError("invalid_manifest_games")
    for rule in games:
        if not isinstance(rule, dict) or rule.get("status") not in STATUSES:
            raise VerificationError("invalid_manifest_rule")
        if not isinstance(rule.get("game"), str) or not isinstance(rule.get("platform"), str):
            raise VerificationError("invalid_manifest_rule")
        if (
            _normalise_title(rule["game"]) == "grandtheftautovenhanced"
            and rule["status"] in {"write_candidate", "write_verified"}
        ):
            supported = rule.get("supported_settings")
            values = rule.get("supported_values")
            if (
                rule["platform"] != "Steam"
                or not isinstance(rule.get("version"), str)
                or rule["version"] in {"", "unknown", "*"}
                or not isinstance(rule.get("fingerprint"), str)
                or re.fullmatch(r"[0-9a-f]{64}", rule["fingerprint"]) is None
                or rule.get("writer_id") != "gta-enhanced-xml-writer"
                or rule.get("config_patterns") != ["settings.xml"]
                or not isinstance(supported, list)
                or not supported
                or not all(isinstance(key, str) for key in supported)
                or len(supported) != len(set(supported))
                or set(supported) - set(GTA_ENHANCED_WRITE_CODES)
                or not isinstance(values, dict)
                or set(values) != set(supported)
                or any(
                    not isinstance(allowed, list)
                    or not allowed
                    or any(not isinstance(value, str) or value not in GTA_ENHANCED_WRITE_CODES[key] for value in allowed)
                    for key, allowed in values.items()
                )
            ):
                raise VerificationError("invalid_gta_write_rule")


def merge_with_builtin(manifest: Dict[str, Any], client_version: str) -> Dict[str, Any]:
    """Merge downloaded rules over the conservative built-in baseline."""
    baseline = builtin_manifest(client_version)
    merged = dict(manifest)
    remote_rules = manifest.get("games", [])
    remote_keys = {
        (_normalise_title(rule["game"]), rule["platform"].lower())
        for rule in remote_rules
    }
    merged["games"] = [
        rule for rule in baseline["games"]
        if (_normalise_title(rule["game"]), rule["platform"].lower()) not in remote_keys
    ] + list(remote_rules)
    return merged


class VerificationRegistry:
    """Load, update, and evaluate release-published verification rules."""

    def __init__(
        self,
        client_version: str,
        data_dir: Optional[Path] = None,
        release_api: str = DEFAULT_RELEASE_API,
        http_get: Callable[..., Any] = requests.get,
    ) -> None:
        self.client_version = client_version
        self.data_dir = data_dir or app_data_dir()
        self.release_api = release_api
        self.http_get = http_get
        self.current_path = self.data_dir / "verified-games.json"
        self.previous_path = self.data_dir / "verified-games.previous.json"
        self.test_write_consent_path = self.data_dir / "test-write-consent.json"
        self.log_path = configure_file_logging(self.data_dir)

    def test_write_enabled(self) -> bool:
        """Return whether this user explicitly enabled experimental writes."""
        try:
            with self.test_write_consent_path.open(encoding="utf-8") as handle:
                return bool(json.load(handle).get("enabled"))
        except (OSError, ValueError):
            return False

    def enable_test_writes(self) -> None:
        """Persist the user's explicit acknowledgement of experimental writes."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.test_write_consent_path.write_text(
            json.dumps({"enabled": True, "acknowledged_at": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8",
        )

    def disable_test_writes(self) -> None:
        """Disable experimental writes without deleting verification data."""
        self.test_write_consent_path.unlink(missing_ok=True)

    def load(self) -> Dict[str, Any]:
        for path in (self.current_path, self.previous_path):
            try:
                with path.open(encoding="utf-8") as handle:
                    manifest = json.load(handle)
                validate_manifest(manifest, self.client_version)
                return merge_with_builtin(manifest, self.client_version)
            except (OSError, ValueError, VerificationError):
                continue
        return builtin_manifest(self.client_version)

    def update(self, timeout: int = 10) -> Dict[str, Any]:
        """Fetch and atomically install the latest valid GitHub Release manifest."""
        logger.debug("update: requesting latest release from %s", self.release_api)
        try:
            release = self.http_get(self.release_api, timeout=timeout)
            logger.debug("update: release API responded status=%s", getattr(release, "status_code", "unknown"))
            release.raise_for_status()
            assets = {asset["name"]: asset["browser_download_url"] for asset in release.json().get("assets", [])}
            logger.debug("update: release assets=%s", sorted(assets.keys()))
            manifest_url = assets.get("verified-games.json")
            checksum_url = assets.get("verified-games.json.sha256")
            if not manifest_url or not checksum_url:
                logger.warning("update: release_assets_missing (found=%s)", sorted(assets.keys()))
                raise VerificationError("release_assets_missing")
            logger.debug("update: downloading manifest_url=%s checksum_url=%s", manifest_url, checksum_url)
            manifest_response = self.http_get(manifest_url, timeout=timeout)
            checksum_response = self.http_get(checksum_url, timeout=timeout)
            manifest_response.raise_for_status()
            checksum_response.raise_for_status()
            raw = manifest_response.content
            expected = checksum_response.text.strip().split()[0].lower()
            actual = hashlib.sha256(raw).hexdigest()
            logger.debug("update: checksum expected=%s actual=%s", expected, actual)
            if actual != expected:
                logger.warning("update: manifest_checksum_mismatch expected=%s actual=%s", expected, actual)
                raise VerificationError("manifest_checksum_mismatch")
            manifest = json.loads(raw.decode("utf-8"))
            validate_manifest(manifest, self.client_version)
            self._replace_current(raw)
            logger.info("update: installed manifest_version=%s", manifest.get("manifest_version"))
            return {
                "updated": True,
                "manifest_version": manifest.get("manifest_version"),
                "error": None,
                "log_path": str(self.log_path),
            }
        except (requests.RequestException, ValueError, VerificationError, KeyError) as exc:
            logger.exception("update: failed")
            return {
                "updated": False,
                "manifest_version": self.load().get("manifest_version"),
                "error": str(exc),
                "log_path": str(self.log_path),
            }

    def _read_offline_bundle(self, bundle_path: Path) -> tuple[Dict[str, Any], bytes]:
        try:
            with zipfile.ZipFile(bundle_path) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)) or set(names) != OFFLINE_BUNDLE_FILES:
                    raise VerificationError("invalid_offline_bundle_contents")
                manifest_info = archive.getinfo("verified-games.json")
                checksum_info = archive.getinfo("verified-games.json.sha256")
                if manifest_info.file_size > MAX_OFFLINE_MANIFEST_BYTES:
                    raise VerificationError("offline_manifest_too_large")
                if checksum_info.file_size > 1024:
                    raise VerificationError("invalid_offline_bundle_checksum")
                raw = archive.read("verified-games.json")
                checksum_text = archive.read("verified-games.json.sha256").decode("ascii")
        except VerificationError:
            raise
        except (OSError, UnicodeError, zipfile.BadZipFile, KeyError) as exc:
            raise VerificationError("invalid_offline_bundle") from exc

        expected = checksum_text.strip().split()[0].lower() if checksum_text.strip() else ""
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise VerificationError("invalid_offline_bundle_checksum")
        if hashlib.sha256(raw).hexdigest() != expected:
            raise VerificationError("manifest_checksum_mismatch")
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise VerificationError("invalid_offline_manifest") from exc
        if not isinstance(manifest, dict):
            raise VerificationError("invalid_offline_manifest")
        validate_manifest(manifest, self.client_version)
        if not isinstance(manifest.get("manifest_version"), str):
            raise VerificationError("invalid_manifest_version")
        if not isinstance(manifest.get("published_at"), str):
            raise VerificationError("invalid_manifest_published_at")
        return manifest, raw

    def preview_offline_bundle(self, bundle_path: Path) -> Dict[str, Any]:
        """Validate an offline bundle and return non-installing review metadata."""
        manifest, _ = self._read_offline_bundle(Path(bundle_path))
        current_version = str(self.load().get("manifest_version", "builtin-1"))
        incoming_version = str(manifest["manifest_version"])
        rollback = _manifest_version_key(incoming_version) < _manifest_version_key(current_version)
        return {
            "source": "offline_bundle",
            "manifest_version": incoming_version,
            "current_version": current_version,
            "published_at": manifest["published_at"],
            "minimum_client_version": manifest["minimum_client_version"],
            "rule_count": len(manifest["games"]),
            "integrity": "sha256_verified",
            "publisher_authenticated": False,
            "trusted_channel_required": True,
            "rollback": rollback,
        }

    def import_offline_bundle(
        self, bundle_path: Path, allow_rollback: bool = False
    ) -> Dict[str, Any]:
        """Validate and atomically install a trusted-channel offline rule bundle."""
        current_version = str(self.load().get("manifest_version", "builtin-1"))
        incoming_version = "unknown"
        try:
            manifest, raw = self._read_offline_bundle(Path(bundle_path))
            incoming_version = str(manifest["manifest_version"])
            rollback = _manifest_version_key(incoming_version) < _manifest_version_key(current_version)
            if rollback and not allow_rollback:
                raise VerificationError("offline_manifest_rollback_required")
            try:
                self._replace_current(raw)
            except OSError as exc:
                raise VerificationError("offline_bundle_install_failed") from exc
            logger.info(
                "import source=offline_bundle current_version=%s incoming_version=%s "
                "result=installed rollback=%s",
                current_version, incoming_version, rollback,
            )
            return {
                "installed": True,
                "source": "offline_bundle",
                "manifest_version": incoming_version,
                "previous_version": current_version,
                "rollback": rollback,
                "integrity": "sha256_verified",
                "publisher_authenticated": False,
                "trusted_channel_required": True,
                "log_path": str(self.log_path),
            }
        except (OSError, VerificationError) as exc:
            logger.error(
                "import source=offline_bundle current_version=%s incoming_version=%s "
                "result=rejected reason=%s",
                current_version, incoming_version, exc,
            )
            raise

    def _replace_current(self, raw: bytes) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.data_dir, delete=False) as handle:
            handle.write(raw)
            temporary_path = Path(handle.name)
        try:
            if self.current_path.exists():
                shutil.copy2(self.current_path, self.previous_path)
            os.replace(temporary_path, self.current_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def status_for(
        self,
        game: str,
        platform: str,
        game_version: str,
        fingerprint: str,
    ) -> Dict[str, Any]:
        """Return the safest status that matches known game facts."""
        matching = [
            rule for rule in self.load()["games"]
            if _normalise_title(rule["game"]) == _normalise_title(game)
            and rule["platform"].lower() in ("*", platform.lower())
        ]
        exact_platform = [
            rule for rule in matching if rule["platform"].lower() == platform.lower()
        ]
        if exact_platform:
            matching = exact_platform
        matching.sort(
            key=lambda rule: (
                rule["platform"].lower() != "*",
                rule.get("fingerprint") not in (None, "*"),
            ),
            reverse=True,
        )
        if not matching:
            return {"status": "candidate", "reason": "game_not_listed", "rule": None}
        for rule in matching:
            if rule.get("fingerprint") not in ("*", fingerprint):
                continue
            rule_version = str(rule.get("version", "unknown"))
            if rule_version == game_version:
                return {"status": rule["status"], "reason": "verified", "rule": rule}
            if rule["status"] == "write_verified":
                return {"status": "read_verified", "reason": "version_mismatch", "rule": rule}
            if rule["status"] == "write_candidate":
                return {"status": "candidate", "reason": "version_mismatch", "rule": rule}
            return {"status": rule["status"], "reason": "version_mismatch", "rule": rule}
        return {"status": "candidate", "reason": "fingerprint_mismatch", "rule": None}


def _check_write_rule(
    game: str,
    platform: str,
    game_version: str,
    fingerprint: str,
    config_files: List[Dict[str, Any]],
    settings: Dict[str, str],
    registry: VerificationRegistry,
) -> None:
    verification = registry.status_for(game, platform, game_version, fingerprint)
    if verification["status"] not in {"write_candidate", "write_verified"}:
        raise VerificationError(f"write_not_allowed:{verification['reason']}")
    rule = verification.get("rule") or {}
    supported_settings = rule.get("supported_settings")
    if isinstance(supported_settings, list):
        unsupported = sorted(set(settings) - set(supported_settings))
        if unsupported:
            raise VerificationError(f"write_setting_not_allowed:{','.join(unsupported)}")

    if "grand theft auto v enhanced" not in game.casefold():
        return
    if (
        verification.get("reason") != "verified"
        or platform != "Steam"
        or rule.get("platform") != platform
        or game_version in ("", "unknown")
        or rule.get("version") != game_version
        or rule.get("fingerprint") != fingerprint
        or rule.get("writer_id") != "gta-enhanced-xml-writer"
    ):
        raise VerificationError("write_not_allowed:exact_gta_rule_required")
    if (
        not isinstance(supported_settings, list)
        or not supported_settings
        or len(supported_settings) != len(set(supported_settings))
        or set(supported_settings) - set(GTA_ENHANCED_WRITE_CODES)
    ):
        raise VerificationError("write_not_allowed:gta_allowlist_required")
    values = rule.get("supported_values")
    if not isinstance(values, dict) or set(values) != set(supported_settings) or any(
        not isinstance(allowed, list) or not allowed
        or any(not isinstance(value, str) or value not in GTA_ENHANCED_WRITE_CODES[key] for value in allowed)
        for key, allowed in values.items()
    ):
        raise VerificationError("write_not_allowed:gta_values_required")
    for key, value in settings.items():
        if value not in values[key]:
            raise VerificationError(f"write_value_not_allowed:{key}")
    if (
        len(config_files) != 1
        or Path(str(config_files[0].get("expanded_path", ""))).name.casefold() != "settings.xml"
        or Path(str(config_files[0].get("expanded_path", ""))).parent.name.casefold() != "gtav enhanced"
        or not config_files[0].get("found")
        or not isinstance(config_files[0].get("content"), str)
    ):
        raise VerificationError("write_not_allowed:gta_config_not_unique")
    try:
        _write_gta_enhanced_xml(config_files[0]["content"], settings)
    except (ValueError, ET.ParseError) as exc:
        raise VerificationError("write_preflight_failed:gta_xml") from exc


def preflight_write(
    game: str,
    platform: str,
    game_version: str,
    config_files: List[Dict[str, Any]],
    settings: Dict[str, str],
    registry: VerificationRegistry,
) -> Dict[str, Any]:
    if "grand theft auto v enhanced" not in game.casefold():
        raise VerificationError("preflight_not_supported")
    refreshed_files: List[Dict[str, Any]] = []
    for config_file in config_files:
        refreshed = dict(config_file)
        path = Path(str(config_file.get("expanded_path", "")))
        if path.is_file():
            try:
                refreshed["content"] = path.read_bytes().decode("utf-8")
                refreshed["found"] = True
            except (OSError, UnicodeError):
                refreshed["content"] = None
                refreshed["found"] = False
        else:
            refreshed["content"] = None
            refreshed["found"] = False
        refreshed_files.append(refreshed)
    fingerprint = game_structural_fingerprint(game, refreshed_files)
    _check_write_rule(game, platform, game_version, fingerprint, refreshed_files, settings, registry)
    content = refreshed_files[0]["content"]
    patched = _write_gta_enhanced_xml(content, settings)
    if patched == content:
        raise VerificationError("write_no_change")
    parsed = extract_key_settings(game, [{**refreshed_files[0], "content": patched}])
    if any(parsed.get(key) != value for key, value in settings.items()):
        raise VerificationError("write_preflight_failed:readback")
    if _detect_parser_type(game, refreshed_files) != "gta_enhanced_xml":
        raise VerificationError("write_not_connected:gta_enhanced_xml")
    return {"status": "ok", "game": game, "settings": settings, "files_checked": 1}


def restore_gta_baseline_no_change(
    game: str,
    platform: str,
    game_version: str,
    config_files: List[Dict[str, Any]],
    package_path: Path,
    expected_package_sha256: str,
    registry: VerificationRegistry,
    confirm_no_change_restore: bool = False,
) -> Dict[str, Any]:
    if not confirm_no_change_restore:
        raise VerificationError("restore_consent_required")
    if game != "Grand Theft Auto V Enhanced" or platform != "Steam" or len(config_files) != 1:
        raise VerificationError("restore_scope_not_allowed")
    package_bytes = Path(package_path).read_bytes()
    if (
        re.fullmatch(r"[0-9a-fA-F]{64}", expected_package_sha256) is None
        or hashlib.sha256(package_bytes).hexdigest() != expected_package_sha256.lower()
    ):
        raise VerificationError("restore_package_hash_mismatch")
    try:
        package = json.loads(package_bytes.decode("utf-8"))
        games = package["games"]
        entries = games[game]["config_files"]
    except (UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise VerificationError("restore_invalid_package") from exc
    if (
        package.get("version") != 2 or not isinstance(games, dict)
        or set(games) != {game} or not isinstance(entries, list) or len(entries) != 1
        or not isinstance(entries[0], dict)
    ):
        raise VerificationError("restore_invalid_package")
    entry = entries[0]
    detected = config_files[0]
    if (
        not entry.get("found") or entry.get("error") or entry.get("truncated")
        or entry.get("type") == "registry" or not isinstance(entry.get("content"), str)
        or not detected.get("found") or detected.get("error") or detected.get("truncated")
    ):
        raise VerificationError("restore_incomplete_config")
    try:
        target = Path(str(entry["expanded_path"])).resolve(strict=True)
        detected_path = Path(str(detected["expanded_path"])).resolve(strict=True)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise VerificationError("restore_invalid_target") from exc
    if (
        target != detected_path or target.name.casefold() != "settings.xml"
        or target.parent.name.casefold() != "gtav enhanced" or not target.is_file()
    ):
        raise VerificationError("restore_invalid_target")
    original = target.read_bytes()
    try:
        content = original.decode("utf-8")
        baseline = entry["content"].encode("utf-8")
    except UnicodeError as exc:
        raise VerificationError("restore_invalid_encoding") from exc
    if baseline != original:
        raise VerificationError("restore_not_no_change")
    refreshed = [{**detected, "expanded_path": str(target), "content": content}]
    parsed_before = extract_key_settings(game, refreshed)
    _check_write_rule(
        game, platform, game_version, game_structural_fingerprint(game, refreshed),
        refreshed, {key: parsed_before.get(key) for key in ("vsync", "frame_limit")}, registry,
    )

    backup_dir = registry.data_dir / "restore-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=backup_dir, prefix="gta-", suffix=".bak", delete=False) as backup:
        backup.write(original)
        backup.flush()
        os.fsync(backup.fileno())
        backup_path = Path(backup.name)
    if backup_path.read_bytes() != original:
        raise VerificationError("restore_backup_mismatch")
    if target.read_bytes() != original:
        raise VerificationError("restore_file_changed_before_import")

    try:
        restored = ConfigPackage()._import_v2(package)
        after = target.read_bytes()
        parsed_after = extract_key_settings(game, [{**refreshed[0], "content": after.decode("utf-8")}])
        if restored != {game: [entry["expanded_path"]]} or after != original or parsed_after != parsed_before:
            raise VerificationError("restore_validation_failed")
    except Exception as exc:
        try:
            if target.read_bytes() != original:
                target.write_bytes(original)
            if target.read_bytes() != original:
                raise VerificationError("restore_rollback_failed")
        except OSError as rollback_error:
            raise VerificationError(f"restore_rollback_failed:backup_at:{backup_path}") from rollback_error
        raise VerificationError("restore_validation_failed_restored") from exc

    digest = hashlib.sha256(original).hexdigest()
    return {
        "status": "ok", "files_restored": 1, "sha256_before": digest,
        "sha256_after": hashlib.sha256(after).hexdigest(),
        "settings_before": parsed_before, "settings_after": parsed_after,
        "rescue_backup": str(backup_path),
    }


def backup_and_write(
    game: str,
    platform: str,
    game_version: str,
    config_files: List[Dict[str, Any]],
    settings: Dict[str, str],
    write: Callable[[str, List[Dict[str, Any]], Dict[str, str]], List[Dict[str, Any]]],
    registry: VerificationRegistry,
) -> List[Dict[str, Any]]:
    """Write only verified configs, restoring the backup if validation fails."""
    if not registry.test_write_enabled():
        raise VerificationError("test_write_consent_required")
    gta = "grand theft auto v enhanced" in game.casefold()
    refreshed_files: List[Dict[str, Any]] = []
    for config_file in config_files:
        refreshed = dict(config_file)
        path = Path(str(config_file.get("expanded_path", "")))
        if config_file.get("type") != "registry":
            if path.is_file():
                try:
                    refreshed["content"] = (
                        path.read_bytes().decode("utf-8") if gta
                        else path.read_text(encoding="utf-8", errors="replace")
                    )
                    refreshed["found"] = True
                except (OSError, UnicodeError):
                    refreshed["content"] = None
                    refreshed["found"] = False
            else:
                refreshed["content"] = None
                refreshed["found"] = False
        refreshed_files.append(refreshed)
    config_files = refreshed_files
    fingerprint = game_structural_fingerprint(game, config_files)
    _check_write_rule(game, platform, game_version, fingerprint, config_files, settings, registry)
    if gta:
        preflight_write(game, platform, game_version, config_files, settings, registry)
    if (
        "forza" in game.lower()
        and settings.get("vsync") == "On"
        and settings.get("frame_limit") == "Unlimited"
    ):
        raise VerificationError("forza_incompatible_settings:vsync_on_unlimited")
    if (
        "f1" in game.lower()
        and "25" in game.lower()
        and settings.get("frame_generation") not in (None, "", "Off", "N/A")
        and settings.get("screen_mode") == "Fullscreen"
    ):
        raise VerificationError("f1_incompatible_settings:frame_generation_fullscreen")

    backup_root = registry.data_dir / "backups" / re.sub(r"[^A-Za-z0-9_.-]+", "_", game)
    staging = backup_root.with_name(backup_root.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    originals: List[tuple[Path, str]] = []
    gta_originals: Dict[Path, bytes] = {}
    for index, config_file in enumerate(config_files):
        path = Path(str(config_file.get("expanded_path", "")))
        content = config_file.get("content")
        if path.is_file() and isinstance(content, str):
            backup_file = staging / f"{index}-{path.name}"
            shutil.copy2(path, backup_file)
            originals.append((path, content))
            if gta:
                gta_originals[path] = path.read_bytes()

    auxiliary_originals: List[tuple[Path, Optional[bytes]]] = []
    for index, auxiliary_path_text in enumerate(forza_auxiliary_paths(config_files)):
        auxiliary_path = Path(auxiliary_path_text)
        if auxiliary_path.is_file():
            backup_file = staging / f"auxiliary-{index}-{auxiliary_path.name}"
            shutil.copy2(auxiliary_path, backup_file)
            auxiliary_originals.append((auxiliary_path, auxiliary_path.read_bytes()))
        else:
            auxiliary_originals.append((auxiliary_path, None))

    result = _write_gta_enhanced_settings(config_files, settings) if gta else write(game, config_files, settings)
    expected = {key: value for key, value in settings.items() if value is not None}
    reread = []
    for path, _ in originals:
        try:
            content = path.read_bytes().decode("utf-8") if gta else path.read_text(encoding="utf-8")
            reread.append({"expanded_path": str(path), "found": True, "content": content})
        except (OSError, UnicodeError):
            pass
    parsed = extract_key_settings(game, reread)
    def _setting_matches(key: str, expected_value: Any) -> bool:
        actual_value = str(parsed.get(key))
        expected_text = str(expected_value)
        if key == "resolution":
            expected_text = expected_text.split(" (", 1)[0]
        if key == "frame_limit" and "cyberpunk" in game.lower():
            return actual_value.removesuffix(" FPS") == expected_text.removesuffix(" FPS")
        if key == "upscaling" and "cyberpunk" in game.lower():
            aliases = {"FSR2": "FSR 2.1", "FSR3": "FSR 3"}
            return aliases.get(actual_value, actual_value).casefold() == aliases.get(expected_text, expected_text).casefold()
        if key == "quick_preset" and game.lower().find("f1") >= 0 and game.lower().find("25") >= 0:
            return actual_value in {expected_text, f"Custom ({expected_text})"}
        return actual_value == expected_text

    valid = all(_setting_matches(key, value) for key, value in expected.items())
    if gta:
        valid = (
            valid and len(result) == 1 and result[0].get("status") == "ok"
            and Path(result[0]["path"]) == originals[0][0]
            and originals[0][0].read_bytes() != gta_originals[originals[0][0]]
        )
    if not valid:
        for path, content in originals:
            if gta:
                path.write_bytes(gta_originals[path])
            else:
                path.write_text(content, encoding="utf-8")
        for path, content in auxiliary_originals:
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        shutil.rmtree(staging, ignore_errors=True)
        raise VerificationError("write_validation_failed_restored")

    shutil.rmtree(backup_root, ignore_errors=True)
    staging.replace(backup_root)
    return result