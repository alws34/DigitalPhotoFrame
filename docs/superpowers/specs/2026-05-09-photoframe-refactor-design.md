# DigitalPhotoFrame — Refactor Design Spec
**Date:** 2026-05-09  
**Status:** Approved  
**Scope:** 4 sequenced sub-projects

---

## Overview

Full modernization of DigitalPhotoFrame: config moved to SQLite, hot reload via watchdog sentinel, Docker fixed for Pi Bookworm Wayland, both UIs (web + Python) dynamically render all settings from DB, glass/blur web UI redesign, code quality cleanup.

All existing features preserved: headless mode, pygame mode, Qt mode, MJPEG stream, MQTT, weather, transitions, autoupdate.

---

## Sub-Project Order

| # | Name | Dependency |
|---|------|------------|
| 1 | Config DB + Hot Reload | None — do first |
| 2 | Docker + Pi Display Fix | Stable config layer |
| 3 | Dynamic Settings UI + Web Redesign | Config DB must exist |
| 4 | Code Quality Cleanup | Parallel to 2-3 |

---

## Sub-Project 1 — Config DB + Hot Reload

### Data Model

Table added to existing `WebAPI/database.db`:

```sql
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,  -- always 'main'
    value      TEXT NOT NULL,     -- full settings JSON blob
    updated_at REAL               -- unix timestamp
);
```

Single row, single blob. Nested JSON structure preserved — no schema churn when settings keys change.

### Config Store (`Utilities/config_store.py`)

Replaces `Settings.py` entirely. Public API:

```python
def load_settings() -> dict
def save_settings(data: dict) -> None          # writes DB + touches sentinel
def get_default_settings() -> dict             # canonical defaults (moved from SettingsModel.ensure_defaults)
```

On first `load_settings()`: if `app_settings` empty AND `photoframe_settings.json` exists → migrate JSON to DB → log. After migration, JSON file ignored (not deleted).

Sentinel file: `/tmp/pf_settings.sentinel` — touched on every `save_settings()` call.

### Hot Reload Event Bus (`Utilities/config_events.py`)

```python
def on_settings_changed(callback: Callable[[dict], None]) -> None  # register subscriber
def notify_settings_changed(new_data: dict) -> None                # fire all callbacks
```

`watchdog` `FileSystemEventHandler` watches `/tmp/pf_settings.sentinel`. On modify event: reads fresh settings from DB → calls `notify_settings_changed(data)`.

Subscribers registered at startup:
- `PhotoFrameServer` — reloads playback, effects, overlay params
- `overlay.py` — reloads UI/font/weather display settings
- `MqttBridge` — reloads MQTT connection params (reconnects if host/port changed)
- `AutoUpdater` — reloads autoupdate schedule

Thread safety: callbacks fire on watchdog thread. Subscribers must be thread-safe (use locks or Qt signals as appropriate).

### Migration

`WebAPI/database.py` `init_db()` creates `app_settings` table.  
`WebAPI/database.py` `migrate_settings_if_needed(json_path)` runs once at startup.

### Deleted

- `Settings.py` (`SettingsHandler` class) — all callers updated to use `config_store`
- `FrameGUI/SettingsFrom/model.py` `ensure_defaults()` — moved to `config_store.get_default_settings()`

---

## Sub-Project 2 — Docker + Pi Display Fix

### Problem

`docker-compose.pi.yml` uses shell variable expansion (`${XDG_RUNTIME_DIR:-/run/user/1000}`) for volume mount paths. Docker Compose resolves these at parse time on host but the socket path inside container doesn't match. SDL2 fails to find Wayland → falls back to offscreen → black screen.

### Fix

`docker-compose.pi.yml` hardcodes paths, adds group membership and SDL driver hint:

```yaml
services:
  photoframe:
    group_add:
      - video
      - render
    devices:
      - /dev/dri:/dev/dri
      - /dev/input:/dev/input
    volumes:
      - /app/Images:/app/Images
      - /data:/data
      - /sys/class/backlight:/sys/class/backlight
      - /run/user/1000:/run/user/1000
    environment:
      - WAYLAND_DISPLAY=wayland-1
      - XDG_RUNTIME_DIR=/run/user/1000
      - SDL_VIDEODRIVER=wayland
```

Entrypoint fallback order: wayland → kmsdrm → fail with clear error message.

### Dockerfile Changes

- Add `libwayland-client0`, `libwayland-egl1` to apt deps
- Remove healthcheck dependency on `photoframe_settings.json` (use HTTP ping only)
- Healthcheck hits `http://localhost:{port}/` — no file read

### DB Volume

Settings DB lives at `/data/photoframe.db` inside container. Compose mounts `/data` as named volume. DB path env var: `PF_DB_PATH=/data/photoframe.db`.

---

## Sub-Project 3 — Dynamic Settings UI + Web Redesign

### Schema Contract

`GET /api/settings` returns full settings blob (same structure as today).  
`POST /api/settings` accepts full blob, saves to DB, triggers hot reload.  
No change to route shape — only backing store changes (DB instead of JSON file).

Both UIs treat the JSON as the source of truth for what to render. No hardcoded field lists in either UI.

### Web UI — React (`frontend/`)

**Design:** Glass/blur aesthetic.
- Background: full-screen blurred photo or dark gradient
- Panels: `backdrop-filter: blur(20px)`, `background: rgba(255,255,255,0.08)`, `border: 1px solid rgba(255,255,255,0.15)`, `border-radius: 16px`
- Text: white / off-white
- Accent: subtle blue-white glow on focus/active
- Font: system-ui or Inter

**`SettingsView.jsx` — dynamic renderer:**
1. `GET /api/settings` on mount
2. Top-level keys → tabs (e.g. `playback`, `ui`, `mqtt`, `screen`)
3. Each section: iterate key-value pairs → render input by type:
   - `boolean` → toggle switch
   - `integer` → number input with step=1
   - `float` → number input with step=0.01
   - `string` → text input
   - `object` → nested collapsible accordion (recursive)
   - `array` → list editor (add/remove rows)
4. Save: POST full merged blob
5. SSE subscription: `GET /api/settings/events` — on `settings_updated` event, re-fetch and re-render changed fields (no full page reload)

**Pages kept:** Login, Gallery, Stream, Settings, Dashboard layout  
**Pages removed:** Old static templates in `WebAPI/templates/` — fully replaced by React build

### Python GUI — Qt (`FrameGUI/`)

**`SettingsFrom/dialog.py` — dynamic renderer:**
1. Remove hardcoded tabs (Stats, WiFi, Screen, Notifications, Config, About)
2. On open: load settings from `config_store.load_settings()`
3. Top-level keys → `QTabWidget` tabs (auto-generated)
4. Each tab: `QFormLayout` — iterate key-value → widget by type:
   - `boolean` → `QCheckBox`
   - `int/float` → `QDoubleSpinBox`
   - `string` → `QLineEdit`
   - `object` → nested `QGroupBox` (recursive)
5. Save: calls `config_store.save_settings()` → triggers hot reload automatically
6. Special overlay: Stats/system widgets kept as a pinned "System" tab (CPU, RAM, temp graphs), not from settings schema

**`SettingsFrom/model.py`:** Deleted. No longer needed.  
**`SettingsFrom/viewmodel.py`:** Stripped to stats/wifi/notifications only. Settings data comes from `config_store` directly.

### SSE Endpoint

```python
# WebAPI/routes/settings.py
@settings_bp.route("/events")
def settings_events():
    # Server-Sent Events stream
    # Yields "data: settings_updated\n\n" when sentinel file changes
```

---

## Sub-Project 4 — Code Quality

### Deletions

| File/Symbol | Reason |
|-------------|--------|
| `Settings.py` | Replaced by `config_store.py` |
| `iFrame.py` | Dead code, unused |
| `FrameGUI/SettingsFrom/model.py` | Absorbed into `config_store` |
| `WebAPI/templates/` | Replaced by React build |
| `WebAPI/static/scripts.js`, `styles.css`, `signup.js` | Replaced by React build |
| `users.json` | Already in DB — delete after confirming migration |
| `foss_env/` | Second venv, not referenced anywhere |

### Module Boundaries (enforced)

- `FrameServer/` → imports from `Utilities/` only (incl. `config_store`, `config_events`)
- `FrameGUI/` → imports from `FrameServer/`, `Utilities/` only (incl. `config_store`, `config_events`)
- `WebAPI/` → imports from `Utilities/`, `database` only (incl. `config_store`, `config_events`)
- No cross-imports between `FrameServer` ↔ `WebAPI`, `FrameGUI` ↔ `WebAPI`

### File Size Targets

- `app.py`: three `_run_*` functions extracted to `app_modes.py` — `app.py` becomes <50 lines (arg parse + dispatch only)
- `FrameGUI/SettingsFrom/dialog.py`: hardcoded tab builders deleted, dynamic renderer ~150 lines
- `WebAPI/API.py`: route registration only, business logic in route files

### Naming

- `PhotoFrameServer` stays (well-known entry point)
- `Backend` → rename to `APIServer` (clearer)
- `MqttBridge` stays

---

## Cross-Cutting Concerns

### DB Path

Single env var `PF_DB_PATH` controls DB location.  
Default: `WebAPI/database.db` (existing, non-Docker).  
Docker: `/data/photoframe.db` (mounted volume).  
`database.py` reads `os.environ.get("PF_DB_PATH", default)`.

### Settings Defaults

`config_store.get_default_settings()` returns the canonical defaults dict (merged from `photoframe_settings.example.json` shape). On load, deep-merge defaults ← saved settings so missing keys always have values.

### Auth

No change. Existing JWT/session auth on all `/api/` routes preserved.

### Tests

- Add `Tests/test_config_store.py`: load/save/migrate/hot-reload unit tests
- Existing tests kept and updated for renamed symbols

---

## Non-Goals

- No new features beyond what's described
- No database other than SQLite
- No Socket.IO (SSE sufficient for hot reload notification)
- No breaking changes to MJPEG stream, transition effects, or MQTT discovery format
