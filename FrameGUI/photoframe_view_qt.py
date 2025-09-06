from __future__ import annotations
from datetime import time
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

        # Wire signals
        self.dateTimeChanged.connect(self._update_datetime_gui)
        self.frameChanged.connect(self._canvas.set_qimage)
        self.weatherChanged.connect(self._update_weather_gui)

    def stop(self):
        """A simple method to close the window, can be expanded for more cleanup."""
        self.close()

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


class ImageCanvas(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._qimage: Optional[QtGui.QImage] = None

    @QtCore.Slot(QtGui.QImage)
    def set_qimage(self, qimage: QtGui.QImage) -> None:
        self._qimage = qimage
        self.update() # Schedule a repaint

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtCore.Qt.black)
        if self._qimage is None or self._qimage.isNull():
            return
        
        # Scale image to fit the canvas while preserving aspect ratio
        scaled_image = self._qimage.scaled(self.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        
        # Center the image
        rect = scaled_image.rect()
        rect.moveCenter(self.rect().center())
        painter.drawImage(rect.topLeft(), scaled_image)


class OverlayPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, settings: Dict[str, Any] = None):
        super().__init__(parent)
        self.settings = settings or {}

        # Transparent overlay
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # ---- Settings (only font + margins) ----
        self.font_name = self.settings.get("font_name", "Arial")
        self.time_px   = int(self.settings.get("time_font_size", 120))
        self.date_px   = int(self.settings.get("date_font_size", 80))
        self.ml        = int(self.settings.get("margin_left", 50))
        self.mr        = int(self.settings.get("margin_right", 50))
        self.mb        = int(self.settings.get("margin_bottom", 50))
        self.mt        = int(self.settings.get("margin_top", self.mb))

        # Weather sizes FIRST (used below for shadows)
        self.weather_num_px  = int(max(24, int(self.date_px * 0.9)))
        self.weather_desc_px = int(max(18, int(self.weather_num_px * 0.6)))
        self.weather_icon_px = int(max(24, int(self.weather_num_px * 1.2)))

        # Hard-coded spacings (derived, not from settings)
        self.time_date_spacing    = max(8, self.date_px // 6)          # time ↕ date
        self.weather_line_spacing = max(6, self.weather_num_px // 6)   # temp ↕ desc
        self.icon_text_gap        = max(10, self.weather_icon_px // 3) # icon ↔ text

        # Shadow tuning
        scale = getattr(self, "devicePixelRatioF", lambda: 1.0)()
        self.shadow_alpha = int(self.settings.get("shadow_alpha", 200))
        self.shadow_color = QtGui.QColor(0, 0, 0, self.shadow_alpha)

        # Per-label (time/date) shadow sizes
        self._time_shadow_r  = int(max(12,  self.time_px * 0.18) * scale)
        self._time_shadow_dx = int(max(2,   self.time_px * 0.04)  * scale)
        self._time_shadow_dy = self._time_shadow_dx

        self._date_shadow_r  = int(max(10,  self.date_px * 0.16) * scale)
        self._date_shadow_dx = int(max(2,   self.date_px * 0.035) * scale)
        self._date_shadow_dy = self._date_shadow_dx

        # Single group shadow for the weather block (avoid stacking)
        self._weather_shadow_r  = int(max(10, self.weather_num_px * 0.16) * scale)
        self._weather_shadow_dx = int(max(2,  self.weather_num_px * 0.035) * scale)
        self._weather_shadow_dy = self._weather_shadow_dx

        self._maybe_load_font(self.font_name)

        # ---- Time + Date (bottom-left) ----
        self._time_label = QtWidgets.QLabel("00:00:00")
        self._date_label = QtWidgets.QLabel("—")
        for lbl in (self._time_label, self._date_label):
            lbl.setStyleSheet("color: white;")
            lbl.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

        # padding to avoid shadow clipping
        pad_time = self._time_shadow_r // 3
        pad_date = self._date_shadow_r // 3
        self._time_label.setContentsMargins(pad_time, pad_time, pad_time, pad_time)
        self._date_label.setContentsMargins(pad_date, pad_date, pad_date, pad_date)

        # font
        self._apply_font(self._time_label, self.time_px, bold=True)
        self._apply_font(self._date_label, self.date_px, bold=False)

        # HINT: prefer fixed-pitch digits for time; fall back to system fixed if needed
        f = self._time_label.font()
        f.setKerning(False)
        f.setStyleHint(QtGui.QFont.Monospace, QtGui.QFont.PreferDefault)
        f.setFixedPitch(True)
        self._time_label.setFont(f)
        if not QtGui.QFontInfo(self._time_label.font()).fixedPitch():
            mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
            mono.setPixelSize(self.time_px); mono.setBold(True); mono.setKerning(False)
            self._time_label.setFont(mono)

        # LOCK WIDTH so the label doesn't resize as digits change
        fm = QtGui.QFontMetrics(self._time_label.font())
        max_time_text = "88:88:88"                    # widest string for HH:MM:SS
        fixed_w = fm.horizontalAdvance(max_time_text) + pad_time * 2
        self._time_label.setFixedWidth(fixed_w)
        self._time_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)

        # Per-label shadows
        self._apply_shadow(self._time_label, self._time_shadow_r, self._time_shadow_dx, self._time_shadow_dy)
        self._apply_shadow(self._date_label, self._date_shadow_r, self._date_shadow_dx, self._date_shadow_dy)

        # layout (keep centered inside its fixed box)
        left_box = QtWidgets.QVBoxLayout()
        left_box.setSpacing(self.time_date_spacing)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.addWidget(self._time_label, 0, QtCore.Qt.AlignHCenter)
        left_box.addWidget(self._date_label, 0, QtCore.Qt.AlignHCenter)

        self._left_widget = QtWidgets.QWidget()
        self._left_widget.setLayout(left_box)
        self._left_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self._left_widget.setStyleSheet("background: transparent;")

        # ---- Weather (bottom-right) ----
        self._weather_icon = QtWidgets.QLabel()
        self._weather_icon.setFixedSize(self.weather_icon_px, self.weather_icon_px)
        self._weather_icon.setScaledContents(True)

        self._weather_num  = QtWidgets.QLabel("")
        self._weather_desc = QtWidgets.QLabel("")
        for lbl in (self._weather_num, self._weather_desc):
            lbl.setStyleSheet("color: white;")
            lbl.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
            lbl.setAlignment(QtCore.Qt.AlignHCenter)

        self._apply_font(self._weather_num,  self.weather_num_px,  bold=True)
        self._apply_font(self._weather_desc, self.weather_desc_px, bold=False)

        weather_text_col = QtWidgets.QVBoxLayout()
        weather_text_col.setSpacing(self.weather_line_spacing)
        weather_text_col.setContentsMargins(0, 0, 0, 0)
        weather_text_col.addWidget(self._weather_num,  0, QtCore.Qt.AlignHCenter)
        weather_text_col.addWidget(self._weather_desc, 0, QtCore.Qt.AlignHCenter)

        weather_row = QtWidgets.QHBoxLayout()
        weather_row.setSpacing(self.icon_text_gap)
        weather_row.setContentsMargins(0, 0, 0, 0)
        weather_row.addWidget(self._weather_icon, 0, QtCore.Qt.AlignVCenter)
        weather_row.addLayout(weather_text_col)

        self._weather_widget = QtWidgets.QWidget()
        self._weather_widget.setLayout(weather_row)
        self._weather_widget.setStyleSheet("background: transparent;")
        self._weather_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self._weather_widget.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

        # Small padding so the group shadow isn’t clipped
        pad = max(4, self._weather_shadow_r // 4)
        self._weather_widget.setContentsMargins(pad, pad, pad, pad)

        # One shadow on the whole weather block
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
        temp = data.get("temp", "")
        unit = data.get("unit", "")
        desc = data.get("description", "")
        icon = data.get("icon", None)

        if isinstance(temp, (int, float)):
            temp_str = f"{int(round(temp))} °{unit}".strip()
        else:
            temp_str = f"{temp} {unit}".strip()

        self._weather_num.setText(temp_str)
        self._weather_desc.setText(str(desc or ""))

        qimg = QtGui.QImage()
        if isinstance(icon, QtGui.QImage):
            qimg = icon
        elif isinstance(icon, (bytes, bytearray)):
            qimg.loadFromData(bytes(icon))
        if not qimg.isNull():
            self._weather_icon.setPixmap(QtGui.QPixmap.fromImage(qimg))
            self._weather_icon.show()
        else:
            self._weather_icon.clear()
            self._weather_icon.hide()

    # ---- helpers ----
    def _apply_shadow(self, widget: QtWidgets.QWidget,
                  radius: int, dx: float, dy: float, alpha: int = None) -> None:
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


def cv2_to_rgb_bytes(bgr: np.ndarray) -> bytes:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb.tobytes()