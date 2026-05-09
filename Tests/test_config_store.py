import os
import pytest


def test_app_settings_table_created(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    # Force reimport so env var is picked up
    import importlib
    import WebAPI.database as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    assert "app_settings" in tables
