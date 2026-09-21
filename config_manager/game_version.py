"""Best-effort game version detection without customer-entered values."""

from __future__ import annotations

import os
import subprocess

import vdf


_NON_GAME_EXECUTABLE_TERMS = (
    "launcher", "launch", "crash", "report", "uninstall", "setup", "install",
    "helper", "tool", "updater", "update",
)


def _normalise(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _is_game_executable(executable: str) -> bool:
    name = _normalise(os.path.splitext(os.path.basename(executable))[0])
    return not any(term in name for term in _NON_GAME_EXECUTABLE_TERMS)


def _executable_rank(executable: str, install_path: str) -> tuple[int, str]:
    name = _normalise(os.path.splitext(os.path.basename(executable))[0])
    game_name = _normalise(os.path.basename(os.path.normpath(install_path)))
    score = 0
    if name == game_name:
        score += 100
    elif game_name and game_name in name:
        score += 80
    elif len(name) >= 4 and name in game_name:
        score += 40
    if any(term in name for term in _NON_GAME_EXECUTABLE_TERMS):
        score -= 100
    return -score, executable.casefold()


def _steam_build_version(install_path: str) -> str:
    install_dir = os.path.normpath(install_path)
    common_dir = os.path.dirname(install_dir)
    steamapps_dir = os.path.dirname(common_dir)
    if os.path.basename(common_dir).casefold() != "common":
        return "unknown"
    expected_install_dir = os.path.basename(install_dir).casefold()
    try:
        manifest_names = os.listdir(steamapps_dir)
    except OSError:
        return "unknown"
    for manifest_name in manifest_names:
        if not manifest_name.casefold().startswith("appmanifest_") or not manifest_name.casefold().endswith(".acf"):
            continue
        manifest_path = os.path.join(steamapps_dir, manifest_name)
        try:
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                app_state = vdf.load(manifest_file).get("AppState", {})
        except (OSError, ValueError):
            continue
        if str(app_state.get("installdir", "")).casefold() != expected_install_dir:
            continue
        build_id = str(app_state.get("buildid", "")).strip()
        if build_id:
            return f"Steam build {build_id}"
    return "unknown"


def detect_game_version(install_path: str) -> str:
    """Read the most likely game executable's Windows product version."""
    if os.name != "nt" or not os.path.isdir(install_path):
        return "unknown"
    executables: list[str] = []
    for root, _, files in os.walk(install_path):
        executables.extend(
            os.path.join(root, name)
            for name in files
            if name.lower().endswith(".exe") and _is_game_executable(name)
        )
    if not executables:
        return "unknown"
    command = "[System.Diagnostics.FileVersionInfo]::GetVersionInfo($env:GAME_TUNER_EXE).ProductVersion"
    for executable in sorted(executables, key=lambda path: _executable_rank(path, install_path)):
        environment = os.environ.copy()
        environment["GAME_TUNER_EXE"] = executable
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=5, check=True, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.strip()
            if result:
                return result
        except (OSError, subprocess.SubprocessError):
            continue
    return _steam_build_version(install_path)