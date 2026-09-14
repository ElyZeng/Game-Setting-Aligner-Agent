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