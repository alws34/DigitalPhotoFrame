from __future__ import annotations
from datetime import time
import subprocess
import sys
import os
import threading
import logging
from typing import Any, Dict, Optional
import cv2
from PySide6 import QtCore, QtGui, QtWidgets
import numpy as np
from PIL import Image
from iFrame import iFrame
from FrameGUI.SettingsFrom.model import SettingsModel
from FrameGUI.SettingsFrom.viewmodel import SettingsViewModel
from FrameGUI.SettingsFrom.dialog import SettingsDialog
from Utilities.brightness import set_brightness_percent
from Utilities.screen_scheduler import ScreenScheduler
try:
    from PySide6.QtSvg import QSvgRenderer
    _HAS_SVG = True
except Exception:
    _HAS_SVG = False

class IFrameQtWidgetMeta(type(QtWidgets.QWidget), type(iFrame)):
    pass

class PhotoFrameQtWidget(QtWidgets.QWidget, iFrame, metaclass=IFrameQtWidgetMeta):
    dateTimeChanged = QtCore.Signal(str)
    frameChanged = QtCore.Signal(QtGui.QImage)
    weatherChanged  = QtCore.Signal(object) 
    
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

        # Stack: image canvas + overlay
        self._stack = QtWidgets.QStackedLayout(self)
        self._stack.setContentsMargins(0,0,0,0)
        self.setLayout(self._stack)

        self._canvas  = ImageCanvas(self)
        self._overlay = OverlayPanel(self, settings=self.settings)   # <-- pass settings
        self._stack.addWidget(self._canvas)
        self._stack.addWidget(self._overlay)
        self._stack.setStackingMode(QtWidgets.QStackedLayout.StackAll)
        self._overlay.raise_()

        self._scheduler = ScreenScheduler(self, interval_ms=30000)
        
        self._scheduler.stateChanged.connect(
            lambda off: logging.info("ScreenScheduler: %s", "OFF" if off else "ON")
        )
        
        # Wire signals
        self.dateTimeChanged.connect(self._update_datetime_gui)
        self.frameChanged.connect(self._canvas.set_qimage)
        self.weatherChanged.connect(self._update_weather_gui)
        
        # setting form
        self._last_clicks = []
        self._settings_vm = None
        self.backend_port = int(self.settings.get("backend_configs", {}).get("server_port", 5001))
        # optional, if not already set elsewhere:
        self.service_name = self.settings.get("service_name", "photoframe")
        self.screen_ctrl = None
        # adopt any preattached controller if the app set one before:
        if hasattr(self, "screen") and not callable(getattr(self, "screen")):
            # (back-compat if someone assigned self.screen = ScreenController(...))
            self.screen_ctrl = getattr(self, "screen")
            
            
    
    
    
    def stop(self):
        """A simple method to close the window, can be expanded for more cleanup."""
        self.close()

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        # record tap time (ms since boot)
        now = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        self._last_clicks.append(now)
        self._last_clicks = self._last_clicks[-3:]

        # triple-tap within 800 ms window
        if len(self._last_clicks) == 3 and (self._last_clicks[-1] - self._last_clicks[0] <= 800):
            # If we have a screen controller and the panel is off/blank, wake it.
            is_off = False
            try:
                if self.screen_ctrl and hasattr(self.screen_ctrl, "is_off"):
                    is_off = bool(self.screen_ctrl.is_off())
            except Exception:
                # if the controller errors or doesn't expose is_off(), fall back to waking
                is_off = True

            if self.screen_ctrl and is_off:
                try:
                    self.screen_ctrl.wake()
                except Exception as ex:
                    logging.exception("Failed to wake screen: %s", ex)
                finally:
                    self._last_clicks.clear()
                    return

            # Otherwise, keep your existing behavior (triple-tap opens Settings)
            self._open_settings()
            self._last_clicks.clear()
            return

        super().mousePressEvent(e)

    def _open_settings(self):
        """
        Builds Model + ViewModel + Dialog and shows it modally.
        """
        model = SettingsModel(self.settings, getattr(self, "settings_path", None))
        vm = SettingsViewModel(
            model=model,
            backend_port=self.backend_port,
            on_apply_brightness=set_brightness_percent,
            on_apply_orientation=self._on_apply_orientation,
            on_autoupdate_pull=self._on_autoupdate_pull,
            on_restart_service_async=self._on_restart_service_async,
            wake_screen_worker=(self.screen_ctrl.wake if self.screen_ctrl else (lambda: None)),
            notifications=(self.notifications if hasattr(self, "notifications") else None),
            parent=self,
        )
        dlg = SettingsDialog(vm, model, parent=self)
        dlg.exec()

        
    def set_frame(self, bgr: np.ndarray) -> None:
        if bgr is None:
            return
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = bgr.shape[:2]
        qimg = QtGui.QImage(rgb.data, w, h, QtGui.QImage.Format_RGB888)
        self.frameChanged.emit(qimg.copy())

    def set_date_time(self, dt_string: str) -> None:
        self.dateTimeChanged.emit(dt_string)

    def set_weather(self, weather_data: dict) -> None:
        self.weatherChanged.emit(weather_data or {})
    # endregion

    # region Private GUI Slots (Run on Main Thread)
    @QtCore.Slot(str)
    def _update_datetime_gui(self, text: str):
        self._overlay.update_time_and_date(text)

    @QtCore.Slot(object)
    def _update_weather_gui(self, weather_obj: dict):
        self._overlay.update_weather(weather_obj)  
    # endregion

    #region settings_form
    @staticmethod
    def _list_outputs() -> list[str]:
        try:
            out = subprocess.check_output(["wlr-randr"], universal_newlines=True, stderr=subprocess.DEVNULL, timeout=3)
        except Exception:
            return []
        names = []
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
            if not self.screen_ctrl:
                QtWidgets.QMessageBox.warning(self, "Brightness", "Screen controller not available.")
                return False
            ok = self.screen_ctrl.set_brightness_percent(pct, allow_zero=False)
            if ok:
                self.settings.setdefault("screen", {})["brightness"] = pct
            return bool(ok)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Brightness error", str(e))
            return False
     
        def attach_screen_controller(self, controller) -> None:
            """Call this after creating the widget to wire the ScreenController."""
            self.screen_ctrl = controller
            # Ask the scheduler to re-evaluate now that we have a controller.
            try:
                self._scheduler.recheck_now()
            except Exception:
                pass

    # ---- Orientation ----
    def _on_apply_orientation(self, transform: str) -> bool:
        """
        Calls wlr-randr with the default output. Shows errors to the user.
        """
        output = self._pick_default_output()
        if not output:
            QtWidgets.QMessageBox.critical(self, "No display", "Could not detect a Wayland output via wlr-randr.")
            return False
        try:
            subprocess.run(["wlr-randr", "--output", output, "--transform", transform], check=True)
            return True
        except subprocess.CalledProcessError as e:
            QtWidgets.QMessageBox.critical(self, "Failed to set orientation", e.stdout or str(e))
            return False

    # ---- Auto-update (pull now) ----
    def _on_autoupdate_pull(self) -> None:
        """
        Asynchronous pull with notifications and a result dialog.
        """
        def worker():
            ok, msg = False, "Unknown"
            try:
                if not hasattr(self, "autoupdater") or self.autoupdater is None:
                    raise RuntimeError("AutoUpdater not available.")
                ok, msg = self.autoupdater.pull_now()
            except Exception as e:
                ok, msg = False, f"pull_now() crashed: {e}"

            # file a notification
            try:
                if hasattr(self, "notifications") and self.notifications:
                    self.notifications.add(
                        f"Manual update {'succeeded' if ok else 'failed'}: {msg}",
                        level=("update" if ok else "error")
                    )
            except Exception:
                pass

            # UI feedback
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
        """
        Asks systemd to restart the desktop app service. No sudo here; polkit rules handle auth.
        """
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

    #endregion

    

class ImageCanvas(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._qimage: Optional[QtGui.QImage] = None
        # Make sure we expand to fill any parent container
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    @QtCore.Slot(QtGui.QImage)
    def set_qimage(self, qimage: QtGui.QImage) -> None:
        self._qimage = qimage
        self.update()  # schedule repaint

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

        # Compute a crop rect on the source image so that it "covers" the widget
        image_ar = iw / float(ih)
        widget_ar = ww / float(wh)

        if widget_ar > image_ar:
            # Widget is wider than the image: crop vertically
            new_h = int(round(iw / widget_ar))
            new_h = min(new_h, ih)
            y = max(0, (ih - new_h) // 2)
            src = QtCore.QRect(0, y, iw, new_h)
        else:
            # Widget is taller (or equal): crop horizontally
            new_w = int(round(ih * widget_ar))
            new_w = min(new_w, iw)
            x = max(0, (iw - new_w) // 2)
            src = QtCore.QRect(x, 0, new_w, ih)

        # Draw the cropped portion scaled to exactly fill the widget
        painter.drawImage(self.rect(), self._qimage, src)


from PySide6 import QtCore, QtGui, QtWidgets
try:
    from PySide6.QtSvg import QSvgRenderer
    _HAS_SVG = True
except Exception:
    _HAS_SVG = False

import os
import io
import logging
from typing import Dict, Any

# Optional PIL support for converting PIL.Image -> QPixmap
try:
    from PIL import Image as _PIL_Image  # noqa: F401
    from PIL.ImageQt import ImageQt
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


class OverlayPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, settings: Dict[str, Any] = None):
        super().__init__(parent)
        self.settings = settings or {}

        # Transparent overlay
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # ---- Settings (font + margins) ----
        self.font_name = self.settings.get("font_name", "Arial")
        self.time_px   = int(self.settings.get("time_font_size", 120))
        self.date_px   = int(self.settings.get("date_font_size", 80))
        self.ml        = int(self.settings.get("margin_left", 50))
        self.mr        = int(self.settings.get("margin_right", 50))
        self.mb        = int(self.settings.get("margin_bottom", 50))
        self.mt        = int(self.settings.get("margin_top", self.mb))

        dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()
        self.shadow_alpha = int(self.settings.get("shadow_alpha", 200))
        self.shadow_color = QtGui.QColor(0, 0, 0, self.shadow_alpha)

        self._maybe_load_font(self.font_name)

        # ---- Time + Date (bottom-left) ----
        self._time_label = QtWidgets.QLabel("00:00:00")
        self._date_label = QtWidgets.QLabel("-")
        for lbl in (self._time_label, self._date_label):
            lbl.setStyleSheet("color: white;")
            lbl.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

        # font
        self._apply_font(self._time_label, self.time_px, bold=True)
        self._apply_font(self._date_label, self.date_px, bold=False)

        # Prefer fixed-pitch digits for time
        f = self._time_label.font()
        f.setKerning(False)
        f.setStyleHint(QtGui.QFont.Monospace, QtGui.QFont.PreferDefault)
        f.setFixedPitch(True)
        self._time_label.setFont(f)
        if not QtGui.QFontInfo(self._time_label.font()).fixedPitch():
            mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
            mono.setPixelSize(self.time_px); mono.setBold(True); mono.setKerning(False)
            self._time_label.setFont(mono)

        fm_time = QtGui.QFontMetrics(self._time_label.font())
        max_time_text = "88:88:88"
        fixed_w = fm_time.horizontalAdvance(max_time_text)
        self._time_label.setFixedWidth(fixed_w)
        self._time_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)

        # Shadows for time/date
        self._time_shadow_r  = int(max(12,  self.time_px * 0.18) * dpr)
        self._time_shadow_dx = int(max(2,   self.time_px * 0.04)  * dpr)
        self._time_shadow_dy = self._time_shadow_dx
        self._date_shadow_r  = int(max(10,  self.date_px * 0.16)  * dpr)
        self._date_shadow_dx = int(max(2,   self.date_px * 0.035) * dpr)
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

        # ---- Weather (bottom-right) ----
        # Temperature matches time size; condition text matches date size.
        self.weather_num_px  = self.time_px
        self.weather_desc_px = self.date_px

        # Big temp
        self._weather_num = QtWidgets.QLabel("")
        self._weather_num.setStyleSheet("color: white;")
        self._weather_num.setAlignment(QtCore.Qt.AlignHCenter)
        self._weather_num.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self._apply_font(self._weather_num, self.weather_num_px, bold=True)

        # Condition row: [emoji] [description], emoji right next to text
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
        cond_row.addWidget(self._weather_desc,  0, QtCore.Qt.AlignVCenter)

        # Stack: temp on top, condition row beneath
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

        # One shadow on the whole weather block
        self._weather_shadow_r  = int(max(10, self.weather_num_px * 0.16) * dpr)
        self._weather_shadow_dx = int(max(2,  self.weather_num_px * 0.035) * dpr)
        self._weather_shadow_dy = self._weather_shadow_dx
        pad = max(4, self._weather_shadow_r // 4)
        self._weather_widget.setContentsMargins(pad, pad, pad, pad)
        self._apply_shadow(self._weather_widget, self._weather_shadow_r,
                           self._weather_shadow_dx, self._weather_shadow_dy)

        # ---- Main grid (corners) ----
        main = QtWidgets.QGridLayout(self)
        main.setContentsMargins(self.ml, self.mt, self.mr, self.mb)
        main.setHorizontalSpacing(0)
        main.setVerticalSpacing(0)
        main.addWidget(self._left_widget,    1, 0, QtCore.Qt.AlignLeft  | QtCore.Qt.AlignBottom)
        main.addWidget(self._weather_widget, 1, 1, QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom)
        main.setRowStretch(0, 1)
        main.setRowStretch(1, 0)
        main.setColumnStretch(0, 1)
        main.setColumnStretch(1, 0)

    # ---- public updates ----
    def update_time_and_date(self, time_text: str) -> None:
        self._time_label.setText(time_text)
        date_fmt = self.settings.get("date_format", "dddd, MMM d, yyyy")
        self._date_label.setText(QtCore.QDate.currentDate().toString(date_fmt))

    def update_weather(self, data: dict) -> None:
        data = data or {}

        # Temperature string
        temp = data.get("temp", "")
        unit = data.get("unit", "")
        if isinstance(temp, (int, float)):
            temp_str = f"{int(round(temp))} °{unit}".strip()  # ASCII only
        else:
            temp_str = f"{str(temp)} °{unit}".strip()
        self._weather_num.setText(temp_str)

        # Condition text matches the date size
        desc = str(data.get("description", "") or "")
        self._weather_desc.setText(desc)

        # Emoji near the condition (fallback from AccuWeather id)
        symbol = ""
        icon_obj = data.get("icon")
        if isinstance(icon_obj, int):
            symbol = self._accuweather_symbol(icon_obj)
        # If you later carry WMO codes, you can map them here, too.

        self._weather_emoji.setText(symbol)
        self._weather_emoji.setVisible(bool(symbol))

    # ---- helpers ----
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
        # Minimal readable mapping. Extend as needed.
        day = icon_id < 30
        if icon_id in (1, 2, 33, 34):        return "☀" if day else "☾"
        if icon_id in (3, 4, 35, 36):        return "⛅" if day else "☁"
        if icon_id in (6, 7):                return "☁"
        if icon_id in (11, 20):              return "〰"
        if icon_id in (12, 13, 14, 39, 40):  return "🌧"
        if icon_id in (15, 41, 42):          return "⛈"
        if icon_id in (18, 26):              return "🌧"
        if icon_id in (22, 29):              return "❄"
        return "☁"

def cv2_to_rgb_bytes(bgr: np.ndarray) -> bytes:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb.tobytes()




