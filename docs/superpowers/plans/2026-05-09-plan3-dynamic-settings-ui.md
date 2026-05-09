# Dynamic Settings UI + Web Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Both UIs (React web and Python Qt) dynamically render all settings from DB with no hardcoded field lists. Web UI gets glass/blur redesign. Config changes hot-reload in < 1s.

**Architecture:** `GET /api/settings` returns full JSON blob → both UIs iterate key-value pairs and auto-render typed widgets. Web UI subscribes to SSE `settings_updated` events for live refresh. Python GUI subscribes to `config_events.on_settings_changed`. No hardcoded tab/field lists in either UI.

**Tech Stack:** React + Vite (frontend), PySide6 Qt (Python GUI), Flask SSE (no Socket.IO), `backdrop-filter` CSS for glass effect.

**Dependency:** Plan 1 (Config DB) must be complete.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `WebAPI/routes/settings.py` | Add SSE `/events` endpoint |
| Modify | `frontend/src/pages/SettingsView.jsx` | Full dynamic renderer |
| Create | `frontend/src/components/settings/SettingField.jsx` | Typed input by value type |
| Create | `frontend/src/components/settings/SettingsSection.jsx` | Tab/accordion section |
| Modify | `frontend/src/styles/` or `frontend/src/index.css` | Glass/blur theme |
| Modify | `frontend/src/App.jsx` | Apply global theme |
| Modify | `FrameGUI/SettingsFrom/dialog.py` | Dynamic Qt renderer |
| Modify | `FrameGUI/SettingsFrom/viewmodel.py` | Strip settings data, keep stats/wifi/notif |
| Delete | `FrameGUI/SettingsFrom/model.py` | Already deleted in Plan 1 |

---

## Task 1: SSE endpoint for settings change notifications

**Files:**
- Modify: `WebAPI/routes/settings.py`

- [ ] **Step 1: Add SSE endpoint**

Append to `WebAPI/routes/settings.py`:

```python
import queue
import threading

_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _broadcast_settings_updated() -> None:
    """Called by config_events subscriber to push SSE to all connected web clients."""
    with _sse_lock:
        clients = list(_sse_clients)
    for q in clients:
        try:
            q.put_nowait("settings_updated")
        except queue.Full:
            pass


def _register_sse_broadcaster() -> None:
    from Utilities.config_events import on_settings_changed
    on_settings_changed(lambda _: _broadcast_settings_updated())


# Register once at import time
_register_sse_broadcaster()


@settings_bp.route("/events", methods=["GET"])
def settings_events():
    """Server-Sent Events stream. Pushes 'settings_updated' when settings change."""
    backend = current_app.config.get('backend')
    if backend and not backend.is_authenticated():
        return jsonify({"error": "unauthorized"}), 401

    def event_stream():
        q: queue.Queue = queue.Queue(maxsize=10)
        with _sse_lock:
            _sse_clients.append(q)
        try:
            yield "data: connected\n\n"
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _sse_lock:
                try:
                    _sse_clients.remove(q)
                except ValueError:
                    pass

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 2: Test SSE endpoint manually**

```bash
env/bin/python app.py --headless &
sleep 3
# In another terminal (after login):
curl -N http://localhost:5002/api/settings/events
# In another terminal, trigger a save:
env/bin/python -c "
from Utilities.config_store import load_settings, save_settings
d = load_settings(); save_settings(d)
"
```
Expected: SSE stream receives `data: settings_updated`.

- [ ] **Step 3: Commit**

```bash
git add WebAPI/routes/settings.py
git commit -m "feat: add SSE /api/settings/events endpoint for hot reload notifications"
```

---

## Task 2: Global glass/blur CSS theme

**Files:**
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Replace `frontend/src/index.css` contents**

```css
/* ── Reset ─────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── Root tokens ────────────────────────────────────── */
:root {
  --glass-bg:      rgba(255, 255, 255, 0.07);
  --glass-border:  rgba(255, 255, 255, 0.15);
  --glass-blur:    20px;
  --glass-radius:  16px;
  --glass-shadow:  0 8px 32px rgba(0, 0, 0, 0.35);

  --text-primary:  rgba(255, 255, 255, 0.92);
  --text-secondary:rgba(255, 255, 255, 0.55);
  --accent:        rgba(120, 180, 255, 0.85);
  --accent-hover:  rgba(150, 200, 255, 1);
  --danger:        rgba(255, 90, 90, 0.85);

  --input-bg:      rgba(255, 255, 255, 0.06);
  --input-border:  rgba(255, 255, 255, 0.18);
  --input-focus:   rgba(120, 180, 255, 0.5);

  --transition:    0.18s ease;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px;
  color: var(--text-primary);
}

/* ── Body / background ──────────────────────────────── */
body {
  min-height: 100vh;
  background: linear-gradient(135deg, #0d0d1a 0%, #111827 50%, #0d1a2a 100%);
  background-attachment: fixed;
}

/* ── Glass panel ────────────────────────────────────── */
.glass {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius: var(--glass-radius);
  box-shadow: var(--glass-shadow);
}

/* ── Inputs ─────────────────────────────────────────── */
input, select, textarea {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-primary);
  padding: 6px 10px;
  width: 100%;
  transition: border-color var(--transition), box-shadow var(--transition);
}
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--input-focus);
  box-shadow: 0 0 0 2px rgba(120, 180, 255, 0.2);
}
input[type="checkbox"] {
  width: auto;
  accent-color: var(--accent);
}
input[type="range"] { padding: 0; background: transparent; }

/* ── Buttons ────────────────────────────────────────── */
button {
  cursor: pointer;
  border: 1px solid var(--glass-border);
  border-radius: 8px;
  background: var(--glass-bg);
  color: var(--text-primary);
  padding: 8px 18px;
  transition: background var(--transition), border-color var(--transition);
}
button:hover { background: rgba(255,255,255,0.14); border-color: var(--accent); }
button.primary {
  background: rgba(90, 150, 255, 0.25);
  border-color: var(--accent);
  color: var(--accent-hover);
}
button.primary:hover { background: rgba(90, 150, 255, 0.4); }
button.danger { border-color: var(--danger); color: var(--danger); }

/* ── Toggle switch ──────────────────────────────────── */
.toggle { position: relative; display: inline-flex; align-items: center; gap: 8px; cursor: pointer; }
.toggle input { display: none; }
.toggle-track {
  width: 40px; height: 22px;
  background: rgba(255,255,255,0.12);
  border-radius: 11px;
  border: 1px solid var(--glass-border);
  transition: background var(--transition);
  position: relative;
}
.toggle input:checked + .toggle-track { background: rgba(90,150,255,0.5); border-color: var(--accent); }
.toggle-track::after {
  content: "";
  position: absolute;
  top: 2px; left: 2px;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: white;
  transition: transform var(--transition);
}
.toggle input:checked + .toggle-track::after { transform: translateX(18px); }

/* ── Scrollbar ──────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 3px; }
```

- [ ] **Step 2: Run lint**

```bash
cd frontend && npm run lint
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat: glass/blur CSS theme — tokens, glass panel, inputs, toggles"
```

---

## Task 3: `SettingField` component — typed input renderer

**Files:**
- Create: `frontend/src/components/settings/SettingField.jsx`

- [ ] **Step 1: Create the component**

```jsx
// frontend/src/components/settings/SettingField.jsx
import React from "react";

// Renders a single key-value pair as the appropriate input widget.
// Calls onChange(key, newValue) when user changes a value.
export default function SettingField({ fieldKey, value, onChange, depth = 0 }) {
  const label = fieldKey
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  const labelEl = (
    <span style={{ color: "var(--text-secondary)", fontSize: "0.85em", minWidth: 160 }}>
      {label}
    </span>
  );

  const row = (input) => (
    <div
      key={fieldKey}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "6px 0",
        paddingLeft: depth * 16,
      }}
    >
      {labelEl}
      <div style={{ flex: 1 }}>{input}</div>
    </div>
  );

  if (typeof value === "boolean") {
    return row(
      <label className="toggle">
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(fieldKey, e.target.checked)}
        />
        <span className="toggle-track" />
      </label>
    );
  }

  if (typeof value === "number") {
    const isFloat = !Number.isInteger(value);
    return row(
      <input
        type="number"
        value={value}
        step={isFloat ? 0.01 : 1}
        onChange={(e) => {
          const v = isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10);
          if (!isNaN(v)) onChange(fieldKey, v);
        }}
        style={{ maxWidth: 160 }}
      />
    );
  }

  if (typeof value === "string") {
    return row(
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(fieldKey, e.target.value)}
      />
    );
  }

  if (Array.isArray(value)) {
    // Simple comma-separated display for arrays of primitives
    const isSimple = value.every((v) => typeof v !== "object");
    if (isSimple) {
      return row(
        <input
          type="text"
          value={value.join(", ")}
          onChange={(e) =>
            onChange(
              fieldKey,
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
                .map((s) => (isNaN(Number(s)) ? s : Number(s)))
            )
          }
        />
      );
    }
    // Complex array (e.g. schedules) — show as JSON textarea
    return row(
      <textarea
        rows={3}
        value={JSON.stringify(value, null, 2)}
        onChange={(e) => {
          try {
            onChange(fieldKey, JSON.parse(e.target.value));
          } catch (_) {}
        }}
        style={{ fontFamily: "monospace", fontSize: "0.8em" }}
      />
    );
  }

  // Object — do not render here; SettingsSection handles recursion
  return null;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/SettingField.jsx
git commit -m "feat: SettingField component - typed input renderer for settings values"
```

---

## Task 4: `SettingsSection` component — recursive section renderer

**Files:**
- Create: `frontend/src/components/settings/SettingsSection.jsx`

- [ ] **Step 1: Create the component**

```jsx
// frontend/src/components/settings/SettingsSection.jsx
import React, { useState } from "react";
import SettingField from "./SettingField";

// Renders a settings object as a list of fields.
// Nested objects become collapsible accordion groups.
// onChange(key, value) called for every leaf change.
export default function SettingsSection({ data, onChange, depth = 0 }) {
  const [collapsed, setCollapsed] = useState({});

  const toggle = (key) =>
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {Object.entries(data).map(([key, value]) => {
        if (value !== null && typeof value === "object" && !Array.isArray(value)) {
          const isCollapsed = collapsed[key] ?? false;
          const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
          return (
            <div
              key={key}
              style={{
                border: "1px solid var(--glass-border)",
                borderRadius: 10,
                marginTop: 6,
                overflow: "hidden",
                paddingLeft: depth * 8,
              }}
            >
              <button
                onClick={() => toggle(key)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 14px",
                  background: "rgba(255,255,255,0.04)",
                  border: "none",
                  borderRadius: 0,
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span style={{ fontWeight: 500 }}>{label}</span>
                <span>{isCollapsed ? "▶" : "▼"}</span>
              </button>
              {!isCollapsed && (
                <div style={{ padding: "8px 14px" }}>
                  <SettingsSection
                    data={value}
                    onChange={(subKey, subVal) =>
                      onChange(key, { ...value, [subKey]: subVal })
                    }
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
            value={value}
            onChange={onChange}
            depth={depth}
          />
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/SettingsSection.jsx
git commit -m "feat: SettingsSection component - recursive accordion renderer for nested settings"
```

---

## Task 5: Rewrite `SettingsView.jsx` — dynamic renderer + SSE

**Files:**
- Modify: `frontend/src/pages/SettingsView.jsx`

- [ ] **Step 1: Replace `SettingsView.jsx` entirely**

```jsx
// frontend/src/pages/SettingsView.jsx
import React, { useEffect, useRef, useState, useCallback } from "react";
import SettingsSection from "../components/settings/SettingsSection";

// Keys to exclude from tabs (internal/read-only)
const HIDDEN_KEYS = new Set(["about"]);

export default function SettingsView() {
  const [settings, setSettings] = useState(null);
  const [activeTab, setActiveTab] = useState(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const pendingRef = useRef(null);
  const sseRef = useRef(null);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch("/api/settings", { credentials: "include" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSettings(data);
      if (!activeTab) setActiveTab(Object.keys(data).find((k) => !HIDDEN_KEYS.has(k)));
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }, [activeTab]);

  // Initial load
  useEffect(() => { fetchSettings(); }, []);

  // SSE subscription for hot reload
  useEffect(() => {
    const es = new EventSource("/api/settings/events", { withCredentials: true });
    sseRef.current = es;
    es.onmessage = (e) => {
      if (e.data === "settings_updated") fetchSettings();
    };
    return () => es.close();
  }, [fetchSettings]);

  // Deep-set a value at a path in the settings tree
  const handleChange = useCallback((topKey, sectionKey, value) => {
    setSettings((prev) => {
      const next = {
        ...prev,
        [topKey]: { ...prev[topKey], [sectionKey]: value },
      };
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
      pendingRef.current = null;
      setStatus("Saved");
      setTimeout(() => setStatus(""), 2000);
    } catch (e) {
      setStatus(`Save failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (!settings) {
    return (
      <div style={{ padding: 40, color: "var(--text-secondary)" }}>
        Loading settings…
      </div>
    );
  }

  const tabs = Object.keys(settings).filter((k) => !HIDDEN_KEYS.has(k));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 24, gap: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "1.4em", fontWeight: 600 }}>Settings</h1>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {status && (
            <span style={{ color: status.startsWith("Error") || status.startsWith("Save failed") ? "var(--danger)" : "var(--accent)", fontSize: "0.85em" }}>
              {status}
            </span>
          )}
          <button className="primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {tabs.map((key) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: "6px 16px",
              borderRadius: 20,
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

      {/* Active section */}
      {activeTab && settings[activeTab] && (
        <div
          className="glass"
          style={{ flex: 1, overflowY: "auto", padding: 20 }}
        >
          {typeof settings[activeTab] === "object" && !Array.isArray(settings[activeTab]) ? (
            <SettingsSection
              data={settings[activeTab]}
              onChange={(sectionKey, value) => handleChange(activeTab, sectionKey, value)}
            />
          ) : (
            <p style={{ color: "var(--text-secondary)" }}>
              {JSON.stringify(settings[activeTab])}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Build and verify**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: Build succeeds, no errors.

- [ ] **Step 3: Run lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/SettingsView.jsx frontend/src/components/settings/
git commit -m "feat: dynamic SettingsView - auto-renders all settings from API, SSE hot reload, glass UI"
```

---

## Task 6: Apply glass theme to remaining pages

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/pages/Login.jsx`

- [ ] **Step 1: Wrap app layout in dark background**

In `frontend/src/App.jsx`, ensure the root element uses a dark background (already handled by `body` CSS above, but verify no white background override in App styles).

Remove any `background: white` or `background-color: #fff` overrides in `App.jsx` or layout components.

- [ ] **Step 2: Style `Login.jsx` with glass card**

In `frontend/src/pages/Login.jsx`, wrap the form in a `glass` div:

```jsx
// Wrap existing form content:
<div style={{
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
}}>
  <div className="glass" style={{ padding: 40, width: 380, display: "flex", flexDirection: "column", gap: 16 }}>
    <h1 style={{ fontSize: "1.5em", textAlign: "center" }}>Photo Frame</h1>
    {/* existing form fields */}
  </div>
</div>
```

- [ ] **Step 3: Build and lint**

```bash
cd frontend && npm run build && npm run lint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx frontend/src/pages/Login.jsx
git commit -m "feat: apply glass theme to Login and App layout"
```

---

## Task 7: Python GUI — dynamic Qt settings dialog

**Files:**
- Modify: `FrameGUI/SettingsFrom/dialog.py`
- Modify: `FrameGUI/SettingsFrom/viewmodel.py`

- [ ] **Step 1: Replace `SettingsDialog._build_config_tab` and all hardcoded tab builders**

Open `FrameGUI/SettingsFrom/dialog.py`. 

Remove all `_build_*_tab` methods except `_build_stats_tab` (kept as pinned "System" tab).

Add these helper methods:

```python
def _build_dynamic_tabs(self, settings: dict) -> None:
    """Auto-generate one tab per top-level settings key."""
    SKIP = {"about"}  # read-only keys not shown
    PINNED_FIRST = "stats"

    for key, section in settings.items():
        if key in SKIP or not isinstance(section, dict):
            continue
        tab_label = key.replace("_", " ").title()
        widget = self._build_section_widget(section, parent_key=key)
        self._tabs.addTab(self._wrap_scroll(widget), tab_label)

def _build_section_widget(self, section: dict, parent_key: str) -> QWidget:
    """Build a QWidget with a QFormLayout for all key-value pairs in section."""
    from PySide6 import QtWidgets as QW
    widget = QW.QWidget()
    form = QW.QFormLayout(widget)
    form.setRowWrapPolicy(QW.QFormLayout.WrapLongRows)

    for key, value in section.items():
        label = key.replace("_", " ").title()
        input_widget = self._make_input_widget(key, value, parent_key, section)
        if input_widget:
            form.addRow(label, input_widget)
    return widget

def _make_input_widget(self, key: str, value, parent_key: str, section: dict):
    """Return the appropriate Qt widget for value type."""
    from PySide6 import QtWidgets as QW, QtCore as QC

    def on_bool(state, k=key, pk=parent_key):
        self._pending_changes.setdefault(pk, {})[k] = bool(state)

    def on_int(val, k=key, pk=parent_key):
        self._pending_changes.setdefault(pk, {})[k] = int(val)

    def on_float(val, k=key, pk=parent_key):
        self._pending_changes.setdefault(pk, {})[k] = float(val)

    def on_str(text, k=key, pk=parent_key):
        self._pending_changes.setdefault(pk, {})[k] = text

    if isinstance(value, bool):
        w = QW.QCheckBox()
        w.setChecked(value)
        w.stateChanged.connect(on_bool)
        return w

    if isinstance(value, int):
        w = QW.QSpinBox()
        w.setRange(-9999999, 9999999)
        w.setValue(value)
        w.valueChanged.connect(on_int)
        return w

    if isinstance(value, float):
        w = QW.QDoubleSpinBox()
        w.setRange(-9999999.0, 9999999.0)
        w.setDecimals(3)
        w.setValue(value)
        w.valueChanged.connect(on_float)
        return w

    if isinstance(value, str):
        w = QW.QLineEdit(value)
        w.textChanged.connect(on_str)
        return w

    if isinstance(value, dict):
        w = QW.QGroupBox()
        layout = QW.QVBoxLayout(w)
        inner = self._build_section_widget(value, parent_key=f"{parent_key}.{key}")
        layout.addWidget(inner)
        return w

    # Arrays and other types — show as JSON text
    import json
    w = QW.QPlainTextEdit(json.dumps(value, indent=2))
    w.setFixedHeight(80)
    return w
```

Replace `__init__` tab building with:
```python
self._tabs = QtWidgets.QTabWidget(self)
self.layout().addWidget(self._tabs)
self._pending_changes: dict = {}

# Pinned system tab first
stats_tab = self._build_stats_tab()
self._tabs.addTab(self._wrap_scroll(stats_tab), "System")

# Dynamic tabs from settings
from Utilities.config_store import load_settings
current_settings = load_settings()
self._build_dynamic_tabs(current_settings)

# Save button
save_btn = QtWidgets.QPushButton("Save")
save_btn.clicked.connect(self._save_settings)
self.layout().addWidget(save_btn)
```

Add save method:
```python
def _save_settings(self) -> None:
    from Utilities.config_store import load_settings, save_settings
    import copy
    current = load_settings()
    for section_key, changes in self._pending_changes.items():
        if "." in section_key:
            # nested key like "screen.schedules"
            parts = section_key.split(".")
            target = current
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = changes
        else:
            if isinstance(current.get(section_key), dict):
                current[section_key].update(changes)
            else:
                current[section_key] = changes
    save_settings(current)
    self._pending_changes.clear()
```

- [ ] **Step 2: Subscribe dialog to hot reload**

In `__init__`, after building tabs:
```python
from Utilities.config_events import on_settings_changed
on_settings_changed(self._on_hot_reload)
```

Add method (uses Qt signal to thread-safely update UI):
```python
_hot_reload_signal = QtCore.Signal(dict)  # class-level

def __init__(self, ...):
    ...
    self._hot_reload_signal.connect(self._refresh_from_settings)

def _on_hot_reload(self, new_data: dict) -> None:
    self._hot_reload_signal.emit(new_data)

def _refresh_from_settings(self, new_data: dict) -> None:
    # Rebuild dynamic tabs
    while self._tabs.count() > 1:  # keep System tab at index 0
        self._tabs.removeTab(1)
    self._build_dynamic_tabs(new_data)
    self._pending_changes.clear()
```

- [ ] **Step 3: Smoke test Python GUI (if display available)**

```bash
env/bin/python app.py --display qt
# Open settings dialog — verify all settings sections appear as tabs
```

- [ ] **Step 4: Commit**

```bash
git add FrameGUI/SettingsFrom/dialog.py FrameGUI/SettingsFrom/viewmodel.py
git commit -m "feat: Python GUI settings dialog - fully dynamic from config_store, hot reload via Qt signal"
```

---

## Task 8: Final build verification

- [ ] **Step 1: Full frontend build**

```bash
cd frontend && npm run build && npm run lint
```
Expected: Clean build.

- [ ] **Step 2: Python lint**

```bash
env/bin/python -m ruff check . --select E,W,F
```
Expected: No new errors.

- [ ] **Step 3: Run tests**

```bash
env/bin/python -m pytest -v
```
Expected: All PASS.

- [ ] **Step 4: Headless smoke test with settings change**

```bash
env/bin/python app.py --headless &
sleep 3
# Trigger settings change via API
curl -s -X POST http://localhost:5002/api/settings \
  -H "Content-Type: application/json" \
  -d '{"playback": {"animation_fps": 25}}' \
  --cookie-jar /tmp/pf.cookies
# (Requires auth — test manually in browser instead if needed)
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add -p
git commit -m "chore: final build verification for dynamic settings UI"
```
