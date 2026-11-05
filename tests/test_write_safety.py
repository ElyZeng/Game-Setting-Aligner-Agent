"""Write-safety guarantees: atomic writes, byte-exact rollback, pristine backups,
game-running refusal and the hardened external HTTP API."""

from __future__ import annotations

import http.client
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from config_manager import safe_io
from config_manager.process_guard import running_processes_in
from config_manager.safe_io import atomic_write_bytes, atomic_write_text, detect_newline
from config_manager.settings_writer import write_settings
from config_manager.verification import (
    VerificationError,
    backup_and_write,
    describe_verification_error,
    pristine_backup_dir,
    restore_pristine_backup,
)

GAME = "Test Unreal Game"
INI_CRLF = (
    "[/Script/Engine.GameUserSettings]\r\n"
    "bUseVSync=True\r\n"
    "ResolutionSizeX=1920\r\n"
    "ResolutionSizeY=1080\r\n"
    "FullscreenMode=0\r\n"
    "FrameRateLimit=60.000000\r\n"
)


def _registry(tmp_path: Path, settings=("vsync",)):
    return SimpleNamespace(
        data_dir=tmp_path / "app-data",
        client_version="test",
        test_write_enabled=lambda: True,
        status_for=lambda *_args: {
            "status": "write_candidate",
            "reason": "verified",
            "rule": {"supported_settings": list(settings)},
        },
    )


def _game_file(tmp_path: Path, data: bytes) -> tuple[Path, list]:
    path = tmp_path / "game" / "Saved" / "Config" / "Windows" / "GameUserSettings.ini"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    content = path.read_text(encoding="utf-8", errors="replace")
    return path, [{"expanded_path": str(path), "found": True, "content": content, "type": "ini"}]


# ── safe_io ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "original, newline",
    [(b"a=1\nb=2\n", "\n"), (b"a=1\r\nb=2\r\n", "\r\n")],
)
def test_atomic_write_text_keeps_existing_line_endings(tmp_path, original, newline):
    target = tmp_path / "cfg.ini"
    target.write_bytes(original)
    atomic_write_text(target, "a=1\nb=3\n")
    assert target.read_bytes() == ("a=1" + newline + "b=3" + newline).encode()


def test_atomic_write_text_keeps_utf8_bom(tmp_path):
    target = tmp_path / "cfg.json"
    target.write_bytes(safe_io.UTF8_BOM + b'{"a": 1}\n')
    atomic_write_text(target, '{"a": 2}\n')
    assert target.read_bytes() == safe_io.UTF8_BOM + b'{"a": 2}\n'


def test_atomic_write_text_new_file_uses_platform_newline(tmp_path):
    target = tmp_path / "sub" / "new.ini"
    atomic_write_text(target, "a=1\n")
    assert target.read_bytes() == ("a=1" + os.linesep).encode()


def test_detect_newline():
    assert detect_newline(b"no newline") is None
    assert detect_newline(b"a\r\nb\r\nc\n") == "\r\n"
    assert detect_newline(b"a\nb\nc\r\n") == "\n"


def test_atomic_write_failure_leaves_original_and_no_temp(tmp_path, monkeypatch):
    target = tmp_path / "cfg.ini"
    target.write_bytes(b"original")

    def boom(*_args):
        raise OSError("simulated crash during replace")

    monkeypatch.setattr(safe_io.os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_bytes(target, b"new content")
    assert target.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["cfg.ini"]


# ── backup_and_write: rollback, backups ─────────────────────────────


def test_failed_validation_restores_exact_bytes_including_non_utf8(tmp_path):
    original = INI_CRLF.encode() + b"; caf\xe9 latin-1 comment\r\n"
    path, files = _game_file(tmp_path, original)

    def bad_write(_game, config_files, _settings):
        Path(config_files[0]["expanded_path"]).write_text("garbage", encoding="utf-8")
        return [{"path": config_files[0]["expanded_path"], "status": "ok", "detail": "fake"}]

    with pytest.raises(VerificationError, match="write_validation_failed_restored"):
        backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, bad_write, _registry(tmp_path))
    assert path.read_bytes() == original


def test_writer_exception_triggers_rollback(tmp_path):
    path, files = _game_file(tmp_path, INI_CRLF.encode())

    def crashing_write(_game, config_files, _settings):
        Path(config_files[0]["expanded_path"]).write_bytes(b"half-writ")
        raise RuntimeError("writer crashed")

    with pytest.raises(RuntimeError):
        backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, crashing_write, _registry(tmp_path))
    assert path.read_bytes() == INI_CRLF.encode()


def test_successful_write_keeps_crlf(tmp_path):
    path, files = _game_file(tmp_path, INI_CRLF.encode())
    result = backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, _registry(tmp_path))
    assert result[0]["status"] == "ok"
    data = path.read_bytes()
    assert b"bUseVSync=False\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_config_changed_between_read_and_write_is_refused(tmp_path):
    path, files = _game_file(tmp_path, INI_CRLF.encode())
    files[0]["content"] = files[0]["content"].replace("60.000000", "30.000000")
    registry = _registry(tmp_path)
    # backup_and_write re-reads the file first, so simulate the game writing
    # between that re-read and the backup step by patching read_bytes.
    original_read_bytes = Path.read_bytes
    calls = {"n": 0}

    def racing_read_bytes(self):
        data = original_read_bytes(self)
        if self == path:
            calls["n"] += 1
            if calls["n"] == 1:
                return data.replace(b"60.000000", b"75.000000")
        return data

    Path.read_bytes = racing_read_bytes
    try:
        with pytest.raises(VerificationError, match="config_changed_during_write"):
            backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, registry)
    finally:
        Path.read_bytes = original_read_bytes
    assert path.read_bytes() == INI_CRLF.encode()


def test_pristine_backup_survives_later_writes_and_restores(tmp_path):
    original = INI_CRLF.encode()
    path, files = _game_file(tmp_path, original)
    registry = _registry(tmp_path)

    backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, registry)
    after_first = path.read_bytes()
    files[0]["content"] = path.read_text(encoding="utf-8")
    backup_and_write(GAME, "Steam", "1", files, {"vsync": "On"}, write_settings, registry)
    assert path.read_bytes() != after_first

    pristine = pristine_backup_dir(GAME, registry)
    manifest = json.loads((pristine / "backup-manifest.json").read_text(encoding="utf-8"))
    assert (pristine / manifest["files"][0]["file"]).read_bytes() == original

    # The rolling backup holds the state before the latest write ...
    rolling = registry.data_dir / "backups" / "Test_Unreal_Game" / "0-GameUserSettings.ini"
    assert rolling.read_bytes() == after_first
    # ... and the older one moved to history.
    history = list((registry.data_dir / "backups" / "history" / "Test_Unreal_Game").iterdir())
    assert len(history) == 1

    result = restore_pristine_backup(GAME, registry)
    assert result["status"] == "ok"
    assert path.read_bytes() == original


def test_restore_pristine_refuses_corrupt_backup(tmp_path):
    path, files = _game_file(tmp_path, INI_CRLF.encode())
    registry = _registry(tmp_path)
    backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, registry)
    written = path.read_bytes()
    pristine = pristine_backup_dir(GAME, registry)
    (pristine / "0-GameUserSettings.ini").write_bytes(b"tampered")
    with pytest.raises(VerificationError, match="pristine_backup_corrupt"):
        restore_pristine_backup(GAME, registry)
    assert path.read_bytes() == written


def test_restore_pristine_without_backup(tmp_path):
    with pytest.raises(VerificationError, match="pristine_backup_not_found"):
        restore_pristine_backup(GAME, _registry(tmp_path))


# ── game-running refusal ─────────────────────────────────────────────


def test_write_refused_while_game_running(tmp_path):
    path, files = _game_file(tmp_path, INI_CRLF.encode())
    install = tmp_path / "install"
    (install / "Binaries").mkdir(parents=True)
    exe = str(install / "Binaries" / "Game-Win64-Shipping.exe")
    with pytest.raises(VerificationError, match="game_running:Game-Win64-Shipping.exe"):
        backup_and_write(
            GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, _registry(tmp_path),
            install_path=str(install), process_lister=lambda: ["/usr/bin/other", exe],
        )
    assert path.read_bytes() == INI_CRLF.encode()
    assert not (tmp_path / "app-data" / "backups").exists()


def test_write_allowed_when_game_closed(tmp_path):
    path, files = _game_file(tmp_path, INI_CRLF.encode())
    install = tmp_path / "install"
    install.mkdir()
    sibling = str(tmp_path / "install-other" / "game.exe")  # prefix match must not count
    result = backup_and_write(
        GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, _registry(tmp_path),
        install_path=str(install), process_lister=lambda: [sibling],
    )
    assert result[0]["status"] == "ok"


def test_process_check_failure_fails_closed(tmp_path):
    _path, files = _game_file(tmp_path, INI_CRLF.encode())
    install = tmp_path / "install"
    install.mkdir()

    def broken_lister():
        raise OSError("EnumProcesses failed")

    with pytest.raises(VerificationError, match="process_check_failed"):
        backup_and_write(
            GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, _registry(tmp_path),
            install_path=str(install), process_lister=broken_lister,
        )


def test_running_processes_in_missing_folder_is_empty(tmp_path):
    assert running_processes_in(str(tmp_path / "missing"), lambda: ["x"]) == []


def test_describe_verification_error():
    text = describe_verification_error(VerificationError("game_running:a.exe,b.exe"))
    assert "a.exe,b.exe" in text and "Close the game" in text
    assert describe_verification_error(VerificationError("something_else")) == "something_else"


# ── external API ─────────────────────────────────────────────────────


@pytest.fixture
def api_server(monkeypatch):
    import external_api

    calls = {}

    def fake_backup_and_write(game, platform, version, config_files, settings, write, registry, install_path=None):
        calls["apply"] = {"game": game, "config_files": config_files, "install_path": install_path}
        return [{"path": "x", "status": "ok", "detail": "fake"}]

    monkeypatch.setattr(external_api, "_scan_match", lambda game: {
        "name": game, "platform": "Steam", "install_path": "C:/Games/Test",
    })
    monkeypatch.setattr(external_api, "_detect_config_files", lambda game, install_path="": [{"detected": True}])
    monkeypatch.setattr(external_api, "detect_game_version", lambda _path: "1")
    monkeypatch.setattr(external_api, "backup_and_write", fake_backup_and_write)
    monkeypatch.setattr(external_api.GameTunerAPIHandler, "api_token", "secret-token")
    monkeypatch.setattr(external_api.GameTunerAPIHandler, "registry_factory", staticmethod(lambda: object()))

    server = ThreadingHTTPServer(("127.0.0.1", 0), external_api.GameTunerAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], calls
    finally:
        server.shutdown()
        server.server_close()


def _request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    payload = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    conn.request(method, path, body=payload, headers=hdrs)
    response = conn.getresponse()
    data = response.read()
    result = (response.status, dict(response.getheaders()), json.loads(data) if data else None)
    conn.close()
    return result


def test_api_apply_requires_token(api_server):
    port, calls = api_server
    status, _headers, body = _request(port, "POST", "/apply", {"game": "G", "settings": {"vsync": "Off"}})
    assert status == 401 and body["error"] == "token_required"
    assert "apply" not in calls


def test_api_apply_uses_guarded_write_and_ignores_supplied_files(api_server):
    port, calls = api_server
    status, _headers, body = _request(
        port, "POST", "/apply",
        {"game": "G", "settings": {"vsync": "Off"}, "config_files": [{"expanded_path": "C:/Windows/evil.ini"}]},
        {"X-GameTuner-Token": "secret-token"},
    )
    assert status == 200 and body[0]["status"] == "ok"
    assert calls["apply"]["config_files"] == [{"detected": True}]
    assert calls["apply"]["install_path"] == "C:/Games/Test"


def test_api_rejects_foreign_host_and_sends_no_cors(api_server):
    port, _calls = api_server
    status, _headers, body = _request(port, "GET", "/health", headers={"Host": "evil.example:8787"})
    assert status == 403 and body["error"] == "forbidden_host"
    status, headers, _body = _request(port, "GET", "/health")
    assert status == 200
    assert not any(name.lower().startswith("access-control-") for name in headers)


def test_api_export_requires_token(api_server):
    port, _calls = api_server
    status, _headers, _body = _request(port, "POST", "/export", {"output": "C:/Windows/x.json"})
    assert status == 401


def test_api_import_requires_token(api_server):
    port, _calls = api_server
    status, _headers, _body = _request(port, "POST", "/import", {"package": "p.json"})
    assert status == 401


# ── S8: no writer guessing from file extensions ─────────────────────


def test_unknown_xml_is_not_sent_to_forza_writer(tmp_path):
    from config_manager.settings_writer import _detect_parser_type

    files = [{"expanded_path": str(tmp_path / "settings.xml"), "found": True, "content": "<a/>"}]
    assert _detect_parser_type("Some XML Game", files) == "unknown"
    files = [{"expanded_path": str(tmp_path / "config.ini"), "found": True, "content": "[x]\na=1\n"}]
    assert _detect_parser_type("Some INI Game", files) == "unknown"
    files = [{"expanded_path": str(tmp_path / "u.json"), "found": True, "content": '{"data": []}'}]
    assert _detect_parser_type("Some JSON Game", files) == "unknown"
    assert _detect_parser_type("Street Fighter 6", files) == "unknown"


# ── S6: values must be ones the game offers ─────────────────────────


def test_value_outside_game_options_is_refused(tmp_path):
    path, files = _game_file(tmp_path, INI_CRLF.encode())
    registry = _registry(tmp_path, settings=("vsync", "frame_limit"))
    for settings in ({"vsync": "Maybe"}, {"frame_limit": "999 FPS"}):
        with pytest.raises(VerificationError, match="write_value_not_allowed"):
            backup_and_write(GAME, "Steam", "1", files, settings, write_settings, registry)
    assert path.read_bytes() == INI_CRLF.encode()


def test_supported_values_in_rule_restrict_further(tmp_path):
    _path, files = _game_file(tmp_path, INI_CRLF.encode())
    registry = _registry(tmp_path, settings=("frame_limit",))
    rule = registry.status_for()["rule"]
    rule["supported_values"] = {"frame_limit": ["30 FPS"]}
    registry.status_for = lambda *_a: {"status": "write_candidate", "reason": "verified", "rule": rule}
    with pytest.raises(VerificationError, match="write_value_not_allowed:frame_limit=120 FPS"):
        backup_and_write(GAME, "Steam", "1", files, {"frame_limit": "120 FPS"}, write_settings, registry)
    result = backup_and_write(GAME, "Steam", "1", files, {"frame_limit": "30 FPS"}, write_settings, registry)
    assert result[0]["status"] == "ok"


# ── anti-cheat ──────────────────────────────────────────────────────


def test_detect_anticheat_markers(tmp_path):
    from config_manager.anticheat import detect_anticheat

    (tmp_path / "EasyAntiCheat").mkdir()
    (tmp_path / "Binaries" / "Win64").mkdir(parents=True)
    (tmp_path / "Binaries" / "Win64" / "BEService_x64.exe").write_bytes(b"")
    (tmp_path / "pb").mkdir()  # generic folder name without PunkBuster binaries
    assert detect_anticheat(str(tmp_path)) == ["BattlEye", "EasyAntiCheat"]
    assert detect_anticheat(str(tmp_path / "missing")) == []


def test_anticheat_game_is_read_only_without_review(tmp_path):
    path, files = _game_file(tmp_path, INI_CRLF.encode())
    install = tmp_path / "install"
    install.mkdir()
    with pytest.raises(VerificationError, match="anticheat_not_reviewed:EasyAntiCheat"):
        backup_and_write(
            GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, _registry(tmp_path),
            install_path=str(install), process_lister=lambda: [],
            anticheat_detector=lambda _p: ["EasyAntiCheat"],
        )
    assert path.read_bytes() == INI_CRLF.encode()


def test_anticheat_review_allows_scope_and_detects_changes(tmp_path):
    _path, files = _game_file(tmp_path, INI_CRLF.encode())
    install = tmp_path / "install"
    install.mkdir()
    rule = {
        "supported_settings": ["vsync", "frame_limit"],
        "anticheat": {"detected": ["EasyAntiCheat"], "review": "approved", "scope": ["vsync"]},
    }
    registry = _registry(tmp_path)
    registry.status_for = lambda *_a: {"status": "write_candidate", "reason": "verified", "rule": rule}
    common = dict(install_path=str(install), process_lister=lambda: [])

    with pytest.raises(VerificationError, match="anticheat_scope:frame_limit"):
        backup_and_write(GAME, "Steam", "1", files, {"frame_limit": "30 FPS"}, write_settings, registry,
                         anticheat_detector=lambda _p: ["EasyAntiCheat"], **common)
    with pytest.raises(VerificationError, match="anticheat_changed_since_review"):
        backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, registry,
                         anticheat_detector=lambda _p: ["BattlEye", "EasyAntiCheat"], **common)
    result = backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, registry,
                              anticheat_detector=lambda _p: ["EasyAntiCheat"], **common)
    assert result[0]["status"] == "ok"


def test_apply_anticheat_policy_for_display():
    from config_manager.verification import apply_anticheat_policy

    base = {"status": "write_candidate", "reason": "verified", "rule": {"supported_settings": ["vsync", "resolution"]}}
    shown = apply_anticheat_policy(base, "C:/x", detector=lambda _p: ["BattlEye"])
    assert shown["status"] == "read_verified" and shown["reason"].startswith("anticheat_not_reviewed")
    reviewed = {**base, "rule": {**base["rule"], "anticheat": {
        "detected": ["BattlEye"], "review": "approved", "scope": ["vsync"]}}}
    shown = apply_anticheat_policy(reviewed, "C:/x", detector=lambda _p: ["BattlEye"])
    assert shown["status"] == "write_candidate" and shown["rule"]["supported_settings"] == ["vsync"]
    assert apply_anticheat_policy(base, "C:/x", detector=lambda _p: []) is base


# ── consent ─────────────────────────────────────────────────────────


def test_real_registry_requires_current_disclaimer_and_game_consent(tmp_path):
    from config_manager import verification as v

    path, files = _game_file(tmp_path, INI_CRLF.encode())
    registry = v.VerificationRegistry("0.08.23", data_dir=tmp_path / "rules")
    registry.status_for = lambda *_a: {"status": "write_candidate", "reason": "verified",
                                       "rule": {"supported_settings": ["vsync"]}}

    # Old-style consent without a disclaimer version no longer enables writes.
    registry.data_dir.mkdir(parents=True, exist_ok=True)
    registry.test_write_consent_path.write_text('{"enabled": true}', encoding="utf-8")
    assert not registry.test_write_enabled() and registry.disclaimer_outdated()
    with pytest.raises(VerificationError, match="test_write_consent_required"):
        backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, registry)

    registry.enable_test_writes()
    with pytest.raises(VerificationError, match="game_consent_required"):
        backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, registry)

    registry.grant_game_consent(GAME, "Steam", "1")
    assert not registry.game_consent_granted(GAME, "Steam", "2")  # new version asks again
    result = backup_and_write(GAME, "Steam", "1", files, {"vsync": "Off"}, write_settings, registry)
    assert result[0]["status"] == "ok"
    registry.revoke_game_consent(GAME, "Steam", "1")
    assert not registry.game_consent_granted(GAME, "Steam", "1")


# ── S7: registry ────────────────────────────────────────────────────


class _FakeKey:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ, REG_EXPAND_SZ, REG_BINARY, REG_DWORD, REG_QWORD = 1, 2, 3, 4, 11

    def __init__(self, keys):
        self.keys = keys  # {"HKCU\\Software\\Game": {name: (value, type)}}
        self.set_calls = []

    def OpenKey(self, hive, subkey, _reserved, _access):
        path = f"{hive}\\{subkey}"
        if path not in self.keys:
            raise FileNotFoundError(path)
        return _FakeKey(path)

    def EnumValue(self, key, index):
        items = list(self.keys[key.path].items())
        if index >= len(items):
            raise OSError("no more")
        name, (value, value_type) = items[index]
        return name, value, value_type

    def EnumKey(self, key, index):
        prefix = key.path + "\\"
        children = sorted({p[len(prefix):].split("\\")[0] for p in self.keys if p.startswith(prefix)})
        if index >= len(children):
            raise OSError("no more")
        return children[index]

    def QueryValueEx(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(name)
        return self.keys[key.path][name]

    def SetValueEx(self, key, name, _reserved, value_type, value):
        self.set_calls.append((key.path, name, value_type, value))
        self.keys[key.path][name] = (value, value_type)


def _registry_game(monkeypatch):
    from config_manager import registry_io

    fake = FakeWinreg({
        "HKCU\\Software\\Studio\\Game": {"Version": ("1.0", 1)},
        "HKCU\\Software\\Studio\\Game\\Graphics": {
            "VSync": (1, 4), "FullscreenWidth": (1920, 4), "FullscreenHeight": (1080, 4),
            "Blob": (b"\x00\x01binary", 3), "Fullscreen": (1, 4),
        },
    })
    monkeypatch.setattr(registry_io, "default_backend", lambda: fake)
    reg_path = "HKEY_CURRENT_USER\\Software\\Studio\\Game"
    entry = registry_io.read_key_as_json(reg_path, fake)
    return fake, reg_path, [entry]


def test_registry_write_changes_only_target_value_and_keeps_type(tmp_path, monkeypatch):
    fake, _reg_path, files = _registry_game(monkeypatch)
    result = backup_and_write("Shadow of the Tomb Raider", "Steam", "1", files, {"vsync": "Off"},
                              write_settings, _registry(tmp_path), registry_backend=fake)
    assert result[0]["status"] == "ok", result
    assert fake.set_calls == [("HKCU\\Software\\Studio\\Game\\Graphics", "VSync", 4, 0)]
    assert fake.keys["HKCU\\Software\\Studio\\Game\\Graphics"]["Blob"] == (b"\x00\x01binary", 3)


def test_registry_failed_validation_restores_snapshot(tmp_path, monkeypatch):
    fake, _reg_path, files = _registry_game(monkeypatch)

    def bad_write(_game, _files, _settings):
        fake.keys["HKCU\\Software\\Studio\\Game\\Graphics"]["VSync"] = (7, 4)
        fake.keys["HKCU\\Software\\Studio\\Game\\Graphics"]["Blob"] = (b"zz", 3)
        return [{"path": "x", "status": "ok", "detail": "fake"}]

    with pytest.raises(VerificationError, match="write_validation_failed_restored"):
        backup_and_write("Shadow of the Tomb Raider", "Steam", "1", files, {"vsync": "Off"},
                         bad_write, _registry(tmp_path), registry_backend=fake)
    graphics = fake.keys["HKCU\\Software\\Studio\\Game\\Graphics"]
    assert graphics["VSync"] == (1, 4) and graphics["Blob"] == (b"\x00\x01binary", 3)


def test_registry_refuses_binary_and_missing_values(monkeypatch):
    from config_manager import registry_io

    fake, reg_path, _files = _registry_game(monkeypatch)
    with pytest.raises(registry_io.RegistryWriteError, match="registry_type_not_writable"):
        registry_io.write_changes(reg_path, {"Graphics": {"VSync": 0, "Blob": "x"}}, fake)
    with pytest.raises(registry_io.RegistryWriteError, match="registry_value_missing"):
        registry_io.write_changes(reg_path, {"Graphics": {"NewValue": 1}}, fake)
    with pytest.raises(registry_io.RegistryWriteError, match="registry_bad_value"):
        registry_io.write_changes(reg_path, {"Graphics": {"VSync": "1"}}, fake)
    assert fake.set_calls == []  # validation happens before any write


def test_registry_pristine_restore(tmp_path, monkeypatch):
    fake, _reg_path, files = _registry_game(monkeypatch)
    registry = _registry(tmp_path)
    backup_and_write("Shadow of the Tomb Raider", "Steam", "1", files, {"vsync": "Off"},
                     write_settings, registry, registry_backend=fake)
    assert fake.keys["HKCU\\Software\\Studio\\Game\\Graphics"]["VSync"] == (0, 4)
    restore_pristine_backup("Shadow of the Tomb Raider", registry, registry_backend=fake)
    assert fake.keys["HKCU\\Software\\Studio\\Game\\Graphics"]["VSync"] == (1, 4)


# ── package import keeps a backup ───────────────────────────────────


def test_package_import_backs_up_overwritten_files(tmp_path):
    from config_manager.package import ConfigPackage

    target = tmp_path / "game" / "settings.ini"
    target.parent.mkdir()
    target.write_bytes(b"a=1\r\nb=2\r\n")
    package = tmp_path / "pkg.json"
    package.write_text(json.dumps({"version": 2, "games": {"G": {"config_files": [
        {"expanded_path": str(target), "content": "a=9\nb=2\n", "found": True},
    ]}}}), encoding="utf-8")

    pkg = ConfigPackage(backup_root=tmp_path / "imports")
    assert pkg.import_package(str(package)) == {"G": [str(target)]}
    assert target.read_bytes() == b"a=9\r\nb=2\r\n"  # existing CRLF kept
    manifest = json.loads((pkg.last_backup / "backup-manifest.json").read_text(encoding="utf-8"))
    assert (pkg.last_backup / manifest["files"][0]["file"]).read_bytes() == b"a=1\r\nb=2\r\n"
