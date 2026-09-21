"""Tests for Windows game version detection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import config_manager.game_version as game_version


def _make_windows_install(monkeypatch):
    monkeypatch.setattr(game_version.os, "name", "nt")


def test_prefers_game_executable_over_launcher_with_unicode_path(tmp_path, monkeypatch):
    install_path = tmp_path / "Cyberpunk 2077 (測試)"
    launcher = install_path / "REDprelauncher.exe"
    executable = install_path / "bin" / "x64" / "Cyberpunk2077.exe"
    launcher.parent.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    launcher.touch()
    executable.touch()
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="2.31\n")

    _make_windows_install(monkeypatch)
    monkeypatch.setattr(game_version.subprocess, "run", run)

    assert game_version.detect_game_version(str(install_path)) == "2.31"
    assert calls[0][1]["env"]["GAME_TUNER_EXE"] == str(executable)
    assert "ProductVersion" in calls[0][0][-1]
    assert str(executable) not in calls[0][0]


def test_returns_unknown_when_executables_have_no_product_version(tmp_path, monkeypatch):
    executable = tmp_path / "Example Game" / "ExampleGame.exe"
    executable.parent.mkdir()
    executable.touch()

    _make_windows_install(monkeypatch)
    monkeypatch.setattr(
        game_version.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="\n"),
    )

    assert game_version.detect_game_version(str(executable.parent)) == "unknown"


def test_uses_matching_steam_manifest_build_id_when_product_version_is_empty(tmp_path, monkeypatch):
    steamapps = tmp_path / "steamapps"
    install_path = steamapps / "common" / "BlackMythWukong"
    install_path.mkdir(parents=True)
    (install_path / "b1.exe").touch()
    (steamapps / "appmanifest_2358720.acf").write_text(
        '"AppState"\n{\n\t"appid" "2358720"\n\t"installdir" "BlackMythWukong"\n\t"buildid" "21393610"\n}\n',
        encoding="utf-8",
    )

    _make_windows_install(monkeypatch)
    monkeypatch.setattr(
        game_version.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="\n"),
    )

    assert game_version.detect_game_version(str(install_path)) == "Steam build 21393610"


@pytest.mark.parametrize("name", ["GameLauncher.exe", "CrashReporter.exe", "Uninstall.exe", "HelperTool.exe"])
def test_excludes_non_game_executables(name):
    assert game_version._is_game_executable(name) is False