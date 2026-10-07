from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import cli
from tools.manage_verification import build_offline_bundle


def _rules(path):
    path.write_text(json.dumps([{
        "game": "Example", "platform": "Steam", "version": "1.0", "fingerprint": "abc",
        "status": "read_verified", "config_patterns": [], "supported_settings": [],
        "reader_id": "existing-parser", "writer_id": None,
    }]), encoding="utf-8")


def test_import_rules_cli_installs_valid_bundle(tmp_path, capsys):
    rules = tmp_path / "rules.json"
    bundle = tmp_path / "rules.gtrules"
    _rules(rules)
    build_offline_bundle(rules, bundle, "2.0.0", "0.05.1")

    cli.cmd_import_verification(SimpleNamespace(
        bundle=str(bundle), allow_rollback=False, data_dir=str(tmp_path / "data")
    ))

    result = json.loads(capsys.readouterr().out)
    assert result["installed"] is True
    assert result["integrity"] == "sha256_verified"
    assert result["publisher_authenticated"] is False
    assert result["trusted_channel_required"] is True


def test_import_rules_cli_reports_invalid_bundle_and_nonzero_exit(tmp_path, capsys):
    bundle = tmp_path / "bad.gtrules"
    bundle.write_bytes(b"not a zip")

    with pytest.raises(SystemExit, match="1"):
        cli.cmd_import_verification(SimpleNamespace(
            bundle=str(bundle), allow_rollback=False, data_dir=str(tmp_path / "data")
        ))

    result = json.loads(capsys.readouterr().out)
    assert result["installed"] is False
    assert result["error"] == "invalid_offline_bundle"
    assert result["source"] == "offline_bundle"


def test_import_rules_command_parses_rollback_override():
    args = cli.build_parser().parse_args([
        "import-rules", "rules.gtrules", "--allow-rollback",
    ])

    assert args.func is cli.cmd_import_verification
    assert args.bundle == "rules.gtrules"
    assert args.allow_rollback is True


def test_gta_restore_baseline_cli_requires_consent_before_scanning(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_scan_all", lambda: pytest.fail("restore must stop before scanning"))
    args = cli.build_parser().parse_args([
        "restore-baseline", "Grand Theft Auto V Enhanced", "baseline.json",
        "--expected-sha256", "0" * 64, "--rules-dir", str(tmp_path),
    ])

    with pytest.raises(SystemExit, match="1"):
        args.func(args)

    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked", "error": "restore_consent_required",
    }


def test_gta_generic_import_requires_guarded_restore(tmp_path, capsys):
    config_path = tmp_path / "GTAV Enhanced" / "settings.xml"
    config_path.parent.mkdir()
    config_path.write_bytes(b"unchanged")
    package_path = tmp_path / "baseline.json"
    package_path.write_text(json.dumps({
        "version": 2,
        "games": {"Grand Theft Auto V Enhanced": {"config_files": [{
            "expanded_path": str(config_path), "content": "changed", "found": True,
        }]}},
    }), encoding="utf-8")

    with pytest.raises(SystemExit, match="1"):
        cli.cmd_import(SimpleNamespace(package=str(package_path)))

    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked", "error": "gta_restore_requires_guard",
    }
    assert config_path.read_bytes() == b"unchanged"


def test_gta_preflight_cli_blocks_without_rule_or_file_write(tmp_path, monkeypatch, capsys):
    from config_manager import VerificationRegistry

    config_path = tmp_path / "settings.xml"
    content = '<Settings><video><VSync value="1"/></video></Settings>'
    config_path.write_text(content, encoding="utf-8")
    registry = VerificationRegistry("0.08.6", data_dir=tmp_path / "app-data")
    monkeypatch.setattr("config_manager.VerificationRegistry", lambda *_args: registry)
    monkeypatch.setattr(cli, "_scan_all", lambda: [{"name": "Grand Theft Auto V Enhanced", "platform": "Steam"}])
    monkeypatch.setattr(cli, "_detect_game_files", lambda *_args: [
        {"found": True, "expanded_path": str(config_path), "content": content},
    ])

    args = cli.build_parser().parse_args([
        "preflight", "Grand Theft Auto V Enhanced", "--settings", '{"vsync": "Off"}',
    ])
    with pytest.raises(SystemExit, match="1"):
        args.func(args)

    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked", "error": "write_not_allowed:game_not_listed",
    }
    assert config_path.read_text(encoding="utf-8") == content
    assert not registry.test_write_enabled()