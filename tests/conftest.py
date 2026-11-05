"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_app_data(tmp_path, monkeypatch):
    """Keep Game Tuner's per-user data (backups, consent, logs) inside the test's tmp folder."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
