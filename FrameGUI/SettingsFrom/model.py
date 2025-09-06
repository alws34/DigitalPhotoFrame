from __future__ import annotations
import json, os
from typing import Any, Dict, List, Tuple

class SettingsModel:
    """Thin model wrapper around the settings dict + helpers."""
    def __init__(self, settings: Dict[str, Any], settings_path: str | None = None):
        self._settings = settings
        self._path = settings_path

    # ---- basic access ----
    @property
    def data(self) -> Dict[str, Any]:
        return self._settings

    def save(self, path: str | None = None) -> None:
        out = path or self._path
        if not out:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            out = os.path.join(base_dir, "photoframe_settings.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=2)
        self._path = out

    # ---- screen helpers ----
    def ensure_screen_struct(self) -> Dict[str, Any]:
        scr = self._settings.setdefault("screen", {})
        scr.setdefault("orientation", "normal")
        scr.setdefault("brightness", 100)
        scr.setdefault("schedule_enabled", False)
        scr.setdefault("off_hour", 0)
        scr.setdefault("on_hour", 7)
        if "schedules" not in scr or not isinstance(scr["schedules"], list):
            scr["schedules"] = [{
                "enabled": False, "off_hour": 0, "on_hour": 7, "days": [0,1,2,3,4,5,6]
            }]
        return scr

    def mirror_first_enabled_schedule_to_legacy(self) -> None:
        scr = self.ensure_screen_struct()
        enabled = [s for s in scr.get("schedules", []) if s.get("enabled")]
        if enabled:
            first = enabled[0]
            scr["schedule_enabled"] = True
            scr["off_hour"] = int(first.get("off_hour", 0)) % 24
            scr["on_hour"]  = int(first.get("on_hour", 7)) % 24
        else:
            scr["schedule_enabled"] = False
