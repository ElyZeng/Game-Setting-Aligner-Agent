from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

from tools.manage_verification import build_offline_bundle, build_release
from config_manager.verification import VerificationError, validate_manifest


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


def test_gta_reviewed_bundle_keeps_per_value_write_allowlist(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([{
        "game": "Grand Theft Auto V Enhanced", "platform": "Steam",
        "version": "1.0.1158.16", "fingerprint": "a" * 64,
        "status": "write_candidate", "config_patterns": ["settings.xml"],
        "supported_settings": ["vsync", "frame_limit"],
        "supported_values": {"vsync": ["Off", "On"], "frame_limit": ["Unlimited", "60 FPS"]},
        "reader_id": "gta-enhanced-xml-reader", "writer_id": "gta-enhanced-xml-writer",
        "review_notes": "private review data",
    }]), encoding="utf-8")
    output = tmp_path / "rules.gtrules"

    build_offline_bundle(rules, output, "1.0.0", "0.05.1")

    with zipfile.ZipFile(output) as archive:
        rule = json.loads(archive.read("verified-games.json"))["games"][0]
    assert rule["supported_values"] == {
        "vsync": ["Off", "On"], "frame_limit": ["Unlimited", "60 FPS"],
    }
    assert "review_notes" not in rule


def test_gta_release_build_preserves_checksum_verified_base_rules(tmp_path):
    existing = {
        "game": "Existing", "platform": "Steam", "version": "1.0", "fingerprint": "known",
        "status": "write_candidate", "supported_settings": ["vsync"],
        "config_patterns": ["settings.ini"], "reader_id": "existing-reader", "writer_id": "existing-writer",
    }
    base_path = tmp_path / "verified-games.json"
    base_raw = json.dumps({
        "format_version": 1, "manifest_version": "1.2.20",
        "minimum_client_version": "0.08.17", "games": [existing],
    }).encode("utf-8")
    base_path.write_bytes(base_raw)
    base_path.with_name(base_path.name + ".sha256").write_text(
        hashlib.sha256(base_raw).hexdigest() + "  verified-games.json\n", encoding="ascii",
    )
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([{
        "game": "Grand Theft Auto V Enhanced", "platform": "Steam",
        "version": "1.0.1158.16", "fingerprint": "a" * 64,
        "status": "write_candidate", "config_patterns": ["settings.xml"],
        "supported_settings": ["vsync"], "supported_values": {"vsync": ["Off", "On"]},
        "reader_id": "gta-enhanced-xml-reader", "writer_id": "gta-enhanced-xml-writer",
    }]), encoding="utf-8")
    bundle = tmp_path / "rules.gtrules"

    build_offline_bundle(rules, bundle, "1.2.21", "0.08.17", base_manifest=base_path)

    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("verified-games.json"))
    assert manifest["manifest_version"] == "1.2.21"
    assert manifest["games"][0] == existing
    assert manifest["games"][1]["supported_values"] == {"vsync": ["Off", "On"]}

    base_path.with_name(base_path.name + ".sha256").write_text("0" * 64, encoding="ascii")
    with pytest.raises(ValueError, match="base_manifest_checksum_mismatch"):
        build_offline_bundle(rules, tmp_path / "bad.gtrules", "1.2.21", "0.08.17", base_manifest=base_path)
    assert not (tmp_path / "bad.gtrules").exists()

    base_path.with_name(base_path.name + ".sha256").write_text(
        hashlib.sha256(base_raw).hexdigest(), encoding="ascii",
    )
    rules.write_text(json.dumps([existing]), encoding="utf-8")
    with pytest.raises(ValueError, match="reviewed_rule_conflicts_with_base"):
        build_offline_bundle(rules, tmp_path / "conflict.gtrules", "1.2.21", "0.08.17", base_manifest=base_path)
    assert not (tmp_path / "conflict.gtrules").exists()


def test_replacement_requires_one_exact_rule_and_preserves_other_base_rules(tmp_path):
    existing = {
        "game": "Forza Horizon 6", "platform": "Steam", "version": "6.440.853.0",
        "fingerprint": "a" * 64, "status": "write_candidate",
        "supported_settings": ["resolution"], "config_patterns": ["UserConfigSelections"],
        "reader_id": "existing-parser", "writer_id": "forza-xml-writer",
    }
    unrelated = {**existing, "game": "Other Game", "fingerprint": "b" * 64}
    base_path = tmp_path / "verified-games.json"
    base_raw = json.dumps({
        "format_version": 1, "manifest_version": "1.2.20",
        "minimum_client_version": "0.08.17", "games": [existing, unrelated],
    }).encode("utf-8")
    base_path.write_bytes(base_raw)
    base_path.with_name(base_path.name + ".sha256").write_text(
        hashlib.sha256(base_raw).hexdigest() + "  verified-games.json\n", encoding="ascii",
    )
    replacement = {**existing, "supported_settings": ["resolution", "quick_preset"],
                   "supported_values": {"quick_preset": ["Ultra"]}}
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([replacement]), encoding="utf-8")

    with pytest.raises(ValueError, match="reviewed_rule_conflicts_with_base"):
        build_release(rules, tmp_path / "conflict", "1.2.21", "0.08.18", base_path)
    with pytest.raises(ValueError, match="forza_preset_client_update_required"):
        build_release(rules, tmp_path / "old-client", "1.2.21", "0.08.17", base_path, replace_base_rule=True)
    assert not (tmp_path / "old-client").exists()
    build_release(rules, tmp_path / "release", "1.2.21", "0.08.18", base_path, replace_base_rule=True)
    output = tmp_path / "release" / "verified-games.json"
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["games"] == [replacement, unrelated]
    assert manifest["minimum_client_version"] == "0.08.18"
    assert output.with_name(output.name + ".sha256").read_text().split()[0] == hashlib.sha256(output.read_bytes()).hexdigest()

    rules.write_text(json.dumps([{**replacement, "fingerprint": "c" * 64}]), encoding="utf-8")
    with pytest.raises(ValueError, match="replacement_requires_one_exact_base_rule"):
        build_release(rules, tmp_path / "bad-key", "1.2.21", "0.08.18", base_path, replace_base_rule=True)
    rules.write_text(json.dumps([replacement, unrelated]), encoding="utf-8")
    with pytest.raises(ValueError, match="replacement_requires_one_exact_base_rule"):
        build_release(rules, tmp_path / "multiple", "1.2.21", "0.08.18", base_path, replace_base_rule=True)


@pytest.mark.parametrize("invalid", [
    {"supported_values": {"quick_preset": ["Maybe"]}},
    {"supported_values": {"quick_preset": ["Ultra", "Ultra"]}},
    {"supported_values": {}},
    {"fingerprint": "*"},
    {"platform": "Epic"},
    {"writer_id": "generic-xml-writer"},
])
def test_forza_preset_manifest_requires_exact_rule_and_observed_values(invalid):
    rule = {
        "game": "Forza Horizon 6", "platform": "Steam", "version": "6.440.853.0",
        "fingerprint": "a" * 64, "status": "write_candidate",
        "supported_settings": ["resolution", "quick_preset"],
        "supported_values": {"quick_preset": ["Very Low", "Low", "Medium", "High", "Ultra", "Extreme"]},
        "writer_id": "forza-xml-writer",
    }
    manifest = {"format_version": 1, "minimum_client_version": "0.08.18", "games": [rule]}
    validate_manifest(manifest, "0.08.18")
    rule.update(invalid)
    with pytest.raises(VerificationError, match="invalid_forza_preset_rule"):
        validate_manifest(manifest, "0.08.18")


@pytest.mark.parametrize("values", [None, {"vsync": ["Maybe"]}, {"vsync": ["On"], "frame_limit": ["144 FPS"]}])
def test_gta_rule_builder_rejects_missing_or_unobserved_values(tmp_path, values):
    rules = tmp_path / "rules.json"
    rule = {
        "game": "Grand Theft Auto V Enhanced", "platform": "Steam",
        "version": "1.0.1158.16", "fingerprint": "a" * 64,
        "status": "write_candidate", "config_patterns": ["settings.xml"],
        "supported_settings": ["vsync"], "reader_id": "gta-enhanced-xml-reader",
        "writer_id": "gta-enhanced-xml-writer",
    }
    if values is not None:
        rule["supported_values"] = values
    rules.write_text(json.dumps([rule]), encoding="utf-8")
    output = tmp_path / "rules.gtrules"

    with pytest.raises(VerificationError, match="invalid_gta_write_rule"):
        build_offline_bundle(rules, output, "1.0.0", "0.05.1")
    assert not output.exists()


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