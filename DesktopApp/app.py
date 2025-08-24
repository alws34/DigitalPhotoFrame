import os
import sys
import json
import argparse
import tkinter as tk
from typing import Dict, Any

# Ensure local imports resolve
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))

from logging_setup import init_logging
from config import load_settings
from FrameGUI.photoframe_view import PhotoFrameView


def main() -> None:
    init_logging()
    os.environ.setdefault("DISPLAY", ":0")

    # CLI: allow absolute path to settings.json
    parser = argparse.ArgumentParser(description="Digital Photo Frame (GUI)")
    parser.add_argument(
        "--settings",
        default=os.path.join(BASE_DIR, "photoframe_settings.json"),
        help="Absolute path to settings JSON (default: photoframe_settings.json next to app.py)",
    )
    args = parser.parse_args()

    # Resolve to absolute path if a relative path was passed
    settings_path = args.settings
    if not os.path.isabs(settings_path):
        settings_path = os.path.abspath(os.path.join(BASE_DIR, settings_path))

    # Load settings for the GUI layer (server will also get settings_path explicitly)
    settings: Dict[str, Any] = load_settings(settings_path)

    # Helpful diagnostics in logs
    print(f"[PhotoFrame] Using settings file: {settings_path}")
    om = settings.get("open_meteo", {})
    print(f"[PhotoFrame] open_meteo present: {bool(om)} lat={om.get('latitude')} lon={om.get('longitude')}")

    root = tk.Tk()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    view = PhotoFrameView(
        root=root,
        settings=settings,
        desired_width=screen_w,
        desired_height=screen_h,
        settings_path=settings_path,  # <-- pass through to the backend server
    )
    view.pack(fill="both", expand=True)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        view.stop()
        root.destroy()


if __name__ == "__main__":
    main()
