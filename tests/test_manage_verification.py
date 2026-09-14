from __future__ import annotations

import hashlib
import json
import zipfile

from tools.manage_verification import build_offline_bundle, build_release


def test_build_release_writes_matching_checksum(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([{
        "game": "Example", "platform": "Steam", "version": "1.0", "fingerprint": "abc",
        "status": "read_verified", "config_patterns": [], "supported_settings": [],
        "reader_id": "existing-parser", "writer_id": None,
    }]), encoding="utf-8")
    build_release(rules, tmp_path / "release", "1.0.0", "0.05.1")
    payload = (tmp_path / "release" / "verified-games.json").read_bytes()
    checksum = (tmp_path / "release" / "verified-games.json.sha256").read_text().split()[0]
    assert checksum == hashlib.sha256(payload).hexdigest()


def test_build_offline_bundle_contains_only_manifest_and_checksum(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([{
        "game": "Example", "platform": "Steam", "version": "1.0", "fingerprint": "abc",
        "status": "read_verified", "config_patterns": [], "supported_settings": [],
        "reader_id": "existing-parser", "writer_id": None,
    }]), encoding="utf-8")
    output = tmp_path / "rules-1.0.0.gtrules"

    build_offline_bundle(rules, output, "1.0.0", "0.05.1")

    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            "verified-games.json", "verified-games.json.sha256",
        }
        manifest = json.loads(archive.read("verified-games.json"))
        checksum = archive.read("verified-games.json.sha256").decode("ascii").split()[0]
    assert manifest["manifest_version"] == "1.0.0"
    assert checksum == hashlib.sha256(
        json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def test_build_offline_bundle_excludes_private_review_data(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([{
        "game": "Example", "platform": "Steam", "version": "1.0", "fingerprint": "abc",
        "status": "read_verified", "config_patterns": [], "supported_settings": [],
        "reader_id": "existing-parser", "writer_id": None,
        "content": "private config", "hardware": {"gpu": "private"},
        "secret": "do-not-publish", "review_notes": "internal",
    }]), encoding="utf-8")
    output = tmp_path / "rules.gtrules"

    build_offline_bundle(rules, output, "1.0.0", "0.05.1")

    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("verified-games.json"))
    rule = manifest["games"][0]
    assert set(rule) == {
        "game", "platform", "version", "fingerprint", "status", "config_patterns",
        "supported_settings", "reader_id", "writer_id",
    }
    assert "private" not in json.dumps(manifest)
    assert "do-not-publish" not in json.dumps(manifest)