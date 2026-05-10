# Settings Overhaul Design

**Date:** 2026-05-10
**Branch:** settings-overhaul (to be created from main)
**Approach:** Schema-driven — define each field once, all UIs adapt automatically.

---

## Goals

1. All settings are visible and editable in every UI surface (pygame panel, Qt dialog, React web).
2. All settings hot-reload immediately; restart-required fields prompt the user to restart.
3. Web UI has full, bug-free control with appropriate input widgets per field type.
4. Pygame panel supports string entry via system OSK (or native fallback) and a numpad for numeric strings.

---

## 1. Settings Schema (`Utilities/config_store.py`)

### 1.1 Schema structure

Add `SETTINGS_SCHEMA: dict` alongside `get_default_settings()`. Each leaf is a descriptor dict:

```python
{
    "type":             str,   # "int"|"float"|"bool"|"str"|"numeric_string"|"password"|"enum"|"color"
    "label":            str,   # human-readable label
    "restart_required": bool,  # whether this field needs a service restart to take effect
    # type-specific optional keys:
    "min":     int | float,
    "max":     int | float,
    "step":    int | float,
    "choices": list[str],      # for "enum" type
}
```

Non-leaf nodes (dicts) have no descriptor — they are section containers.

### 1.2 Field types

| Type             | Meaning                                              | Pygame widget        | Qt widget       | React widget                    |
|------------------|------------------------------------------------------|----------------------|-----------------|---------------------------------|
| `int`            | Integer with step/min/max                            | +/- buttons          | QSpinBox        | range slider + number input     |
| `float`          | Float with step/min/max                              | +/- buttons          | QDoubleSpinBox  | range slider + number input     |
| `bool`           | Toggle                                               | ON/OFF button        | QCheckBox       | toggle switch                   |
| `str`            | Free text                                            | system OSK           | QLineEdit       | text input                      |
| `numeric_string` | Text that is always a valid number (coords, etc.)   | numpad overlay       | QLineEdit       | `<input type="number">`         |
| `password`       | Sensitive string, masked                             | system OSK (masked)  | QLineEdit (echo=Password) | password input + show/hide |
| `enum`           | One of a fixed set of string choices                 | cycle < / >          | QComboBox       | `<select>` dropdown             |
| `color`          | Named color string (yellow, white, …)               | cycle through palette | QComboBox      | `<select>` dropdown (named choices) |

### 1.3 Restart-required fields

Derived automatically from the schema. Initial set:

- `backend_configs.server_port`
- `backend_configs.host`
- `backend_configs.stream_width`
- `backend_configs.stream_height`
- `backend_configs.supersecretkey`

A helper `get_restart_required_paths() -> frozenset[str]` returns all dotted paths with `restart_required=True`.

### 1.4 Schema helpers

```python
def get_field_schema(path: str) -> dict | None:
    """Resolve a dotted path like 'ui.margins.left' to its descriptor, or None."""

def get_restart_required_paths() -> frozenset[str]:
    """Return set of all dotted paths where restart_required=True."""
```

### 1.5 API exposure

`GET /api/settings/schema` — returns the full schema JSON. No auth required (schema is not sensitive). React fetches this once on mount and caches it in module scope.

---

## 2. Hot-Reload Coverage

### 2.1 Current pipeline (unchanged)

Save → SQLite write → sentinel touch → watchdog fires → `notify_settings_changed(new_data)`.

### 2.2 Subsystem callbacks

Every subsystem that consumes settings registers with `on_settings_changed()`. Registration happens at startup. Callbacks are lightweight — they pull relevant keys from `new_data` and update in-place.

Subsystems to wire:
- `PhotoFrameServer` — playback timing, effects, UI overlay params
- Overlay/compositor — font sizes, margins, shadow, weather visibility
- Weather adapter — cache TTL, units, coordinates
- MQTT bridge — interval, topic
- Screen scheduler / brightness — on/off hours, brightness
- `AutoUpdater` — schedule hour/minute

### 2.3 Restart prompt trigger

After any save, the saving layer (pygame, Qt, or React) diffs changed keys against `get_restart_required_paths()`. If any match, the UI shows a restart prompt. "Restart now" calls the existing service restart path. "Later" dismisses without action (change is persisted; applies on next start).

---

## 3. Pygame Panel

### 3.1 Field rendering

`_build_fields()` is rewritten to use `get_field_schema()` instead of `_SKIP_KEYS` / `_FIELD_CONFIG` / `_STRING_CYCLES`. Fields with no schema entry are rendered as read-only text. The schema is the single source of tab grouping, step/min/max, and type.

### 3.2 New field types in the panel

**Bool** — unchanged (ON/OFF button toggle).  
**Int/Float** — unchanged (−/+ buttons with step/min/max from schema).  
**Enum** — unchanged (< / > cycle through `choices`).  
**Color** — cycle through a small palette defined in schema `choices`.

**Str / Password** — tappable row. Tapping opens the **system OSK overlay**:
1. Launch `matchbox-keyboard` / `onboard` / `wvkbd` as a subprocess (tried in that order via `shutil.which`).
2. Set `SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS=0` before display init so the pygame window stays visible behind the OSK.
3. A text cursor / current-value display is drawn at the bottom of the pygame panel while OSK is open.
4. Keyboard events flow into pygame normally (`pygame.KEYDOWN`). Backspace, printable chars, Enter (confirm), Escape (cancel) are handled.
5. On confirm, value is written to `_pending_changes`. The OSK subprocess is terminated.
6. **Fallback**: if no system OSK binary is found, draw a native QWERTY grid in pygame (rows: QWERTYUIOP / ASDFGHJKL / ZXCVBNM / space/backspace/confirm). Each key is a tap target.

**Numeric_string** — tappable row. Tapping opens the **numpad overlay** (drawn natively in pygame): digits 0–9, `.`, `-`, `←` (backspace), ✓ (confirm), ✗ (cancel). No subprocess.

### 3.3 OSK subprocess handling

```
_osk_proc: subprocess.Popen | None
_osk_field_path: str | None        # which field is being edited
_osk_buffer: str                   # current edit buffer
_osk_masked: bool                  # True for password fields
```

Opening a new OSK field closes any currently open OSK first.

### 3.4 Restart prompt

After `_save_settings()`, compute `changed_paths ∩ get_restart_required_paths()`. If non-empty, show a modal overlay: "Some changes need a restart. Restart now?" with "Restart" and "Later" buttons. "Restart" calls `vm.restart_service()` equivalent (subprocess call to `systemctl restart <service_name>`).

---

## 4. Qt Dialog Fix

### 4.1 Save fix

Replace the broken dotted-key write-back in `_save_settings()` with a recursive deep-merge:

```python
def _apply_pending(base: dict, changes: dict) -> None:
    for k, v in changes.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _apply_pending(base[k], v)
        else:
            base[k] = v
```

`_pending_changes` is keyed by top-level section only (never dotted). Sub-section changes are nested dicts.

### 4.2 Schema-driven widgets

`_make_input_widget()` checks `get_field_schema(f"{parent_key}.{key}")`:
- `enum` → `QComboBox` with `choices`
- `password` → `QLineEdit` with `setEchoMode(QLineEdit.Password)`
- `color` → `QComboBox` with color swatches
- `int`/`float` — existing spinbox, but range clamped to schema min/max/step

### 4.3 Restart prompt

After save, if any changed dotted path is in `get_restart_required_paths()`, show `QMessageBox` with "Restart now" / "Later". "Restart now" calls `vm.restart_service()`.

---

## 5. React Web UI

### 5.1 Deep-nesting fix

`handleChange` signature changes to `(path: string, value: unknown) => void` where `path` is a dot-separated key from the settings root (e.g. `"ui.margins.left"`).

```ts
function setNestedValue(obj: object, path: string, value: unknown): object {
    const [head, ...rest] = path.split(".");
    if (rest.length === 0) return { ...obj, [head]: value };
    return { ...obj, [head]: setNestedValue((obj as any)[head] ?? {}, rest.join("."), value) };
}
```

`SettingsSection` and `SettingField` receive and forward the full dotted path prefix.

### 5.2 Schema fetch

On mount, `SettingsView` fetches `/api/settings/schema` and passes it down as a `schema` prop. `SettingField` looks up `schema[path]` for its descriptor.

### 5.3 Per-type widgets

| Schema type      | React widget                                            |
|------------------|---------------------------------------------------------|
| `int` / `float`  | `<input type="range">` + numeric `<input>` side-by-side |
| `bool`           | existing toggle                                         |
| `str`            | `<input type="text">`                                   |
| `numeric_string` | `<input type="number">`                                 |
| `password`       | `<input type="password">` + show/hide eye icon          |
| `enum`           | `<select>` dropdown                                     |
| `color`          | `<select>` dropdown (named color choices)               |

### 5.4 Restart badge & prompt

Fields where `schema[path].restart_required === true` get a `⚠` badge next to their label. After a successful save, if `changedPaths ∩ restartRequiredPaths` is non-empty, a modal appears: "Some changes require a restart. Restart now?" → calls `POST /api/maintenance/restart`.

---

## 6. Files Changed

| File | Change |
|------|--------|
| `Utilities/config_store.py` | Add `SETTINGS_SCHEMA`, `get_field_schema()`, `get_restart_required_paths()` |
| `WebAPI/routes/settings.py` | Add `GET /api/settings/schema` route |
| `WebAPI/API.py` | Ensure `/api/maintenance/restart` exists (or add it) |
| `FrameGUI/photoframe_view_pygame.py` | Rewrite `_build_fields()`, add OSK/numpad overlays, restart prompt |
| `FrameGUI/SettingsFrom/dialog.py` | Fix save bug, schema-driven widgets, restart prompt |
| `frontend/src/pages/SettingsView.jsx` | Schema fetch, deep-nesting fix, restart modal |
| `frontend/src/components/settings/SettingsSection.jsx` | Forward full dotted path |
| `frontend/src/components/settings/SettingField.jsx` | Schema-driven widget rendering, ⚠ badge |
| `PhotoFrameServer` / subsystems | Wire `on_settings_changed()` callbacks for live hot-reload |

---

## 7. Out of Scope

- Settings search/filter UI
- Multi-profile / per-device settings
- Settings history / undo
- Mobile-specific layout for the web UI
