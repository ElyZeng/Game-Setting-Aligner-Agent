#!/usr/bin/env python3
"""Game Tuner CLI – headless interface for agent/skill invocation.

Subcommands
-----------
scan        Detect installed games across Steam, Epic, GOG.
query       Query PCGamingWiki for a game's config file paths.
detect      Detect and read local config files for a game.
parse       Parse key graphics settings from config files.
apply       Write new graphics settings to a game's config files.
export      Export selected games' configs to a JSON package.
import      Import (restore) configs from a JSON package.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from main import __version__


# ── helpers ──────────────────────────────────────────────────────────

def _json_out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _scan_all():
    """Return a list of dicts for every detected game."""
    from scanner import SteamScanner, EpicScanner, GOGScanner

    results = []
    for Scanner in (SteamScanner, EpicScanner, GOGScanner):
        try:
            for g in Scanner().scan():
                results.append({
                    "name": g.name,
                    "platform": g.platform,
                    "install_path": getattr(g, "install_path", ""),
                    "app_id": getattr(g, "app_id", getattr(g, "game_id", getattr(g, "app_name", ""))),
                })
        except Exception as exc:
            results.append({"error": f"{Scanner.__name__}: {exc}"})
    return results


# ── subcommands ──────────────────────────────────────────────────────

def cmd_scan(args):
    games = _scan_all()
    if args.platform:
        games = [g for g in games if g.get("platform", "").lower() == args.platform.lower()]
    _json_out(games)


def cmd_query(args):
    from wiki_api import PCGamingWikiClient

    client = PCGamingWikiClient()
    info = client.get_config_info(args.game, install_path=args.install_path or "")
    _json_out(info)


def cmd_detect(args):
    from wiki_api import PCGamingWikiClient
    from config_manager import detect_config_files, _try_read_file, _read_registry_key, _is_expanded_registry_path

    client = PCGamingWikiClient()
    info = client.get_config_info(args.game, install_path=args.install_path or "")
    expanded = info.get("expanded_paths") or []
    found = detect_config_files(expanded)

    config_files = []
    for path in found:
        if _is_expanded_registry_path(path):
            config_files.append(_read_registry_key(path))
        else:
            config_files.append(_try_read_file(path))
    _json_out(config_files)


def cmd_parse(args):
    from config_manager import extract_key_settings, SETTING_OPTIONS, DISPLAY_NAMES_EN, setting_options_for_game

    if args.config_json:
        with open(args.config_json, "r", encoding="utf-8") as f:
            config_files = json.load(f)
    else:
        # Detect first, then parse
        from wiki_api import PCGamingWikiClient
        from config_manager import detect_config_files, _try_read_file, _read_registry_key, _is_expanded_registry_path

        client = PCGamingWikiClient()
        info = client.get_config_info(args.game, install_path=args.install_path or "")
        expanded = info.get("expanded_paths") or []
        found = detect_config_files(expanded)

        config_files = []
        for path in found:
            if _is_expanded_registry_path(path):
                config_files.append(_read_registry_key(path))
            else:
                config_files.append(_try_read_file(path))

    settings = extract_key_settings(args.game, config_files)
    _json_out({
        "game": args.game,
        "settings": settings,
        "available_options": {
            key: setting_options_for_game(
                args.game,
                key,
                settings.get(key),
                upscaling_method=settings.get("upscaling"),
            )
            for key in SETTING_OPTIONS
        },
        "setting_names": DISPLAY_NAMES_EN,
    })


def cmd_apply(args):
    from config_manager import VerificationRegistry, backup_and_write, detect_game_version, write_settings

    settings = json.loads(args.settings)

    if args.config_json:
        with open(args.config_json, "r", encoding="utf-8") as f:
            config_files = json.load(f)
    else:
        from wiki_api import PCGamingWikiClient
        from config_manager import detect_config_files, _try_read_file, _read_registry_key, _is_expanded_registry_path

        client = PCGamingWikiClient()
        info = client.get_config_info(args.game, install_path=args.install_path or "")
        expanded = info.get("expanded_paths") or []
        found = detect_config_files(expanded)

        config_files = []
        for path in found:
            if _is_expanded_registry_path(path):
                config_files.append(_read_registry_key(path))
            else:
                config_files.append(_try_read_file(path))

    games = _scan_all()
    matched = next((game for game in games if game.get("name", "").lower() == args.game.lower()), {})
    registry = VerificationRegistry(__version__)
    if args.confirm_test_write:
        registry.enable_test_writes()
    results = backup_and_write(
        args.game, matched.get("platform", "Unknown"), detect_game_version(matched.get("install_path", "")),
        config_files, settings, write_settings, registry,
    )
    _json_out(results)


def cmd_verification_status(args):
    from config_manager import VerificationRegistry, detect_game_version, structural_fingerprint

    games = _scan_all()
    matched = next((game for game in games if game.get("name", "").lower() == args.game.lower()), {})
    config_files = _detect_game_files(args.game, args.install_path or "")
    registry = VerificationRegistry(__version__)
    _json_out(registry.status_for(
        args.game, matched.get("platform", "Unknown"), detect_game_version(matched.get("install_path", "")),
        structural_fingerprint(config_files),
    ))


def _detect_game_files(game: str, install_path: str):
    from wiki_api import PCGamingWikiClient
    from config_manager import detect_config_files, _try_read_file, _read_registry_key, _is_expanded_registry_path

    info = PCGamingWikiClient().get_config_info(game, install_path=install_path)
    result = []
    for path in detect_config_files(info.get("expanded_paths") or []):
        result.append(_read_registry_key(path) if _is_expanded_registry_path(path) else _try_read_file(path))
    return result


def cmd_update_verification(args):
    from config_manager import VerificationRegistry
    _json_out(VerificationRegistry(__version__).update())


def cmd_import_verification(args):
    from config_manager import VerificationError, VerificationRegistry

    data_dir = Path(args.data_dir) if args.data_dir else None
    registry = VerificationRegistry(__version__, data_dir=data_dir)
    try:
        result = registry.import_offline_bundle(
            Path(args.bundle), allow_rollback=args.allow_rollback
        )
        _json_out(result)
    except (OSError, VerificationError) as exc:
        _json_out({
            "installed": False,
            "source": "offline_bundle",
            "error": str(exc),
            "log_path": str(registry.log_path),
        })
        raise SystemExit(1)


def cmd_diagnostic_export(args):
    from config_manager import ConfigExporter, export_diagnostic_package
    from wiki_api import PCGamingWikiClient

    requested = {name.strip().lower() for name in args.games.split(",")} if args.games else set()
    games = [game for game in _scan_all() if "error" not in game and (not requested or game["name"].lower() in requested)]

    class _Game:
        def __init__(self, data):
            self.name = data["name"]
            self.platform = data.get("platform", "")
            self.install_path = data.get("install_path", "")

    exporter = ConfigExporter(wiki_client=PCGamingWikiClient())
    report_games = []
    for game in games:
        info = exporter._build_game_info(_Game(game))
        report_games.append({"name": game["name"], "platform": game.get("platform", ""), **info})
    output = export_diagnostic_package(report_games, args.output_dir, args.include_content, not args.exclude_hardware)
    _json_out({"status": "ok", "output": str(output), "game_count": len(report_games)})


def cmd_export(args):
    from wiki_api import PCGamingWikiClient
    from config_manager import ConfigExporter

    client = PCGamingWikiClient()
    exporter = ConfigExporter(wiki_client=client)

    # Build lightweight game objects from scan results
    games_data = _scan_all()
    if args.games:
        names = {n.strip().lower() for n in args.games.split(",")}
        games_data = [g for g in games_data if g.get("name", "").lower() in names]

    class _Game:
        def __init__(self, d):
            self.name = d["name"]
            self.platform = d.get("platform", "")
            self.install_path = d.get("install_path", "")

    game_objs = [_Game(d) for d in games_data if "error" not in d]
    output = args.output or "export.json"
    exporter.export(game_objs, output)
    _json_out({"status": "ok", "output": os.path.abspath(output), "game_count": len(game_objs)})


def cmd_import(args):
    from config_manager import ConfigPackage

    pkg = ConfigPackage()
    restored = pkg.import_package(args.package)
    _json_out({"status": "ok", "restored": restored})


# ── argument parser ──────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        prog="game-tuner",
        description="Game Tuner CLI – manage PC game graphics settings.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # scan
    s = sub.add_parser("scan", help="Detect installed games")
    s.add_argument("--platform", choices=["steam", "epic", "gog"], help="Filter by platform")
    s.set_defaults(func=cmd_scan)

    # query
    s = sub.add_parser("query", help="Query PCGamingWiki for config paths")
    s.add_argument("game", help="Game title")
    s.add_argument("--install-path", help="Game install path (optional)")
    s.set_defaults(func=cmd_query)

    # detect
    s = sub.add_parser("detect", help="Detect and read local config files")
    s.add_argument("game", help="Game title")
    s.add_argument("--install-path", help="Game install path (optional)")
    s.set_defaults(func=cmd_detect)

    # parse
    s = sub.add_parser("parse", help="Parse key graphics settings")
    s.add_argument("game", help="Game title")
    s.add_argument("--install-path", help="Game install path (optional)")
    s.add_argument("--config-json", help="Path to a JSON file with config file data (skip auto-detect)")
    s.set_defaults(func=cmd_parse)

    # apply
    s = sub.add_parser("apply", help="Write settings to config files")
    s.add_argument("game", help="Game title")
    s.add_argument("--settings", required=True,
                   help='JSON string of settings, e.g. \'{"vsync": "Off", "frame_limit": "120"}\'')
    s.add_argument("--install-path", help="Game install path (optional)")
    s.add_argument("--config-json", help="Path to a JSON file with config file data (skip auto-detect)")
    s.add_argument(
        "--confirm-test-write", action="store_true",
        help="Acknowledge and enable experimental write mode for this Windows user",
    )
    s.set_defaults(func=cmd_apply)

    # verification
    s = sub.add_parser("verification-status", help="Check a game's read/write verification state")
    s.add_argument("game", help="Game title")
    s.add_argument("--install-path", help="Game install path (optional)")
    s.set_defaults(func=cmd_verification_status)

    s = sub.add_parser("update-verification", help="Download the latest verified-games Release manifest")
    s.set_defaults(func=cmd_update_verification)

    s = sub.add_parser("import-rules", help="Import a trusted-channel offline verification-rule bundle")
    s.add_argument("bundle", help="Path to a .gtrules offline bundle")
    s.add_argument(
        "--allow-rollback", action="store_true",
        help="Explicitly allow installation of an older manifest version",
    )
    s.add_argument("--data-dir", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_import_verification)

    s = sub.add_parser("diagnostic-export", help="Export anonymous diagnostic ZIP for selected games")
    s.add_argument("--games", help="Comma-separated detected game names (default: all)")
    s.add_argument("--output-dir", default=os.path.join(os.environ.get("LOCALAPPDATA", "."), "GameTuner", "reports"))
    s.add_argument("--include-content", action="store_true", help="Include anonymized config content after explicit review")
    s.add_argument("--exclude-hardware", action="store_true", help="Exclude approved hardware diagnostic fields")
    s.set_defaults(func=cmd_diagnostic_export)

    # export
    s = sub.add_parser("export", help="Export configs to JSON package")
    s.add_argument("--games", help="Comma-separated game names (default: all)")
    s.add_argument("--output", help="Output file path (default: export.json)")
    s.set_defaults(func=cmd_export)

    # import
    s = sub.add_parser("import", help="Restore configs from JSON package")
    s.add_argument("package", help="Path to the JSON package file")
    s.set_defaults(func=cmd_import)

    return p


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
