# Timezone Setting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `system.timezone` dropdown to Web UI and PySide6 System tab; selecting a value applies it immediately via `os.environ["TZ"] + time.tzset()`.

**Architecture:** Single helper `apply_system_timezone(settings)` in `config_store.py` — called at startup in `app.py` and auto-triggered on every settings change via `config_events.on_settings_changed`. Both UIs auto-render the dropdown because `SETTINGS_SCHEMA` uses `type: "enum"` with `choices`.

**Tech Stack:** Python 3.11 `zoneinfo` (stdlib), `time.tzset()` (POSIX), `config_events`, PySide6 `QComboBox`, React `<select>` (already handled by `SettingsSection.jsx`).

---

### Task 1: Add default + schema + helper to `config_store.py`

**Files:**
- Modify: `Utilities/config_store.py`

- [ ] **Step 1: Add `timezone` to `get_default_settings()` → `system` group**

  In `get_default_settings()`, inside the `"system"` dict (around line 115), add:
  ```python
  "system": {
      "image_dir": "Images",
      "image_quality_encoding": 100,
      "log_file_path": "./FrameServer/PhotoFrame.log",
      "sidebar_collapsed": False,
      "timezone": "",
  },
  ```

- [ ] **Step 2: Add `import zoneinfo` to `config_store.py` imports**

  At the top of `Utilities/config_store.py`, add `import zoneinfo` to the existing imports block:
  ```python
  import json
  import os
  import time
  import zoneinfo
  from typing import Any
  ```

- [ ] **Step 4: Add `timezone` to `SETTINGS_SCHEMA` → `system` group**

  In `SETTINGS_SCHEMA`, inside the `"system"` dict (around line 226), add after `"sidebar_collapsed"`:
  ```python
  "system": {
      "image_dir":              {"type": "str",  "label": "Image Directory",    "restart_required": False},
      "image_quality_encoding": {"type": "int",  "label": "Image Quality (%)", "min": 1, "max": 100, "step": 5, "restart_required": False, "no_slider": True},
      "log_file_path":          {"type": "str",  "label": "Log File Path",     "restart_required": False},
      "sidebar_collapsed":      {"type": "bool", "label": "Sidebar Collapsed", "restart_required": False},
      "timezone": {
          "type":             "enum",
          "label":            "Timezone",
          "choices":          [""] + sorted(zoneinfo.available_timezones()),
          "restart_required": False,
      },
  },
  ```
  
  **Note:** `""` as the first choice means "use system/container default" (i.e., `/etc/localtime` mount).

- [ ] **Step 5: Add `apply_system_timezone` helper at the top of the module (after imports)**

  Add this function after the existing imports block (before `_get_db_path`):
  ```python
  def apply_system_timezone(settings: dict) -> None:
      """Apply system.timezone from settings to the process environment."""
      import time
      tz = settings.get("system", {}).get("timezone", "")
      if tz:
          os.environ["TZ"] = tz
      else:
          os.environ.pop("TZ", None)
      time.tzset()
  ```

- [ ] **Step 6: Verify module imports cleanly**

  Run:
  ```bash
  env/bin/python -c "from Utilities.config_store import apply_system_timezone, SETTINGS_SCHEMA, get_default_settings; print('ok')"
  ```
  Expected output: `ok`

---

### Task 2: Write and run tests

**Files:**
- Modify: `Tests/test_settings_schema.py`

- [ ] **Step 1: Write failing tests**

  Append to `Tests/test_settings_schema.py`:
  ```python
  def test_system_timezone_in_defaults():
      cs = _get_cs()
      defaults = cs.get_default_settings()
      assert "timezone" in defaults["system"]
      assert defaults["system"]["timezone"] == ""


  def test_system_timezone_schema_is_enum_with_choices():
      cs = _get_cs()
      desc = cs.get_field_schema("system.timezone")
      assert desc is not None
      assert desc["type"] == "enum"
      assert "" in desc["choices"]
      assert "Asia/Jerusalem" in desc["choices"]
      assert desc["restart_required"] is False


  def test_apply_system_timezone_sets_env():
      import os, time
      cs = _get_cs()
      cs.apply_system_timezone({"system": {"timezone": "Asia/Jerusalem"}})
      assert os.environ.get("TZ") == "Asia/Jerusalem"
      # Reset to avoid polluting other tests
      os.environ.pop("TZ", None)
      time.tzset()


  def test_apply_system_timezone_clears_env_on_empty():
      import os, time
      cs = _get_cs()
      os.environ["TZ"] = "US/Eastern"
      cs.apply_system_timezone({"system": {"timezone": ""}})
      assert "TZ" not in os.environ
  ```

- [ ] **Step 2: Run tests to verify they fail before implementation**

  Run:
  ```bash
  env/bin/python -m pytest Tests/test_settings_schema.py::test_system_timezone_in_defaults Tests/test_settings_schema.py::test_system_timezone_schema_is_enum_with_choices Tests/test_settings_schema.py::test_apply_system_timezone_sets_env Tests/test_settings_schema.py::test_apply_system_timezone_clears_env_on_empty -v
  ```
  Expected: FAIL (attributes/keys missing).

- [ ] **Step 3: Run tests after Task 1 changes — verify they pass**

  Run the same command. Expected: 4 PASSED.

- [ ] **Step 4: Run full test suite to check for regressions**

  Run:
  ```bash
  env/bin/python -m pytest -v
  ```
  Expected: all pre-existing tests still pass.

---

### Task 3: Apply TZ at startup + on settings change in `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Apply TZ at startup and register change handler**

  In `app.py`, inside `main()`, right after `settings = load_settings(...)` and before `config_events.start_watcher()`, add:
  ```python
  from Utilities.config_store import apply_system_timezone
  apply_system_timezone(settings)
  config_events.on_settings_changed(apply_system_timezone)
  ```

  The full relevant block should look like:
  ```python
  from Utilities import config_events
  from Utilities.config_store import load_settings, apply_system_timezone
  settings = load_settings(json_path=_abs_path(args.settings))
  apply_system_timezone(settings)
  config_events.on_settings_changed(apply_system_timezone)
  config_events.start_watcher()
  ```

- [ ] **Step 2: Verify app starts cleanly**

  Run:
  ```bash
  env/bin/python -c "import app; print('import ok')"
  ```
  Expected: `import ok`

---

### Task 4: Update `photoframe_settings.example.json`

**Files:**
- Modify: `photoframe_settings.example.json`

- [ ] **Step 1: Add `timezone` to `system` section**

  Change:
  ```json
  "system": {
    "image_dir": "Images",
    "service_name": "PhotoFrame",
    "sidebar_collapsed": false
  },
  ```
  To:
  ```json
  "system": {
    "image_dir": "Images",
    "service_name": "PhotoFrame",
    "sidebar_collapsed": false,
    "timezone": ""
  },
  ```

---

### Task 5: Smoke test headless + ruff

**Files:** none new

- [ ] **Step 1: Run ruff**

  ```bash
  env/bin/python -m ruff check .
  ```
  Expected: no errors.

- [ ] **Step 2: Smoke test headless startup**

  ```bash
  timeout 8 env/bin/python app.py --headless || true
  ```
  Expected: app starts, logs appear, no `ImportError` or `AttributeError` relating to `apply_system_timezone` or `zoneinfo`.

---

### Task 6: Commit

- [ ] **Step 1: Stage and commit**

  ```bash
  git add Utilities/config_store.py app.py photoframe_settings.example.json Tests/test_settings_schema.py
  git commit -m "feat: add system.timezone dropdown with immediate TZ apply"
  ```
