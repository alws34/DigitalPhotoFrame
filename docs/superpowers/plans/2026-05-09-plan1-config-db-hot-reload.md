# Config DB + Hot Reload — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `photoframe_settings.json` / `SettingsHandler` with SQLite-backed config store and < 1s hot reload via watchdog sentinel.

**Architecture:** `Utilities/config_store.py` is the single read/write interface for settings (SQLite blob). `Utilities/config_events.py` owns an in-process pub/sub bus + watchdog file watcher that fires all registered callbacks when settings change. Every component that needs live config subscribes at startup.

**Tech Stack:** Python stdlib `sqlite3`, `watchdog==6.0.0` (already in requirements), existing `WebAPI/database.db`.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `Utilities/config_store.py` | load/save/migrate/defaults |
| Create | `Utilities/config_events.py` | pub/sub bus + watchdog watcher |
| Modify | `WebAPI/database.py` | add `app_settings` table + migrate fn |
| Create | `Tests/test_config_store.py` | unit tests for config_store |
| Modify | `FrameServer/PhotoFrameServer.py` | use config_store, subscribe hot reload |
| Modify | `WebAPI/API.py` | use config_store, remove SettingsHandler dep |
| Modify | `WebAPI/routes/settings.py` | use config_store for load/save |
| Modify | `Utilities/MQTT/mqtt_bridge.py` | subscribe hot reload |
| Modify | `Utilities/autoupdate_utils.py` | subscribe hot reload |
| Modify | `app.py` | use config_store instead of _load_settings |
| Delete | `Settings.py` | replaced by config_store |
| Delete | `FrameGUI/SettingsFrom/model.py` | defaults moved to config_store |

---

## Task 1: Add `app_settings` table to database.py

**Files:**
- Modify: `WebAPI/database.py`

- [ ] **Step 1: Write failing test**

```python
# Tests/test_config_store.py (create file)
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
env/bin/python -m pytest Tests/test_config_store.py::test_app_settings_table_created -v
```
Expected: FAIL — `app_settings` not in tables.

- [ ] **Step 3: Add table + migration function to `WebAPI/database.py`**

Add to `init_db()` after the existing `images_metadata` table creation:

```python
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at REAL
            )
        ''')
```

Add this new function after `migrate_jsons_if_needed`:

```python
def migrate_settings_if_needed(json_path: str) -> None:
    """One-time migration from photoframe_settings.json → app_settings table."""
    import json as _json, time as _time
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM app_settings")
        if cursor.fetchone()[0] > 0:
            return  # Already migrated
    if not os.path.exists(json_path):
        return
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        blob = _json.dumps(data, indent=2)
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('main', ?, ?)",
                (blob, _time.time())
            )
        print(f"[database] Migrated settings from {json_path}")
    except Exception as e:
        print(f"[database] Settings migration failed: {e}")
```

Also update `DB_PATH` to read from env var:

```python
DB_PATH = os.environ.get(
    "PF_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
env/bin/python -m pytest Tests/test_config_store.py::test_app_settings_table_created -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add WebAPI/database.py Tests/test_config_store.py
git commit -m "feat: add app_settings table and migration fn to database.py"
```

---

## Task 2: Create `Utilities/config_store.py`

**Files:**
- Create: `Utilities/config_store.py`
- Modify: `Tests/test_config_store.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to Tests/test_config_store.py

import json, time

def test_load_returns_defaults_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PF_SENTINEL_PATH", str(tmp_path / "sentinel"))
    import importlib
    import WebAPI.database as db_mod; importlib.reload(db_mod); db_mod.init_db()
    import Utilities.config_store as cs; importlib.reload(cs)
    data = cs.load_settings()
    assert "playback" in data
    assert "ui" in data
    assert data["playback"]["animation_fps"] == 30

def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PF_SENTINEL_PATH", str(tmp_path / "sentinel"))
    import importlib
    import WebAPI.database as db_mod; importlib.reload(db_mod); db_mod.init_db()
    import Utilities.config_store as cs; importlib.reload(cs)
    settings = cs.get_default_settings()
    settings["playback"]["animation_fps"] = 25
    cs.save_settings(settings)
    loaded = cs.load_settings()
    assert loaded["playback"]["animation_fps"] == 25

def test_sentinel_touched_on_save(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    sentinel = tmp_path / "sentinel"
    monkeypatch.setenv("PF_SENTINEL_PATH", str(sentinel))
    import importlib
    import WebAPI.database as db_mod; importlib.reload(db_mod); db_mod.init_db()
    import Utilities.config_store as cs; importlib.reload(cs)
    cs.save_settings(cs.get_default_settings())
    assert sentinel.exists()

def test_migrate_from_json(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PF_SENTINEL_PATH", str(tmp_path / "sentinel"))
    json_path = tmp_path / "photoframe_settings.json"
    json_path.write_text(json.dumps({"playback": {"animation_fps": 20}}))
    import importlib
    import WebAPI.database as db_mod; importlib.reload(db_mod); db_mod.init_db()
    import Utilities.config_store as cs; importlib.reload(cs)
    data = cs.load_settings(json_path=str(json_path))
    assert data["playback"]["animation_fps"] == 20

def test_deep_merge_preserves_defaults_for_missing_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PF_SENTINEL_PATH", str(tmp_path / "sentinel"))
    import importlib
    import WebAPI.database as db_mod; importlib.reload(db_mod); db_mod.init_db()
    import Utilities.config_store as cs; importlib.reload(cs)
    partial = {"playback": {"animation_fps": 15}}
    cs.save_settings(partial)
    loaded = cs.load_settings()
    # Default key present even though not in saved partial
    assert "ui" in loaded
    assert loaded["playback"]["animation_fps"] == 15
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
env/bin/python -m pytest Tests/test_config_store.py -v
```
Expected: Multiple FAILs — `Utilities.config_store` not found.

- [ ] **Step 3: Create `Utilities/config_store.py`**

```python
"""Single source of truth for reading and writing application settings."""
from __future__ import annotations

import json
import os
import time
from typing import Any


def _get_db_path() -> str:
    return os.environ.get(
        "PF_DB_PATH",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "WebAPI", "database.db",
        ),
    )


def _get_sentinel_path() -> str:
    return os.environ.get("PF_SENTINEL_PATH", "/tmp/pf_settings.sentinel")


def _get_db():
    import sqlite3
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def get_default_settings() -> dict[str, Any]:
    return {
        "about": {
            "image_path": "",
            "text": "Digital Photo Frame",
            "version": "1.0.2",
        },
        "autoupdate": {
            "branch": "None",
            "enabled": True,
            "hour": 4,
            "minute": 0,
            "remote": "origin",
            "repo_path": "",
            "shallow_ok": True,
        },
        "backend_configs": {
            "host": "0.0.0.0",
            "idle_fps": 5,
            "server_port": 5002,
            "stream_fps": 30,
            "stream_height": 1080,
            "stream_width": 1920,
            "supersecretkey": "CHANGE_ME_IN_PRODUCTION",
        },
        "effects": {
            "allow_translucent_background": True,
            "background_blur_radius": 61,
            "background_opacity": 0.4,
            "shadow_blur_radius": 71,
            "shadow_opacity": 0.85,
        },
        "mqtt": {
            "base_topic": "photoframe",
            "client_id": "photoframe-livingroom",
            "discovery": True,
            "discovery_prefix": "homeassistant",
            "enabled": False,
            "host": "",
            "interval_seconds": 1,
            "password": "",
            "port": 1883,
            "retain_config": True,
            "tls": False,
            "username": "",
        },
        "open_meteo": {
            "cache_ttl_minutes": 60,
            "latitude": "32.0853",
            "longitude": "34.7818",
            "precipitation_unit": "mm",
            "temperature_unit": "celsius",
            "timeformat": "iso8601",
            "timezone": "auto",
            "units": "metric",
            "wind_speed_unit": "kmh",
        },
        "playback": {
            "animation_duration": 10,
            "animation_fps": 30,
            "delay_between_images": 30,
        },
        "screen": {
            "brightness": 100,
            "off_hour": 0,
            "on_hour": 8,
            "orientation": 270,
            "schedule_enabled": False,
            "schedules": [
                {"days": [0, 1, 2, 3, 4, 5, 6], "enabled": False, "off_hour": 0, "on_hour": 10}
            ],
        },
        "stats": {"font_color": "yellow", "font_size": 20, "show": False},
        "system": {
            "image_dir": "Images",
            "image_quality_encoding": 100,
            "log_file_path": "./FrameServer/PhotoFrame.log",
            "service_name": "PhotoFrame",
        },
        "ui": {
            "contrast_text": True,
            "date_font_size": 60,
            "date_format": "ddd/MM/yyyy",
            "font_name": "arial.ttf",
            "is_24h": False,
            "margins": {"bottom": 30, "left": 80, "right": 50},
            "show_weather": False,
            "spacing_between": 50,
            "text_shadow": {"alpha": 230, "blur": 16, "offset_x": 2, "offset_y": 2},
            "time_font_size": 80,
        },
    }


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_settings(json_path: str | None = None) -> dict[str, Any]:
    """Load settings from DB. On first run, migrates from json_path if provided."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'main'"
        ).fetchone()
    finally:
        conn.close()

    if row:
        try:
            saved = json.loads(row["value"])
            return _deep_merge(get_default_settings(), saved)
        except Exception:
            pass

    # Empty DB — try JSON migration
    if json_path is None:
        json_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "photoframe_settings.json",
        )
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = _deep_merge(get_default_settings(), saved)
            save_settings(merged)
            print(f"[config_store] Migrated settings from {json_path}")
            return merged
        except Exception as e:
            print(f"[config_store] Migration failed: {e}")

    defaults = get_default_settings()
    save_settings(defaults)
    return defaults


def save_settings(data: dict[str, Any]) -> None:
    """Persist settings to DB and touch sentinel to trigger hot reload."""
    blob = json.dumps(data, indent=2)
    now = time.time()
    conn = _get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('main', ?, ?)",
            (blob, now),
        )
        conn.commit()
    finally:
        conn.close()

    sentinel = _get_sentinel_path()
    try:
        os.makedirs(os.path.dirname(sentinel) or "/tmp", exist_ok=True)
        with open(sentinel, "w") as f:
            f.write(str(now))
    except Exception as e:
        print(f"[config_store] Could not touch sentinel {sentinel}: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
env/bin/python -m pytest Tests/test_config_store.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add Utilities/config_store.py Tests/test_config_store.py
git commit -m "feat: add config_store with SQLite backend, deep-merge defaults, JSON migration"
```

---

## Task 3: Create `Utilities/config_events.py`

**Files:**
- Create: `Utilities/config_events.py`
- Modify: `Tests/test_config_store.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to Tests/test_config_store.py

def test_notify_fires_all_callbacks(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PF_SENTINEL_PATH", str(tmp_path / "sentinel"))
    import importlib
    import Utilities.config_events as ce; importlib.reload(ce)
    received = []
    ce.on_settings_changed(lambda d: received.append(d))
    ce.notify_settings_changed({"playback": {"animation_fps": 99}})
    assert len(received) == 1
    assert received[0]["playback"]["animation_fps"] == 99

def test_callback_exception_does_not_stop_others(tmp_path, monkeypatch):
    monkeypatch.setenv("PF_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PF_SENTINEL_PATH", str(tmp_path / "sentinel"))
    import importlib
    import Utilities.config_events as ce; importlib.reload(ce)
    called = []
    ce.on_settings_changed(lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    ce.on_settings_changed(lambda d: called.append(1))
    ce.notify_settings_changed({})
    assert called == [1]  # Second callback still ran
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
env/bin/python -m pytest Tests/test_config_store.py::test_notify_fires_all_callbacks Tests/test_config_store.py::test_callback_exception_does_not_stop_others -v
```
Expected: FAIL — `Utilities.config_events` not found.

- [ ] **Step 3: Create `Utilities/config_events.py`**

```python
"""In-process pub/sub for settings changes + watchdog sentinel watcher."""
from __future__ import annotations

import os
import threading
from typing import Callable

_callbacks: list[Callable[[dict], None]] = []
_lock = threading.Lock()
_observer = None


def on_settings_changed(callback: Callable[[dict], None]) -> None:
    """Register a callback to be called with fresh settings dict on every change."""
    with _lock:
        _callbacks.append(callback)


def notify_settings_changed(new_data: dict) -> None:
    """Fire all registered callbacks. Swallows individual exceptions."""
    with _lock:
        cbs = list(_callbacks)
    for cb in cbs:
        try:
            cb(new_data)
        except Exception as e:
            print(f"[config_events] Callback {cb} raised: {e}")


def start_watcher() -> None:
    """Start watchdog observer on the sentinel file directory."""
    global _observer
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    sentinel_path = os.environ.get("PF_SENTINEL_PATH", "/tmp/pf_settings.sentinel")
    sentinel_dir = os.path.dirname(os.path.abspath(sentinel_path))

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if os.path.abspath(event.src_path) == os.path.abspath(sentinel_path):
                _reload_and_notify()

        def on_created(self, event):
            if os.path.abspath(event.src_path) == os.path.abspath(sentinel_path):
                _reload_and_notify()

    _observer = Observer()
    _observer.schedule(_Handler(), sentinel_dir, recursive=False)
    _observer.daemon = True
    _observer.start()
    print(f"[config_events] Watching {sentinel_path} for settings changes")


def stop_watcher() -> None:
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None


def _reload_and_notify() -> None:
    try:
        from Utilities.config_store import load_settings
        data = load_settings()
        notify_settings_changed(data)
        print("[config_events] Settings hot-reloaded")
    except Exception as e:
        print(f"[config_events] Hot reload failed: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
env/bin/python -m pytest Tests/test_config_store.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add Utilities/config_events.py Tests/test_config_store.py
git commit -m "feat: add config_events pub/sub bus and watchdog sentinel watcher"
```

---

## Task 4: Wire config_store into `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Replace `_load_settings` with `config_store` in `app.py`**

At top of `app.py`, remove:
```python
# REMOVE these imports:
import json
# (and the _load_settings function below)
```

Add after the existing imports:
```python
from Utilities.config_store import load_settings as _load_settings_from_db
from Utilities import config_events
```

Remove the `_load_settings` function entirely (lines ~28-37).

In `main()`, replace:
```python
settings_path = _abs_path(args.settings)
settings = _load_settings(settings_path)
```
with:
```python
settings_path = _abs_path(args.settings)
settings = _load_settings_from_db(json_path=settings_path)
config_events.start_watcher()
```

In each `_run_*` function, remove the `settings_path` argument from `SettingsHandler` construction — that happens inside `PhotoFrameServer` now. Pass `settings` dict as before (no change to function signatures needed yet — `PhotoFrameServer` migration is Task 5).

- [ ] **Step 2: Smoke test startup**

```bash
env/bin/python app.py --headless &
sleep 3
curl -s http://localhost:5002/ | head -5
kill %1
```
Expected: Flask responds (HTML or JSON), no crash.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: wire config_store into app.py startup and start watchdog watcher"
```

---

## Task 5: Migrate `PhotoFrameServer` to `config_store`

**Files:**
- Modify: `FrameServer/PhotoFrameServer.py`

- [ ] **Step 1: Replace `SettingsHandler` import with `config_store`**

In `FrameServer/PhotoFrameServer.py`:

Remove:
```python
from Settings import SettingsHandler
```

Add:
```python
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..")))
from Utilities.config_store import load_settings as _load_settings
from Utilities.config_events import on_settings_changed
```

- [ ] **Step 2: Replace `SettingsHandler` construction with dict-based settings**

In `PhotoFrameServer.__init__`, replace:
```python
self.settings_handler = SettingsHandler(SETTINGS_PATH, logging)
```
with:
```python
self._settings: dict = _load_settings()
self._settings_lock = threading.Lock()
```

Add a `_on_settings_changed` method:
```python
def _on_settings_changed(self, new_data: dict) -> None:
    with self._settings_lock:
        self._settings = new_data
    playback = new_data.get("playback", {})
    self._target_fps = int(playback.get("animation_fps", 30))
    self._transition_fps = int(playback.get("transition_fps", 30))
    self._transition_frame_interval = 1.0 / max(1.0, float(self._transition_fps))
    self.logger.info("[PhotoFrameServer] Settings hot-reloaded")
```

At end of `__init__`, register the callback:
```python
on_settings_changed(self._on_settings_changed)
```

- [ ] **Step 3: Replace all `self.settings_handler.get(key, default)` calls**

Do a find-replace across `PhotoFrameServer.py`:
- `self.settings_handler.get("playback", {})` → `self._settings.get("playback", {})`
- `self.settings_handler.get("ui", {})` → `self._settings.get("ui", {})`
- `self.settings_handler.get("system", {})` → `self._settings.get("system", {})`
- `self.settings_handler.get("stats", {})` → `self._settings.get("stats", {})`
- `self.settings_handler.get(` (any remaining) → `self._settings.get(`
- `self.settings_handler.reload()` → (delete this line — hot reload replaces polling)

Also remove the `from WebAPI.API import Backend` import at the top of `PhotoFrameServer.py` (circular import — Backend is injected via `srv.m_api`).

- [ ] **Step 4: Update `image_handler` and `weather_client` construction**

`Image_Utils` and `build_weather_client` currently take `settings=self.settings_handler`. Update:
```python
self.image_handler = Image_Utils(settings=self._settings)
self.weather_client = build_weather_client(self, self._settings)
```

Check `image_handler.py` and `weather_adapter.py` — if they call `.get()` on the settings arg, a plain `dict` works fine (dict has `.get()`). Verify no `SettingsHandler`-specific methods are called.

- [ ] **Step 5: Smoke test**

```bash
env/bin/python app.py --headless &
sleep 4
curl -s http://localhost:5002/api/settings -H "Cookie: ..." | python -m json.tool | head -20
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add FrameServer/PhotoFrameServer.py
git commit -m "feat: migrate PhotoFrameServer from SettingsHandler to config_store dict + hot reload"
```

---

## Task 6: Migrate `WebAPI/API.py` to `config_store`

**Files:**
- Modify: `WebAPI/API.py`
- Modify: `WebAPI/routes/settings.py`

- [ ] **Step 1: Update `Backend.__init__` signature**

In `WebAPI/API.py`, remove:
```python
from Settings import SettingsHandler
```

Add:
```python
from Utilities.config_store import load_settings, save_settings
```

In `Backend.__init__`, remove `settings_handler` parameter. Replace:
```python
self.settings_handler = settings_handler
```
with nothing (deleted).

Replace `load_settings` method:
```python
def load_settings(self):
    return load_settings()

def save_settings(self, data: dict):
    save_settings(data)
```

Remove `notify_settings_changed` — hot reload now fires automatically via sentinel watcher. Update any callers of `backend.notify_settings_changed()` in route files to just call `backend.save_settings(data)` (notification is implicit).

- [ ] **Step 2: Update `WebAPI/routes/settings.py`**

Replace the `update_settings` handler — remove `backend.notify_settings_changed()` call (now implicit):
```python
@settings_bp.route("/", methods=["POST"], strict_slashes=False)
def update_settings():
    backend = current_app.config.get('backend')
    if backend is None:
        return jsonify({"error": "backend unavailable"}), 500
    if not backend.is_authenticated():
        return jsonify({"error": "unauthorized"}), 401
    new_settings = request.get_json(silent=True)
    if not isinstance(new_settings, dict):
        return jsonify({"error": "Invalid payload."}), 400
    try:
        backend.save_settings(new_settings)
        return jsonify({"message": "Settings updated successfully."})
    except Exception as e:
        return jsonify({"error": f"Failed to update settings: {e}"}), 500
```

- [ ] **Step 3: Update `Backend` construction in `app.py`**

In `app.py`, remove `settings_handler=srv.settings_handler` from `Backend(...)` calls in all three `_run_*` functions:
```python
backend = Backend(frame=srv, image_dir=images_dir, settings_path=settings_path)
```

- [ ] **Step 4: Smoke test**

```bash
env/bin/python app.py --headless &
sleep 3
# Login first (get session cookie), then:
curl -s http://localhost:5002/api/settings \
  -H "Content-Type: application/json" | python -m json.tool | head -10
kill %1
```
Expected: Settings JSON returned.

- [ ] **Step 5: Commit**

```bash
git add WebAPI/API.py WebAPI/routes/settings.py app.py
git commit -m "feat: migrate Backend/API to config_store, remove SettingsHandler dependency"
```

---

## Task 7: Subscribe `MqttBridge` + `AutoUpdater` to hot reload

**Files:**
- Modify: `Utilities/MQTT/mqtt_bridge.py`
- Modify: `Utilities/autoupdate_utils.py`

- [ ] **Step 1: Update `MqttBridge`**

In `Utilities/MQTT/mqtt_bridge.py`, remove `from Settings import SettingsHandler` if present.

In `MqttBridge.__init__`, after storing settings:
```python
from Utilities.config_events import on_settings_changed
on_settings_changed(self._on_settings_changed)
```

Add method:
```python
def _on_settings_changed(self, new_data: dict) -> None:
    new_cfg = (new_data.get("mqtt") or {}).copy()
    if (new_cfg.get("host") != self.cfg.get("host") or
            new_cfg.get("port") != self.cfg.get("port")):
        self.cfg = new_cfg
        self.settings = new_data
        self.logger.info("[MqttBridge] Settings changed — reconnecting")
        try:
            self.disconnect()
        except Exception:
            pass
    else:
        self.cfg = new_cfg
        self.settings = new_data
```

- [ ] **Step 2: Update `AutoUpdater`**

In `Utilities/autoupdate_utils.py`:
```python
from Utilities.config_events import on_settings_changed

# In __init__, after init:
on_settings_changed(self._on_settings_changed)

def _on_settings_changed(self, new_data: dict) -> None:
    au = new_data.get("autoupdate", {})
    self._auto_restart = bool(au.get("enabled", True))
```

- [ ] **Step 3: Commit**

```bash
git add Utilities/MQTT/mqtt_bridge.py Utilities/autoupdate_utils.py
git commit -m "feat: subscribe MqttBridge and AutoUpdater to config hot reload"
```

---

## Task 8: Delete `Settings.py` and `FrameGUI/SettingsFrom/model.py`

**Files:**
- Delete: `Settings.py`
- Delete: `FrameGUI/SettingsFrom/model.py`

- [ ] **Step 1: Verify no remaining imports**

```bash
grep -rn "from Settings import\|import Settings" --include="*.py" .
grep -rn "from FrameGUI.SettingsFrom.model import\|SettingsModel" --include="*.py" .
```
Expected: No results. If any remain, update those files to use `config_store` first.

- [ ] **Step 2: Delete files**

```bash
git rm Settings.py FrameGUI/SettingsFrom/model.py
```

- [ ] **Step 3: Run full test suite**

```bash
env/bin/python -m pytest -v
```
Expected: All PASS. Fix any import errors before committing.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete Settings.py and SettingsModel — replaced by config_store"
```

---

## Task 9: Integration smoke test

- [ ] **Step 1: Start app headless**

```bash
env/bin/python app.py --headless &
APP_PID=$!
sleep 4
```

- [ ] **Step 2: Verify settings load from DB**

```bash
env/bin/python -c "
from Utilities.config_store import load_settings
d = load_settings()
print('OK — playback.animation_fps =', d['playback']['animation_fps'])
"
```
Expected: `OK — playback.animation_fps = 30`

- [ ] **Step 3: Trigger hot reload manually**

```bash
env/bin/python -c "
from Utilities.config_store import load_settings, save_settings
d = load_settings()
d['playback']['animation_fps'] = 25
save_settings(d)
print('Saved. Check app logs for hot-reload message.')
"
sleep 2
grep "hot-reload\|Settings hot" FrameServer/PhotoFrame.log | tail -3
```
Expected: Log line containing `hot-reload` or `Settings hot-reloaded`.

- [ ] **Step 4: Kill app**

```bash
kill $APP_PID
```

- [ ] **Step 5: Commit if any fixes were made, otherwise just note pass**

```bash
git add -p  # stage only fixes if any
git commit -m "fix: integration smoke test fixes" || echo "No fixes needed"
```
