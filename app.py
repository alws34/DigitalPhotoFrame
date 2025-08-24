import os
import sys
import argparse
import tkinter as tk
from typing import Dict, Any, Optional

# Ensure local imports resolve
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))

from logging_setup import init_logging
from config import load_settings
from FrameGUI.photoframe_view import PhotoFrameView
from FrameServer.PhotoFrameServer import PhotoFrameServer


def _resolve_settings_path(path_arg: str) -> str:
    """Resolve settings path to an absolute path."""
    if os.path.isabs(path_arg):
        return path_arg
    return os.path.abspath(os.path.join(BASE_DIR, path_arg))


def _detect_screen_size() -> Optional[tuple[int, int]]:
    """
    Try to start Tk to probe screen size. Return (w, h) or None if no display.
    We do not keep Tk running here; just probe and destroy.
    """
    try:
        root = tk.Tk()
        # Avoid showing a window during probe
        root.withdraw()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.destroy()
        return (int(w), int(h))
    except Exception:
        return None


def _headless_run(settings: Dict[str, Any], settings_path: str,
                  width: Optional[int], height: Optional[int]) -> None:
    """
    Start PhotoFrameServer without any GUI. Keep it running
    (blocking) similar to a service.
    """
    # Derive resolution:
    if width is None or height is None:
        # Prefer backend_configs if present
        backend = settings.get("backend_configs", {}) or {}
        width = width or int(backend.get("stream_width", 1920))
        height = height or int(backend.get("stream_height", 1080))

    # Images directory from settings (if present)
    images_dir = settings.get("image_dir") or settings.get("images_dir") or None

    print(f"[PhotoFrame] Headless mode. Resolution {width}x{height}. Settings: {settings_path}")
    om = settings.get("open_meteo", {})
    print(f"[PhotoFrame] open_meteo present: {bool(om)} lat={om.get('latitude')} lon={om.get('longitude')}")

    # Start the backend server. PhotoFrameServer.main() will start:
    # - compositor thread (30 fps loop)
    # - API backend thread
    # - weather updater
    # and then block in a loop until KeyboardInterrupt.
    frame = PhotoFrameServer(
        width=width,
        height=height,
        iframe=None,                  # no GUI
        images_dir=images_dir,
        settings_path=settings_path,  # absolute path
    )
    frame.main()  # blocks, acts like a service


def _gui_run(settings: Dict[str, Any], settings_path: str) -> None:
    """
    Start Tk GUI and GUI-owned backend.
    """
    root = tk.Tk()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    print(f"[PhotoFrame] GUI mode. Screen {screen_w}x{screen_h}. Settings: {settings_path}")
    om = settings.get("open_meteo", {})
    print(f"[PhotoFrame] open_meteo present: {bool(om)} lat={om.get('latitude')} lon={om.get('longitude')}")

    view = PhotoFrameView(
        root=root,
        settings=settings,
        desired_width=screen_w,
        desired_height=screen_h,
        settings_path=settings_path,  # forwarded to backend server
    )
    view.pack(fill="both", expand=True)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        # Graceful shutdown
        try:
            view.stop()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass


def main() -> None:
    init_logging()
    # Make sure DISPLAY is set for environments where X is available but not exported
    os.environ.setdefault("DISPLAY", ":0")

    parser = argparse.ArgumentParser(description="Digital Photo Frame")
    parser.add_argument(
        "--settings",
        default=os.path.join(BASE_DIR, "photoframe_settings.json"),
        help="Absolute path to settings JSON (default: photoframe_settings.json next to app.py)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force headless mode (no Tk). Server + API still run.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Override width in headless mode (else uses backend_configs.stream_width or 1920).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="Override height in headless mode (else uses backend_configs.stream_height or 1080).",
    )
    args = parser.parse_args()

    settings_path = _resolve_settings_path(args.settings)
    settings: Dict[str, Any] = load_settings(settings_path)

    # If user forced headless, just run headless.
    if args.headless:
        _headless_run(settings, settings_path, args.width, args.height)
        return

    # Try GUI; if no screen, fall back to headless automatically.
    size = _detect_screen_size()
    if size is None:
        print("[PhotoFrame] No display detected. Falling back to headless mode.")
        _headless_run(settings, settings_path, args.width, args.height)
        return

    # We have a screen: run GUI mode.
    _gui_run(settings, settings_path)


if __name__ == "__main__":
    main()
