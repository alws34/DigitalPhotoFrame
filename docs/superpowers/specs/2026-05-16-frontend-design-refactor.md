# Frontend Design Refactor — Spec

## Goal
Refactor the React admin UI to a polished "Frosted Glass Elevated" aesthetic with user-selectable accent color and motion intensity, a collapsible sidebar, and zero loss of existing functionality.

## Decisions Made

| Decision | Choice |
|---|---|
| Design direction | Frosted Glass Elevated (dark #0d1117, glass panels, layered depth) |
| Sidebar | Collapsible: 240px labeled ↔ 48px icon rail, toggle persisted in settings |
| Accent color | User-selectable: indigo / sky / emerald / rose — stored in settings |
| Motion intensity | User-selectable: subtle (150ms ease-out) / cinematic (350ms spring) — stored in settings |
| Theme application | CSS custom properties injected to `:root` at runtime by ThemeProvider |
| Settings storage | New `admin_ui` top-level key in `SETTINGS_SCHEMA` + `photoframe_settings.example.json` |
| Settings UI | Visual swatch picker for accent color, pill toggle for motion, bool toggle for sidebar |
| Existing functionality | Fully preserved — design changes only |

## Constraint
**Do not remove, hide, or break any existing admin UI functionality** — Gallery, Albums, Stream, Settings, Login, Signup, Reset Password, FrameView all remain fully functional.

## New Settings Schema (`admin_ui`)

```python
"admin_ui": {
    "accent_color":      {"type": "enum", "label": "Accent Color",     "choices": ["indigo","sky","emerald","rose"], "restart_required": False, "ui": "color_theme"},
    "motion_intensity":  {"type": "enum", "label": "Motion Intensity", "choices": ["subtle","cinematic"],           "restart_required": False, "ui": "motion_select"},
    "sidebar_collapsed": {"type": "bool", "label": "Sidebar Collapsed",                                            "restart_required": False},
}
```

## CSS Token Map

### Accent colors
| Name | --accent | --accent-hover | --accent-glow |
|---|---|---|---|
| indigo | #6366f1 | #818cf8 | rgba(99,102,241,0.3) |
| sky | #0ea5e9 | #38bdf8 | rgba(14,165,233,0.3) |
| emerald | #059669 | #10b981 | rgba(5,150,105,0.3) |
| rose | #e11d48 | #f43f5e | rgba(225,29,72,0.3) |

### Motion
| Name | --transition | --transition-slow |
|---|---|---|
| subtle | 0.15s ease-out | 0.2s ease-out |
| cinematic | 0.3s cubic-bezier(0.34,1.56,0.64,1) | 0.4s ease |

## Component Interfaces

### ThemeContext
```jsx
// src/context/ThemeContext.jsx
export function ThemeProvider({ children }) { ... }
export function useTheme() {
  // returns:
  return {
    accent,           // "indigo" | "sky" | "emerald" | "rose"
    motionIntensity,  // "subtle" | "cinematic"
    sidebarCollapsed, // boolean
    setSidebarCollapsed, // (bool) => void  — optimistic local + server save
    saveAdminUiSetting,  // (key, value) => Promise<void>
  }
}
```

### ColorThemePicker
```jsx
// src/components/settings/ColorThemePicker.jsx
export default function ColorThemePicker({ value, onChange }) { ... }
// value: "indigo" | "sky" | "emerald" | "rose"
// onChange: (newValue) => void
```

### MotionSelect
```jsx
// src/components/settings/MotionSelect.jsx
export default function MotionSelect({ value, onChange }) { ... }
// value: "subtle" | "cinematic"
// onChange: (newValue) => void
```

## Files Touched

**New:**
- `frontend/src/context/ThemeContext.jsx`
- `frontend/src/components/settings/ColorThemePicker.jsx`
- `frontend/src/components/settings/MotionSelect.jsx`

**Modified:**
- `Utilities/config_store.py` — add `admin_ui` to SETTINGS_SCHEMA
- `photoframe_settings.example.json` — add `admin_ui` defaults
- `frontend/src/index.css` — swap hardcoded accent tokens → CSS vars, visual polish
- `frontend/src/App.jsx` — wrap with ThemeProvider
- `frontend/src/components/DashboardLayout.jsx` — collapsible sidebar
- `frontend/src/components/settings/SettingField.jsx` — add color_theme + motion_select cases

**Unchanged:** All page components, all backend routes, auth, image handling.
