#!/usr/bin/env python3
"""Offline smoke test suitable for a clean Windows test environment."""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_manager.diagnostic_package import export_diagnostic_package
from config_manager.verification import VerificationError, VerificationRegistry, backup_and_write


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="game-tuner-smoke-") as temp_dir:
        root = Path(temp_dir)
        registry = VerificationRegistry("0.05.1", data_dir=root / "app-data")
        try:
            try:
                backup_and_write("Unknown Game", "Steam", "unknown", [], {}, lambda *_: [], registry)
            except VerificationError as exc:
                if str(exc) != "test_write_consent_required":
                    raise
            else:
                raise AssertionError("write was not blocked without test consent")

            report_path = export_diagnostic_package([{
                "name": "Smoke Test Game",
                "platform": "Steam",
                "version": "unknown",
                "config_files": [{
                    "expanded_path": r"C:\Users\Example\settings.ini",
                    "found": True,
                    "content": "VSync=True\n",
                }],
                "parsed_settings": {"vsync": "On"},
            }], root / "reports", include_content=False, include_hardware=False)
            with zipfile.ZipFile(report_path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                assert manifest["privacy"]["device_name_collected"] is False
                assert "configs/0-0.txt" not in archive.namelist()
        finally:
            logger = logging.getLogger("config_manager.verification")
            for handler in tuple(logger.handlers):
                if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == root / "app-data/logs/verification.log":
                    logger.removeHandler(handler)
                    handler.close()

    print("PASS: clean-environment smoke test completed")


if __name__ == "__main__":
    main()