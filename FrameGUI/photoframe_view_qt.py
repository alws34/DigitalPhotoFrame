from __future__ import annotations

import os
import cv2
import numpy as np
import threading
import logging
import subprocess
from typing import Any, Dict, Optional, List
import sys
import shutil
import time
from PySide6 import QtCore, QtGui, QtWidgets

from iFrame import iFrame
import copy
from FrameGUI.SettingsFrom.model import SettingsModel
from FrameGUI.SettingsFrom.viewmodel import SettingsViewModel
from FrameGUI.SettingsFrom.dialog import SettingsDialog
from Utilities.brightness import set_brightness_percent
from Utilities.screen_scheduler import ScreenScheduler
from Utilities.autoupdate_utils import AutoUpdater

# New Components
from FrameGUI.widgets.image_canvas import ImageCanvas
from FrameGUI.widgets.overlay_panel import OverlayPanel
from FrameGUI.helpers.hardware_manager import HardwareManager
from FrameGUI.helpers.ui_factory import UIFactory


# ---------------------------------------------------------------------
# Metaclass to mix Qt widget and iFrame
# ---------------------------------------------------------------------

class IFrameQtWidgetMeta(type(QtWidgets.QWidget), type(iFrame)):
    pass


# ---------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------

class PhotoFrameQtWidget(QtWidgets.QWidget, iFrame, metaclass=IFrameQtWidgetMeta):
    dateTimeChanged = QtCore.Signal(str)
    frameChanged = QtCore.Signal(QtGui.QImage)
    weatherChanged = QtCore.Signal(object)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None,
                 settings: Dict[str, Any] = None, settings_path: str = None):
        super().__init__(parent)
        self.settings = settings or {}
        self.settings_path = settings_path

        self.setWindowTitle("Digital Photo Frame (Qt)")
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("background-color: black;")
        self.setCursor(QtCore.Qt.BlankCursor)

        # Image canvas + overlay stacked
        self._stack = UIFactory.layout(QtWidgets.QStackedLayout, self, margins=(0,0,0,0))
        self.setLayout(self._stack)

        self._canvas = ImageCanvas(self)
        self._overlay = OverlayPanel(self, settings=self.settings)
        
        self._stack.addWidget(self._canvas)
        self._stack.addWidget(self._overlay)
        self._stack.setStackingMode(QtWidgets.QStackedLayout.StackAll)
        self._overlay.raise_()

        # Screen scheduler
        self._scheduler = ScreenScheduler(self, interval_ms=30000)
        self._scheduler.stateChanged.connect(
            lambda off: logging.info("ScreenScheduler: %s", "OFF" if off else "ON")
        )

        # AutoUpdater (Shared instance will be attached in app.py)
        self.autoupdater = None

        # Signals
        self.dateTimeChanged.connect(self._update_datetime_gui)
        self.frameChanged.connect(self._canvas.set_qimage)
        self.weatherChanged.connect(self._update_weather_gui)

        # Settings form state
        self._last_clicks: List[int] = []
        self._settings_vm = None
        self.backend_port = int(self.settings.get("backend_configs", {}).get("server_port", 5001))
        
        # --- Service Name lookup (system -> root -> default) ---
        sys_cfg = self.settings.get("system", {})
        self.service_name = sys_cfg.get("service_name") or self.settings.get("service_name") or "photoframe"

        self.screen_ctrl = None

        # Apply orientation after startup
        QtCore.QTimer.singleShot(800, self._apply_startup_orientation)

    def _backup_settings_files(self) -> Optional[str]:
        """Back up all JSON settings files before running an update."""
        try:
            cfg_path = getattr(self, "settings_path", None)
            if not cfg_path:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                cfg_path = os.path.join(base_dir, "photoframe_settings.json")

            cfg_path = os.path.abspath(cfg_path)
            cfg_dir = os.path.dirname(cfg_path)

            if not os.path.isdir(cfg_dir):
                return None

            backup_dir = os.path.join(cfg_dir, "config_backups")
            os.makedirs(backup_dir, exist_ok=True)

            ts = time.strftime("%Y%m%d-%H%M%S")
            logging.info("Backing up config JSONs from %s to %s (ts=%s)", cfg_dir, backup_dir, ts)

            for name in os.listdir(cfg_dir):
                if not name.lower().endswith(".json"):
                    continue
                src = os.path.join(cfg_dir, name)
                if not os.path.isfile(src):
                    continue
                dst = os.path.join(backup_dir, f"{name}.{ts}.bak")
                try:
                    shutil.copy2(src, dst)
                except Exception as e:
                    logging.exception("Failed to backup %s -> %s: %s", src, dst, e)

            return backup_dir

        except Exception:
            logging.exception("Config backup failed before update.")
            return None

    # -----------------------------------------------------------------
    # Public lifecycle
    # -----------------------------------------------------------------
    def stop(self) -> None:
        self.close()

    # -----------------------------------------------------------------
    # Input handling
    # -----------------------------------------------------------------
    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        now = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        self._last_clicks.append(now)
        self._last_clicks = self._last_clicks[-3:]

        # triple-tap within 800 ms
        if len(self._last_clicks) == 3 and (self._last_clicks[-1] - self._last_clicks[0] <= 800):
            try:
                sc = self.screen_ctrl
                is_off = False
                if sc and hasattr(sc, "is_off") and callable(sc.is_off):
                    is_off = bool(sc.is_off())
                if sc and is_off and hasattr(sc, "wake") and callable(sc.wake):
                    try:
                        sc.wake()
                    finally:
                        self._last_clicks.clear()
                        return
            except Exception as ex:
                logging.exception("Screen wake sequence failed: %s", ex)

            self._open_settings()
            self._last_clicks.clear()
            return

        super().mousePressEvent(e)

    # -----------------------------------------------------------------
    # Settings dialog
    # -----------------------------------------------------------------
    def _apply_live_settings(self, settings_data: Optional[Dict[str, Any]] = None) -> None:
        """Apply updated settings to live GUI components immediately."""
        if isinstance(settings_data, dict):
            self.settings = settings_data
        else:
            self.settings = {}

        # Keep overlay bound to the latest settings dict.
        try:
            if hasattr(self._overlay, "apply_settings") and callable(self._overlay.apply_settings):
                self._overlay.apply_settings(self.settings)
            else:
                self._overlay.settings = self.settings
                current_time = getattr(self._overlay, "_time_label", None)
                if current_time is not None:
                    self._overlay.update_time_and_date(current_time.text())
        except Exception:
            logging.exception("Failed to apply live overlay settings")

        # Refresh derived fields used by callbacks/actions.
        try:
            sys_cfg = self.settings.get("system", {})
            self.service_name = sys_cfg.get("service_name") or self.settings.get("service_name") or "photoframe"
        except Exception:
            pass
        try:
            backend_cfg = self.settings.get("backend_configs", {})
            self.backend_port = int(backend_cfg.get("server_port", self.backend_port))
        except Exception:
            pass

        # Apply screen settings immediately when edited from Config tab.
        try:
            scr = self.settings.get("screen", {}) if isinstance(self.settings, dict) else {}
            if isinstance(scr, dict):
                if "orientation" in scr:
                    trans_map = {
                        "0": "normal", "normal": "normal",
                        "90": "90", "left": "90",
                        "270": "270", "right": "270",
                        "180": "180", "inverted": "180",
                    }
                    transform = trans_map.get(str(scr.get("orientation", "normal")).strip().lower(), "normal")
                    HardwareManager.apply_orientation(transform)
                if "brightness" in scr:
                    HardwareManager.apply_brightness(self.screen_ctrl, int(scr.get("brightness", 100)))
        except Exception:
            logging.exception("Failed to apply live screen settings")

        try:
            self._scheduler.recheck_now()
        except Exception:
            pass

    def _open_settings(self) -> None:
        handler = getattr(self, "settings_handler", None)
        if not handler:
            # Fallback for direct testing
            from Settings import SettingsHandler
            handler = SettingsHandler(getattr(self, "settings_path", "photoframe_settings.json"), logging)

        # Always refresh from disk before opening the editor.
        try:
            handler.reload()
        except Exception:
            logging.exception("Failed to reload settings before opening dialog.")
        
        model = SettingsModel(copy.deepcopy(handler.data), handler.path)
        # Link model save to handler save and trigger immediate live reload.
        def _persist_settings(_path: str | None = None) -> None:
            handler.save(model.data)
            latest = handler.data if isinstance(handler.data, dict) else model.data
            self._apply_live_settings(latest)
            backend = getattr(self, "backend", None)
            if backend and hasattr(backend, "notify_settings_changed"):
                backend.notify_settings_changed()

        model.save = _persist_settings
        
        sc = self.screen_ctrl
        wake_cb = sc.wake if (sc and hasattr(sc, "wake") and callable(sc.wake)) else (lambda: None)

        vm = SettingsViewModel(
            model=model,
            backend_port=self.backend_port,
            on_apply_brightness=set_brightness_percent,
            on_apply_orientation=self._on_apply_orientation,
            on_autoupdate_pull=self._on_autoupdate_pull,
            on_restart_service_async=self._on_restart_service_async,
            wake_screen_worker=wake_cb,
            notifications=(self.notifications if hasattr(self, "notifications") else None),
            parent=self,
        )
        dlg = SettingsDialog(vm, model, parent=self)
        dlg.exec()

    # -----------------------------------------------------------------
    # iFrame API
    # -----------------------------------------------------------------
    def set_frame(self, bgr: np.ndarray) -> None:
        """Called by the server thread. Accept only proper uint8 images."""
        if bgr is None:
            return

        arr = np.asarray(bgr)
        # Type and Shape checks...
        if not isinstance(arr, np.ndarray) or arr.dtype == object:
            return
        if arr.ndim not in (2, 3):
            return

        try:
            if arr.ndim == 2:
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            elif arr.ndim == 3 and arr.shape[2] == 4:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        except cv2.error:
            return

        if arr.dtype != np.uint8:
            try:
                arr = arr.astype(np.uint8)
            except Exception:
                return

        try:
            rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        except cv2.error:
            return

        h, w = rgb.shape[:2]
        qimg = QtGui.QImage(rgb.data, w, h, QtGui.QImage.Format_RGB888)
        self.frameChanged.emit(qimg.copy())

    def set_date_time(self, dt_string: str) -> None:
        self.dateTimeChanged.emit(dt_string)

    def set_weather(self, weather_data: dict) -> None:
        self.weatherChanged.emit(weather_data or {})

    # -----------------------------------------------------------------
    # Qt slots
    # -----------------------------------------------------------------
    @QtCore.Slot(str)
    def _update_datetime_gui(self, text: str) -> None:
        self._overlay.update_time_and_date(text)

    @QtCore.Slot(object)
    def _update_weather_gui(self, weather_obj: dict) -> None:
        self._overlay.update_weather(weather_obj)

    # -----------------------------------------------------------------
    # Startup orientation
    # -----------------------------------------------------------------
    def _apply_startup_orientation(self) -> None:
        try:
            scr = (self.settings.get("screen") or {}) if "screen" in self.settings else {}
            transform = str(scr.get("orientation", "") or "").strip().lower()
            trans_map = {
                "0": "normal", "normal": "normal",
                "90": "90", "left": "90",
                "270": "270", "right": "270",
                "180": "180", "inverted": "180"
            }
            transform = trans_map.get(transform, "normal")
            
            # Using HardwareManager
            ok = HardwareManager.apply_orientation(transform)
            if not ok:
                logging.warning("Startup orientation apply failed: %s", transform)
        except Exception as e:
            logging.exception("Startup orientation crash: %s", e)

    # -----------------------------------------------------------------
    # Screen controller attach
    # -----------------------------------------------------------------
    def attach_screen_controller(self, controller) -> None:
        self.screen_ctrl = controller
        try:
            self._scheduler.recheck_now()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Hardware callbacks (forwarded to HardwareManager or local logic)
    # -----------------------------------------------------------------
    def _on_apply_brightness(self, pct: int) -> bool:
        ok = HardwareManager.apply_brightness(self.screen_ctrl, pct)
        if ok:
             handler = getattr(self, "settings_handler", None)
             if handler:
                 data = handler.data
                 data.setdefault("screen", {})["brightness"] = pct
                 handler.save(data)
                 latest = handler.data if isinstance(handler.data, dict) else data
                 self._apply_live_settings(latest)
        else:
             QtWidgets.QMessageBox.warning(self, "Brightness", "Screen controller not available.")
        return ok

    def _on_apply_orientation(self, transform: str) -> bool:
        ok = HardwareManager.apply_orientation(transform)
        if not ok and sys.platform == "linux":
            QtWidgets.QMessageBox.critical(self, "Failed to set orientation", "Check logs for details")
        return ok

    # -----------------------------------------------------------------
    # Auto-update / Restart Logic (kept here as it involves UI interaction/Threading)
    # -----------------------------------------------------------------
    def _on_autoupdate_pull(self) -> None:
        def worker():
            # 1) Backup
            try:
                self._backup_settings_files()
            except Exception:
                pass
            
            # 2) Updater
            ok, msg = False, "Unknown"
            try:
                if self.autoupdater:
                    ok, msg = self.autoupdater.pull_now()
            except Exception as e:
                ok, msg = False, str(e)

            # 3) Notify UI
            def ui():
                QtWidgets.QMessageBox.information(
                    self,
                    "Pull OK" if ok else "Pull failed",
                    str(msg)[:2000] if msg else ("Success" if ok else "Failed")
                )
            QtCore.QTimer.singleShot(0, ui)

        threading.Thread(target=worker, daemon=True).start()

    def _on_restart_service_async(self) -> None:
        def worker():
            unit = self.service_name + ".service"
            cmd = ["/usr/bin/systemctl", "restart", unit]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if r.returncode == 0:
                    QtCore.QTimer.singleShot(0, lambda: QtWidgets.QMessageBox.information(self, "Restart", f"Restarted {unit}. App exiting."))
                    QtCore.QTimer.singleShot(200, lambda: os._exit(0))
                else:
                    raise RuntimeError(r.stderr)
            except Exception as e:
                QtCore.QTimer.singleShot(0, lambda: QtWidgets.QMessageBox.critical(self, "Restart failed", str(e)))

        threading.Thread(target=worker, daemon=True).start()
