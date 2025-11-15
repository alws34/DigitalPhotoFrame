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

from PySide6 import QtCore, QtGui, QtWidgets

# Optional SVG
try:
    from PySide6.QtSvg import QSvgRenderer  # noqa: F401
    _HAS_SVG = True
except Exception:
    _HAS_SVG = False

# Optional PIL support
try:
    from PIL import Image  # noqa: F401
    from PIL.ImageQt import ImageQt  # noqa: F401
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

from iFrame import iFrame
from FrameGUI.SettingsFrom.model import SettingsModel
from FrameGUI.SettingsFrom.viewmodel import SettingsViewModel
from FrameGUI.SettingsFrom.dialog import SettingsDialog
from Utilities.brightness import set_brightness_percent
from Utilities.screen_scheduler import ScreenScheduler
from Utilities.autoupdate_utils import AutoUpdater


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def cv2_to_rgb_bytes(bgr: np.ndarray) -> bytes:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb.tobytes()


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
        self._stack = QtWidgets.QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
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

        # AutoUpdater
        self._update_stop_evt = threading.Event()
        self.autoupdater = AutoUpdater(
            stop_event=self._update_stop_evt,
            interval_sec=1800,  # every 30m
            on_update_available=lambda n: logging.info("AutoUpdater: %d commits behind", n),
            on_updated=lambda out: logging.info("AutoUpdater log:\n%s", out),
            restart_service_async=self._on_restart_service_async,
            min_restart_interval_sec=900,
            auto_restart_on_update=True,
        )
        self.autoupdater.start()

        # Signals
        self.dateTimeChanged.connect(self._update_datetime_gui)
        self.frameChanged.connect(self._canvas.set_qimage)
        self.weatherChanged.connect(self._update_weather_gui)

        # Settings form state
        self._last_clicks: List[int] = []
        self._settings_vm = None
        self.backend_port = int(self.settings.get("backend_configs", {}).get("server_port", 5001))
        self.service_name = self.settings.get("service_name", "photoframe")

        # IMPORTANT: do NOT grab QWidget.screen(). Keep None until caller attaches a real controller.
        self.screen_ctrl = None

        # Apply orientation after startup
        QtCore.QTimer.singleShot(800, self._apply_startup_orientation)

    # -----------------------------------------------------------------
    # Public lifecycle
    # -----------------------------------------------------------------
    def stop(self) -> None:
        try:
            if hasattr(self, "_update_stop_evt"):
                self._update_stop_evt.set()
        except Exception:
            pass
        self.close()

    # -----------------------------------------------------------------
    # Input handling
    # -----------------------------------------------------------------
    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        # record tap time (ms since midnight)
        now = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        self._last_clicks.append(now)
        self._last_clicks = self._last_clicks[-3:]

        # triple-tap within 800 ms
        if len(self._last_clicks) == 3 and (self._last_clicks[-1] - self._last_clicks[0] <= 800):
            # If panel is off and we have a controller, wake it
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

            # Otherwise open settings
            self._open_settings()
            self._last_clicks.clear()
            return

        super().mousePressEvent(e)

    # -----------------------------------------------------------------
    # Settings dialog
    # -----------------------------------------------------------------
    def _open_settings(self) -> None:
        model = SettingsModel(self.settings, getattr(self, "settings_path", None))

        # Safely pass optional callbacks
        sc = self.screen_ctrl
        if sc and hasattr(sc, "wake") and callable(sc.wake):
            wake_cb = sc.wake
        else:
            wake_cb = (lambda: None)

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
        """
        Called by the server thread. Accept only proper uint8 images and
        guard against dtype=object or other weird inputs.
        """
        if bgr is None:
            logging.warning("PhotoFrameQtWidget.set_frame: got None frame")
            return

        # Normalize to numpy array
        arr = np.asarray(bgr)
        logging.debug(
            "PhotoFrameQtWidget.set_frame: type=%s, dtype=%s, shape=%s",
            type(bgr),
            getattr(arr, "dtype", None),
            getattr(arr, "shape", None),
        )

        # Reject completely invalid stuff
        if not isinstance(arr, np.ndarray):
            logging.error("PhotoFrameQtWidget.set_frame: non-ndarray frame: %r", type(arr))
            return

        if arr.dtype == object:
            logging.error(
                "PhotoFrameQtWidget.set_frame: bad dtype=object, shape=%s, skipping frame",
                arr.shape,
            )
            return

        if arr.ndim not in (2, 3):
            logging.error(
                "PhotoFrameQtWidget.set_frame: unexpected ndim=%d, shape=%s",
                arr.ndim,
                arr.shape,
            )
            return

        # Gray or BGRA -> BGR
        try:
            if arr.ndim == 2:
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            elif arr.ndim == 3 and arr.shape[2] == 4:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        except cv2.error as e:
            logging.exception("PhotoFrameQtWidget.set_frame: cvtColor (to BGR) failed: %s", e)
            return

        # Ensure uint8
        if arr.dtype != np.uint8:
            try:
                arr = arr.astype(np.uint8)
            except Exception as e:
                logging.exception(
                    "PhotoFrameQtWidget.set_frame: cannot cast dtype %s to uint8: %s",
                    arr.dtype,
                    e,
                )
                return

        # Now convert to RGB for Qt
        try:
            rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        except cv2.error as e:
            logging.exception("PhotoFrameQtWidget.set_frame: cvtColor BGR->RGB failed: %s", e)
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
            scr = {}
            if isinstance(self.settings, dict):
                scr = (self.settings.get("screen") or {}) if "screen" in self.settings else {}

            transform = str(scr.get("orientation", "") or "").strip().lower()
            trans_map = {
                "0": "normal", "normal": "normal",
                "90": "90", "left": "90",
                "270": "270", "right": "270",
                "180": "180", "inverted": "180"
            }
            transform = trans_map.get(transform, "normal")
            ok = self._on_apply_orientation(transform)
            if not ok:
                logging.warning("Startup orientation apply failed: %s", transform)
        except Exception as e:
            logging.exception("Startup orientation crash: %s", e)

    # -----------------------------------------------------------------
    # Screen controller attach
    # -----------------------------------------------------------------
    def attach_screen_controller(self, controller) -> None:
        """
        Call this after creating the widget to wire the ScreenController.
        The controller may expose:
          - is_off() -> bool
          - wake() -> None
          - set_brightness_percent(pct:int, allow_zero:bool=False) -> bool
        """
        self.screen_ctrl = controller
        try:
            self._scheduler.recheck_now()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Utilities for settings form
    # -----------------------------------------------------------------
    @staticmethod
    def _list_outputs() -> list[str]:
        try:
            out = subprocess.check_output(
                ["wlr-randr"], universal_newlines=True,
                stderr=subprocess.DEVNULL, timeout=3
            )
        except Exception:
            return []
        names: list[str] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith(" "):
                continue
            name = line.split()[0]
            if name not in names:
                names.append(name)
        return names

    def _pick_default_output(self) -> Optional[str]:
        outs = self._list_outputs()
        outs.sort(key=lambda n: (0 if n.upper().startswith("DSI") else 1, n))
        return outs[0] if outs else None

    # ---- Brightness ----
    def _on_apply_brightness(self, pct: int) -> bool:
        try:
            pct = max(10, min(100, int(pct)))
            sc = self.screen_ctrl
            if not sc or not hasattr(sc, "set_brightness_percent") or not callable(sc.set_brightness_percent):
                QtWidgets.QMessageBox.warning(self, "Brightness", "Screen controller not available.")
                return False
            ok = sc.set_brightness_percent(pct, allow_zero=False)
            if ok:
                self.settings.setdefault("screen", {})["brightness"] = pct
            return bool(ok)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Brightness error", str(e))
            return False

    # ---- Orientation ----
    def _on_apply_orientation(self, transform: str) -> bool:
        """
        On Linux/Wayland, call wlr-randr to rotate the display.
        On other platforms this is a no-op so the app runs everywhere.
        """
        # Non-Linux platforms: ignore and pretend success.
        # We do NOT want message boxes on macOS/Windows.
        if sys.platform != "linux":
            logging.info("Orientation change (%s) ignored on non-Linux platform.", transform)
            return True

        # Linux but no wlr-randr in PATH: also ignore quietly.
        if shutil.which("wlr-randr") is None:
            logging.warning("wlr-randr not found in PATH; skippƒ√ing orientation change.")
            return True

        output = self._pick_default_output()
        if not output:
            # No Wayland outputs reported. Log, but do not block the app.
            logging.warning("No Wayland outputs reported by wlr-randr; skipping orientation change.")
            return True

        try:
            subprocess.run(
                ["wlr-randr", "--output", output, "--transform", transform],
                check=True,
            )
            logging.info("Orientation set to %s on output %s", transform, output)
            return True
        except subprocess.CalledProcessError as e:
            logging.exception("Failed to set orientation via wlr-randr: %s", e)
            # On Linux kiosk you might want the error dialog; keep it,
            # but it will never be hit on macOS/Windows.
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to set orientation",
                (e.stdout or str(e))[:2000],
            )
            return False

    # ---- Auto-update (pull now) ----
    def _on_autoupdate_pull(self) -> None:
        def worker():
            ok, msg = False, "Unknown"
            try:
                if not hasattr(self, "autoupdater") or self.autoupdater is None:
                    raise RuntimeError("AutoUpdater not available.")
                ok, msg = self.autoupdater.pull_now()
            except Exception as e:
                ok, msg = False, f"pull_now() crashed: {e}"

            try:
                if hasattr(self, "notifications") and self.notifications:
                    self.notifications.add(
                        f"Manual update {'succeeded' if ok else 'failed'}: {msg}",
                        level=("update" if ok else "error")
                    )
            except Exception:
                pass

            def ui():
                QtWidgets.QMessageBox.information(
                    self,
                    "Pull OK" if ok else "Pull failed",
                    str(msg)[:2000] if msg else ("Success" if ok else "Failed")
                )
            QtCore.QTimer.singleShot(0, ui)

        threading.Thread(target=worker, daemon=True).start()

    # ---- Restart service (async) ----
    def _on_restart_service_async(self) -> None:
        def worker():
            unit = "PhotoFrame_Desktop_App.service"  # adjust if needed
            systemctl = "/usr/bin/systemctl"
            cmd = [systemctl, "restart", unit]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            except Exception as e:
                def ui_err():
                    QtWidgets.QMessageBox.critical(self, "Restart failed", f"{' '.join(cmd)}\nerror: {e}")
                return QtCore.QTimer.singleShot(0, ui_err)

            if r.returncode == 0:
                def ui_ok():
                    try:
                        QtWidgets.QMessageBox.information(self, "Restart", f"Restarted {unit}. The app will exit now.")
                    except Exception:
                        pass
                    QtCore.QTimer.singleShot(200, lambda: os._exit(0))
                QtCore.QTimer.singleShot(0, ui_ok)
            else:
                def ui_err():
                    QtWidgets.QMessageBox.critical(
                        self, "Restart failed",
                        f"{' '.join(cmd)}\nstdout:\n{r.stdout}\n\nstderr:\n{r.stderr}"
                    )
                QtCore.QTimer.singleShot(0, ui_err)

        threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------

class ImageCanvas(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._qimage: Optional[QtGui.QImage] = None
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    @QtCore.Slot(QtGui.QImage)
    def set_qimage(self, qimage: QtGui.QImage) -> None:
        self._qimage = qimage
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QtCore.Qt.black)

        if self._qimage is None or self._qimage.isNull():
            return

        iw = self._qimage.width()
        ih = self._qimage.height()
        ww = self.width()
        wh = self.height()
        if iw <= 0 or ih <= 0 or ww <= 0 or wh <= 0:
            return

        image_ar = iw / float(ih)
        widget_ar = ww / float(wh)

        if widget_ar > image_ar:
            new_h = int(round(iw / widget_ar))
            new_h = min(new_h, ih)
            y = max(0, (ih - new_h) // 2)
            src = QtCore.QRect(0, y, iw, new_h)
        else:
            new_w = int(round(ih * widget_ar))
            new_w = min(new_w, iw)
            x = max(0, (iw - new_w) // 2)
            src = QtCore.QRect(x, 0, new_w, ih)

        painter.drawImage(self.rect(), self._qimage, src)


# ---------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------

class OverlayPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, settings: Dict[str, Any] = None):
        super().__init__(parent)
        self.settings = settings or {}

        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Settings (font + margins)
        self.font_name = self.settings.get("font_name", "Arial")
        self.time_px = int(self.settings.get("time_font_size", 120))
        self.date_px = int(self.settings.get("date_font_size", 80))
        self.ml = int(self.settings.get("margin_left", 50))
        self.mr = int(self.settings.get("margin_right", 50))
        self.mb = int(self.settings.get("margin_bottom", 50))
        self.mt = int(self.settings.get("margin_top", self.mb))

        dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()
        self.shadow_alpha = int(self.settings.get("shadow_alpha", 200))
        self.shadow_color = QtGui.QColor(0, 0, 0, self.shadow_alpha)

        self._maybe_load_font(self.font_name)

        # Time + Date
        self._time_label = QtWidgets.QLabel("00:00:00")
        self._date_label = QtWidgets.QLabel("-")
        for lbl in (self._time_label, self._date_label):
            lbl.setStyleSheet("color: white;")
            lbl.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

        self._apply_font(self._time_label, self.time_px, bold=True)
        self._apply_font(self._date_label, self.date_px, bold=False)

        f = self._time_label.font()
        f.setKerning(False)
        f.setStyleHint(QtGui.QFont.Monospace, QtGui.QFont.PreferDefault)
        f.setFixedPitch(True)
        self._time_label.setFont(f)
        if not QtGui.QFontInfo(self._time_label.font()).fixedPitch():
            mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
            mono.setPixelSize(self.time_px)
            mono.setBold(True)
            mono.setKerning(False)
            self._time_label.setFont(mono)

        fm_time = QtGui.QFontMetrics(self._time_label.font())
        max_time_text = "88:88:88"
        fixed_w = fm_time.horizontalAdvance(max_time_text)
        self._time_label.setFixedWidth(fixed_w)
        self._time_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)

        self._time_shadow_r = int(max(12, self.time_px * 0.18) * dpr)
        self._time_shadow_dx = int(max(2, self.time_px * 0.04) * dpr)
        self._time_shadow_dy = self._time_shadow_dx
        self._date_shadow_r = int(max(10, self.date_px * 0.16) * dpr)
        self._date_shadow_dx = int(max(2, self.date_px * 0.035) * dpr)
        self._date_shadow_dy = self._date_shadow_dx

        pad_time = self._time_shadow_r // 3
        pad_date = self._date_shadow_r // 3
        self._time_label.setContentsMargins(pad_time, pad_time, pad_time, pad_time)
        self._date_label.setContentsMargins(pad_date, pad_date, pad_date, pad_date)
        self._apply_shadow(self._time_label, self._time_shadow_r, self._time_shadow_dx, self._time_shadow_dy)
        self._apply_shadow(self._date_label, self._date_shadow_r, self._date_shadow_dx, self._date_shadow_dy)

        left_box = QtWidgets.QVBoxLayout()
        left_box.setSpacing(max(8, self.date_px // 6))
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.addWidget(self._time_label, 0, QtCore.Qt.AlignHCenter)
        left_box.addWidget(self._date_label, 0, QtCore.Qt.AlignHCenter)

        self._left_widget = QtWidgets.QWidget()
        self._left_widget.setLayout(left_box)
        self._left_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self._left_widget.setStyleSheet("background: transparent;")

        # Weather (bottom-right)
        self.weather_num_px = self.time_px
        self.weather_desc_px = self.date_px

        self._weather_num = QtWidgets.QLabel("")
        self._weather_num.setStyleSheet("color: white;")
        self._weather_num.setAlignment(QtCore.Qt.AlignHCenter)
        self._weather_num.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self._apply_font(self._weather_num, self.weather_num_px, bold=True)

        self._weather_emoji = QtWidgets.QLabel("")
        self._weather_emoji.setStyleSheet("color: white;")
        self._weather_emoji.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight)
        self._weather_emoji.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self._apply_font(self._weather_emoji, self.weather_desc_px, bold=True)

        self._weather_desc = QtWidgets.QLabel("")
        self._weather_desc.setStyleSheet("color: white;")
        self._weather_desc.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self._weather_desc.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self._apply_font(self._weather_desc, self.weather_desc_px, bold=False)

        cond_row = QtWidgets.QHBoxLayout()
        cond_row.setSpacing(max(8, self.weather_desc_px // 4))
        cond_row.setContentsMargins(0, 0, 0, 0)
        cond_row.addWidget(self._weather_emoji, 0, QtCore.Qt.AlignVCenter)
        cond_row.addWidget(self._weather_desc, 0, QtCore.Qt.AlignVCenter)

        weather_col = QtWidgets.QVBoxLayout()
        weather_col.setSpacing(max(6, self.weather_desc_px // 4))
        weather_col.setContentsMargins(0, 0, 0, 0)
        weather_col.addWidget(self._weather_num, 0, QtCore.Qt.AlignHCenter)
        weather_col.addLayout(cond_row)

        self._weather_widget = QtWidgets.QWidget()
        self._weather_widget.setLayout(weather_col)
        self._weather_widget.setStyleSheet("background: transparent;")
        self._weather_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self._weather_widget.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

        self._weather_shadow_r = int(max(10, self.weather_num_px * 0.16) * dpr)
        self._weather_shadow_dx = int(max(2, self.weather_num_px * 0.035) * dpr)
        self._weather_shadow_dy = self._weather_shadow_dx
        pad = max(4, self._weather_shadow_r // 4)
        self._weather_widget.setContentsMargins(pad, pad, pad, pad)
        self._apply_shadow(self._weather_widget, self._weather_shadow_r, self._weather_shadow_dx, self._weather_shadow_dy)

        # Main grid
        main = QtWidgets.QGridLayout(self)
        main.setContentsMargins(self.ml, self.mt, self.mr, self.mb)
        main.setHorizontalSpacing(0)
        main.setVerticalSpacing(0)
        main.addWidget(self._left_widget, 1, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        main.addWidget(self._weather_widget, 1, 1, QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom)
        main.setRowStretch(0, 1)
        main.setRowStretch(1, 0)
        main.setColumnStretch(0, 1)
        main.setColumnStretch(1, 0)

    # Public updates
    def update_time_and_date(self, time_text: str) -> None:
        self._time_label.setText(time_text)
        date_fmt = self.settings.get("date_format", "dddd, MMM d, yyyy")
        self._date_label.setText(QtCore.QDate.currentDate().toString(date_fmt))

    def update_weather(self, data: dict) -> None:
        data = data or {}

        temp = data.get("temp", "")
        unit = data.get("unit", "")
        if isinstance(temp, (int, float)):
            temp_str = f"{int(round(temp))} °{unit}".strip()
        else:
            temp_str = f"{str(temp)} °{unit}".strip()
        self._weather_num.setText(temp_str)

        desc = str(data.get("description", "") or "")
        self._weather_desc.setText(desc)

        symbol = ""
        icon_obj = data.get("icon")
        if isinstance(icon_obj, int):
            symbol = self._accuweather_symbol(icon_obj)

        self._weather_emoji.setText(symbol)
        self._weather_emoji.setVisible(bool(symbol))

    # Helpers
    def _apply_shadow(self, widget: QtWidgets.QWidget, radius: int, dx: float, dy: float, alpha: int = None) -> None:
        eff = QtWidgets.QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(int(radius))
        eff.setOffset(float(dx), float(dy))
        a = self.shadow_alpha if alpha is None else alpha
        eff.setColor(QtGui.QColor(0, 0, 0, int(a)))
        widget.setGraphicsEffect(eff)

    def _maybe_load_font(self, font_name_or_path: str) -> None:
        if not font_name_or_path:
            return
        if os.path.exists(font_name_or_path) and os.path.isfile(font_name_or_path):
            try:
                fid = QtGui.QFontDatabase.addApplicationFont(font_name_or_path)
                fams = QtGui.QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    self.font_name = fams[0]
            except Exception:
                logging.exception("Failed to load font '%s'", font_name_or_path)
        else:
            self.font_name = font_name_or_path

    def _apply_font(self, label: QtWidgets.QLabel, px: int, bold: bool = False) -> None:
        f = QtGui.QFont(self.font_name)
        f.setPixelSize(px)
        f.setBold(bold)
        label.setFont(f)

    def _accuweather_symbol(self, icon_id: int) -> str:
        # Simple ASCII mapping (extend as needed)
        # Use plain ASCII per your request.
        day = icon_id < 30
        if icon_id in (1, 2, 33, 34):
            return "o" if day else "c"  # sun / moon placeholder
        if icon_id in (3, 4, 35, 36):
            return "o"  # partly cloudy placeholder
        if icon_id in (6, 7):
            return "o"  # cloudy placeholder
        if icon_id in (11, 20):
            return "~"  # fog/wind placeholder
        if icon_id in (12, 13, 14, 39, 40):
            return "r"  # rain placeholder
        if icon_id in (15, 41, 42):
            return "t"  # thunder placeholder
        if icon_id in (18, 26):
            return "r"
        if icon_id in (22, 29):
            return "*"
        return "o"
