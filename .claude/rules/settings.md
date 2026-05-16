---
paths:
  - "Settings.py"
  - "photoframe_settings.example.json"
  - "photoframe_settings.json"
  - "WebAPI/routes/settings.py"
  - "FrameGUI/SettingsFrom/**/*"
  - "FrameGUI/widgets/overlay_panel.py"
  - "config.py"
---

# Settings Rules

- Treat `photoframe_settings.example.json` as the public shape/defaults reference.
- Treat `Settings.py` as the persistence/cache source of truth.
- When adding, renaming, or removing settings, update every layer that depends on them:
  - example/default JSON
  - settings load/save behavior
  - backend route handling
  - GUI/settings editor exposure
  - any frontend consumer or display
- Avoid one-sided settings changes that only update UI or only update persistence.
- Preserve backward-compatible defaults when feasible because deployed devices may carry older settings files.
