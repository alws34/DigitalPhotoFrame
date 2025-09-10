#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Digital Photo Frame - Qt main (fullscreen frame; Settings at 800x600).
"""

from __future__ import annotations
import os
import sys
import json
import argparse
import threading
from typing import Any, Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

# QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
# QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DontUseNativeDialogs, True)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from WebAPI.API import Backend         
from Utilities.MQTT.mqtt_bridge import MqttBridge   

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
        print(f"[PhotoFrame] Failed to load settings '{path}': {e}", file=sys.stderr)
        return {}


def _apply_safe_theme(app: QtWidgets.QApplication) -> None:
    # Robust readable style regardless of system theme
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

    # Minimal stylesheet to prevent black-on-black
    app.setStyleSheet(
        "QWidget { background: #f5f5f5; color: #000; }"
        "QLineEdit, QComboBox, QTableWidget, QTableView { background: #fff; }"
        "QPushButton { background: #e6e6e6; border: 1px solid #c9c9c9; padding: 4px 8px; }"
        "QTabWidget::pane { border: 1px solid #cfcfcf; }"
        "QTabBar::tab { padding: 6px 10px; }"
    )


# ----------------------- Settings dialog sizing hook -----------------------

class _SettingsSizer(QtCore.QObject):
    """
    Event filter that forces SettingsDialog windows to 800x600 and centers them.
    This overrides any size the dialog tries to set in its own __init__.
    """
    def __init__(self, app: QtWidgets.QApplication):
        super().__init__(app)
        self._cls = None
        try:
            # Import lazily so missing modules don't crash headless
            from FrameGUI.SettingsFrom.dialog import SettingsDialog  # type: ignore
            self._cls = SettingsDialog
        except Exception:
            self._cls = None

    def eventFilter(self, obj: QtCore.QObject, ev: QtCore.QEvent) -> bool:
        if self._cls and isinstance(obj, self._cls):
            if ev.type() == QtCore.QEvent.Show:
                dlg: QtWidgets.QDialog = obj  # type: ignore
                # Force fixed 800x600 and center on the active screen
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
        return super().eventFilter(obj, ev)


# ------------------------------ runners ------------------------------

def _run_headless(settings: Dict[str, Any], settings_path: str,
                  width: Optional[int], height: Optional[int]) -> None:
    from FrameServer.PhotoFrameServer import PhotoFrameServer

    backend_cfg = settings.get("backend_configs", {}) or {}
    w = width or int(backend_cfg.get("stream_width", 1920))
    h = height or int(backend_cfg.get("stream_height", 1080))
    images_dir = settings.get("image_dir") or settings.get("images_dir") or None

    print(f"[PhotoFrame] Headless mode. Resolution {w}x{h}. Settings: {settings_path}")

    srv = PhotoFrameServer(width=w, height=h, iframe=None,
                           images_dir=images_dir, settings_path=settings_path)

    # Start HTTP backend ONCE and tie it to the producer
    backend = Backend(frame=srv, settings=settings,
                      image_dir=images_dir, settings_path=settings_path)
    threading.Thread(target=backend.start, daemon=True).start()
    srv.m_api = backend

    # compositor loop
    t = threading.Thread(target=srv.run_photoframe, daemon=True)
    t.start()

    # optional: MQTT if you need it headless
    # mqtt = MqttBridge(view=srv, settings=settings)
    # mqtt.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        try: srv.stop_services()
        except Exception: pass
        # try: mqtt.stop()
        # except Exception: pass


def _run_gui(settings: Dict[str, Any], settings_path: str) -> None:
    from FrameGUI.photoframe_view_qt import PhotoFrameQtWidget
    from FrameServer.PhotoFrameServer import PhotoFrameServer

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    _apply_safe_theme(app)

    sizer = _SettingsSizer(app)
    app.installEventFilter(sizer)

    screen = app.primaryScreen()
    if not screen:
        print("[PhotoFrame] No display detected. Falling back to headless mode.", file=sys.stderr)
        _run_headless(settings, settings_path, None, None)
        return

    avail = screen.availableGeometry()
    sw, sh = max(1, avail.width()), max(1, avail.height())

    # main UI
    view = PhotoFrameQtWidget(settings=settings, settings_path=settings_path)
    view.showFullScreen()

    images_dir = settings.get("image_dir") or settings.get("images_dir") or None

    # Producer owns frames; view is just the GUI sink
    srv = PhotoFrameServer(width=sw, height=sh, iframe=view,
                           images_dir=images_dir, settings_path=settings_path)

    # Start HTTP backend ONCE and tie it to the producer
    backend = Backend(frame=srv, settings=settings,
                      image_dir=images_dir, settings_path=settings_path)
    threading.Thread(target=backend.start, daemon=True).start()
    srv.m_api = backend

    # optional MQTT
    mqtt = MqttBridge(view=view, settings=settings)
    mqtt.start()

    # keep refs
    view.backend = backend
    view.mqtt = mqtt

    # graceful shutdown
    def _on_quit():
        try: mqtt.stop()
        except Exception: pass
        try: srv.stop_services()
        except Exception: pass
    app.aboutToQuit.connect(_on_quit)

    # compositor loop
    t = threading.Thread(target=srv.run_photoframe, daemon=True)
    t.start()

    qpa = os.environ.get("QT_QPA_PLATFORM", "(unset)")
    print(f"[PhotoFrame] GUI fullscreen {sw}x{sh}, QPA={qpa}")
    sys.exit(app.exec())


# ------------------------------- main -------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Digital Photo Frame")
    p.add_argument("--settings", default="photoframe_settings.json",
                   help="Path to settings JSON file.")
    p.add_argument("--headless", action="store_true",
                   help="Run without GUI (backend server only).")
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

    _run_gui(settings, settings_path)


if __name__ == "__main__":
    main()
