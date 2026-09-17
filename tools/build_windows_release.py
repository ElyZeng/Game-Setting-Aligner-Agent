#!/usr/bin/env python3
"""Build a complete Windows release bundle.

This command is intentionally release-oriented: it builds the PyInstaller
bundle, creates a SHA-256 file, obtains the verification manifest assets, and
validates that all four deliverables exist before returning success.

Examples:
    python tools/build_windows_release.py --version 0.07.4
    python tools/build_windows_release.py --version 0.07.4 --rules-dir release-assets/verification-rules-v1.2.1
    python tools/build_windows_release.py --version 0.07.4 --rules-release verification-rules-v1.2.1

It does not create a GitHub Release. Upload the four files from the printed
output only after reviewing the generated bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "release-output"
RULE_FILES = ("verified-games.json", "verified-games.json.sha256")


def run(command: list[str], *, cwd: Path = REPO_ROOT) -> None:
    print("+", " ".join(str(part) for part in command))
    subprocess.run(command, cwd=cwd, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_app_version() -> str:
    main_text = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    marker = '__version__ = "'
    start = main_text.index(marker) + len(marker)
    return main_text[start:main_text.index('"', start)]


def prepare_rules(output: Path, rules_dir: Path | None, rules_release: str | None) -> None:
    if rules_dir and rules_release:
        raise ValueError("choose only one of --rules-dir or --rules-release")
    source_dir = rules_dir
    temporary_dir: Path | None = None
    try:
        if rules_release:
            gh = shutil.which("gh") or shutil.which("gh.exe")
            if not gh:
                raise RuntimeError("GitHub CLI is required for --rules-release")
            temporary_dir = Path(tempfile.mkdtemp(prefix="game-tuner-rules-"))
            run([gh, "release", "download", rules_release, "--repo", "ElyZeng/Game-Setting-Aligner-Agent", "--pattern", "verified-games.json", "--pattern", "verified-games.json.sha256", "--dir", str(temporary_dir), "--clobber"])
            source_dir = temporary_dir
        if source_dir is None:
            raise ValueError("provide --rules-dir or --rules-release")
        for name in RULE_FILES:
            source = source_dir / name
            if not source.is_file():
                raise FileNotFoundError(f"missing verification asset: {source}")
            shutil.copy2(source, output / name)
    finally:
        if temporary_dir:
            shutil.rmtree(temporary_dir, ignore_errors=True)


def validate_manifest(output: Path) -> None:
    manifest_path = output / "verified-games.json"
    checksum_path = output / "verified-games.json.sha256"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = checksum_path.read_text(encoding="ascii").split()[0].lower()
    actual = sha256(manifest_path)
    if expected != actual:
        raise ValueError(f"verification manifest checksum mismatch: expected {expected}, got {actual}")
    if not manifest.get("games"):
        raise ValueError("verification manifest has no games")


def build(args: argparse.Namespace) -> Path:
    version = args.version or read_app_version()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bundle_name = "GameTuner-windows-x64"
    zip_path = output / f"{bundle_name}.zip"
    checksum_path = output / f"{bundle_name}.zip.sha256"
    build_dir = REPO_ROOT / "build"
    dist_dir = REPO_ROOT / "dist"

    run([sys.executable, "-m", "pytest", "-q"])
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", bundle_name, "--add-data", "cache;cache", "main.py"])
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=dist_dir, base_dir=bundle_name)
    checksum_path.write_text(f"{sha256(zip_path)}  {zip_path.name}\n", encoding="ascii")
    prepare_rules(output, args.rules_dir, args.rules_release)
    validate_manifest(output)

    expected = [zip_path, checksum_path, output / RULE_FILES[0], output / RULE_FILES[1]]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise FileNotFoundError("release bundle incomplete: " + ", ".join(missing))
    print(f"Release version: {version}")
    print("Release assets:")
    for path in expected:
        print(f"  {path} ({path.stat().st_size} bytes)")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Version label for the build report; defaults to main.py __version__")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    rules = parser.add_mutually_exclusive_group(required=True)
    rules.add_argument("--rules-dir", type=Path)
    rules.add_argument("--rules-release", help="GitHub Release tag containing verification assets")
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
