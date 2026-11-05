#!/usr/bin/env python3
"""Game Tuner External HTTP API.

Expose the existing CLI/skill capabilities through a lightweight JSON API
that can be called from any external tool or service.

Run:
    python external_api.py --host 127.0.0.1 --port 8787

Security model
--------------
* Read endpoints (``/health``, ``/scan``, ``/query``, ``/detect``, ``/parse``)
  are open to local callers.
* Endpoints that change files (``/apply``, ``/import``, ``/export``) require
  the ``X-GameTuner-Token`` header.  The token is printed at start-up, or set
  with ``--token`` / the ``GAMETUNER_API_TOKEN`` environment variable.
* No CORS headers are sent and the ``Host`` header must be a loopback name, so
  a web page open in the user's browser cannot drive the API.
* ``/apply`` uses the same guarded path as the GUI and CLI: user consent,
  verification rules, game-running check, backup and rollback.  Caller-supplied
  ``config_files`` are ignored for writes; files are always detected on disk.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cli import _scan_all
from config_manager import (
    ConfigPackage,
    ConfigExporter,
    DISPLAY_NAMES_EN,
    SETTING_OPTIONS,
    setting_options_for_game,
    _is_expanded_registry_path,
    _read_registry_key,
    _try_read_file,
    detect_config_files,
    extract_key_settings,
    write_settings,
)
from config_manager.verification import (
    VerificationError,
    VerificationRegistry,
    app_data_dir,
    backup_and_write,
    describe_verification_error,
)
from config_manager.game_version import detect_game_version
from main import __version__
from wiki_api import PCGamingWikiClient

TOKEN_HEADER = "X-GameTuner-Token"
WRITE_ENDPOINTS = frozenset({"/apply", "/import", "/export"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
MAX_BODY_BYTES = 10 * 1024 * 1024


def _detect_config_files(game: str, install_path: str = ""):
    client = PCGamingWikiClient()
    info = client.get_config_info(game, install_path=install_path or "")
    expanded = info.get("expanded_paths") or []
    found = detect_config_files(expanded)

    config_files = []
    for path in found:
        if _is_expanded_registry_path(path):
            config_files.append(_read_registry_key(path))
        else:
            config_files.append(_try_read_file(path))

    return config_files


def _host_is_loopback(host_header: str) -> bool:
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        host = host.split("]", 1)[0] + "]"
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host in _LOOPBACK_HOSTS


def _scan_match(game: str):
    return next(
        (entry for entry in _scan_all() if entry.get("name", "").lower() == game.lower()), {}
    )


def _export_target(output: str) -> Path:
    """Exports always go to the Game Tuner exports folder (file name only)."""
    name = Path(str(output or "export.json")).name or "export.json"
    if not name.lower().endswith(".json"):
        name += ".json"
    folder = app_data_dir() / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


class GameTunerAPIHandler(BaseHTTPRequestHandler):
    server_version = "GameTunerAPI/0.2"
    api_token: str = ""
    registry_factory = staticmethod(lambda: VerificationRegistry(__version__))

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}
        if content_length < 0 or content_length > MAX_BODY_BYTES:
            raise ValueError("request_body_too_large")
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8"))

    def _reject_foreign_host(self) -> bool:
        if _host_is_loopback(self.headers.get("Host", "")):
            return False
        self._send_json({"error": "forbidden_host"}, status=403)
        return True

    def _token_ok(self) -> bool:
        supplied = self.headers.get(TOKEN_HEADER, "")
        return bool(self.api_token) and hmac.compare_digest(supplied, self.api_token)

    def do_OPTIONS(self):
        # No CORS: browsers must not be able to call this API cross-origin.
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self._reject_foreign_host():
            return
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/health":
                self._send_json({"status": "ok"})
                return

            if path == "/scan":
                platform = (query.get("platform") or [""])[0].strip().lower()
                games = _scan_all()
                if platform:
                    games = [g for g in games if g.get("platform", "").lower() == platform]
                self._send_json(games)
                return

            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_POST(self):
        if self._reject_foreign_host():
            return
        try:
            path = urlparse(self.path).path
            if path in WRITE_ENDPOINTS and not self._token_ok():
                self._send_json({"error": "token_required", "header": TOKEN_HEADER}, status=401)
                return
            data = self._read_json_body()

            if path == "/query":
                game = data.get("game", "")
                install_path = data.get("install_path", "")
                if not game:
                    self._send_json({"error": "Missing required field: game"}, status=400)
                    return
                info = PCGamingWikiClient().get_config_info(game, install_path=install_path)
                self._send_json(info)
                return

            if path == "/detect":
                game = data.get("game", "")
                install_path = data.get("install_path", "")
                if not game:
                    self._send_json({"error": "Missing required field: game"}, status=400)
                    return
                config_files = _detect_config_files(game, install_path)
                self._send_json(config_files)
                return

            if path == "/parse":
                game = data.get("game", "")
                install_path = data.get("install_path", "")
                config_files = data.get("config_files")
                if not game:
                    self._send_json({"error": "Missing required field: game"}, status=400)
                    return
                if config_files is None:
                    config_files = _detect_config_files(game, install_path)

                settings = extract_key_settings(game, config_files)
                self._send_json(
                    {
                        "game": game,
                        "settings": settings,
                        "available_options": {
                            key: setting_options_for_game(
                                game,
                                key,
                                settings.get(key),
                                upscaling_method=settings.get("upscaling"),
                            )
                            for key in SETTING_OPTIONS
                        },
                        "setting_names": DISPLAY_NAMES_EN,
                    }
                )
                return

            if path == "/apply":
                game = data.get("game", "")
                settings = data.get("settings")
                if not game:
                    self._send_json({"error": "Missing required field: game"}, status=400)
                    return
                if not isinstance(settings, dict) or not all(
                    isinstance(key, str) and isinstance(value, str) for key, value in settings.items()
                ):
                    self._send_json({"error": "Missing or invalid field: settings (object of strings)"}, status=400)
                    return
                matched = _scan_match(game)
                if not matched:
                    self._send_json({"error": "game_not_installed"}, status=404)
                    return
                install_path = matched.get("install_path", "")
                # Never trust caller-supplied file lists or paths for a write.
                config_files = _detect_config_files(game, install_path)
                try:
                    result = backup_and_write(
                        game, matched.get("platform", "Unknown"), detect_game_version(install_path),
                        config_files, settings, write_settings, self.registry_factory(),
                        install_path=install_path or None,
                    )
                except VerificationError as exc:
                    self._send_json(
                        {"status": "blocked", "error": str(exc), "message": describe_verification_error(exc)},
                        status=409,
                    )
                    return
                self._send_json(result)
                return

            if path == "/export":
                games_filter = data.get("games") or []
                output = data.get("output") or "export.json"

                games_data = _scan_all()
                if games_filter:
                    names = {str(name).strip().lower() for name in games_filter}
                    games_data = [g for g in games_data if g.get("name", "").lower() in names]

                class _Game:
                    def __init__(self, d):
                        self.name = d["name"]
                        self.platform = d.get("platform", "")
                        self.install_path = d.get("install_path", "")

                game_objs = [_Game(d) for d in games_data if "error" not in d]
                target = _export_target(output)
                exporter = ConfigExporter(wiki_client=PCGamingWikiClient())
                exporter.export(game_objs, str(target))
                self._send_json(
                    {
                        "status": "ok",
                        "output": str(target),
                        "game_count": len(game_objs),
                    }
                )
                return

            if path == "/import":
                package = data.get("package", "")
                if not package:
                    self._send_json({"error": "Missing required field: package"}, status=400)
                    return
                with open(package, encoding="utf-8") as handle:
                    package_data = json.load(handle)
                if isinstance(package_data.get("games"), dict) and "Grand Theft Auto V Enhanced" in package_data["games"]:
                    self._send_json({"status": "blocked", "error": "gta_restore_requires_guard"}, status=409)
                    return
                restored = ConfigPackage().import_package(package)
                self._send_json({"status": "ok", "restored": restored})
                return

            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON request body"}, status=400)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)


def build_parser():
    p = argparse.ArgumentParser(description="Game Tuner external HTTP API")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8787, help="Port to bind (default: 8787)")
    p.add_argument(
        "--token",
        help=f"Token required in the {TOKEN_HEADER} header for /apply, /import and /export "
             "(default: $GAMETUNER_API_TOKEN, else a random token printed at start-up)",
    )
    return p


def main():
    args = build_parser().parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Refusing to bind a non-loopback address: the API controls local game files.")
        raise SystemExit(2)
    GameTunerAPIHandler.api_token = args.token or os.environ.get("GAMETUNER_API_TOKEN") or secrets.token_urlsafe(24)
    server = ThreadingHTTPServer((args.host, args.port), GameTunerAPIHandler)
    print(f"Game Tuner API listening on http://{args.host}:{args.port}")
    if not (args.token or os.environ.get("GAMETUNER_API_TOKEN")):
        print(f"Write token ({TOKEN_HEADER}): {GameTunerAPIHandler.api_token}")
    print("Endpoints: GET /health, GET /scan, POST /query /detect /parse /apply /export /import")
    server.serve_forever()


if __name__ == "__main__":
    main()
