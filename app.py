import os
import sys
import argparse
import threading
from typing import Dict, Any, Optional

# Ensure local imports resolve
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from PySide6 import QtWidgets

# Conditional imports for logging and config if they exist
try:
    from logging_setup import init_logging
except ImportError:
    import logging
    def init_logging():
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

try:
    from config import load_settings
except ImportError:
    import json
    def load_settings(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

# Import the Qt View and the Server
from FrameGUI.photoframe_view_qt import PhotoFrameQtWidget
from FrameServer.PhotoFrameServer import PhotoFrameServer


def _resolve_settings_path(path_arg: str) -> str:
    """Resolve settings path to an absolute path."""
    if os.path.isabs(path_arg):
        return path_arg
    return os.path.abspath(os.path.join(BASE_DIR, path_arg))


def _headless_run(settings: Dict[str, Any], settings_path: str,
                  width: Optional[int], height: Optional[int]) -> None:
    """
    Start PhotoFrameServer without any GUI. Keep it running
    (blocking) similar to a service.
    """
    if width is None or height is None:
        backend = settings.get("backend_configs", {}) or {}
        width = width or int(backend.get("stream_width", 1920))
        height = height or int(backend.get("stream_height", 1080))

    images_dir = settings.get("image_dir") or settings.get("images_dir") or None

    print(f"[PhotoFrame] Headless mode. Resolution {width}x{height}. Settings: {settings_path}")
    m_weather_api = settings.get("open_meteo", {})
    print(f"[PhotoFrame] open_meteo present: {bool(m_weather_api)} lat={m_weather_api.get('latitude')} lon={m_weather_api.get('longitude')}")

    frame = PhotoFrameServer(
        width=width,
        height=height,
        iframe=None,                  # no GUI
        images_dir=images_dir,
        settings_path=settings_path,
    )
    frame.main()


def _gui_run(settings: Dict[str, Any], settings_path: str, args) -> None:
    """
    Start the Qt GUI and the backend PhotoFrameServer. This function now handles
    QApplication creation and screen detection.
    """
    # 1. Ensure only one QApplication instance exists.
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    # 2. Detect screen size. If none is found, fall back to headless mode.
    screen = app.primaryScreen()
    if not screen:
        print("[PhotoFrame] No display detected. Falling back to headless mode.")
        _headless_run(settings, settings_path, args.width, args.height)
        return

    screen_size = screen.size()
    screen_w, screen_h = screen_size.width(), screen_size.height()

    print(f"[PhotoFrame] Qt GUI mode. Screen {screen_w}x{screen_h}. Settings: {settings_path}")
    om = settings.get("open_meteo", {})
    print(f"[PhotoFrame] open_meteo present: {bool(om)} lat={om.get('latitude')} lon={om.get('longitude')}")

    # 3. Create the GUI window (the view)
    view = PhotoFrameQtWidget(settings=settings, settings_path=settings_path)
    view.resize(screen_w, screen_h)
    
    # 4. Create the backend server, passing the view as the iFrame interface
    server = PhotoFrameServer(
        width=screen_w,
        height=screen_h,
        iframe=view, # Link server to the Qt widget
        images_dir=settings.get("image_dir") or None,
        settings_path=settings_path,
    )

    # 5. Set up graceful shutdown
    app.aboutToQuit.connect(server.stop_services)
    
    # 6. Start the server's main logic in a background thread
    server_thread = threading.Thread(target=server.run_photoframe, daemon=True)
    server_thread.start()

    # 7. Show the window and start the Qt event loop
    view.showFullScreen()
    sys.exit(app.exec())


def main() -> None:
    init_logging()
    os.environ.setdefault("DISPLAY", ":0")

    parser = argparse.ArgumentParser(description="Digital Photo Frame")
    parser.add_argument(
        "--settings",
        default="photoframe_settings.json",
        help="Path to settings JSON file.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force headless mode (no GUI). Server + API still run.",
    )
    parser.add_argument(
        "--width", type=int, default=None, help="Override width in headless mode."
    )
    parser.add_argument(
        "--height", type=int, default=None, help="Override height in headless mode."
    )
    args = parser.parse_args()

    settings_path = _resolve_settings_path(args.settings)
    settings: Dict[str, Any] = load_settings(settings_path)

    if args.headless:
        _headless_run(settings, settings_path, args.width, args.height)
        return

    # A screen is assumed to exist, so we run the GUI.
    # _gui_run will handle the fallback to headless if no screen is detected.
    _gui_run(settings, settings_path, args)


if __name__ == "__main__":
    main()