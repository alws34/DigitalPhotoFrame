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
    """Load settings from DB. On first run, migrates from json_path if DB is empty."""
    conn = _get_db()
    try:
        # Ensure table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL
            )
        """)
        conn.commit()
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'main'"
        ).fetchone()
    finally:
        conn.close()

    if row:
        try:
            saved = json.loads(row["value"])
            return _deep_merge(get_default_settings(), saved)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"[Config] Corrupt settings in DB, using defaults: {e}")

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
            print(f"[Config] Migrated settings from {json_path}")
            return merged
        except Exception as e:
            print(f"[Config] Migration failed: {e}")

    defaults = get_default_settings()
    save_settings(defaults)
    return defaults


def save_settings(data: dict[str, Any]) -> None:
    """Persist settings to DB and touch sentinel to trigger hot reload."""
    blob = json.dumps(data, indent=2)
    now = time.time()
    conn = _get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('main', ?, ?)",
            (blob, now),
        )
        conn.commit()
    finally:
        conn.close()

    sentinel = _get_sentinel_path()
    try:
        sentinel_dir = os.path.dirname(os.path.abspath(sentinel))
        os.makedirs(sentinel_dir, exist_ok=True)
        with open(sentinel, "w") as f:
            f.write(str(now))
    except Exception as e:
        print(f"[Config] Could not touch sentinel {sentinel}: {e}")
