#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Digital Photo Frame - entry point.

Modes:
  --headless        Backend server only (no display)
  --display pygame  Lightweight fullscreen via pygame/SDL2 (default in Docker)
  (default)         PySide6/Qt fullscreen GUI (legacy, requires PySide6)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional

from Utilities.autoupdate_utils import AutoUpdater
from Utilities.MQTT.mqtt_bridge import MqttBridge
from WebAPI.API import Backend

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------ utilities ------------------------------


def _abs_path(p: str) -> str:
    return p if os.path.isabs(p) else os.path.abspath(os.path.join(BASE_DIR, p))


def _load_settings(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(
            f"[PhotoFrame] Failed to load settings '{path}': {e}", file=sys.stderr)
        return {}


# ------------------------------ runners ------------------------------


def _restart_program():
    """Restarts the current program. Note: Executable must be executable."""
    print("[PhotoFrame] Restarting...")
    python = sys.executable
    os.execl(python, python, *sys.argv)


def _run_headless(settings: Dict[str, Any], settings_path: str,
                  width: Optional[int], height: Optional[int]) -> None:
    from FrameServer.PhotoFrameServer import PhotoFrameServer

    backend_cfg = settings.get("backend_configs", {}) or {}
    w = width or int(backend_cfg.get("stream_width", 1920))
    h = height or int(backend_cfg.get("stream_height", 1080))

    sys_cfg = settings.get("system", {})
    images_dir = sys_cfg.get("image_dir") or settings.get(
        "image_dir") or settings.get("images_dir") or None

    print(
        f"[PhotoFrame] Headless mode. Resolution {w}x{h}. Settings: {settings_path}")

    # --- AutoUpdater Setup ---
    stop_event = threading.Event()
    au_cfg = settings.get("autoupdate", {})
    updater = AutoUpdater(
        stop_event=stop_event,
        interval_sec=3600,
        restart_service_async=_restart_program,
        auto_restart_on_update=au_cfg.get("enabled", True)
    )
    updater.start()

    srv = PhotoFrameServer(width=w, height=h, iframe=None,
                           images_dir=images_dir, settings_path=settings_path)

    backend = Backend(frame=srv, settings_handler=srv.settings_handler,
                      image_dir=images_dir, settings_path=settings_path)
    backend.updater = updater

    threading.Thread(target=backend.start, daemon=True).start()
    srv.m_api = backend

    t = threading.Thread(target=srv.run_photoframe, daemon=True)
    t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        try:
            srv.stop_services()
        except Exception:
            pass


def _run_pygame(settings: Dict[str, Any], settings_path: str) -> None:
    from FrameGUI.photoframe_view_pygame import PhotoFramePygame
    from FrameServer.PhotoFrameServer import PhotoFrameServer

    sys_cfg = settings.get("system", {})
    images_dir = sys_cfg.get("image_dir") or settings.get(
        "image_dir") or settings.get("images_dir") or None

    # Create the pygame display (detects screen resolution)
    view = PhotoFramePygame(settings=settings)
    sw, sh = view.width, view.height

    print(f"[PhotoFrame] Pygame display {sw}x{sh}. Settings: {settings_path}")

    # Create the compositor with the display as its frame target
    srv = PhotoFrameServer(width=sw, height=sh, iframe=view,
                           images_dir=images_dir, settings_path=settings_path)

    # Start Flask backend
    backend = Backend(frame=srv, settings_handler=srv.settings_handler,
                      image_dir=images_dir, settings_path=settings_path)
    threading.Thread(target=backend.start, daemon=True).start()
    srv.m_api = backend

    # AutoUpdater
    stop_event = threading.Event()
    au_cfg = settings.get("autoupdate", {})
    updater = AutoUpdater(
        stop_event=stop_event,
        interval_sec=1800,
        restart_service_async=_restart_program,
        auto_restart_on_update=au_cfg.get("enabled", True)
    )
    updater.start()
    backend.updater = updater

    # MQTT
    mqtt = MqttBridge(view=view, settings=settings)
    mqtt.start()

    # Start compositor in background thread
    t = threading.Thread(target=srv.run_photoframe, daemon=True)
    t.start()

    print(f"[PhotoFrame] Running. Admin UI at http://0.0.0.0:"
          f"{settings.get('backend_configs', {}).get('server_port', 5002)}")

    # Main loop: process SDL events and render frames
    # pygame requires display updates from the main thread
    try:
        while view.get_is_running() and srv.get_is_running():
            if not view.process_events():
                break
            view.render_pending_frame()
            time.sleep(0.016)  # ~60 Hz event polling
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        try:
            mqtt.stop()
        except Exception:
            pass
        try:
            srv.stop_services()
        except Exception:
            pass
        try:
            view.stop()
        except Exception:
            pass


def _run_gui(settings: Dict[str, Any], settings_path: str) -> None:
    from PySide6 import QtCore, QtGui, QtWidgets
    from FrameGUI.photoframe_view_qt import PhotoFrameQtWidget
    from FrameServer.PhotoFrameServer import PhotoFrameServer

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DontUseNativeDialogs, True)

    # ----------------------- Theme helper -----------------------
    def _apply_safe_theme(app: QtWidgets.QApplication) -> None:
        try:
            app.setStyle("Fusion")
        except Exception:
            pass

        pal = app.palette()
        pal.setColor(QtGui.QPalette.Window,           QtGui.QColor(245, 245, 245))
        pal.setColor(QtGui.QPalette.WindowText,       QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Base,             QtGui.QColor(255, 255, 255))
        pal.setColor(QtGui.QPalette.AlternateBase,    QtGui.QColor(240, 240, 240))
        pal.setColor(QtGui.QPalette.Text,             QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Button,           QtGui.QColor(230, 230, 230))
        pal.setColor(QtGui.QPalette.ButtonText,       QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Highlight,        QtGui.QColor(0, 120, 215))
        pal.setColor(QtGui.QPalette.HighlightedText,  QtCore.Qt.white)
        app.setPalette(pal)

        app.setStyleSheet(
            "QWidget { background: #f5f5f5; color: #000; }"
            "QLineEdit, QComboBox, QTableWidget, QTableView { background: #fff; }"
            "QPushButton { background: #e6e6e6; border: 1px solid #c9c9c9; padding: 4px 8px; }"
            "QTabWidget::pane { border: 1px solid #cfcfcf; }"
            "QTabBar::tab { padding: 6px 10px; }"
        )

    # ----------------------- Settings dialog sizing hook -----------------------
    class _SettingsSizer(QtCore.QObject):
        def __init__(self, app: QtWidgets.QApplication):
            super().__init__(app)
            self._cls = None
            try:
                from FrameGUI.SettingsFrom.dialog import SettingsDialog
                self._cls = SettingsDialog
            except Exception:
                self._cls = None

        def eventFilter(self, obj: QtCore.QObject, ev: QtCore.QEvent) -> bool:
            if ev.type() == QtCore.QEvent.Show:
                if self._cls and isinstance(obj, self._cls):
                    dlg: QtWidgets.QDialog = obj
                    dlg.setMinimumSize(800, 600)
                    dlg.setMaximumSize(800, 600)
                    dlg.resize(800, 600)
                    try:
                        screen = dlg.screen() or QtWidgets.QApplication.primaryScreen()
                        if screen:
                            geo = screen.availableGeometry()
                            x = geo.x() + (geo.width() - 800) // 2
                            y = geo.y() + (geo.height() - 600) // 2
                            dlg.move(max(geo.x(), x), max(geo.y(), y))
                    except Exception:
                        pass
            return False

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    _apply_safe_theme(app)

    sizer = _SettingsSizer(app)
    app.installEventFilter(sizer)

    screen = app.primaryScreen()
    if not screen:
        print(
            "[PhotoFrame] No display detected. Falling back to headless mode.", file=sys.stderr)
        _run_headless(settings, settings_path, None, None)
        return

    avail = screen.availableGeometry()
    sw, sh = max(1, avail.width()), max(1, avail.height())

    view = PhotoFrameQtWidget(settings=settings, settings_path=settings_path)
    view.showFullScreen()

    sys_cfg = settings.get("system", {})
    images_dir = sys_cfg.get("image_dir") or settings.get(
        "image_dir") or settings.get("images_dir") or None

    srv = PhotoFrameServer(width=sw, height=sh, iframe=view,
                           images_dir=images_dir, settings_path=settings_path)

    backend = Backend(frame=srv, settings_handler=srv.settings_handler,
                      image_dir=images_dir, settings_path=settings_path)
    threading.Thread(target=backend.start, daemon=True).start()
    srv.m_api = backend

    # --- AutoUpdater Setup ---
    stop_event = threading.Event()
    au_cfg = settings.get("autoupdate", {})
    updater = AutoUpdater(
        stop_event=stop_event,
        interval_sec=1800,
        restart_service_async=_restart_program,
        auto_restart_on_update=au_cfg.get("enabled", True)
    )
    updater.start()

    mqtt = MqttBridge(view=view, settings=settings)
    mqtt.start()

    view.backend = backend
    view.mqtt = mqtt
    view.updater = updater
    view.settings_handler = srv.settings_handler

    def _on_quit():
        stop_event.set()
        try:
            mqtt.stop()
        except Exception:
            pass
        try:
            srv.stop_services()
        except Exception:
            pass
    app.aboutToQuit.connect(_on_quit)

    t = threading.Thread(target=srv.run_photoframe, daemon=True)
    t.start()

    qpa = os.environ.get("QT_QPA_PLATFORM", "(unset)")
    print(f"[PhotoFrame] GUI fullscreen {sw}x{sh}, QPA={qpa}")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec())


# ------------------------------- main -------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Digital Photo Frame")
    p.add_argument("--settings", default="photoframe_settings.json",
                   help="Path to settings JSON file.")
    p.add_argument("--headless", action="store_true",
                   help="Run without GUI (backend server only).")
    p.add_argument("--display", choices=["pygame", "qt"],
                   help="Display backend: pygame (lightweight) or qt (PySide6).")
    p.add_argument("--width", type=int, default=None,
                   help="Headless mode: override stream width.")
    p.add_argument("--height", type=int, default=None,
                   help="Headless mode: override stream height.")
    args = p.parse_args()

    settings_path = _abs_path(args.settings)
    settings = _load_settings(settings_path)

    if args.headless:
        _run_headless(settings, settings_path, args.width, args.height)
        return

    if args.display == "pygame":
        _run_pygame(settings, settings_path)
        return

    if args.display == "qt":
        _run_gui(settings, settings_path)
        return

    # Default: try pygame first (lighter), fall back to Qt
    try:
        import pygame  # noqa: F401
        _run_pygame(settings, settings_path)
    except ImportError:
        _run_gui(settings, settings_path)


if __name__ == "__main__":
    main()
