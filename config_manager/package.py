"""Config package serialisation.

Provides ConfigPackage which bundles multiple game configuration files into
a single JSON archive for backup / transfer, and restores them from one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .reader import ConfigReader
from .safe_io import atomic_write_bytes, atomic_write_text, sha256_bytes
from .writer import ConfigWriter


class ConfigPackage:
    """Bundle and restore game configuration files.

    The package format is a JSON file with the following structure::

        {
            "version": 1,
            "games": {
                "<game_name>": {
                    "<original_path>": <config_data_dict>,
                    ...
                },
                ...
            }
        }
    """

    SUPPORTED_VERSIONS = {1, 2}

    def __init__(self, backup_root: Optional[Path] = None) -> None:
        self._reader = ConfigReader()
        self._writer = ConfigWriter()
        self._backup_root = backup_root
        self.last_backup: Optional[Path] = None

    def _backup_existing(self, paths: List[str]) -> Optional[Path]:
        """Copy every existing target file before an import overwrites it.

        Stored under ``<app data>/backups/imports/<timestamp>/`` with a
        manifest (original path + SHA-256), so an import can always be undone.
        """
        existing = [path for path in dict.fromkeys(paths) if path and os.path.isfile(path)]
        if not existing:
            return None
        root = self._backup_root
        if root is None:
            from .verification import app_data_dir  # local import: avoids a cycle

            root = app_data_dir() / "backups" / "imports"
        folder = Path(root) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder.mkdir(parents=True, exist_ok=False)
        entries = []
        for index, path in enumerate(existing):
            data = Path(path).read_bytes()
            copy = folder / f"{index}-{os.path.basename(path)}"
            shutil.copy2(path, copy)
            if copy.read_bytes() != data:
                raise OSError(f"import_backup_mismatch:{path}")
            entries.append({"file": copy.name, "path": path, "sha256": sha256_bytes(data)})
        (folder / "backup-manifest.json").write_text(
            json.dumps({"format_version": 1, "kind": "import", "files": entries}, indent=2), encoding="utf-8"
        )
        self.last_backup = folder
        return folder

    def export(self, game_configs: Dict[str, List[str]], output_path: str) -> None:
        """Export configuration files for multiple games to *output_path*.

        Parameters
        ----------
        game_configs:
            A mapping of game name → list of absolute config file paths.
        output_path:
            Destination path for the generated JSON package (e.g.
            ``backup.json``).
        """
        package: Dict[str, Any] = {
            "version": 1,
            "games": {},
        }

        for game_name, paths in game_configs.items():
            game_data: Dict[str, Any] = {}
            for config_path in paths:
                if not os.path.isfile(config_path):
                    continue
                try:
                    data = self._reader.read(config_path)
                    game_data[config_path] = data
                except Exception as exc:
                    game_data[config_path] = {"_error": str(exc)}
            package["games"][game_name] = game_data

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(package, f, indent=2, ensure_ascii=False)

    def import_package(self, package_path: str) -> Dict[str, List[str]]:
        """Restore configuration files from a package created by :meth:`export`.

        Each configuration file is written back to its original absolute path.
        Returns a mapping of game name → list of restored file paths.

        Raises ``FileNotFoundError`` if *package_path* does not exist.
        Raises ``ValueError`` if the package version is unsupported.
        """
        if not os.path.isfile(package_path):
            raise FileNotFoundError(f"Package not found: {package_path}")

        with open(package_path, "r", encoding="utf-8") as f:
            package: Dict[str, Any] = json.load(f)

        pkg_version = package.get("version")
        if pkg_version not in self.SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported package version: {pkg_version}"
            )

        if pkg_version == 2:
            return self._import_v2(package)

        self._backup_existing([
            config_path
            for game_data in package.get("games", {}).values()
            for config_path, data in game_data.items()
            if isinstance(data, dict) and "_error" not in data
        ])
        restored: Dict[str, List[str]] = {}
        for game_name, game_data in package.get("games", {}).items():
            restored_paths: List[str] = []
            for config_path, data in game_data.items():
                if "_error" in data:
                    continue
                try:
                    self._writer.write(data, config_path)
                    restored_paths.append(config_path)
                except Exception:
                    pass
            restored[game_name] = restored_paths

        return restored

    def _import_v2(self, package: Dict[str, Any]) -> Dict[str, List[str]]:
        """Restore config files from a version-2 package (ConfigExporter format).

        Version 2 stores each config file as a dict with ``expanded_path``,
        ``content``, ``found``, ``error``, and optionally ``type`` keys.
        Registry entries are skipped (cannot be written back easily).
        """
        targets: List[str] = []
        for game_name, game_data in package.get("games", {}).items():
            for cfg in game_data.get("config_files", []):
                if cfg.get("type") == "registry" or not cfg.get("expanded_path") or not cfg.get("content"):
                    continue
                targets.append(cfg["expanded_path"])
                sidecar = self._forza_fullscreen_sidecar(cfg["expanded_path"], cfg["content"])
                if sidecar is not None:
                    targets.append(sidecar)
        self._backup_existing(targets)

        restored: Dict[str, List[str]] = {}
        for game_name, game_data in package.get("games", {}).items():
            restored_paths: List[str] = []
            config_files = game_data.get("config_files", [])
            for cfg in config_files:
                # Skip registry entries – we can't write back to the registry
                if cfg.get("type") == "registry":
                    continue
                path = cfg.get("expanded_path", "")
                content = cfg.get("content")
                if not path or not content:
                    continue
                if cfg.get("error"):
                    continue
                try:
                    if "grand theft auto v enhanced" in game_name.casefold():
                        # Exact bytes: the GTA guarded restore compares them.
                        atomic_write_bytes(path, content.encode("utf-8"))
                    else:
                        atomic_write_text(path, content)
                    restored_paths.append(path)
                    sidecar = self._forza_fullscreen_sidecar(path, content)
                    if sidecar is not None:
                        atomic_write_bytes(
                            sidecar, bytes([1 if self._forza_fullscreen_value(content) == "1" else 0])
                        )
                        restored_paths.append(sidecar)
                except Exception:
                    pass
            restored[game_name] = restored_paths

        return restored

    @staticmethod
    def _forza_fullscreen_sidecar(path: str, content: str) -> str | None:
        config_path = os.path.normpath(path)
        if (
            os.path.basename(config_path) == "UserConfigSelections"
            and os.path.basename(os.path.dirname(config_path)) == "ForzaUserConfigSelections"
            and "<UserConfig" in content
        ):
            root = os.path.dirname(os.path.dirname(os.path.dirname(config_path)))
            return os.path.join(root, "fullscreen_choice")
        return None

    @staticmethod
    def _forza_fullscreen_value(content: str) -> str:
        match = re.search(r'<Fullscreen\s+value="([01])"', content)
        return match.group(1) if match else "0"
