from PySide6 import QtWidgets, QtGui, QtCore
from typing import Dict, Any
from FrameGUI.helpers.ui_factory import UIFactory


class OverlayPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, settings: Dict[str, Any] = None):
        super().__init__(parent)
        self.settings = settings or {}

        # Basic attributes
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # --- Load strictly from nested 'ui' structure ---
        ui_cfg = self.settings.get("ui", {})

        # Fonts
        self.font_name = UIFactory.load_font(ui_cfg.get("font_name", "Arial"))

        # Font Sizes
        self.time_px = int(ui_cfg.get("time_font_size", 120))
        self.date_px = int(ui_cfg.get("date_font_size", 80))

        # Margins (ui -> margins -> left/right/bottom)
        margins = ui_cfg.get("margins", {})
        self.ml = int(margins.get("left", 80))
        self.mr = int(margins.get("right", 50))
        self.mb = int(margins.get("bottom", 30))
        # JSON doesn't specify top, default to match bottom for symmetry
        self.mt = int(margins.get("top", self.mb))

        # Shadows (ui -> text_shadow -> blur/offset/alpha)
        shadow_cfg = ui_cfg.get("text_shadow", {})
        self.shadow_blur = int(shadow_cfg.get("blur", 16))
        self.shadow_x = int(shadow_cfg.get("offset_x", 2))
        self.shadow_y = int(shadow_cfg.get("offset_y", 2))
        self.shadow_alpha = int(shadow_cfg.get("alpha", 230))
        self.shadow_color = QtGui.QColor(0, 0, 0, self.shadow_alpha)

        # Spacing
        self.spacing_val = int(ui_cfg.get("spacing_between", 50))

        # Device Pixel Ratio for scaling shadows/margins on high DPI
        dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()

        # -- Time & Date --
        self._time_label = UIFactory.create_widget(
            QtWidgets.QLabel, self,
            text="00:00:00",
            style_sheet="color: white;",
            sizePolicy=QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        UIFactory.apply_font(
            self._time_label, self.font_name, self.time_px, bold=True)

        # Monospace fix for time
        f = self._time_label.font()
        f.setKerning(False)
        f.setStyleHint(QtGui.QFont.Monospace, QtGui.QFont.PreferDefault)
        f.setFixedPitch(True)
        self._time_label.setFont(f)

        self._date_label = UIFactory.create_widget(
            QtWidgets.QLabel, self,
            text="-",
            style_sheet="color: white;",
            sizePolicy=QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        UIFactory.apply_font(
            self._date_label, self.font_name, self.date_px, bold=False)

        # Apply Shadows using values from JSON
        # Scale shadow radius and offset by DPI
        s_radius = int(self.shadow_blur * dpr)
        s_dx = int(self.shadow_x * dpr)
        s_dy = int(self.shadow_y * dpr)

        UIFactory.apply_shadow(self._time_label, s_radius,
                               s_dx, s_dy, self.shadow_color)
        UIFactory.apply_shadow(self._date_label, s_radius,
                               s_dx, s_dy, self.shadow_color)

        # Add padding so shadows aren't clipped
        pad_time = s_radius // 3
        pad_date = s_radius // 3
        self._time_label.setContentsMargins(
            pad_time, pad_time, pad_time, pad_time)
        self._date_label.setContentsMargins(
            pad_date, pad_date, pad_date, pad_date)

        # Container for Left (Time/Date)
        self._left_container = UIFactory.create_widget(
            QtWidgets.QWidget, self, style_sheet="background: transparent;")
        self._left_container.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        left_layout = UIFactory.layout(
            QtWidgets.QVBoxLayout, self._left_container, spacing=self.spacing_val)
        left_layout.addWidget(self._time_label, 0, QtCore.Qt.AlignHCenter)
        left_layout.addWidget(self._date_label, 0, QtCore.Qt.AlignHCenter)

        # -- Weather --
        # Reusing font sizes for weather consistency
        self.weather_num_px = self.time_px
        self.weather_desc_px = self.date_px

        self._weather_num = UIFactory.create_widget(
            QtWidgets.QLabel, self,
            style_sheet="color: white;",
            sizePolicy=QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        self._weather_num.setAlignment(QtCore.Qt.AlignHCenter)
        UIFactory.apply_font(self._weather_num, self.font_name,
                             self.weather_num_px, bold=True)

        self._weather_emoji = UIFactory.create_widget(
            QtWidgets.QLabel, self,
            style_sheet="color: white;",
            sizePolicy=QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        self._weather_emoji.setAlignment(
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight)
        UIFactory.apply_font(self._weather_emoji,
                             self.font_name, self.weather_desc_px, bold=True)

        self._weather_desc = UIFactory.create_widget(
            QtWidgets.QLabel, self,
            style_sheet="color: white;",
            sizePolicy=QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        self._weather_desc.setAlignment(
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        UIFactory.apply_font(self._weather_desc, self.font_name,
                             self.weather_desc_px, bold=False)

        # Weather Container
        self._weather_widget = UIFactory.create_widget(
            QtWidgets.QWidget, self,
            style_sheet="background: transparent;",
            sizePolicy=QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        self._weather_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        weather_col = UIFactory.layout(
            QtWidgets.QVBoxLayout, self._weather_widget, spacing=max(6, self.weather_desc_px // 4))

        cond_row_widget = UIFactory.create_widget(
            QtWidgets.QWidget, self, style_sheet="background: transparent;")
        cond_row = UIFactory.layout(
            QtWidgets.QHBoxLayout, cond_row_widget, spacing=max(8, self.weather_desc_px // 4))
        cond_row.addWidget(self._weather_emoji, 0, QtCore.Qt.AlignVCenter)
        cond_row.addWidget(self._weather_desc, 0, QtCore.Qt.AlignVCenter)

        weather_col.addWidget(self._weather_num, 0, QtCore.Qt.AlignHCenter)
        weather_col.addWidget(cond_row_widget, 0, QtCore.Qt.AlignHCenter)

        # Weather Shadows (Consistent with Time/Date)
        pad = max(4, s_radius // 4)
        self._weather_widget.setContentsMargins(pad, pad, pad, pad)
        UIFactory.apply_shadow(self._weather_widget,
                               s_radius, s_dx, s_dy, self.shadow_color)

        # Main Layout using JSON margins
        main = UIFactory.layout(QtWidgets.QGridLayout, self, margins=(
            self.ml, self.mt, self.mr, self.mb))
        main.addWidget(self._left_container, 1, 0,
                       QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        main.addWidget(self._weather_widget, 1, 1,
                       QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom)
        main.setRowStretch(0, 1)
        main.setRowStretch(1, 0)
        main.setColumnStretch(0, 1)
        main.setColumnStretch(1, 0)

    def update_time_and_date(self, time_text: str) -> None:
        self._time_label.setText(time_text)

        # Read format strictly from ui -> date_format
        ui_cfg = self.settings.get("ui", {})
        date_fmt = ui_cfg.get("date_format", "dddd, MMM d, yyyy")

        self._date_label.setText(QtCore.QDate.currentDate().toString(date_fmt))

        # Maintain centered text width logic for time
        fm_time = QtGui.QFontMetrics(self._time_label.font())
        max_time_text = "88:88:88"
        fixed_w = fm_time.horizontalAdvance(max_time_text)
        if self._time_label.width() != fixed_w:
            self._time_label.setFixedWidth(fixed_w)

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

    def _accuweather_symbol(self, icon_id: int) -> str:
        # Simple ASCII mapping for weather icons
        day = icon_id < 30
        if icon_id in (1, 2, 33, 34):
            return "o" if day else "c"
        if icon_id in (3, 4, 35, 36):
            return "o"
        if icon_id in (6, 7):
            return "o"
        if icon_id in (11, 20):
            return "~"
        if icon_id in (12, 13, 14, 39, 40):
            return "r"
        if icon_id in (15, 41, 42):
            return "t"
        if icon_id in (18, 26):
            return "r"
        if icon_id in (22, 29):
            return "*"
        return ""
