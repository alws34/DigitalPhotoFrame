---
paths:
  - "Utilities/config_store.py"
  - "photoframe_settings.example.json"
  - "photoframe_settings.json"
  - "WebAPI/routes/settings.py"
  - "FrameGUI/SettingsForm/**/*"
  - "FrameGUI/widgets/overlay_panel.py"
  - "frontend/src/pages/SettingsPage.jsx"
---

# Settings Rules

- Treat `photoframe_settings.example.json` as the public shape/defaults reference.
- Treat `Utilities/config_store.py` as the persistence/cache source of truth (SQLAlchemy + SQLite via `WebAPI/database.py`).
- When adding, renaming, or removing settings, update every layer that depends on them:
  - example/default JSON
  - settings load/save behavior in `config_store.py`
  - backend route handling in `WebAPI/routes/settings.py`
  - GUI/settings editor exposure in `FrameGUI/SettingsForm/`
  - frontend UI in `frontend/src/pages/SettingsPage.jsx`
- Avoid one-sided settings changes that only update UI or only update persistence.
- Preserve backward-compatible defaults when feasible because deployed devices may carry older settings files.
