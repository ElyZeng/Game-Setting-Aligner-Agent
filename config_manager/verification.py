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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests

from .settings_parser import extract_key_settings
from .settings_writer import forza_auxiliary_paths

logger = logging.getLogger(__name__)

MANIFEST_FORMAT_VERSION = 1
STATUSES = frozenset({"candidate", "read_verified", "write_candidate", "write_verified", "deprecated"})
DEFAULT_RELEASE_API = "https://api.github.com/repos/ElyZeng/Game-Tuner-POC/releases/latest"
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


def merge_with_builtin(manifest: Dict[str, Any], client_version: str) -> Dict[str, Any]:
    """Merge downloaded rules over the conservative built-in baseline."""
    baseline = builtin_manifest(client_version)
    merged = dict(manifest)
    rules_by_key = {
        (_normalise_title(rule["game"]), rule["platform"].lower()): rule
        for rule in baseline["games"]
    }
    for rule in manifest.get("games", []):
        rules_by_key[(_normalise_title(rule["game"]), rule["platform"].lower())] = rule
    merged["games"] = list(rules_by_key.values())
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
    fingerprint = structural_fingerprint(config_files)
    verification = registry.status_for(game, platform, game_version, fingerprint)
    if verification["status"] not in {"write_candidate", "write_verified"}:
        raise VerificationError(f"write_not_allowed:{verification['reason']}")
    if (
        "forza" in game.lower()
        and settings.get("vsync") == "On"
        and settings.get("frame_limit") == "Unlimited"
    ):
        raise VerificationError("forza_incompatible_settings:vsync_on_unlimited")

    backup_root = registry.data_dir / "backups" / re.sub(r"[^A-Za-z0-9_.-]+", "_", game)
    staging = backup_root.with_name(backup_root.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    originals: List[tuple[Path, str]] = []
    for index, config_file in enumerate(config_files):
        path = Path(str(config_file.get("expanded_path", "")))
        content = config_file.get("content")
        if path.is_file() and isinstance(content, str):
            backup_file = staging / f"{index}-{path.name}"
            shutil.copy2(path, backup_file)
            originals.append((path, content))

    auxiliary_originals: List[tuple[Path, Optional[bytes]]] = []
    for index, auxiliary_path_text in enumerate(forza_auxiliary_paths(config_files)):
        auxiliary_path = Path(auxiliary_path_text)
        if auxiliary_path.is_file():
            backup_file = staging / f"auxiliary-{index}-{auxiliary_path.name}"
            shutil.copy2(auxiliary_path, backup_file)
            auxiliary_originals.append((auxiliary_path, auxiliary_path.read_bytes()))
        else:
            auxiliary_originals.append((auxiliary_path, None))

    result = write(game, config_files, settings)
    expected = {key: value for key, value in settings.items() if value is not None}
    reread = []
    for path, _ in originals:
        try:
            reread.append({"expanded_path": str(path), "found": True, "content": path.read_text(encoding="utf-8")})
        except OSError:
            pass
    parsed = extract_key_settings(game, reread)
    valid = all(str(parsed.get(key)) == str(value) for key, value in expected.items())
    if not valid:
        for path, content in originals:
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