import os
import sys
import json
import tkinter as tk
from typing import Dict, Any

# Ensure local imports resolve
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))

from logging_setup import init_logging
from config import load_settings
from photoframe_view import PhotoFrameView


def main() -> None:
    init_logging()
    os.environ.setdefault("DISPLAY", ":0")

    settings_path = os.path.join(BASE_DIR, "photoframe_settings.json")
    settings: Dict[str, Any] = load_settings(settings_path)

    root = tk.Tk()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    view = PhotoFrameView(
        root=root,
        settings=settings,
        desired_width=screen_w,
        desired_height=screen_h,
    )
    view.pack(fill="both", expand=True)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        view.stop()
        root.destroy()


if __name__ == "__main__":
    main()
