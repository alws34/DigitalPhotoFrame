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


import json as _json

def test_migrate_settings_if_needed_loads_json(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    json_path = tmp_path / "settings.json"
    json_path.write_text(_json.dumps({"playback": {"animation_fps": 20}}))
    import importlib
    import WebAPI.database as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    db_mod.migrate_settings_if_needed(str(json_path))
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    row = conn.execute("SELECT value FROM app_settings WHERE key = 'main'").fetchone()
    conn.close()
    assert row is not None
    data = _json.loads(row[0])
    assert data["playback"]["animation_fps"] == 20

def test_migrate_settings_if_needed_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    json_path = tmp_path / "settings.json"
    json_path.write_text(_json.dumps({"playback": {"animation_fps": 20}}))
    import importlib
    import WebAPI.database as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    db_mod.migrate_settings_if_needed(str(json_path))
    # Call again — should not raise and should not duplicate
    db_mod.migrate_settings_if_needed(str(json_path))
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    count = conn.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0]
    conn.close()
    assert count == 1

def test_migrate_settings_if_needed_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    import importlib
    import WebAPI.database as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    # Should not raise even if file doesn't exist
    db_mod.migrate_settings_if_needed(str(tmp_path / "nonexistent.json"))
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    count = conn.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0]
    conn.close()
    assert count == 0
