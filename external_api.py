#!/usr/bin/env python3
"""Game Tuner External HTTP API.

Expose the existing CLI/skill capabilities through a lightweight JSON API
that can be called from any external tool or service.

Run:
    python external_api.py --host 127.0.0.1 --port 8787
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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
from wiki_api import PCGamingWikiClient


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


class GameTunerAPIHandler(BaseHTTPRequestHandler):
    server_version = "GameTunerAPI/0.1"

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self):
        self._send_json({"status": "ok"}, status=200)

    def do_GET(self):
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
        try:
            path = urlparse(self.path).path
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
                install_path = data.get("install_path", "")
                settings = data.get("settings")
                config_files = data.get("config_files")
                if not game:
                    self._send_json({"error": "Missing required field: game"}, status=400)
                    return
                if not isinstance(settings, dict):
                    self._send_json({"error": "Missing or invalid field: settings (object)"}, status=400)
                    return
                if config_files is None:
                    config_files = _detect_config_files(game, install_path)

                result = write_settings(game, config_files, settings)
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
                exporter = ConfigExporter(wiki_client=PCGamingWikiClient())
                exporter.export(game_objs, output)
                self._send_json(
                    {
                        "status": "ok",
                        "output": os.path.abspath(output),
                        "game_count": len(game_objs),
                    }
                )
                return

            if path == "/import":
                package = data.get("package", "")
                if not package:
                    self._send_json({"error": "Missing required field: package"}, status=400)
                    return
                restored = ConfigPackage().import_package(package)
                self._send_json({"status": "ok", "restored": restored})
                return

            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON request body"}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)


def build_parser():
    p = argparse.ArgumentParser(description="Game Tuner external HTTP API")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8787, help="Port to bind (default: 8787)")
    return p


def main():
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), GameTunerAPIHandler)
    print(f"Game Tuner API listening on http://{args.host}:{args.port}")
    print("Endpoints: GET /health, GET /scan, POST /query /detect /parse /apply /export /import")
    server.serve_forever()


if __name__ == "__main__":
    main()
