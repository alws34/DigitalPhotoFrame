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
        "albums": {
            "active_album_id": "all",
            "sync_interval_hours": 6,
            "sync_on_startup": True,
            "sync_delete_removed": True,
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
            "show_weather": True,
            "spacing_between": 50,
            "text_shadow": {"alpha": 230, "blur": 16, "offset_x": 2, "offset_y": 2},
            "time_font_size": 80,
        },
    }


SETTINGS_SCHEMA: dict = {
    "albums": {
        "active_album_id":      {"type": "str",  "label": "Active Album ID",          "restart_required": False},
        "sync_interval_hours":  {"type": "int",  "label": "Sync Interval (hours)",    "min": 1, "max": 168, "step": 1, "restart_required": False},
        "sync_on_startup":      {"type": "bool", "label": "Sync on Startup",          "restart_required": False},
        "sync_delete_removed":  {"type": "bool", "label": "Delete Removed Media",     "restart_required": False},
    },
    "autoupdate": {
        "branch":     {"type": "str",  "label": "Branch",               "restart_required": False},
        "enabled":    {"type": "bool", "label": "Enable Auto-Update",    "restart_required": False},
        "hour":       {"type": "int",  "label": "Update Hour",   "min": 0,  "max": 23,  "step": 1, "restart_required": False},
        "minute":     {"type": "int",  "label": "Update Minute", "min": 0,  "max": 59,  "step": 1, "restart_required": False},
        "remote":     {"type": "str",  "label": "Git Remote",            "restart_required": False},
        "repo_path":  {"type": "str",  "label": "Repo Path",             "restart_required": False},
        "shallow_ok": {"type": "bool", "label": "Allow Shallow Clone",   "restart_required": False},
    },
    "backend_configs": {
        # Network-critical settings first
        "server_port":    {"type": "int",      "label": "Server Port",    "min": 1,   "max": 65535, "step": 1,  "restart_required": True},
        "host":           {"type": "str",      "label": "Bind Host",      "restart_required": True},
        "supersecretkey": {"type": "password", "label": "Secret Key",     "restart_required": True},
        # Stream / performance settings below
        "stream_fps":     {"type": "int",      "label": "Stream FPS",     "min": 1,   "max": 60,    "step": 1,  "restart_required": False},
        "stream_height":  {"type": "int",      "label": "Stream Height",  "min": 100, "max": 4320,  "step": 10, "restart_required": True},
        "stream_width":   {"type": "int",      "label": "Stream Width",   "min": 100, "max": 7680,  "step": 10, "restart_required": True},
        "idle_fps":       {"type": "int",      "label": "Idle FPS",       "min": 1,   "max": 30,    "step": 1,  "restart_required": True},
    },
    "effects": {
        "allow_translucent_background": {"type": "bool",  "label": "Translucent Background", "restart_required": False},
        "background_blur_radius":       {"type": "int",   "label": "Background Blur",  "min": 0, "max": 200, "step": 2,    "restart_required": False},
        "background_opacity":           {"type": "float", "label": "Background Opacity","min": 0.0,"max": 1.0,"step": 0.05, "restart_required": False},
        "shadow_blur_radius":           {"type": "int",   "label": "Shadow Blur",      "min": 0, "max": 200, "step": 2,    "restart_required": False},
        "shadow_opacity":               {"type": "float", "label": "Shadow Opacity",   "min": 0.0,"max": 1.0,"step": 0.05, "restart_required": False},
    },
    "mqtt": {
        "base_topic":       {"type": "str",      "label": "Base Topic",           "restart_required": False},
        "client_id":        {"type": "str",      "label": "Client ID",            "restart_required": False},
        "discovery":        {"type": "bool",     "label": "HA Discovery",         "restart_required": False},
        "discovery_prefix": {"type": "str",      "label": "Discovery Prefix",     "restart_required": False},
        "enabled":          {"type": "bool",     "label": "Enable MQTT",          "restart_required": False},
        "host":             {"type": "str",      "label": "Broker Host",          "restart_required": False},
        "interval_seconds": {"type": "int",      "label": "Publish Interval (s)", "min": 1, "max": 3600, "step": 1, "restart_required": False},
        "password":         {"type": "password", "label": "Password",             "restart_required": False},
        "port":             {"type": "int",      "label": "Broker Port",          "min": 1, "max": 65535, "step": 1, "restart_required": False},
        "retain_config":    {"type": "bool",     "label": "Retain Config",        "restart_required": False},
        "tls":              {"type": "bool",     "label": "Use TLS",              "restart_required": False},
        "username":         {"type": "str",      "label": "Username",             "restart_required": False},
    },
    "open_meteo": {
        "cache_ttl_minutes":  {"type": "int",            "label": "Cache TTL (min)",    "min": 1, "max": 1440, "step": 5, "restart_required": False},
        "latitude":           {"type": "numeric_string", "label": "Latitude",           "restart_required": False},
        "longitude":          {"type": "numeric_string", "label": "Longitude",          "restart_required": False},
        "precipitation_unit": {"type": "enum",           "label": "Precipitation Unit", "choices": ["mm", "inch"],               "restart_required": False},
        "temperature_unit":   {"type": "enum",           "label": "Temperature Unit",   "choices": ["celsius", "fahrenheit"],    "restart_required": False},
        "timeformat":         {"type": "str",            "label": "Time Format",        "restart_required": False},
        "timezone":           {"type": "str",            "label": "Timezone",           "restart_required": False},
        "units":              {"type": "enum",           "label": "Units",              "choices": ["metric", "imperial"],       "restart_required": False},
        "wind_speed_unit":    {"type": "enum",           "label": "Wind Speed Unit",    "choices": ["kmh", "mph", "ms", "kn"],  "restart_required": False},
    },
    "playback": {
        "animation_duration":   {"type": "int", "label": "Animation Duration (s)",  "min": 1,  "max": 120, "step": 1, "restart_required": False},
        "animation_fps":        {"type": "int", "label": "Animation FPS",           "min": 1,  "max": 60,  "step": 1, "restart_required": False},
        "delay_between_images": {"type": "int", "label": "Delay Between Images (s)","min": 1,  "max": 600, "step": 5, "restart_required": False},
    },
    "screen": {
        "brightness":       {"type": "int",  "label": "Brightness (%)",  "min": 0, "max": 100, "step": 5,  "restart_required": False},
        "off_hour":         {"type": "int",  "label": "Screen Off Hour", "min": 0, "max": 23,  "step": 1,  "restart_required": False},
        "on_hour":          {"type": "int",  "label": "Screen On Hour",  "min": 0, "max": 23,  "step": 1,  "restart_required": False},
        "orientation":      {"type": "int",  "label": "Orientation (°)", "min": 0, "max": 270, "step": 90, "restart_required": False},
        "schedule_enabled": {"type": "bool", "label": "Enable Schedule",                                   "restart_required": False},
        # "schedules" is a list of per-schedule objects — managed via web UI only, intentionally absent
    },
    "stats": {
        "font_color": {"type": "color", "label": "Font Color", "choices": ["yellow", "white", "red", "green", "blue"], "restart_required": False},
        "font_size":  {"type": "int",   "label": "Font Size",  "min": 8, "max": 100, "step": 2,                        "restart_required": False},
        "show":       {"type": "bool",  "label": "Show Stats",                                                          "restart_required": False},
    },
    "system": {
        "image_dir":              {"type": "str", "label": "Image Directory",    "restart_required": False},
        "image_quality_encoding": {"type": "int", "label": "Image Quality (%)", "min": 1, "max": 100, "step": 5, "restart_required": False},
        "log_file_path":          {"type": "str", "label": "Log File Path",     "restart_required": False},
        "service_name":           {"type": "str", "label": "Service Name",      "restart_required": False},
    },
    "ui": {
        "contrast_text":   {"type": "bool", "label": "Contrast Text",  "restart_required": False},
        "date_font_size":  {"type": "int",  "label": "Date Font Size", "min": 10, "max": 200, "step": 5, "restart_required": False},
        "date_format":     {"type": "str",  "label": "Date Format",    "restart_required": False},
        "font_name":       {"type": "str",  "label": "Font File Name", "restart_required": False},
        "is_24h":          {"type": "bool", "label": "24-Hour Clock",  "restart_required": False},
        "margins": {
            "bottom": {"type": "int", "label": "Bottom Margin", "min": 0, "max": 300, "step": 5, "restart_required": False},
            "left":   {"type": "int", "label": "Left Margin",   "min": 0, "max": 300, "step": 5, "restart_required": False},
            "right":  {"type": "int", "label": "Right Margin",  "min": 0, "max": 300, "step": 5, "restart_required": False},
        },
        "show_weather":    {"type": "bool", "label": "Show Weather",    "restart_required": False},
        "spacing_between": {"type": "int",  "label": "Spacing Between", "min": 0, "max": 300, "step": 5, "restart_required": False},
        "text_shadow": {
            "alpha":    {"type": "int", "label": "Shadow Alpha",    "min": 0,   "max": 255, "step": 5,  "restart_required": False},
            "blur":     {"type": "int", "label": "Shadow Blur",     "min": 0,   "max": 50,  "step": 1,  "restart_required": False},
            "offset_x": {"type": "int", "label": "Shadow Offset X", "min": -50, "max": 50,  "step": 1, "restart_required": False},
            "offset_y": {"type": "int", "label": "Shadow Offset Y", "min": -50, "max": 50,  "step": 1, "restart_required": False},
        },
        "time_font_size": {"type": "int", "label": "Time Font Size", "min": 10, "max": 300, "step": 5, "restart_required": False},
    },
}


def get_field_schema(path: str) -> "dict | None":
    """Resolve a dotted path like 'ui.margins.left' to its leaf descriptor, or None."""
    parts = path.split(".")
    node = SETTINGS_SCHEMA
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    if isinstance(node, dict) and "type" in node:
        return node
    return None


def get_restart_required_paths() -> frozenset:
    """Return frozenset of every dotted path whose schema has restart_required=True."""
    result: set = set()

    def _walk(node: dict, prefix: str) -> None:
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                if "type" in v:
                    if v.get("restart_required"):
                        result.add(path)
                else:
                    _walk(v, path)

    _walk(SETTINGS_SCHEMA, "")
    return frozenset(result)


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
            # Auto-enable weather when coordinates are configured
            lat = merged.get("open_meteo", {}).get("latitude", "")
            lon = merged.get("open_meteo", {}).get("longitude", "")
            if lat and lon:
                merged.setdefault("ui", {})["show_weather"] = True
            save_settings(merged)
            print(f"[Config] Migrated settings from {json_path}")
            try:
                migrated_path = json_path + ".migrated"
                os.rename(json_path, migrated_path)
                print(f"[Config] Renamed {json_path} → {migrated_path}")
            except Exception as rename_err:
                print(f"[Config] Could not rename settings JSON: {rename_err}")
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
