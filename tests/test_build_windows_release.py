from argparse import Namespace
from pathlib import Path

import tools.build_windows_release as release_builder
from tools.build_windows_release import ARCHIVE_NAME, PRODUCT_NAME


def test_release_uses_product_name_for_executable_and_platform_archive():
    assert PRODUCT_NAME == "Game-Setting-Aligner-Agent"
    assert ARCHIVE_NAME == "Game-Setting-Aligner-Agent-windows-x64"


def test_build_wires_product_name_to_pyinstaller_and_archive(tmp_path, monkeypatch):
    commands = []
    archives = []

    monkeypatch.setattr(release_builder, "run", lambda command, **_kwargs: commands.append(command))

    def make_archive(base_name, archive_format, *, root_dir, base_dir):
        archives.append((base_name, archive_format, root_dir, base_dir))
        Path(f"{base_name}.zip").write_bytes(b"release")

    def prepare_rules(output, _rules_dir, _rules_release):
        (output / "verified-games.json").write_text("{}", encoding="utf-8")
        (output / "verified-games.json.sha256").write_text("checksum", encoding="ascii")

    monkeypatch.setattr(release_builder.shutil, "make_archive", make_archive)
    monkeypatch.setattr(release_builder, "prepare_rules", prepare_rules)
    monkeypatch.setattr(release_builder, "validate_manifest", lambda _output: None)

    release_builder.build(Namespace(
        version="test",
        output_dir=tmp_path,
        rules_dir=tmp_path,
        rules_release=None,
    ))

    assert commands[1][commands[1].index("--name") + 1] == PRODUCT_NAME
    assert archives[0][0] == str(tmp_path / ARCHIVE_NAME)
    assert archives[0][3] == PRODUCT_NAME
    assert (tmp_path / f"{ARCHIVE_NAME}.zip.sha256").is_file()