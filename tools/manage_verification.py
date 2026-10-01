#!/usr/bin/env python3
"""Create review candidates and signed-by-hash GitHub Release assets locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_manager.verification import MANIFEST_FORMAT_VERSION, validate_manifest


PUBLIC_RULE_FIELDS = (
    "game", "platform", "version", "fingerprint", "status", "config_patterns",
    "supported_settings", "supported_values", "reader_id", "writer_id",
)


def create_candidate(report_path: Path, output_path: Path) -> None:
    with zipfile.ZipFile(report_path) as archive:
        report = json.loads(archive.read("manifest.json"))
    candidate = {
        "status": "candidate",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report_id": report["report_id"],
        "games": report["games"],
        "review_notes": "",
    }
    output_path.write_text(json.dumps(candidate, indent=2, ensure_ascii=False), encoding="utf-8")


def build_release(
    source_path: Path, output_dir: Path, version: str, client_version: str,
    base_manifest: Path | None = None,
) -> None:
    manifest, raw = _build_manifest(source_path, version, client_version, base_manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "verified-games.json"
    json_path.write_bytes(raw)
    (output_dir / "verified-games.json.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  verified-games.json\n", encoding="ascii"
    )


def _build_manifest(
    source_path: Path, version: str, client_version: str,
    base_manifest: Path | None = None,
):
    rules = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(rules, list):
        raise ValueError("reviewed rules must be a JSON array")
    public_rules = [
        {key: rule[key] for key in PUBLIC_RULE_FIELDS if key in rule}
        for rule in rules
        if isinstance(rule, dict)
    ]
    if base_manifest is not None:
        base_raw = base_manifest.read_bytes()
        checksum_path = base_manifest.with_name(base_manifest.name + ".sha256")
        expected = checksum_path.read_text(encoding="ascii").split()[0].lower()
        if re.fullmatch(r"[0-9a-f]{64}", expected) is None or hashlib.sha256(base_raw).hexdigest() != expected:
            raise ValueError("base_manifest_checksum_mismatch")
        base = json.loads(base_raw.decode("utf-8"))
        validate_manifest(base, client_version)
        base_rules = base["games"]
        def rule_key(rule):
            return (rule["game"].casefold(), rule["platform"].casefold(), rule.get("version"), rule.get("fingerprint"))
        if len({rule_key(rule) for rule in base_rules + public_rules}) != len(base_rules) + len(public_rules):
            raise ValueError("reviewed_rule_conflicts_with_base")
        public_rules = base_rules + public_rules
    manifest = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "manifest_version": version,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "generator_version": "manage_verification.py",
        "minimum_client_version": client_version,
        "games": public_rules,
    }
    validate_manifest(manifest, client_version)
    raw = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    return manifest, raw


def build_offline_bundle(
    source_path: Path, output_path: Path, version: str, client_version: str,
    base_manifest: Path | None = None,
) -> None:
    """Create a portable integrity-checked bundle from reviewed public rules."""
    _, raw = _build_manifest(source_path, version, client_version, base_manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256(raw).hexdigest() + "  verified-games.json\n"
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("verified-games.json", raw)
        archive.writestr("verified-games.json.sha256", checksum.encode("ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare verification candidates and Release assets")
    commands = parser.add_subparsers(dest="command", required=True)
    candidate = commands.add_parser("candidate")
    candidate.add_argument("report", type=Path)
    candidate.add_argument("--output", type=Path, required=True)
    release = commands.add_parser("build-release")
    release.add_argument("rules", type=Path, help="Human-reviewed array of verification rules")
    release.add_argument("--output-dir", type=Path, required=True)
    release.add_argument("--version", required=True)
    release.add_argument("--minimum-client-version", required=True)
    release.add_argument("--base-manifest", type=Path, help="Checksum-verified published manifest to preserve")
    bundle = commands.add_parser("build-bundle")
    bundle.add_argument("rules", type=Path, help="Human-reviewed public verification rules")
    bundle.add_argument("--output", type=Path, required=True)
    bundle.add_argument("--version", required=True)
    bundle.add_argument("--minimum-client-version", required=True)
    bundle.add_argument("--base-manifest", type=Path, help="Checksum-verified published manifest to preserve")
    args = parser.parse_args()
    if args.command == "candidate":
        create_candidate(args.report, args.output)
    elif args.command == "build-release":
        build_release(args.rules, args.output_dir, args.version, args.minimum_client_version, args.base_manifest)
    else:
        build_offline_bundle(args.rules, args.output, args.version, args.minimum_client_version, args.base_manifest)


if __name__ == "__main__":
    main()