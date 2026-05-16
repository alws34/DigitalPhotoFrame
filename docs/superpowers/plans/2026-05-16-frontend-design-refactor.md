# Frontend Design Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the PhotoFrame admin UI to Frosted Glass Elevated aesthetic with user-selectable accent color, motion intensity, and collapsible sidebar — zero functionality loss.

**Architecture:** CSS custom properties drive all theming; a ThemeProvider injects tokens to `:root` on load and on settings change. New `admin_ui` settings key stores preferences server-side. Sidebar collapse is a toggle with optimistic local update + server persist.

**Tech Stack:** React 18, Vite, Flask, Python `SETTINGS_SCHEMA` dict in `Utilities/config_store.py`, lucide-react icons, axios.

**Branch:** `frontend_design` (from `dockerization`)

**CONSTRAINT:** Do NOT remove, hide, or break any existing functionality in Gallery, Albums, Stream, Settings, Login, Signup, Reset Password, or FrameView pages.

---

## Task 1: Backend — Add `admin_ui` to Settings Schema

**Files:**
- Modify: `Utilities/config_store.py` (around line 240, after `"ui"` block)
- Modify: `photoframe_settings.example.json`

- [ ] **Step 1: Add `admin_ui` block to SETTINGS_SCHEMA**

In `Utilities/config_store.py`, after the closing `}` of the `"ui"` block (line ~240), add:

```python
    "admin_ui": {
        "accent_color":      {"type": "enum", "label": "Accent Color",     "choices": ["indigo", "sky", "emerald", "rose"], "restart_required": False, "ui": "color_theme"},
        "motion_intensity":  {"type": "enum", "label": "Motion Intensity", "choices": ["subtle", "cinematic"],              "restart_required": False, "ui": "motion_select"},
        "sidebar_collapsed": {"type": "bool", "label": "Sidebar Collapsed",                                                 "restart_required": False},
    },
```

- [ ] **Step 2: Add defaults to `photoframe_settings.example.json`**

Add to the top-level JSON object:

```json
"admin_ui": {
  "accent_color": "indigo",
  "motion_intensity": "subtle",
  "sidebar_collapsed": false
}
```

- [ ] **Step 3: Run existing schema test to verify no breakage**

```bash
env/bin/python -m pytest Tests/test_settings_schema.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add Utilities/config_store.py photoframe_settings.example.json
git commit -m "feat: add admin_ui settings schema (accent_color, motion_intensity, sidebar_collapsed)"
```

---

## Task 2: ThemeContext — Fetch Settings and Inject CSS Vars

**Files:**
- Create: `frontend/src/context/ThemeContext.jsx`

The accent color and motion tokens to inject:

```js
const ACCENT_TOKENS = {
  indigo:  { '--accent': '#6366f1', '--accent-hover': '#818cf8', '--accent-glow': 'rgba(99,102,241,0.3)' },
  sky:     { '--accent': '#0ea5e9', '--accent-hover': '#38bdf8', '--accent-glow': 'rgba(14,165,233,0.3)' },
  emerald: { '--accent': '#059669', '--accent-hover': '#10b981', '--accent-glow': 'rgba(5,150,105,0.3)' },
  rose:    { '--accent': '#e11d48', '--accent-hover': '#f43f5e', '--accent-glow': 'rgba(225,29,72,0.3)' },
};

const MOTION_TOKENS = {
  subtle:    { '--transition': '0.15s ease-out', '--transition-slow': '0.2s ease-out' },
  cinematic: { '--transition': '0.3s cubic-bezier(0.34,1.56,0.64,1)', '--transition-slow': '0.4s ease' },
};
```

- [ ] **Step 1: Create `frontend/src/context/ThemeContext.jsx`**

```jsx
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const ACCENT_TOKENS = {
  indigo:  { '--accent': '#6366f1', '--accent-hover': '#818cf8', '--accent-glow': 'rgba(99,102,241,0.3)' },
  sky:     { '--accent': '#0ea5e9', '--accent-hover': '#38bdf8', '--accent-glow': 'rgba(14,165,233,0.3)' },
  emerald: { '--accent': '#059669', '--accent-hover': '#10b981', '--accent-glow': 'rgba(5,150,105,0.3)' },
  rose:    { '--accent': '#e11d48', '--accent-hover': '#f43f5e', '--accent-glow': 'rgba(225,29,72,0.3)' },
};

const MOTION_TOKENS = {
  subtle:    { '--transition': '0.15s ease-out', '--transition-slow': '0.2s ease-out' },
  cinematic: { '--transition': '0.3s cubic-bezier(0.34,1.56,0.64,1)', '--transition-slow': '0.4s ease' },
};

const DEFAULTS = { accent: 'indigo', motionIntensity: 'subtle', sidebarCollapsed: false };

const ThemeContext = createContext(DEFAULTS);

function applyTokens(accent, motion) {
  const root = document.documentElement;
  const accentMap = ACCENT_TOKENS[accent] ?? ACCENT_TOKENS.indigo;
  const motionMap = MOTION_TOKENS[motion] ?? MOTION_TOKENS.subtle;
  Object.entries({ ...accentMap, ...motionMap }).forEach(([k, v]) => root.style.setProperty(k, v));
}

export function ThemeProvider({ children }) {
  const [accent, setAccent] = useState(DEFAULTS.accent);
  const [motionIntensity, setMotionIntensity] = useState(DEFAULTS.motionIntensity);
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(DEFAULTS.sidebarCollapsed);

  useEffect(() => {
    axios.get('/api/settings', { withCredentials: true })
      .then(res => {
        const ui = res.data?.admin_ui ?? {};
        const a = ui.accent_color ?? DEFAULTS.accent;
        const m = ui.motion_intensity ?? DEFAULTS.motionIntensity;
        const s = ui.sidebar_collapsed ?? DEFAULTS.sidebarCollapsed;
        setAccent(a);
        setMotionIntensity(m);
        setSidebarCollapsedState(s);
        applyTokens(a, m);
      })
      .catch(() => applyTokens(DEFAULTS.accent, DEFAULTS.motionIntensity));
  }, []);

  const saveAdminUiSetting = useCallback(async (key, value) => {
    try {
      const res = await axios.get('/api/settings', { withCredentials: true });
      const current = res.data ?? {};
      const next = { ...current, admin_ui: { ...(current.admin_ui ?? {}), [key]: value } };
      await axios.post('/api/settings', next, { withCredentials: true });
    } catch (e) {
      console.error('Failed to save admin_ui setting', e);
    }
  }, []);

  const setSidebarCollapsed = useCallback((val) => {
    setSidebarCollapsedState(val);
    saveAdminUiSetting('sidebar_collapsed', val);
  }, [saveAdminUiSetting]);

  const handleAccentChange = useCallback((val) => {
    setAccent(val);
    applyTokens(val, motionIntensity);
    saveAdminUiSetting('accent_color', val);
  }, [motionIntensity, saveAdminUiSetting]);

  const handleMotionChange = useCallback((val) => {
    setMotionIntensity(val);
    applyTokens(accent, val);
    saveAdminUiSetting('motion_intensity', val);
  }, [accent, saveAdminUiSetting]);

  return (
    <ThemeContext.Provider value={{
      accent, setAccent: handleAccentChange,
      motionIntensity, setMotionIntensity: handleMotionChange,
      sidebarCollapsed, setSidebarCollapsed,
      saveAdminUiSetting,
    }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/context/ThemeContext.jsx
git commit -m "feat: add ThemeContext with CSS var injection for accent and motion"
```

---

## Task 3: index.css — Token Swap + Visual Polish

**Files:**
- Modify: `frontend/src/index.css`

Replace the entire file. All existing selectors preserved; accent tokens replaced with CSS vars; visual polish added (sidebar depth, card hover lift, improved typography).

- [ ] **Step 1: Replace `frontend/src/index.css`**

```css
/* ── Reset ─────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── Root tokens ────────────────────────────────────── */
:root {
  /* Accent — overridden at runtime by ThemeProvider */
  --accent:        #6366f1;
  --accent-hover:  #818cf8;
  --accent-glow:   rgba(99, 102, 241, 0.3);

  /* Motion — overridden at runtime by ThemeProvider */
  --transition:      0.15s ease-out;
  --transition-slow: 0.2s ease-out;

  /* Glass */
  --glass-bg:      rgba(255, 255, 255, 0.05);
  --glass-border:  rgba(255, 255, 255, 0.10);
  --glass-blur:    20px;
  --glass-radius:  14px;
  --glass-shadow:  0 8px 32px rgba(0, 0, 0, 0.4), 0 1px 0 rgba(255,255,255,0.06) inset;

  /* Text */
  --text-primary:   rgba(255, 255, 255, 0.92);
  --text-secondary: rgba(255, 255, 255, 0.50);

  /* Input */
  --input-bg:     rgba(255, 255, 255, 0.05);
  --input-border: rgba(255, 255, 255, 0.14);
  --input-focus:  var(--accent);

  /* Danger */
  --danger: #f43f5e;

  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px;
  color: var(--text-primary);
}

/* ── Body / background ──────────────────────────────── */
body {
  min-height: 100vh;
  background: linear-gradient(135deg, #080b12 0%, #0d1117 50%, #080d14 100%);
  background-attachment: fixed;
}

#root {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ── Glass panel ────────────────────────────────────── */
.glass,
.glass-panel {
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
  padding: 7px 11px;
  width: 100%;
  transition: border-color var(--transition), box-shadow var(--transition);
  font-family: inherit;
  font-size: inherit;
}
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
input[type="checkbox"] { width: auto; accent-color: var(--accent); }
input[type="range"] { padding: 0; background: transparent; accent-color: var(--accent); }

/* ── Buttons ────────────────────────────────────────── */
button {
  cursor: pointer;
  border: 1px solid var(--glass-border);
  border-radius: 8px;
  background: var(--glass-bg);
  color: var(--text-primary);
  padding: 8px 18px;
  font-family: inherit;
  font-size: inherit;
  font-weight: 500;
  transition: background var(--transition), border-color var(--transition), box-shadow var(--transition);
}
button:hover {
  background: rgba(255, 255, 255, 0.10);
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-glow);
}
button:disabled { opacity: 0.45; cursor: not-allowed; }

button.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  box-shadow: 0 2px 12px var(--accent-glow);
}
button.primary:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
  box-shadow: 0 4px 20px var(--accent-glow);
}

button.danger { border-color: var(--danger); color: var(--danger); }
button.danger:hover { background: rgba(244,63,94,0.12); box-shadow: none; }

/* ── Toggle switch ──────────────────────────────────── */
.toggle { position: relative; display: inline-flex; align-items: center; gap: 8px; cursor: pointer; }
.toggle input { display: none; }
.toggle-track {
  width: 40px; height: 22px;
  background: rgba(255, 255, 255, 0.10);
  border-radius: 11px;
  border: 1px solid var(--glass-border);
  transition: background var(--transition), border-color var(--transition);
  position: relative;
}
.toggle input:checked + .toggle-track {
  background: var(--accent);
  border-color: var(--accent);
}
.toggle-track::after {
  content: "";
  position: absolute;
  top: 2px; left: 2px;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: white;
  transition: transform var(--transition);
  box-shadow: 0 1px 4px rgba(0,0,0,0.3);
}
.toggle input:checked + .toggle-track::after { transform: translateX(18px); }

/* ── Animations ─────────────────────────────────────── */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.fade-in { animation: fadeIn var(--transition-slow) ease-out forwards; }

/* ── Layout helpers ─────────────────────────────────── */
.app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.sidebar {
  background: rgba(255, 255, 255, 0.03);
  border-right: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  transition: width var(--transition-slow);
  overflow: hidden;
  flex-shrink: 0;
}

.sidebar.expanded { width: 240px; padding: 1.25rem 0.875rem; }
.sidebar.collapsed { width: 56px; padding: 1.25rem 0.5rem; align-items: center; }

.main-content {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

/* ── Typography ─────────────────────────────────────── */
h1, h2, h3, h4, h5, h6 { margin: 0 0 1rem 0; color: var(--text-primary); letter-spacing: -0.3px; }
a { font-weight: 500; color: var(--accent); text-decoration: inherit; }
a:hover { color: var(--accent-hover); }

/* ── Scrollbar ──────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: 3px; }

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 768px) {
  .app-container { flex-direction: column; }
  .sidebar.expanded, .sidebar.collapsed {
    width: 100%;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--glass-border);
    flex-direction: row;
    padding: 0.75rem 1rem;
  }
  .main-content { height: calc(100vh - 60px); }
}
```

- [ ] **Step 2: Verify lint passes**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat: refactor CSS to use accent/motion custom properties, add sidebar transition classes"
```

---

## Task 4: ColorThemePicker Component

**Files:**
- Create: `frontend/src/components/settings/ColorThemePicker.jsx`

- [ ] **Step 1: Create `frontend/src/components/settings/ColorThemePicker.jsx`**

```jsx
const THEMES = [
  { value: 'indigo',  label: 'Indigo',  gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)' },
  { value: 'sky',     label: 'Sky',     gradient: 'linear-gradient(135deg, #0ea5e9, #38bdf8)' },
  { value: 'emerald', label: 'Emerald', gradient: 'linear-gradient(135deg, #059669, #10b981)' },
  { value: 'rose',    label: 'Rose',    gradient: 'linear-gradient(135deg, #e11d48, #f43f5e)' },
];

export default function ColorThemePicker({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
      {THEMES.map(t => {
        const selected = value === t.value;
        return (
          <button
            key={t.value}
            title={t.label}
            onClick={() => onChange(t.value)}
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: t.gradient,
              border: selected ? '2px solid #fff' : '2px solid transparent',
              outline: selected ? '2px solid var(--accent)' : 'none',
              outlineOffset: 2,
              padding: 0,
              cursor: 'pointer',
              boxShadow: selected ? '0 0 10px var(--accent-glow)' : 'none',
              transition: 'box-shadow var(--transition), outline var(--transition)',
            }}
          />
        );
      })}
      <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginLeft: 4 }}>
        {THEMES.find(t => t.value === value)?.label ?? value}
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/ColorThemePicker.jsx
git commit -m "feat: add ColorThemePicker swatch component"
```

---

## Task 5: MotionSelect Component

**Files:**
- Create: `frontend/src/components/settings/MotionSelect.jsx`

- [ ] **Step 1: Create `frontend/src/components/settings/MotionSelect.jsx`**

```jsx
const OPTIONS = [
  { value: 'subtle',    label: 'Subtle',    detail: '150ms' },
  { value: 'cinematic', label: 'Cinematic', detail: '350ms' },
];

export default function MotionSelect({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {OPTIONS.map(o => {
        const selected = value === o.value;
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            style={{
              padding: '5px 14px',
              borderRadius: 20,
              border: selected ? '1px solid var(--accent)' : '1px solid var(--glass-border)',
              background: selected ? 'var(--accent-glow)' : 'transparent',
              color: selected ? 'var(--accent-hover)' : 'var(--text-secondary)',
              fontWeight: selected ? 600 : 400,
              fontSize: '0.82rem',
              cursor: 'pointer',
              transition: 'all var(--transition)',
            }}
          >
            {o.label} <span style={{ opacity: 0.6, fontSize: '0.75em' }}>({o.detail})</span>
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/MotionSelect.jsx
git commit -m "feat: add MotionSelect pill-toggle component"
```

---

## Task 6: SettingField — Add `color_theme` and `motion_select` UI Cases

**Files:**
- Modify: `frontend/src/components/settings/SettingField.jsx`

- [ ] **Step 1: Add imports at top of `frontend/src/components/settings/SettingField.jsx`**

After the existing `import ClockKnob from "./ClockKnob";` line, add:

```jsx
import ColorThemePicker from "./ColorThemePicker";
import MotionSelect from "./MotionSelect";
```

- [ ] **Step 2: Add `color_theme` case before the `album_select` block**

In `SettingField.jsx`, after the `if (schema?.ui === "clock")` block (around line 75) and before `if (schema?.ui === "album_select")`, insert:

```jsx
  if (schema?.ui === "color_theme") {
    return row(
      <ColorThemePicker value={value ?? "indigo"} onChange={(v) => onChange(fieldPath, v)} />
    );
  }

  if (schema?.ui === "motion_select") {
    return row(
      <MotionSelect value={value ?? "subtle"} onChange={(v) => onChange(fieldPath, v)} />
    );
  }
```

- [ ] **Step 3: Verify lint**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings/SettingField.jsx
git commit -m "feat: add color_theme and motion_select UI cases to SettingField"
```

---

## Task 7: DashboardLayout — Collapsible Sidebar

**Files:**
- Modify: `frontend/src/components/DashboardLayout.jsx`

Replace the entire file. Existing nav items, user display, and logout preserved. Sidebar now reads `sidebarCollapsed` from ThemeContext and applies `.sidebar.expanded` / `.sidebar.collapsed` CSS classes. Toggle button in header.

- [ ] **Step 1: Replace `frontend/src/components/DashboardLayout.jsx`**

```jsx
import { Outlet, NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { MonitorPlay, Aperture, Settings, LogOut, User, BookImage, PanelLeftClose, PanelLeftOpen } from 'lucide-react';

const NAV_ITEMS = [
  { path: '/stream',   icon: <MonitorPlay size={20} />, label: 'Live Stream' },
  { path: '/gallery',  icon: <Aperture size={20} />,    label: 'Gallery'     },
  { path: '/albums',   icon: <BookImage size={20} />,   label: 'Albums'      },
  { path: '/settings', icon: <Settings size={20} />,    label: 'Settings'    },
];

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const { sidebarCollapsed, setSidebarCollapsed } = useTheme();

  const collapsed = sidebarCollapsed;

  return (
    <div className="app-container">
      <aside className={`sidebar ${collapsed ? 'collapsed' : 'expanded'} fade-in`}>

        {/* Header row */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          marginBottom: '1.5rem',
          gap: '0.5rem',
          width: '100%',
        }}>
          {!collapsed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', overflow: 'hidden' }}>
              <div style={{ padding: '0.4rem', borderRadius: '8px', background: 'var(--accent)', color: 'white', flexShrink: 0 }}>
                <MonitorPlay size={18} />
              </div>
              <span style={{ fontWeight: 700, fontSize: '1rem', letterSpacing: '-0.3px', whiteSpace: 'nowrap' }}>PhotoFrame</span>
            </div>
          )}
          <button
            onClick={() => setSidebarCollapsed(!collapsed)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{
              background: 'transparent',
              border: 'none',
              padding: '6px',
              color: 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'center',
              borderRadius: '6px',
              flexShrink: 0,
            }}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        {/* Nav */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', flex: 1, width: '100%' }}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              title={collapsed ? item.label : undefined}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                justifyContent: collapsed ? 'center' : 'flex-start',
                gap: '0.7rem',
                padding: collapsed ? '0.7rem' : '0.65rem 0.875rem',
                borderRadius: '10px',
                color: isActive ? '#fff' : 'var(--text-secondary)',
                backgroundColor: isActive ? 'var(--accent)' : 'transparent',
                boxShadow: isActive ? '0 2px 12px var(--accent-glow)' : 'none',
                transition: 'all var(--transition)',
                textDecoration: 'none',
                width: '100%',
              })}
            >
              {item.icon}
              {!collapsed && <span style={{ fontWeight: 500, fontSize: '0.9rem', whiteSpace: 'nowrap' }}>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div style={{
          marginTop: 'auto',
          paddingTop: '1rem',
          borderTop: '1px solid var(--glass-border)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
          width: '100%',
          alignItems: collapsed ? 'center' : 'stretch',
        }}>
          {!collapsed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--text-secondary)' }}>
              <div style={{ background: 'rgba(255,255,255,0.08)', padding: '0.4rem', borderRadius: '50%', flexShrink: 0 }}>
                <User size={14} />
              </div>
              <div style={{ fontSize: '0.85rem', overflow: 'hidden' }}>
                <div style={{ color: 'white', fontWeight: 600, whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{user?.username}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{user?.role}</div>
              </div>
            </div>
          )}

          <button
            onClick={logout}
            title={collapsed ? 'Sign Out' : undefined}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.4rem',
              width: '100%',
              background: 'transparent',
              border: '1px solid var(--glass-border)',
              color: 'var(--text-secondary)',
              padding: collapsed ? '0.6rem' : '0.6rem 0.875rem',
              borderRadius: '10px',
            }}
          >
            <LogOut size={15} />
            {!collapsed && <span style={{ fontSize: '0.85rem' }}>Sign Out</span>}
          </button>
        </div>
      </aside>

      <main className="main-content fade-in" style={{ animationDelay: '0.05s' }}>
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DashboardLayout.jsx
git commit -m "feat: implement collapsible sidebar with ThemeContext integration"
```

---

## Task 8: App.jsx — Wrap with ThemeProvider

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Add ThemeProvider import and wrap**

Replace `frontend/src/App.jsx` with:

```jsx
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Login from './pages/Login';
import Signup from './pages/Signup';
import DashboardLayout from './components/DashboardLayout';
import StreamView from './pages/StreamView';
import GalleryView from './pages/GalleryView';
import SettingsView from './pages/SettingsView';
import AlbumsView from './pages/AlbumsView';
import ResetPassword from './pages/ResetPassword';
import FrameView from './pages/FrameView';

const PrivateRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>Loading...</div>;
  }
  return user ? children : <Navigate to="/login" />;
};

function App() {
  return (
    <Router>
      <AuthProvider>
        <ThemeProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/frame" element={<FrameView />} />
            <Route path="/" element={
              <PrivateRoute>
                <DashboardLayout />
              </PrivateRoute>
            }>
              <Route index element={<Navigate to="/stream" replace />} />
              <Route path="stream" element={<StreamView />} />
              <Route path="gallery" element={<GalleryView />} />
              <Route path="albums" element={<AlbumsView />} />
              <Route path="settings" element={<SettingsView />} />
            </Route>
          </Routes>
        </ThemeProvider>
      </AuthProvider>
    </Router>
  );
}

export default App;
```

- [ ] **Step 2: Lint + build**

```bash
cd frontend && npm run lint && npm run build
```

Expected: no errors, build succeeds with output in `frontend/dist/`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: wrap app with ThemeProvider"
```

---

## Task 9: Final Verification

- [ ] **Step 1: Run backend schema tests**

```bash
env/bin/python -m pytest Tests/test_settings_schema.py -v
```

Expected: all pass.

- [ ] **Step 2: Full frontend lint + build**

```bash
cd frontend && npm run lint && npm run build
```

Expected: zero lint errors, clean build.

- [ ] **Step 3: Smoke test headless backend**

```bash
env/bin/python app.py --headless &
sleep 3
curl -s http://localhost:5002/api/settings/schema | python3 -c "import sys,json; s=json.load(sys.stdin); print('admin_ui' in s)"
kill %1
```

Expected: `True`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: frontend design refactor complete — frosted glass elevated, collapsible sidebar, theme settings"
```
