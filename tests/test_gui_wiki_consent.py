"""Tests for first-launch PCGamingWiki download consent."""

from __future__ import annotations

from types import SimpleNamespace

from gui import app as gui_app


def test_open_export_folder_opens_zip_parent(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(gui_app.os, "startfile", opened.append)
    output = tmp_path / "reports" / "game-tuner-report.zip"

    gui_app._open_export_folder(output)

    assert opened == [output.parent]


class FakeWikiClient:
    def __init__(self, states):
        self.states = dict(states)
        self.decisions = []

    def download_state(self, game_title):
        return self.states.get(game_title, "no_decision")

    def set_download_decision(self, game_title, decision):
        self.decisions.append((game_title, decision))
        self.states[game_title] = "needs_update" if decision == "accepted" else "declined"


def _make_app(states):
    app = gui_app.App.__new__(gui_app.App)
    app._wiki_client = FakeWikiClient(states)
    app._detected_games = []
    return app


def test_first_launch_accepts_only_games_without_decision(monkeypatch):
    app = _make_app({"Cached": "cached", "Declined": "declined"})
    games = [
        SimpleNamespace(name="New Game"),
        SimpleNamespace(name="Cached"),
        SimpleNamespace(name="Declined"),
    ]
    prompts = []
    monkeypatch.setattr(
        gui_app.messagebox,
        "askyesno",
        lambda title, message: prompts.append((title, message)) or True,
    )

    assert app._offer_wiki_download(games) is True
    assert app._wiki_client.decisions == [("New Game", "accepted")]
    assert len(prompts) == 1


def test_first_launch_decline_is_persisted_and_not_prompted_again(monkeypatch):
    app = _make_app({})
    games = [SimpleNamespace(name="New Game")]
    prompts = []
    monkeypatch.setattr(
        gui_app.messagebox,
        "askyesno",
        lambda title, message: prompts.append((title, message)) or False,
    )

    assert app._offer_wiki_download(games) is False
    assert app._wiki_client.decisions == [("New Game", "declined")]
    assert app._offer_wiki_download(games) is None
    assert len(prompts) == 1


def test_manual_retry_includes_declined_games(monkeypatch):
    app = _make_app({"Declined": "declined", "Cached": "cached"})
    games = [SimpleNamespace(name="Declined"), SimpleNamespace(name="Cached")]
    monkeypatch.setattr(gui_app.messagebox, "askyesno", lambda *args, **kwargs: True)

    assert app._offer_wiki_download(games, retry=True) is True
    assert app._wiki_client.decisions == [("Declined", "accepted")]


def test_manual_retry_starts_detection_after_acceptance(monkeypatch):
    app = _make_app({"Declined": "declined"})
    app._detected_games = [SimpleNamespace(name="Declined")]
    started = []
    monkeypatch.setattr(gui_app.messagebox, "askyesno", lambda *args, **kwargs: True)
    app._start_config_detection = lambda games: started.extend(games)

    app._retry_wiki_download()

    assert [game.name for game in started] == ["Declined"]


def test_scan_completion_does_not_offer_rule_update():
    app = gui_app.App.__new__(gui_app.App)
    app._detected_games = []
    app._game_rows = []
    app._status_label = SimpleNamespace(configure=lambda **kwargs: None)
    app._set_scanning = lambda scanning: None
    scheduled = []
    app.root = SimpleNamespace(after=lambda *args: scheduled.append(args))

    app._on_scan_done([])

    assert scheduled == []


def test_later_scan_prompts_only_for_new_uncached_game(monkeypatch):
    app = _make_app({"Installed Game": "cached"})
    installed = SimpleNamespace(name="Installed Game")
    new_game = SimpleNamespace(name="Newly Installed Game")
    prompts = []
    monkeypatch.setattr(
        gui_app.messagebox,
        "askyesno",
        lambda title, message: prompts.append((title, message)) or True,
    )

    assert app._offer_wiki_download([installed]) is None
    assert app._offer_wiki_download([installed, new_game]) is True

    assert app._wiki_client.decisions == [("Newly Installed Game", "accepted")]
    assert len(prompts) == 1
    assert "Newly Installed Game" in prompts[0][1]


def test_declined_new_game_is_not_prompted_on_next_refresh(monkeypatch):
    app = _make_app({"Installed Game": "cached"})
    games = [
        SimpleNamespace(name="Installed Game"),
        SimpleNamespace(name="New Game"),
    ]
    prompts = []
    monkeypatch.setattr(
        gui_app.messagebox,
        "askyesno",
        lambda title, message: prompts.append((title, message)) or False,
    )

    assert app._offer_wiki_download(games) is False
    assert app._offer_wiki_download(games) is None

    assert app._wiki_client.states["Installed Game"] == "cached"
    assert app._wiki_client.states["New Game"] == "declined"
    assert len(prompts) == 1


def test_stale_detection_result_does_not_update_removed_row():
    app = gui_app.App.__new__(gui_app.App)
    app._game_rows = []
    stale_row = SimpleNamespace(
        update_config_status=lambda result: (_ for _ in ()).throw(AssertionError()),
        update_key_settings=lambda settings: (_ for _ in ()).throw(AssertionError()),
        update_config_dicts=lambda configs: (_ for _ in ()).throw(AssertionError()),
        update_verification=lambda verification: (_ for _ in ()).throw(AssertionError()),
    )

    app._apply_detection_result(
        stale_row,
        [],
        {"vsync": "On"},
        [{"path": "settings.ini"}],
        {"status": "candidate"},
    )


def test_failed_rule_update_does_not_refresh_visible_rows(monkeypatch, tmp_path):
    app = gui_app.App.__new__(gui_app.App)
    app._verification_registry = SimpleNamespace(
        log_path=tmp_path / "verification.log",
        update=lambda: {
            "updated": False,
            "manifest_version": "1.0.0",
            "error": "manifest_checksum_mismatch",
            "log_path": str(tmp_path / "verification.log"),
        },
    )
    app._refresh_verification_statuses = lambda version: (_ for _ in ()).throw(
        AssertionError("failed updates must not refresh rows")
    )
    warnings = []
    monkeypatch.setattr(
        gui_app.messagebox,
        "showwarning",
        lambda title, message: warnings.append((title, message)),
    )
    app.root = SimpleNamespace(after=lambda delay, callback, *args: callback(*args))

    app._do_rule_update()

    assert len(warnings) == 1
    assert warnings[0][0] == "Verification Rules"
    assert "manifest_checksum_mismatch" in warnings[0][1]
    assert str(tmp_path / "verification.log") in warnings[0][1]