from __future__ import annotations

import hashlib
import json

import pytest

from config_manager.verification import (
    builtin_manifest,
    VerificationError,
    VerificationRegistry,
    backup_and_write,
    structural_fingerprint,
)


class _Response:
    def __init__(self, payload=None, content=b"", text=""):
        self.payload = payload
        self.content = content
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_unknown_game_is_not_allowed_to_write(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.enable_test_writes()
    with pytest.raises(VerificationError, match="write_not_allowed:game_not_listed"):
        backup_and_write(
            "Unknown Game", "Steam", "1.0", [], {"vsync": "On"},
            lambda *_: [], registry,
        )


def test_verified_game_still_requires_test_write_consent(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    fingerprint = structural_fingerprint([])
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Example", "platform": "Steam", "version": "1.0", "fingerprint": fingerprint,
            "status": "write_verified", "config_patterns": [], "supported_settings": [],
            "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }), encoding="utf-8")
    with pytest.raises(VerificationError, match="test_write_consent_required"):
        backup_and_write("Example", "Steam", "1.0", [], {"vsync": "On"}, lambda *_: [], registry)


def test_structural_fingerprint_ignores_setting_values():
    one = structural_fingerprint([{"expanded_path": "GameUserSettings.ini", "content": "VSync=True\n"}])
    two = structural_fingerprint([{"expanded_path": "GameUserSettings.ini", "content": "VSync=False\n"}])
    assert one == two


def test_release_update_installs_manifest_and_keeps_previous(tmp_path):
    manifest = {
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [],
    }
    raw = json.dumps(manifest).encode("utf-8")
    checksum = hashlib.sha256(raw).hexdigest()
    responses = iter([
        _Response({"assets": [
            {"name": "verified-games.json", "browser_download_url": "manifest"},
            {"name": "verified-games.json.sha256", "browser_download_url": "checksum"},
        ]}),
        _Response(content=raw),
        _Response(text=checksum),
    ])
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path, http_get=lambda *_args, **_kwargs: next(responses))

    assert registry.update()["updated"] is True
    assert registry.load()["manifest_version"] == "1.0.0"


def test_status_uses_newly_installed_manifest_after_update(tmp_path):
    config_files = [{"expanded_path": "UserConfigSelections", "content": "VSync=On\n"}]
    fingerprint = structural_fingerprint(config_files)
    manifest = {
        "format_version": 1,
        "manifest_version": "2.0.0",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Forza Horizon 6", "platform": "Steam", "version": "1.0",
            "fingerprint": fingerprint, "status": "write_candidate", "config_patterns": [],
            "supported_settings": [], "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }
    raw = json.dumps(manifest).encode("utf-8")
    checksum = hashlib.sha256(raw).hexdigest()
    responses = iter([
        _Response({"assets": [
            {"name": "verified-games.json", "browser_download_url": "manifest"},
            {"name": "verified-games.json.sha256", "browser_download_url": "checksum"},
        ]}),
        _Response(content=raw),
        _Response(text=checksum),
    ])
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path, http_get=lambda *_args, **_kwargs: next(responses))

    assert registry.status_for("Forza Horizon 6", "Steam", "1.0", fingerprint)["reason"] == "game_not_listed"
    assert registry.update()["manifest_version"] == "2.0.0"
    assert registry.status_for("Forza Horizon 6", "Steam", "1.0", fingerprint)["status"] == "write_candidate"
    assert registry.status_for("Forza Horizon 6", "Steam", "2.0", fingerprint)["status"] == "candidate"
    assert registry.status_for("Forza Horizon 6", "Steam", "1.0", "other")["status"] == "candidate"


def test_empty_remote_manifest_preserves_builtin_rules(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [],
    }), encoding="utf-8")

    loaded = registry.load()

    assert loaded["manifest_version"] == "1.0.0"
    assert len(loaded["games"]) == len(builtin_manifest("0.05.1")["games"])
    assert registry.status_for("Counter-Strike 2", "Steam", "unknown", "anything")["status"] == "read_verified"


def test_remote_rule_overrides_builtin_rule(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "1.0.0",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Counter-Strike 2",
            "platform": "*",
            "version": "unknown",
            "fingerprint": "*",
            "status": "deprecated",
            "config_patterns": [],
            "supported_settings": [],
            "reader_id": "existing-parser",
            "writer_id": None,
        }],
    }), encoding="utf-8")

    assert registry.status_for("Counter-Strike 2", "Steam", "unknown", "anything")["status"] == "deprecated"


@pytest.mark.parametrize(
    ("declared_status", "expected_status"),
    [
        ("candidate", "candidate"),
        ("read_verified", "read_verified"),
        ("write_candidate", "candidate"),
        ("write_verified", "read_verified"),
        ("deprecated", "deprecated"),
    ],
)
def test_version_mismatch_preserves_or_safely_downgrades_status(
    tmp_path, declared_status, expected_status
):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "test",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Example", "platform": "Steam", "version": "1.0", "fingerprint": "*",
            "status": declared_status, "config_patterns": [], "supported_settings": [],
            "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }), encoding="utf-8")

    result = registry.status_for("Example", "Steam", "2.0", "anything")

    assert result["status"] == expected_status
    assert result["reason"] == "version_mismatch"


def test_write_candidate_allows_guarded_test_write(tmp_path):
    registry = VerificationRegistry("0.05.1", data_dir=tmp_path)
    registry.enable_test_writes()
    registry.current_path.write_text(json.dumps({
        "format_version": 1,
        "manifest_version": "test",
        "minimum_client_version": "0.05.1",
        "games": [{
            "game": "Example", "platform": "Steam", "version": "1.0",
            "fingerprint": structural_fingerprint([]), "status": "write_candidate",
            "config_patterns": [], "supported_settings": [],
            "reader_id": "existing-parser", "writer_id": "existing-writer",
        }],
    }), encoding="utf-8")

    called = []
    result = backup_and_write(
        "Example", "Steam", "1.0", [], {},
        lambda *_: called.append(True) or [], registry,
    )

    assert result == []
    assert called == [True]