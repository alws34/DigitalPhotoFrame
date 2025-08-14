import json
from typing import Dict, Any


def load_settings(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        settings = json.load(f)
    # Provide sane defaults that downstream code expects
    settings.setdefault("backend_configs", {})
    settings["backend_configs"].setdefault("host", "localhost")
    settings["backend_configs"].setdefault("server_port", 5001)

    settings.setdefault("screen", {
        "orientation": "normal",
        "brightness": 100,
        "schedule_enabled": False,
        "off_hour": 0,
        "on_hour": 7,
    })

    settings.setdefault("autoupdate", {
        "enabled": True,
        "hour": 4,
        "minute": 0,
        "repo_path": "",
        "remote": "origin",
        "branch": None,
    })

    settings.setdefault("stats", {
        "font_size": 20,
        "font_color": "yellow",
    })

    settings.setdefault("margin_left", 50)
    settings.setdefault("margin_bottom", 50)
    settings.setdefault("spacing_between", 10)
    settings.setdefault("margin_right", 50)
    return settings
