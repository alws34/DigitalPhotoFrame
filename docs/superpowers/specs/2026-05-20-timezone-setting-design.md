# Timezone Setting — Design Spec
Date: 2026-05-20

## Goal

Allow user to select system timezone from a dropdown in the Web UI (System tab) and PySide6 settings dialog (System tab). Change takes effect immediately — no restart required.

## Context

- Settings stored in SQLite DB at `$PF_DB_PATH` via `config_store._cs_save()`.
- `photoframe_settings.example.json` is a one-time seed for DB migration only.
- Overlay clock (`FrameServer/overlay.py`) uses `time.strftime()` — respects `TZ` env var + `time.tzset()`.
- Container already mounts `/etc/localtime:ro` as default. This setting overrides it at the process level.
- Target platform: Raspberry Pi / Linux. `time.tzset()` is a POSIX call — works on all targets.

## Architecture

### 1. Data Layer — `Utilities/config_store.py`

**Defaults** (`get_default_settings()` → `system` group):
```python
"timezone": "",
```
Empty string means "use container/host default" (i.e., don't override `TZ`).

**Schema** (`SETTINGS_SCHEMA` → `system` group):
```python
"timezone": {
    "type":             "str",
    "label":            "Timezone",
    "choices":          sorted(zoneinfo.available_timezones()),
    "restart_required": False,
},
```
`choices` drives dropdown rendering in both UIs automatically — no UI code changes needed.

### 2. Apply Logic

Two call sites:

**Startup** — `app.py` (after settings load, before frame loop starts):
```python
tz = settings.get("system", {}).get("timezone", "")
if tz:
    os.environ["TZ"] = tz
    time.tzset()
```

**On settings change** — settings save path in `WebAPI/routes/settings.py` (POST handler) and PySide6 dialog save handler:
```python
tz = new_settings.get("system", {}).get("timezone", "")
if tz:
    os.environ["TZ"] = tz
    time.tzset()
else:
    os.environ.pop("TZ", None)
    time.tzset()
```

The overlay clock re-calls `time.strftime()` each frame — picks up the new TZ immediately.

### 3. Example JSON (`photoframe_settings.example.json`)

Add to `system` section for documentation / fresh-install seed:
```json
"timezone": ""
```

### 4. UI Rendering

Both UIs already handle `choices` in schema:
- **React** `SettingsSection.jsx` — renders `<select>` when `choices` present.
- **PySide6** `_make_input_widget()` in `dialog.py` — renders `QComboBox` when `choices` present.

No UI code changes required. Setting appears automatically under System tab in both UIs.

## Data Flow

```
User picks TZ in dropdown
  → POST /api/settings (Web) or dialog save (PySide6)
  → config_store._cs_save() → SQLite DB
  → save handler calls os.environ["TZ"] = tz; time.tzset()
  → overlay.py next frame: time.strftime() uses new TZ
  → clock/date display updated immediately
```

## Edge Cases

- **Empty string selected**: pop `TZ` from env + `tzset()` → falls back to `/etc/localtime` mount.
- **Invalid TZ name**: `zoneinfo.available_timezones()` is the source of truth for `choices` — only valid names appear.
- **Windows**: `time.tzset()` is a no-op; env var change still affects Python's `datetime` in some cases. Acceptable — Pi is primary target.

## What Changes

| File | Change |
|------|--------|
| `Utilities/config_store.py` | Add `timezone: ""` to defaults; add schema entry with `choices` |
| `app.py` | Apply TZ at startup |
| `WebAPI/routes/settings.py` | Apply TZ on POST save |
| `FrameGUI/SettingsFrom/dialog.py` | Apply TZ on dialog save |
| `photoframe_settings.example.json` | Add `"timezone": ""` to system section |

## What Does NOT Change

- UI tab structure — System tab already exists in both UIs.
- Widget rendering code — `choices` key already handled.
- DB schema — settings stored as JSON blob, new key added to defaults.
- Docker compose — `/etc/localtime` mount stays as the out-of-the-box default.
