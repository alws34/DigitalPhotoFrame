# Settings Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every setting visible and editable in all three UI surfaces (pygame panel, Qt dialog, React web), with full hot-reload and restart prompts for fields that require it.

**Architecture:** A central `SETTINGS_SCHEMA` dict in `Utilities/config_store.py` describes every leaf field (type, range, choices, restart_required). All UIs query `get_field_schema(path)` to decide which widget to render. Hot-reload is already plumbed via sentinel + watchdog; this plan adds schema helpers, fixes three known save bugs, wires missing subsystem callbacks, and adds OSK/numpad support to the pygame panel.

**Tech Stack:** Python 3.11, PySide6, pygame 2, Flask, React 18 (JSX), SQLite, watchdog, qrcode, subprocess (for system OSK on Linux/RPi)

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `Utilities/config_store.py` | Modify | Add `SETTINGS_SCHEMA`, `get_field_schema()`, `get_restart_required_paths()` |
| `Tests/test_settings_schema.py` | Create | Tests for schema helpers |
| `WebAPI/routes/settings.py` | Modify | Add `GET /api/settings/schema` route |
| `WebAPI/routes/maintenance.py` | Create | `POST /api/maintenance/restart` route |
| `WebAPI/API.py` | Modify | Register `maintenance_bp`; store restart callback in `app.config` |
| `Utilities/Weather/weather_adapter.py` | Modify | Register `on_settings_changed` callback to update weather config |
| `FrameGUI/SettingsFrom/dialog.py` | Modify | Fix `_save_settings()` deep-merge bug; schema-driven widgets; restart prompt |
| `FrameGUI/photoframe_view_pygame.py` | Modify | Rewrite `_build_fields()`; add numpad overlay; add OSK overlay; restart prompt |
| `frontend/src/pages/SettingsView.jsx` | Modify | Fetch schema; `setNestedValue` helper; dotted-path `handleChange`; restart modal |
| `frontend/src/components/settings/SettingsSection.jsx` | Modify | Forward full dotted-path prefix |
| `frontend/src/components/settings/SettingField.jsx` | Modify | Schema-driven widget rendering; ⚠ badge for restart-required |

---

## Task 1: Settings Schema + Helpers

**Files:**
- Modify: `Utilities/config_store.py`
- Create: `Tests/test_settings_schema.py`

- [ ] **Step 1: Write failing tests for schema helpers**

Create `Tests/test_settings_schema.py`:

```python
import importlib
import pytest


def _get_cs():
    import Utilities.config_store as cs
    importlib.reload(cs)
    return cs


def test_schema_covers_all_default_sections():
    cs = _get_cs()
    defaults = cs.get_default_settings()
    schema = cs.SETTINGS_SCHEMA
    for section in defaults:
        if section == "about":
            continue
        assert section in schema, f"Section '{section}' missing from SETTINGS_SCHEMA"


def test_get_field_schema_simple_path():
    cs = _get_cs()
    desc = cs.get_field_schema("playback.animation_fps")
    assert desc is not None
    assert desc["type"] == "int"
    assert desc["min"] == 1
    assert desc["max"] == 60


def test_get_field_schema_nested_path():
    cs = _get_cs()
    desc = cs.get_field_schema("ui.margins.left")
    assert desc is not None
    assert desc["type"] == "int"


def test_get_field_schema_unknown_path_returns_none():
    cs = _get_cs()
    assert cs.get_field_schema("nonexistent.field") is None


def test_get_field_schema_section_node_returns_none():
    cs = _get_cs()
    # "ui.margins" is a container, not a leaf — should return None
    assert cs.get_field_schema("ui.margins") is None


def test_get_restart_required_paths_contains_known_fields():
    cs = _get_cs()
    rr = cs.get_restart_required_paths()
    assert "backend_configs.server_port" in rr
    assert "backend_configs.stream_width" in rr
    assert "backend_configs.supersecretkey" in rr


def test_get_restart_required_paths_excludes_non_restart_fields():
    cs = _get_cs()
    rr = cs.get_restart_required_paths()
    assert "playback.animation_fps" not in rr
    assert "ui.time_font_size" not in rr


def test_schema_password_type():
    cs = _get_cs()
    desc = cs.get_field_schema("backend_configs.supersecretkey")
    assert desc["type"] == "password"


def test_schema_enum_has_choices():
    cs = _get_cs()
    desc = cs.get_field_schema("open_meteo.temperature_unit")
    assert desc["type"] == "enum"
    assert "celsius" in desc["choices"]
    assert "fahrenheit" in desc["choices"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
env/bin/python -m pytest Tests/test_settings_schema.py -v 2>&1 | head -40
```
Expected: multiple failures (AttributeError / AssertionError — SETTINGS_SCHEMA not defined yet).

- [ ] **Step 3: Add SETTINGS_SCHEMA and helpers to config_store.py**

Open `Utilities/config_store.py`. After the closing `}` of `get_default_settings()` (around line 122), add:

```python
SETTINGS_SCHEMA: dict = {
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
        "host":          {"type": "str",      "label": "Bind Host",      "restart_required": True},
        "idle_fps":      {"type": "int",      "label": "Idle FPS",       "min": 1,   "max": 30,    "step": 1,  "restart_required": False},
        "server_port":   {"type": "int",      "label": "Server Port",    "min": 1,   "max": 65535, "step": 1,  "restart_required": True},
        "stream_fps":    {"type": "int",      "label": "Stream FPS",     "min": 1,   "max": 60,    "step": 1,  "restart_required": False},
        "stream_height": {"type": "int",      "label": "Stream Height",  "min": 100, "max": 4320,  "step": 10, "restart_required": True},
        "stream_width":  {"type": "int",      "label": "Stream Width",   "min": 100, "max": 7680,  "step": 10, "restart_required": True},
        "supersecretkey":{"type": "password", "label": "Secret Key",     "restart_required": True},
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
        "cache_ttl_minutes":  {"type": "int",            "label": "Cache TTL (min)",      "min": 1, "max": 1440, "step": 5, "restart_required": False},
        "latitude":           {"type": "numeric_string", "label": "Latitude",             "restart_required": False},
        "longitude":          {"type": "numeric_string", "label": "Longitude",            "restart_required": False},
        "precipitation_unit": {"type": "enum",           "label": "Precipitation Unit",   "choices": ["mm", "inch"],                    "restart_required": False},
        "temperature_unit":   {"type": "enum",           "label": "Temperature Unit",     "choices": ["celsius", "fahrenheit"],          "restart_required": False},
        "timeformat":         {"type": "str",            "label": "Time Format",          "restart_required": False},
        "timezone":           {"type": "str",            "label": "Timezone",             "restart_required": False},
        "units":              {"type": "enum",           "label": "Units",                "choices": ["metric", "imperial"],             "restart_required": False},
        "wind_speed_unit":    {"type": "enum",           "label": "Wind Speed Unit",      "choices": ["kmh", "mph", "ms", "kn"],         "restart_required": False},
    },
    "playback": {
        "animation_duration":   {"type": "int", "label": "Animation Duration (s)", "min": 1,  "max": 120, "step": 1, "restart_required": False},
        "animation_fps":        {"type": "int", "label": "Animation FPS",          "min": 1,  "max": 60,  "step": 1, "restart_required": False},
        "delay_between_images": {"type": "int", "label": "Delay Between Images (s)","min": 1, "max": 600, "step": 5, "restart_required": False},
    },
    "screen": {
        "brightness":       {"type": "int",  "label": "Brightness (%)",  "min": 0, "max": 100, "step": 5, "restart_required": False},
        "off_hour":         {"type": "int",  "label": "Screen Off Hour", "min": 0, "max": 23,  "step": 1, "restart_required": False},
        "on_hour":          {"type": "int",  "label": "Screen On Hour",  "min": 0, "max": 23,  "step": 1, "restart_required": False},
        "orientation":      {"type": "int",  "label": "Orientation (°)", "min": 0, "max": 270, "step": 90,"restart_required": False},
        "schedule_enabled": {"type": "bool", "label": "Enable Schedule",                        "restart_required": False},
        # "schedules" is a complex array managed only via web UI — intentionally absent
    },
    "stats": {
        "font_color": {"type": "color", "label": "Font Color", "choices": ["yellow", "white", "red", "green", "blue"], "restart_required": False},
        "font_size":  {"type": "int",   "label": "Font Size",  "min": 8, "max": 100, "step": 2, "restart_required": False},
        "show":       {"type": "bool",  "label": "Show Stats",                                   "restart_required": False},
    },
    "system": {
        "image_dir":              {"type": "str", "label": "Image Directory",    "restart_required": False},
        "image_quality_encoding": {"type": "int", "label": "Image Quality (%)", "min": 1, "max": 100, "step": 5, "restart_required": False},
        "log_file_path":          {"type": "str", "label": "Log File Path",     "restart_required": False},
        "service_name":           {"type": "str", "label": "Service Name",      "restart_required": False},
    },
    "ui": {
        "contrast_text":   {"type": "bool", "label": "Contrast Text",     "restart_required": False},
        "date_font_size":  {"type": "int",  "label": "Date Font Size",    "min": 10, "max": 200, "step": 5, "restart_required": False},
        "date_format":     {"type": "str",  "label": "Date Format",       "restart_required": False},
        "font_name":       {"type": "str",  "label": "Font File Name",    "restart_required": False},
        "is_24h":          {"type": "bool", "label": "24-Hour Clock",     "restart_required": False},
        "margins": {
            "bottom": {"type": "int", "label": "Bottom Margin", "min": 0, "max": 300, "step": 5, "restart_required": False},
            "left":   {"type": "int", "label": "Left Margin",   "min": 0, "max": 300, "step": 5, "restart_required": False},
            "right":  {"type": "int", "label": "Right Margin",  "min": 0, "max": 300, "step": 5, "restart_required": False},
        },
        "show_weather":    {"type": "bool", "label": "Show Weather",      "restart_required": False},
        "spacing_between": {"type": "int",  "label": "Spacing Between",  "min": 0, "max": 300, "step": 5, "restart_required": False},
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
env/bin/python -m pytest Tests/test_settings_schema.py -v
```
Expected: all 9 tests PASS.

- [ ] **Step 5: Run full test suite to catch regressions**

```bash
env/bin/python -m pytest -x -q
```
Expected: all existing tests pass.

- [ ] **Step 6: Ruff check**

```bash
env/bin/python -m ruff check Utilities/config_store.py
```
Fix any issues. Then commit:

```bash
git add Utilities/config_store.py Tests/test_settings_schema.py
git commit -m "feat: add SETTINGS_SCHEMA and get_field_schema/get_restart_required_paths helpers"
```

---

## Task 2: Web API — Schema Endpoint + Restart Endpoint

**Files:**
- Modify: `WebAPI/routes/settings.py`
- Create: `WebAPI/routes/maintenance.py`
- Modify: `WebAPI/API.py`

- [ ] **Step 1: Add GET /api/settings/schema to settings route**

In `WebAPI/routes/settings.py`, add after the existing imports:

```python
from Utilities.config_store import SETTINGS_SCHEMA
```

Then add this route after the existing `get_settings` route (around line 50):

```python
@settings_bp.route("/schema", methods=["GET"], strict_slashes=False)
def get_schema():
    return jsonify(SETTINGS_SCHEMA)
```

- [ ] **Step 2: Create WebAPI/routes/maintenance.py**

```python
import os
import sys
import threading

from flask import Blueprint, current_app, jsonify

maintenance_bp = Blueprint("maintenance_bp", __name__, url_prefix="/api/maintenance")


@maintenance_bp.route("/restart", methods=["POST"])
def restart_service():
    backend = current_app.config.get("backend")
    if backend and not backend.is_authenticated():
        return jsonify({"error": "unauthorized"}), 401

    restart_fn = current_app.config.get("restart_fn")
    if restart_fn is None:
        return jsonify({"error": "restart not configured"}), 501

    def _do_restart():
        import time
        time.sleep(0.3)
        try:
            restart_fn()
        except Exception as e:
            print(f"[Maintenance] Restart failed: {e}")

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"message": "Restarting…"})
```

- [ ] **Step 3: Register maintenance_bp and store restart_fn in WebAPI/API.py**

In `WebAPI/API.py`, find the imports block and add:

```python
from WebAPI.routes.maintenance import maintenance_bp
```

Find where blueprints are registered (around line 652–655, the block with `register_blueprint` calls) and add:

```python
self.app.register_blueprint(maintenance_bp)
```

In the same class, find the `__init__` or `create_app` method where Flask app config is set up and add a way to store the restart callback. Look for where `self.app` is created and add after it:

```python
self.app.config["restart_fn"] = None  # set by caller via set_restart_fn()
```

Then add this method to the `APIServer` / `Backend` class:

```python
def set_restart_fn(self, fn) -> None:
    self.app.config["restart_fn"] = fn
```

- [ ] **Step 4: Wire restart_fn in app_modes.py**

In `app_modes.py`, wherever `APIServer` / `Backend` is created and `_restart_program` is available, add a call to `set_restart_fn`. Look for the pattern `restart_service_async=_restart_program` and, in the same block after the backend is created, add:

```python
backend.set_restart_fn(_restart_program)
```

(Do this in all three places where `restart_service_async=_restart_program` appears — lines ~45, ~104, ~247.)

- [ ] **Step 5: Manual smoke test**

```bash
env/bin/python app.py --headless &
sleep 3
curl -s http://localhost:5002/api/settings/schema | python3 -m json.tool | head -30
kill %1
```
Expected: JSON schema printed with `playback`, `ui`, etc. sections.

- [ ] **Step 6: Ruff + commit**

```bash
env/bin/python -m ruff check WebAPI/routes/settings.py WebAPI/routes/maintenance.py WebAPI/API.py app_modes.py
git add WebAPI/routes/settings.py WebAPI/routes/maintenance.py WebAPI/API.py app_modes.py
git commit -m "feat: add /api/settings/schema and /api/maintenance/restart endpoints"
```

---

## Task 3: Hot-Reload Coverage — Weather Adapter

**Files:**
- Modify: `Utilities/Weather/weather_adapter.py`

> Note: `PhotoFrameServer` (`_on_settings_changed`) and `MqttBridge` already register `on_settings_changed` callbacks. `ScreenScheduler` reads from `owner.settings` on each tick so it picks up changes automatically. This task wires the weather adapter — the main remaining gap.

- [ ] **Step 1: Read the weather adapter**

Open `Utilities/Weather/weather_adapter.py`. Find:
- Where `OpenMeteoWeatherHandler` (or the active handler) stores its settings reference.
- Whether `build_weather_client()` is called once at startup or can be called again.

- [ ] **Step 2: Add on_settings_changed callback to the weather handler**

The `WeatherClient` wraps a handler (either `OpenMeteoWeatherHandler` or `accuweather_handler`). The handler likely stores `settings` as an instance variable. Add a callback that updates those keys in-place.

In `weather_adapter.py`, find `WeatherClient.__init__` and add:

```python
from Utilities.config_events import on_settings_changed as _on_sc

def __init__(self, impl):
    self._impl = impl
    _on_sc(self._on_settings_changed)

def _on_settings_changed(self, new_data: dict) -> None:
    try:
        om = new_data.get("open_meteo", {}) or {}
        if hasattr(self._impl, "settings") and isinstance(self._impl.settings, dict):
            self._impl.settings.update(om)
        # Reset weather cache so next fetch uses new coords/units
        if hasattr(self._impl, "_cache"):
            self._impl._cache = None
        if hasattr(self._impl, "_cache_time"):
            self._impl._cache_time = 0.0
    except Exception as e:
        print(f"[Weather] Hot-reload error: {e}")
```

Adapt the attribute names (`settings`, `_cache`, `_cache_time`) to match what you actually find in the file.

- [ ] **Step 3: Headless smoke test**

```bash
env/bin/python app.py --headless &
sleep 5
# Change cache_ttl_minutes via the API (requires login — skip if inconvenient)
# Just verify no import errors or crashes
kill %1
```
Expected: no exceptions in output.

- [ ] **Step 4: Ruff + commit**

```bash
env/bin/python -m ruff check Utilities/Weather/weather_adapter.py
git add Utilities/Weather/weather_adapter.py
git commit -m "feat: hot-reload weather adapter settings on config change"
```

---

## Task 4: Qt Dialog — Save Bug Fix + Schema-Driven Widgets + Restart Prompt

**Files:**
- Modify: `FrameGUI/SettingsFrom/dialog.py`

- [ ] **Step 1: Fix the save bug**

In `FrameGUI/SettingsFrom/dialog.py`, find `_save_settings` (around line 429). Replace the entire method with:

```python
def _save_settings(self) -> None:
    from Utilities.config_store import load_settings, save_settings, get_restart_required_paths
    current = load_settings()
    _apply_pending(current, self._pending_changes)
    save_settings(current)

    changed_paths = _collect_paths(self._pending_changes)
    self._pending_changes.clear()

    rr = get_restart_required_paths()
    if changed_paths & rr:
        self._prompt_restart()
```

Add these two module-level helpers just above the `SettingsModel` class (top of file, after imports):

```python
def _apply_pending(base: dict, changes: dict) -> None:
    """Recursively merge changes into base in-place."""
    for k, v in changes.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _apply_pending(base[k], v)
        else:
            base[k] = v


def _collect_paths(d: dict, prefix: str = "") -> set:
    """Return set of all dotted leaf paths in a nested dict."""
    paths = set()
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            paths |= _collect_paths(v, path)
        else:
            paths.add(path)
    return paths
```

- [ ] **Step 2: Add _prompt_restart method to SettingsDialog**

Inside the `SettingsDialog` class, add:

```python
def _prompt_restart(self) -> None:
    try:
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Restart Required")
        msg.setText("Some changes require a restart to take effect.\nRestart now?")
        msg.setIcon(QtWidgets.QMessageBox.Question)
        yes = msg.addButton("Restart Now", QtWidgets.QMessageBox.AcceptRole)
        msg.addButton("Later", QtWidgets.QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() is yes:
            self.vm.restart_service()
    except Exception as e:
        print(f"[Settings] Restart prompt error: {e}")
```

- [ ] **Step 3: Fix _pending_changes keying for nested dicts**

The current `_make_input_widget` closures use `parent_key` for the section key. When `parent_key` is `"ui.margins"`, changes end up under a dotted key. Replace the approach: always key `_pending_changes` by the top-level section name and build nested dicts.

Find `_make_input_widget` (around line 379). Replace the four `on_*` closures at the top of that method with:

```python
def _set_change(key, value, parent_key=parent_key):
    parts = parent_key.split(".")
    target = self._pending_changes
    for p in parts:
        target = target.setdefault(p, {})
    target[key] = value

def on_bool(state, k=key):  _set_change(k, bool(state))
def on_int(val,   k=key):   _set_change(k, int(val))
def on_float(val, k=key):   _set_change(k, float(val))
def on_str(text,  k=key):   _set_change(k, text)
```

- [ ] **Step 4: Schema-driven widget types**

At the top of `_make_input_widget`, before the isinstance checks, add:

```python
from Utilities.config_store import get_field_schema
schema = get_field_schema(f"{parent_key}.{key}")
ftype = schema["type"] if schema else None
```

Then add these cases before the existing `isinstance(value, bool)` check:

```python
if ftype == "password":
    w = QtWidgets.QLineEdit(str(value))
    w.setEchoMode(QtWidgets.QLineEdit.Password)
    w.textChanged.connect(on_str)
    return w

if ftype in ("enum", "color"):
    choices = schema.get("choices", [str(value)])
    w = QtWidgets.QComboBox()
    w.addItems(choices)
    if str(value) in choices:
        w.setCurrentText(str(value))
    w.currentTextChanged.connect(on_str)
    return w
```

Also update `_build_section_widget` to append `" ⚠"` to the label for restart-required fields:

```python
def _build_section_widget(self, section: dict, parent_key: str) -> QtWidgets.QWidget:
    from Utilities.config_store import get_field_schema
    widget = QtWidgets.QWidget()
    form = QtWidgets.QFormLayout(widget)
    form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
    for key, value in section.items():
        schema = get_field_schema(f"{parent_key}.{key}")
        label = key.replace("_", " ").title()
        if schema and schema.get("restart_required"):
            label += " ⚠"
        input_widget = self._make_input_widget(key, value, parent_key)
        if input_widget:
            form.addRow(label, input_widget)
    return widget
```

- [ ] **Step 5: Ruff check + commit**

```bash
env/bin/python -m ruff check FrameGUI/SettingsFrom/dialog.py
git add FrameGUI/SettingsFrom/dialog.py
git commit -m "fix: Qt dialog deep-merge save bug; schema-driven widgets; restart prompt"
```

---

## Task 5: Pygame Panel — Schema-Driven Field Rendering + Restart Prompt

**Files:**
- Modify: `FrameGUI/photoframe_view_pygame.py`

This task rewrites `_build_fields()` to use the schema and adds a restart-prompt overlay. It does NOT yet add the OSK or numpad (those are Tasks 6 and 7).

- [ ] **Step 1: Replace _build_fields() with schema-driven version**

In `photoframe_view_pygame.py`, delete the existing `_build_fields()` function (lines ~129–185) and replace it with:

```python
def _build_fields(settings: dict, sections: List[str]) -> List[tuple]:
    """
    Return flat list of field descriptors for the given section keys.
    Each entry is one of:
      ("header", label_text)
      (path, label, ftype, meta)
        where meta is:
          for bool:           None
          for int/float:      (step, fmin, fmax)
          for enum/color:     choices_list
          for str/password/numeric_string: None
    """
    from Utilities.config_store import get_field_schema
    result: List[tuple] = []
    show_headers = len(sections) > 1

    def _recurse(data: dict, prefix: str, depth: int) -> None:
        for key, val in data.items():
            path = f"{prefix}.{key}"
            schema = get_field_schema(path)

            label = "  " * depth + key.replace("_", " ").title()
            if schema and schema.get("restart_required"):
                label += " ⚠"

            if schema is None:
                # No schema = container node or unregistered field
                if isinstance(val, dict):
                    result.append(("header", label))
                    _recurse(val, path, depth + 1)
                # skip lists and unregistered leaf values
                continue

            ftype = schema["type"]

            if ftype == "bool":
                result.append((path, label, "bool", None))

            elif ftype in ("int", "float"):
                py_type = int if ftype == "int" else float
                step = schema.get("step", 1 if ftype == "int" else 0.05)
                fmin = schema.get("min", -999999)
                fmax = schema.get("max",  999999)
                result.append((path, label, py_type, (step, fmin, fmax)))

            elif ftype in ("enum", "color"):
                result.append((path, label, "cycle", schema.get("choices", [])))

            elif ftype in ("str", "password", "numeric_string"):
                result.append((path, label, ftype, None))

    for section_key in sections:
        section_data = settings.get(section_key)
        if not isinstance(section_data, dict):
            continue
        if show_headers:
            result.append(("header", section_key.replace("_", " ").upper()))
        _recurse(section_data, section_key, 0)

    return result
```

Remove the now-unused module-level constants `_SKIP_KEYS`, `_STRING_CYCLES`, and `_FIELD_CONFIG`.

- [ ] **Step 2: Update _draw_settings_tab to handle new field descriptor shape**

The existing `_draw_settings_tab` unpacks fields as `(path, label, ftype, step, fmin, fmax)` — 6-tuple. The new format uses a 4-tuple `(path, label, ftype, meta)`. Update the unpack line in `_draw_settings_tab` (around line 446):

```python
path, label, ftype, meta = field
```

Then update the rendering branches to use `meta`:

```python
if ftype == "bool":
    # meta is None — unchanged toggle rendering
    cur = bool(_get_nested(merged, path, False))
    # ... existing toggle drawing code ...

elif ftype == "cycle":
    choices = meta  # was: step
    # ... existing cycle drawing code (unchanged) ...

elif ftype in ("str", "password", "numeric_string"):
    # Show current value as tappable text row (OSK/numpad handling in Tasks 6–7)
    cur_str = str(_get_nested(merged, path, ""))
    display = ("*" * len(cur_str)) if ftype == "password" else cur_str
    val_surf = self._font_value.render(display[:24] or "(tap to edit)", True, (200, 230, 255))
    right_x = W - pad
    row_rect = pygame.Rect(pad, row_y, W - pad * 2, ROW_H)
    tap_r = pygame.Rect(right_x - max(200, W // 4), btn_y, max(200, W // 4), btn_h)
    pygame.draw.rect(panel, (40, 60, 140, 220), tap_r, border_radius=6)
    panel.blit(val_surf, (tap_r.centerx - val_surf.get_width() // 2,
                          tap_r.centery - val_surf.get_height() // 2))
    self._ui_rects.append((tap_r, f"edit_{ftype}", path))

else:  # int or float
    step, fmin, fmax = meta
    py_type = ftype  # already int or float class
    try:
        cur_num = py_type(_get_nested(merged, path, 0))
    except Exception:
        cur_num = py_type(0)
    # ... existing +/- drawing code (unchanged, but use step/fmin/fmax from meta) ...
    self._ui_rects.append((minus_r, "dec", (path, py_type, step, fmin, fmax)))
    self._ui_rects.append((plus_r,  "inc", (path, py_type, step, fmin, fmax)))
```

- [ ] **Step 3: Add restart-prompt overlay state and drawing**

Add instance variables in `__init__` (after `_save_msg_until`):

```python
self._restart_prompt: bool = False
```

Add `_draw_restart_prompt` method:

```python
def _draw_restart_prompt(self, panel: "pygame.Surface") -> None:
    W, H = self.width, self.height
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    panel.blit(overlay, (0, 0))

    box_w, box_h = min(600, W - 80), 200
    box = pygame.Rect((W - box_w) // 2, (H - box_h) // 2, box_w, box_h)
    pygame.draw.rect(panel, (20, 28, 60, 245), box, border_radius=12)
    pygame.draw.rect(panel, (60, 110, 255, 180), box, 2, border_radius=12)

    msg = self._font_label.render("Some changes need a restart.", True, (220, 225, 255))
    panel.blit(msg, (box.centerx - msg.get_width() // 2, box.y + 28))

    btn_w = box_w // 3
    restart_r = pygame.Rect(box.x + 20,            box.y + 120, btn_w, 52)
    later_r   = pygame.Rect(box.right - btn_w - 20, box.y + 120, btn_w, 52)
    for r, txt, col in [(restart_r, "Restart Now", (30, 160, 80, 220)),
                        (later_r,   "Later",        (80, 80, 120, 220))]:
        pygame.draw.rect(panel, col, r, border_radius=8)
        s = self._font_label.render(txt, True, (255, 255, 255))
        panel.blit(s, (r.centerx - s.get_width() // 2, r.centery - s.get_height() // 2))
    self._ui_rects.append((restart_r, "restart_confirm", None))
    self._ui_rects.append((later_r,   "restart_later",   None))
```

Call `_draw_restart_prompt` at the end of `_draw_panel`, just before `self.screen.blit(panel, (0, 0))`:

```python
if self._restart_prompt:
    self._draw_restart_prompt(panel)
```

- [ ] **Step 4: Wire restart actions in _dispatch and _save_settings**

In `_save_settings()`, after `notify_settings_changed(current)`, add:

```python
from Utilities.config_store import get_restart_required_paths
changed = set(_collect_dotted_keys(self._pending_changes))
if changed & get_restart_required_paths():
    self._restart_prompt = True
```

Add the helper at module level:

```python
def _collect_dotted_keys(d: dict, prefix: str = "") -> list:
    keys = []
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(_collect_dotted_keys(v, path))
        else:
            keys.append(path)
    return keys
```

In `_dispatch`, add two new action handlers:

```python
elif action == "restart_confirm":
    self._restart_prompt = False
    import sys, os
    python = sys.executable
    os.execl(python, python, *sys.argv)

elif action == "restart_later":
    self._restart_prompt = False
```

Also add handlers for `"edit_str"`, `"edit_password"`, `"edit_numeric_string"` — these will be fleshed out in Tasks 6 and 7. For now, stub them to prevent crashes:

```python
elif action in ("edit_str", "edit_password", "edit_numeric_string"):
    pass  # OSK/numpad implemented in Tasks 6–7
```

- [ ] **Step 5: Ruff check**

```bash
env/bin/python -m ruff check FrameGUI/photoframe_view_pygame.py
```

Fix any issues.

- [ ] **Step 6: Smoke test**

```bash
env/bin/python app.py --headless &
sleep 3
echo "No crash = PASS"
kill %1
```

- [ ] **Step 7: Commit**

```bash
git add FrameGUI/photoframe_view_pygame.py
git commit -m "feat: pygame panel schema-driven field rendering and restart prompt"
```

---

## Task 6: Pygame Panel — Numpad Overlay (numeric_string fields)

**Files:**
- Modify: `FrameGUI/photoframe_view_pygame.py`

This task implements the native numpad overlay that appears when the user taps a `numeric_string` field (latitude, longitude).

- [ ] **Step 1: Add numpad state variables to __init__**

In `PhotoFramePygame.__init__`, after `self._restart_prompt = False`, add:

```python
# Numpad overlay state
self._numpad_active: bool = False
self._numpad_field_path: "str | None" = None
self._numpad_buffer: str = ""
```

- [ ] **Step 2: Add _draw_numpad method**

```python
def _draw_numpad(self, panel: "pygame.Surface") -> None:
    W, H = self.width, self.height
    pad = 16

    # Dim background
    dim = pygame.Surface((W, H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 190))
    panel.blit(dim, (0, 0))

    keys = [
        ["7", "8", "9"],
        ["4", "5", "6"],
        ["1", "2", "3"],
        [".", "0", "-"],
    ]
    action_row = ["←", "✓", "✗"]

    btn_size = max(80, min(H // 8, W // 6))
    grid_w = btn_size * 3 + pad * 2
    grid_h = btn_size * 5 + pad * 4
    gx = (W - grid_w) // 2
    gy = (H - grid_h) // 2

    # Current buffer display
    field_label = (self._numpad_field_path or "").split(".")[-1].replace("_", " ").title()
    buf_surf = self._font_value.render(
        f"{field_label}: {self._numpad_buffer or '_'}", True, (220, 230, 255)
    )
    panel.blit(buf_surf, (gx, gy - buf_surf.get_height() - pad))

    for row_i, row in enumerate(keys):
        for col_i, key_label in enumerate(row):
            r = pygame.Rect(
                gx + col_i * (btn_size + pad // 2),
                gy + row_i * (btn_size + pad // 2),
                btn_size, btn_size
            )
            pygame.draw.rect(panel, (40, 60, 150, 230), r, border_radius=10)
            pygame.draw.rect(panel, (80, 120, 255, 150), r, 2, border_radius=10)
            s = self._font_value.render(key_label, True, (255, 255, 255))
            panel.blit(s, (r.centerx - s.get_width() // 2, r.centery - s.get_height() // 2))
            self._ui_rects.append((r, "numpad_key", key_label))

    action_y = gy + 4 * (btn_size + pad // 2)
    action_colors = [(80, 60, 60, 230), (30, 140, 70, 230), (140, 40, 40, 230)]
    for col_i, (act_label, color) in enumerate(zip(action_row, action_colors)):
        r = pygame.Rect(
            gx + col_i * (btn_size + pad // 2),
            action_y,
            btn_size, btn_size
        )
        pygame.draw.rect(panel, color, r, border_radius=10)
        s = self._font_value.render(act_label, True, (255, 255, 255))
        panel.blit(s, (r.centerx - s.get_width() // 2, r.centery - s.get_height() // 2))
        actions = {"←": "numpad_back", "✓": "numpad_confirm", "✗": "numpad_cancel"}
        self._ui_rects.append((r, actions[act_label], None))
```

- [ ] **Step 3: Call _draw_numpad from _draw_panel**

In `_draw_panel`, just before the `if self._restart_prompt:` block, add:

```python
if self._numpad_active:
    self._draw_numpad(panel)
```

- [ ] **Step 4: Wire numpad actions in _dispatch**

Replace the `"edit_numeric_string": pass` stub with:

```python
elif action == "edit_numeric_string":
    path = data
    merged: dict = {}
    _deep_update(merged, self._live_settings)
    _deep_update(merged, self._pending_changes)
    self._numpad_field_path = path
    self._numpad_buffer = str(_get_nested(merged, path, ""))
    self._numpad_active = True
```

Add the numpad action handlers:

```python
elif action == "numpad_key":
    key_label = data
    self._numpad_buffer += key_label

elif action == "numpad_back":
    self._numpad_buffer = self._numpad_buffer[:-1]

elif action == "numpad_confirm":
    if self._numpad_field_path:
        _set_nested(self._pending_changes, self._numpad_field_path, self._numpad_buffer)
    self._numpad_active = False
    self._numpad_field_path = None
    self._numpad_buffer = ""

elif action == "numpad_cancel":
    self._numpad_active = False
    self._numpad_field_path = None
    self._numpad_buffer = ""
```

- [ ] **Step 5: Block other taps when numpad is active**

In `_handle_panel_tap`, wrap the existing loop so taps outside numpad don't dispatch settings actions while the numpad is open. The numpad draws its own rects into `_ui_rects`, so this already works naturally (numpad rects are drawn last and checked first). No change needed — verify with a quick test.

- [ ] **Step 6: Ruff check + commit**

```bash
env/bin/python -m ruff check FrameGUI/photoframe_view_pygame.py
git add FrameGUI/photoframe_view_pygame.py
git commit -m "feat: pygame numpad overlay for numeric_string settings fields"
```

---

## Task 7: Pygame Panel — OSK for String / Password Fields

**Files:**
- Modify: `FrameGUI/photoframe_view_pygame.py`

This task adds system OSK launch (with fallback QWERTY grid) for `str` and `password` fields.

- [ ] **Step 1: Add OSK state variables to __init__**

After the numpad state block, add:

```python
# OSK state
self._osk_active: bool = False
self._osk_field_path: "str | None" = None
self._osk_buffer: str = ""
self._osk_masked: bool = False
self._osk_proc: "subprocess.Popen | None" = None
self._osk_use_subprocess: bool = False
self._osk_shift: bool = False
```

Also add the import at the top of the file if not already present:

```python
import shutil
import subprocess
```

- [ ] **Step 2: Add _find_osk_binary helper**

```python
@staticmethod
def _find_osk_binary() -> "str | None":
    for name in ("matchbox-keyboard", "onboard", "wvkbd-mobintl", "wvkbd"):
        path = shutil.which(name)
        if path:
            return path
    return None
```

- [ ] **Step 3: Add _open_osk and _close_osk methods**

```python
def _open_osk(self, path: str, masked: bool, current_value: str) -> None:
    self._osk_field_path = path
    self._osk_buffer = current_value
    self._osk_masked = masked
    self._osk_shift = False

    osk_bin = self._find_osk_binary()
    if osk_bin:
        try:
            self._osk_proc = subprocess.Popen(
                [osk_bin],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._osk_use_subprocess = True
        except Exception as e:
            logging.warning("OSK launch failed (%s): %s — using fallback", osk_bin, e)
            self._osk_use_subprocess = False
    else:
        self._osk_use_subprocess = False

    self._osk_active = True


def _close_osk(self) -> None:
    if self._osk_proc is not None:
        try:
            self._osk_proc.terminate()
        except Exception:
            pass
        self._osk_proc = None
    self._osk_active = False
    self._osk_use_subprocess = False
    self._osk_field_path = None
    self._osk_buffer = ""
    self._osk_masked = False
    self._osk_shift = False
```

- [ ] **Step 4: Add _draw_osk_overlay method (fallback QWERTY grid)**

```python
_QWERTY_ROWS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]

def _draw_osk_overlay(self, panel: "pygame.Surface") -> None:
    W, H = self.width, self.height
    pad = 10

    dim = pygame.Surface((W, H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 200))
    panel.blit(dim, (0, 0))

    # Input buffer display
    display = ("*" * len(self._osk_buffer)) if self._osk_masked else self._osk_buffer
    field_label = (self._osk_field_path or "").split(".")[-1].replace("_", " ").title()
    buf_text = f"{field_label}: {display or '_'}"
    buf_surf = self._font_value.render(buf_text[:60], True, (220, 230, 255))
    panel.blit(buf_surf, ((W - buf_surf.get_width()) // 2, H // 2 - 220))

    if self._osk_use_subprocess:
        hint = self._font_label.render(
            "Type on the on-screen keyboard  •  Enter = confirm  •  Esc = cancel",
            True, (160, 180, 220)
        )
        panel.blit(hint, ((W - hint.get_width()) // 2, H // 2 - 160))
        # Still draw Confirm / Cancel buttons for mouse users
        btn_w = 160
        for bx, label, act in [
            ((W // 2 - btn_w - 10), "Confirm", "osk_confirm"),
            ((W // 2 + 10),          "Cancel",  "osk_cancel"),
        ]:
            r = pygame.Rect(bx, H // 2 - 100, btn_w, 52)
            col = (30, 140, 70, 230) if act == "osk_confirm" else (140, 40, 40, 230)
            pygame.draw.rect(panel, col, r, border_radius=8)
            s = self._font_label.render(label, True, (255, 255, 255))
            panel.blit(s, (r.centerx - s.get_width() // 2, r.centery - s.get_height() // 2))
            self._ui_rects.append((r, act, None))
        return

    # Fallback: draw QWERTY grid
    key_w = max(52, W // 12)
    key_h = max(52, H // 14)
    start_y = H // 2 - 100

    for row_i, row in enumerate(self._QWERTY_ROWS):
        chars = list(row.lower() if not self._osk_shift else row)
        row_x = (W - (len(chars) * (key_w + 4))) // 2
        for col_i, ch in enumerate(chars):
            r = pygame.Rect(row_x + col_i * (key_w + 4), start_y + row_i * (key_h + 6), key_w, key_h)
            pygame.draw.rect(panel, (40, 60, 150, 230), r, border_radius=7)
            s = self._font_label.render(ch, True, (255, 255, 255))
            panel.blit(s, (r.centerx - s.get_width() // 2, r.centery - s.get_height() // 2))
            self._ui_rects.append((r, "osk_char", ch))

    # Bottom row: Shift, Space, Backspace, Confirm, Cancel
    bottom_y = start_y + 3 * (key_h + 6)
    specials = [
        ("Shift", key_w * 2, "osk_shift"),
        ("Space", key_w * 4, "osk_space"),
        ("←",    key_w,     "osk_back"),
        ("✓",    key_w,     "osk_confirm"),
        ("✗",    key_w,     "osk_cancel"),
    ]
    bx = (W - sum(w + 6 for _, w, _ in specials)) // 2
    for label, btn_w_sp, act in specials:
        r = pygame.Rect(bx, bottom_y, btn_w_sp, key_h)
        colors = {
            "osk_confirm": (30, 140, 70, 230),
            "osk_cancel":  (140, 40, 40, 230),
            "osk_shift":   (80, 100, 180, 230) if self._osk_shift else (40, 60, 130, 230),
        }
        pygame.draw.rect(panel, colors.get(act, (50, 70, 160, 230)), r, border_radius=7)
        s = self._font_label.render(label, True, (255, 255, 255))
        panel.blit(s, (r.centerx - s.get_width() // 2, r.centery - s.get_height() // 2))
        self._ui_rects.append((r, act, None))
        bx += btn_w_sp + 6
```

- [ ] **Step 5: Call _draw_osk_overlay from _draw_panel**

After the numpad check and before the restart prompt check in `_draw_panel`:

```python
if self._osk_active:
    self._draw_osk_overlay(panel)
```

- [ ] **Step 6: Wire OSK keyboard events in process_events**

In `process_events`, inside the `pygame.KEYDOWN` block (after the Escape/Q handling), add:

```python
if self._osk_active:
    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
        self._dispatch("osk_confirm", None)
    elif event.key == pygame.K_ESCAPE:
        self._dispatch("osk_cancel", None)
    elif event.key == pygame.K_BACKSPACE:
        self._dispatch("osk_back", None)
    elif event.unicode and event.unicode.isprintable():
        self._dispatch("osk_char", event.unicode)
    continue  # swallow all other keys while OSK is open
```

Place this block before the existing Escape/Q key handling so it takes priority.

- [ ] **Step 7: Wire OSK dispatch actions**

Replace the `"edit_str": pass` and `"edit_password": pass` stubs in `_dispatch`:

```python
elif action in ("edit_str", "edit_password"):
    path = data
    merged: dict = {}
    _deep_update(merged, self._live_settings)
    _deep_update(merged, self._pending_changes)
    current_val = str(_get_nested(merged, path, ""))
    self._open_osk(path, masked=(action == "edit_password"), current_value=current_val)
```

Add OSK action handlers:

```python
elif action == "osk_char":
    ch = data
    self._osk_buffer += ch

elif action == "osk_back":
    self._osk_buffer = self._osk_buffer[:-1]

elif action == "osk_space":
    self._osk_buffer += " "

elif action == "osk_shift":
    self._osk_shift = not self._osk_shift

elif action == "osk_confirm":
    if self._osk_field_path:
        _set_nested(self._pending_changes, self._osk_field_path, self._osk_buffer)
    self._close_osk()

elif action == "osk_cancel":
    self._close_osk()
```

- [ ] **Step 8: Clean up OSK subprocess on panel close**

In `_close_panel`, add:

```python
if self._osk_active:
    self._close_osk()
if self._numpad_active:
    self._numpad_active = False
    self._numpad_field_path = None
    self._numpad_buffer = ""
```

- [ ] **Step 9: Ruff check + commit**

```bash
env/bin/python -m ruff check FrameGUI/photoframe_view_pygame.py
git add FrameGUI/photoframe_view_pygame.py
git commit -m "feat: pygame OSK overlay (system + fallback QWERTY) for string settings"
```

---

## Task 8: React Web UI — Deep-Nesting Fix + Schema Widgets + Restart Modal

**Files:**
- Modify: `frontend/src/pages/SettingsView.jsx`
- Modify: `frontend/src/components/settings/SettingsSection.jsx`
- Modify: `frontend/src/components/settings/SettingField.jsx`

- [ ] **Step 1: Update SettingsView.jsx**

Replace the entire file content with:

```jsx
import React, { useCallback, useEffect, useRef, useState } from "react";
import SettingsSection from "../components/settings/SettingsSection";

const HIDDEN_KEYS = new Set(["about"]);

function setNestedValue(obj, path, value) {
  const [head, ...rest] = path.split(".");
  if (rest.length === 0) return { ...obj, [head]: value };
  return { ...obj, [head]: setNestedValue(obj[head] ?? {}, rest.join("."), value) };
}

function collectChangedPaths(original, updated, prefix = "") {
  const paths = new Set();
  for (const key of Object.keys(updated)) {
    const path = prefix ? `${prefix}.${key}` : key;
    const orig = original?.[key];
    const upd = updated[key];
    if (upd !== null && typeof upd === "object" && !Array.isArray(upd)) {
      const sub = collectChangedPaths(orig, upd, path);
      sub.forEach((p) => paths.add(p));
    } else if (orig !== upd) {
      paths.add(path);
    }
  }
  return paths;
}

export default function SettingsView() {
  const [settings, setSettings] = useState(null);
  const [schema, setSchema] = useState({});
  const [activeTab, setActiveTab] = useState(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [showRestartModal, setShowRestartModal] = useState(false);
  const originalRef = useRef(null);
  const pendingRef = useRef(null);
  const sseRef = useRef(null);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch("/api/settings", { credentials: "include" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSettings(data);
      originalRef.current = data;
      if (!activeTab) setActiveTab(Object.keys(data).find((k) => !HIDDEN_KEYS.has(k)));
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }, [activeTab]);

  useEffect(() => { fetchSettings(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch("/api/settings/schema")
      .then((r) => r.json())
      .then(setSchema)
      .catch(() => {});
  }, []);

  useEffect(() => {
    const es = new EventSource("/api/settings/events", { withCredentials: true });
    sseRef.current = es;
    es.onmessage = (e) => { if (e.data === "settings_updated") fetchSettings(); };
    return () => es.close();
  }, [fetchSettings]);

  const handleChange = useCallback((path, value) => {
    setSettings((prev) => {
      const next = setNestedValue(prev, path, value);
      pendingRef.current = next;
      return next;
    });
    setStatus("Unsaved changes");
  }, []);

  const handleSave = async () => {
    if (!pendingRef.current) return;
    setSaving(true);
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pendingRef.current),
      });
      if (!res.ok) throw new Error(await res.text());

      // Check for restart-required paths
      const changed = collectChangedPaths(originalRef.current, pendingRef.current);
      const restartPaths = gatherRestartPaths(schema);
      const needsRestart = [...changed].some((p) => restartPaths.has(p));

      originalRef.current = pendingRef.current;
      pendingRef.current = null;
      setStatus("Saved");
      setTimeout(() => setStatus(""), 2000);
      if (needsRestart) setShowRestartModal(true);
    } catch (e) {
      setStatus(`Save failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRestart = async () => {
    setShowRestartModal(false);
    try {
      await fetch("/api/maintenance/restart", { method: "POST", credentials: "include" });
      setStatus("Restarting…");
    } catch (e) {
      setStatus(`Restart failed: ${e.message}`);
    }
  };

  if (!settings) {
    return <div style={{ padding: 40, color: "var(--text-secondary)" }}>Loading settings…</div>;
  }

  const tabs = Object.keys(settings).filter((k) => !HIDDEN_KEYS.has(k));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 24, gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "1.4em", fontWeight: 600 }}>Settings</h1>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {status && (
            <span style={{
              color: status.startsWith("Error") || status.startsWith("Save failed")
                ? "var(--danger)" : "var(--accent)",
              fontSize: "0.85em"
            }}>
              {status}
            </span>
          )}
          <button className="primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {tabs.map((key) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: "6px 16px", borderRadius: 20,
              border: activeTab === key ? "1px solid var(--accent)" : "1px solid var(--glass-border)",
              background: activeTab === key ? "rgba(90,150,255,0.2)" : "var(--glass-bg)",
              color: activeTab === key ? "var(--accent-hover)" : "var(--text-secondary)",
              fontWeight: activeTab === key ? 600 : 400,
              textTransform: "capitalize",
            }}
          >
            {key.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {activeTab && settings[activeTab] && (
        <div className="glass" style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          {typeof settings[activeTab] === "object" && !Array.isArray(settings[activeTab]) ? (
            <SettingsSection
              data={settings[activeTab]}
              pathPrefix={activeTab}
              schema={schema[activeTab] ?? {}}
              onChange={handleChange}
            />
          ) : (
            <p style={{ color: "var(--text-secondary)" }}>{JSON.stringify(settings[activeTab])}</p>
          )}
        </div>
      )}

      {showRestartModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
        }}>
          <div className="glass" style={{ padding: 32, maxWidth: 420, borderRadius: 16, textAlign: "center" }}>
            <h2 style={{ marginBottom: 12 }}>Restart Required</h2>
            <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
              Some changes require a restart to take effect.
            </p>
            <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
              <button className="primary" onClick={handleRestart}>Restart Now</button>
              <button onClick={() => setShowRestartModal(false)}>Later</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function gatherRestartPaths(schema, prefix = "") {
  const paths = new Set();
  for (const [key, val] of Object.entries(schema)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (val && typeof val === "object") {
      if ("type" in val) {
        if (val.restart_required) paths.add(path);
      } else {
        const sub = gatherRestartPaths(val, path);
        sub.forEach((p) => paths.add(p));
      }
    }
  }
  return paths;
}
```

- [ ] **Step 2: Update SettingsSection.jsx**

Replace the file content with:

```jsx
import React, { useState } from "react";
import SettingField from "./SettingField";

export default function SettingsSection({ data, pathPrefix, schema, onChange, depth = 0 }) {
  const [collapsed, setCollapsed] = useState({});
  const toggle = (key) => setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {Object.entries(data).map(([key, value]) => {
        const fieldPath = pathPrefix ? `${pathPrefix}.${key}` : key;
        const fieldSchema = schema?.[key] ?? null;

        if (value !== null && typeof value === "object" && !Array.isArray(value)
            && !(fieldSchema && "type" in fieldSchema)) {
          const isCollapsed = collapsed[key] ?? false;
          const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
          return (
            <div key={key} style={{
              border: "1px solid var(--glass-border)", borderRadius: 10,
              marginTop: 6, overflow: "hidden", paddingLeft: depth * 8,
            }}>
              <button onClick={() => toggle(key)} style={{
                width: "100%", textAlign: "left", padding: "8px 14px",
                background: "rgba(255,255,255,0.04)", border: "none", borderRadius: 0,
                display: "flex", justifyContent: "space-between",
              }}>
                <span style={{ fontWeight: 500 }}>{label}</span>
                <span>{isCollapsed ? "▶" : "▼"}</span>
              </button>
              {!isCollapsed && (
                <div style={{ padding: "8px 14px" }}>
                  <SettingsSection
                    data={value}
                    pathPrefix={fieldPath}
                    schema={fieldSchema ?? {}}
                    onChange={onChange}
                    depth={depth + 1}
                  />
                </div>
              )}
            </div>
          );
        }

        return (
          <SettingField
            key={key}
            fieldKey={key}
            fieldPath={fieldPath}
            value={value}
            schema={fieldSchema}
            onChange={onChange}
            depth={depth}
          />
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Update SettingField.jsx**

Replace the file content with:

```jsx
import React, { useState } from "react";

export default function SettingField({ fieldKey, fieldPath, value, schema, onChange, depth = 0 }) {
  const [showPassword, setShowPassword] = useState(false);
  const ftype = schema?.type ?? null;

  const rawLabel = (schema?.label ?? fieldKey)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  const label = schema?.restart_required ? `${rawLabel} ⚠` : rawLabel;

  const labelEl = (
    <span style={{
      color: "var(--text-secondary)", fontSize: "0.85em", minWidth: 180,
      display: "flex", alignItems: "center", gap: 4,
    }}>
      {label}
    </span>
  );

  const row = (input) => (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "6px 0", paddingLeft: depth * 16,
    }}>
      {labelEl}
      <div style={{ flex: 1 }}>{input}</div>
    </div>
  );

  // password
  if (ftype === "password") {
    return row(
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <input
          type={showPassword ? "text" : "password"}
          value={value ?? ""}
          onChange={(e) => onChange(fieldPath, e.target.value)}
          style={{ flex: 1 }}
        />
        <button onClick={() => setShowPassword((p) => !p)} style={{ padding: "2px 8px", fontSize: "0.8em" }}>
          {showPassword ? "Hide" : "Show"}
        </button>
      </div>
    );
  }

  // enum or color (named choices)
  if (ftype === "enum" || ftype === "color") {
    const choices = schema?.choices ?? [];
    return row(
      <select value={value ?? ""} onChange={(e) => onChange(fieldPath, e.target.value)}>
        {choices.map((c) => <option key={c} value={c}>{c}</option>)}
        {!choices.includes(String(value)) && <option value={value}>{value}</option>}
      </select>
    );
  }

  // numeric_string
  if (ftype === "numeric_string") {
    return row(
      <input
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(fieldPath, e.target.value)}
        style={{ maxWidth: 160 }}
      />
    );
  }

  // bool
  if (typeof value === "boolean" || ftype === "bool") {
    return row(
      <label className="toggle">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(fieldPath, e.target.checked)}
        />
        <span className="toggle-track" />
      </label>
    );
  }

  // int / float
  if (typeof value === "number" || ftype === "int" || ftype === "float") {
    const isFloat = ftype === "float" || (!Number.isInteger(value) && ftype !== "int");
    const step = schema?.step ?? (isFloat ? 0.01 : 1);
    const min = schema?.min;
    const max = schema?.max;
    return row(
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {min !== undefined && max !== undefined && (
          <input
            type="range"
            min={min} max={max} step={step}
            value={value ?? 0}
            onChange={(e) => {
              const v = isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10);
              if (!isNaN(v)) onChange(fieldPath, v);
            }}
            style={{ flex: 1 }}
          />
        )}
        <input
          type="number"
          value={value ?? 0}
          step={step}
          min={min} max={max}
          onChange={(e) => {
            const v = isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10);
            if (!isNaN(v)) onChange(fieldPath, v);
          }}
          style={{ maxWidth: 100 }}
        />
      </div>
    );
  }

  // string
  if (typeof value === "string") {
    return row(
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(fieldPath, e.target.value)}
      />
    );
  }

  // array (unchanged from original)
  if (Array.isArray(value)) {
    const isSimple = value.every((v) => typeof v !== "object");
    if (isSimple) {
      return row(
        <input
          type="text"
          value={value.join(", ")}
          onChange={(e) =>
            onChange(fieldPath, e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
              .map((s) => (isNaN(Number(s)) ? s : Number(s))))
          }
        />
      );
    }
    return row(
      <textarea rows={3}
        value={JSON.stringify(value, null, 2)}
        onChange={(e) => { try { onChange(fieldPath, JSON.parse(e.target.value)); } catch {} }}
        style={{ fontFamily: "monospace", fontSize: "0.8em" }}
      />
    );
  }

  return null;
}
```

- [ ] **Step 4: Lint and build**

```bash
cd frontend && npm run lint
```
Fix any lint errors. Then:

```bash
npm run build
```
Expected: build succeeds with no errors.

- [ ] **Step 5: Manual test in browser**

```bash
env/bin/python app.py --headless &
sleep 3
open http://localhost:5002
```

Verify:
1. Settings page loads and shows all tabs.
2. Editing `ui.margins.left` (a 3-deep field) saves correctly — check that sibling margin fields (`right`, `bottom`) are not zeroed out.
3. `backend_configs.supersecretkey` renders as a password field with show/hide.
4. `open_meteo.temperature_unit` renders as a dropdown with celsius/fahrenheit.
5. `playback.delay_between_images` renders a range slider alongside the number input.
6. Changing `server_port` and saving shows the restart modal.

```bash
kill %1
```

- [ ] **Step 6: Full test suite**

```bash
cd .. && env/bin/python -m pytest -x -q
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/SettingsView.jsx \
        frontend/src/components/settings/SettingsSection.jsx \
        frontend/src/components/settings/SettingField.jsx
git commit -m "feat: React settings UI deep-nesting fix, schema-driven widgets, restart modal"
```

---

## Self-Review Notes

- Task 1 adds schema + helpers; all subsequent tasks depend on it — do not reorder.
- Task 2 wires the `/api/settings/schema` route; Task 8 fetches it — both must be deployed together.
- Task 5 (pygame schema-driven fields) must precede Tasks 6 and 7 (which implement the overlays those fields open).
- `screen.orientation` is stored as an `int` (0/90/180/270) in `get_default_settings()` — the schema defines it as `int` with `step=90`, consistent with the existing `_FIELD_CONFIG` entry.
- `screen.schedules` is a complex array intentionally absent from the schema — it is managed only via the web UI's raw textarea fallback.
- The `color` type uses named string choices (yellow, white, etc.) — rendered as `<select>` in React, not `<input type="color">` (which requires hex).
