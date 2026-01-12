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

        # --- Load settings with nested 'ui' fallback ---
        self.font_name = UIFactory.load_font(self._get_val("font_name", "Arial"))
        
        # Font Sizes
        self.time_px = int(self._get_val("time_font_size", 120))
        self.date_px = int(self._get_val("date_font_size", 80))
        
        # Margins (try ui.margins.left -> margin_left -> default)
        self.ml = int(self._get_ui_sub_val("margins", "left", "margin_left", 50))
        self.mr = int(self._get_ui_sub_val("margins", "right", "margin_right", 50))
        self.mb = int(self._get_ui_sub_val("margins", "bottom", "margin_bottom", 50))
        self.mt = int(self._get_ui_sub_val("margins", "top", "margin_top", self.mb))
        
        # Shadows (try ui.text_shadow.alpha -> shadow_alpha -> default)
        self.shadow_alpha = int(self._get_ui_sub_val("text_shadow", "alpha", "shadow_alpha", 200))
        self.shadow_color = QtGui.QColor(0, 0, 0, self.shadow_alpha)
        
        dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()

        # -- Time & Date --
        self._time_label = UIFactory.create_widget(
            QtWidgets.QLabel, self, 
            text="00:00:00", 
            style_sheet="color: white;", 
            sizePolicy=QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        UIFactory.apply_font(self._time_label, self.font_name, self.time_px, bold=True)
        # Monospace fix
        f = self._time_label.font()
        f.setKerning(False)
        f.setStyleHint(QtGui.QFont.Monospace, QtGui.QFont.PreferDefault)
        f.setFixedPitch(True)
        self._time_label.setFont(f)
        
        self._date_label = UIFactory.create_widget(
            QtWidgets.QLabel, self, 
            text="-",
            style_sheet="color: white;",
            sizePolicy=QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        UIFactory.apply_font(self._date_label, self.font_name, self.date_px, bold=False)

        # Shadows
        # Try to get specific offsets from ui.text_shadow, else calculate dynamic defaults
        ts_blur = self._get_ui_sub_val("text_shadow", "blur", None, None)
        ts_x = self._get_ui_sub_val("text_shadow", "offset_x", None, None)
        ts_y = self._get_ui_sub_val("text_shadow", "offset_y", None, None)

        if ts_blur is not None:
            # Use explicit settings if available
            self._time_shadow_r = int(int(ts_blur) * dpr)
            self._time_shadow_dx = int(int(ts_x or 2) * dpr)
            self._time_shadow_dy = int(int(ts_y or 2) * dpr)
            
            self._date_shadow_r = self._time_shadow_r
            self._date_shadow_dx = self._time_shadow_dx
            self._date_shadow_dy = self._time_shadow_dy
        else:
            # Dynamic calculation fallback
            self._time_shadow_r = int(max(12, self.time_px * 0.18) * dpr)
            self._time_shadow_dx = int(max(2, self.time_px * 0.04) * dpr)
            self._time_shadow_dy = self._time_shadow_dx
            
            self._date_shadow_r = int(max(10, self.date_px * 0.16) * dpr)
            self._date_shadow_dx = int(max(2, self.date_px * 0.035) * dpr)
            self._date_shadow_dy = self._date_shadow_dx

        UIFactory.apply_shadow(self._time_label, self._time_shadow_r, self._time_shadow_dx, self._time_shadow_dy, self.shadow_color)
        UIFactory.apply_shadow(self._date_label, self._date_shadow_r, self._date_shadow_dx, self._date_shadow_dy, self.shadow_color)

        pad_time = self._time_shadow_r // 3
        pad_date = self._date_shadow_r // 3
        self._time_label.setContentsMargins(pad_time, pad_time, pad_time, pad_time)
        self._date_label.setContentsMargins(pad_date, pad_date, pad_date, pad_date)

        # Container for Left (Time/Date)
        self._left_container = UIFactory.create_widget(QtWidgets.QWidget, self, style_sheet="background: transparent;")
        self._left_container.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        spacing_val = int(self._get_val("spacing_between", max(8, self.date_px // 6)))
        left_layout = UIFactory.layout(QtWidgets.QVBoxLayout, self._left_container, spacing=spacing_val)
        left_layout.addWidget(self._time_label, 0, QtCore.Qt.AlignHCenter)
        left_layout.addWidget(self._date_label, 0, QtCore.Qt.AlignHCenter)


        # -- Weather --
        self.weather_num_px = self.time_px
        self.weather_desc_px = self.date_px

        self._weather_num = UIFactory.create_widget(
            QtWidgets.QLabel, self, 
            style_sheet="color: white;", 
            sizePolicy=QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        self._weather_num.setAlignment(QtCore.Qt.AlignHCenter)
        UIFactory.apply_font(self._weather_num, self.font_name, self.weather_num_px, bold=True)

        self._weather_emoji = UIFactory.create_widget(
             QtWidgets.QLabel, self,
             style_sheet="color: white;",
             sizePolicy=QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        self._weather_emoji.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight)
        UIFactory.apply_font(self._weather_emoji, self.font_name, self.weather_desc_px, bold=True)

        self._weather_desc = UIFactory.create_widget(
             QtWidgets.QLabel, self,
             style_sheet="color: white;",
             sizePolicy=QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        self._weather_desc.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        UIFactory.apply_font(self._weather_desc, self.font_name, self.weather_desc_px, bold=False)

        # Weather Container
        self._weather_widget = UIFactory.create_widget(
            QtWidgets.QWidget, self, 
            style_sheet="background: transparent;",
            sizePolicy=QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        )
        self._weather_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        weather_col = UIFactory.layout(QtWidgets.QVBoxLayout, self._weather_widget, spacing=max(6, self.weather_desc_px // 4))
        
        cond_row_widget = UIFactory.create_widget(QtWidgets.QWidget, self, style_sheet="background: transparent;")
        cond_row = UIFactory.layout(QtWidgets.QHBoxLayout, cond_row_widget, spacing=max(8, self.weather_desc_px // 4))
        cond_row.addWidget(self._weather_emoji, 0, QtCore.Qt.AlignVCenter)
        cond_row.addWidget(self._weather_desc, 0, QtCore.Qt.AlignVCenter)

        weather_col.addWidget(self._weather_num, 0, QtCore.Qt.AlignHCenter)
        weather_col.addWidget(cond_row_widget, 0, QtCore.Qt.AlignHCenter)

        # Weather Shadows (same logic)
        self._weather_shadow_r = int(max(10, self.weather_num_px * 0.16) * dpr)
        self._weather_shadow_dx = int(max(2, self.weather_num_px * 0.035) * dpr)
        
        pad = max(4, self._weather_shadow_r // 4)
        self._weather_widget.setContentsMargins(pad, pad, pad, pad)
        UIFactory.apply_shadow(self._weather_widget, self._weather_shadow_r, self._weather_shadow_dx, self._weather_shadow_dx, self.shadow_color)


        # Main Layout
        main = UIFactory.layout(QtWidgets.QGridLayout, self, margins=(self.ml, self.mt, self.mr, self.mb))
        main.addWidget(self._left_container, 1, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        main.addWidget(self._weather_widget, 1, 1, QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom)
        main.setRowStretch(0, 1)
        main.setRowStretch(1, 0)
        main.setColumnStretch(0, 1)
        main.setColumnStretch(1, 0)

    # --- Helpers for Nested Settings ---
    def _get_val(self, key: str, default: Any) -> Any:
        """Get from 'ui' object first, then root, then default."""
        ui_cfg = self.settings.get("ui", {})
        if key in ui_cfg:
            return ui_cfg[key]
        return self.settings.get(key, default)

    def _get_ui_sub_val(self, group: str, subkey: str, legacy_key: str, default: Any) -> Any:
        """
        Get from ui[group][subkey], e.g. ui['margins']['left'].
        Fallback to root legacy_key (e.g. 'margin_left').
        """
        ui_cfg = self.settings.get("ui", {})
        if group in ui_cfg and isinstance(ui_cfg[group], dict):
            if subkey in ui_cfg[group]:
                return ui_cfg[group][subkey]
        
        if legacy_key and legacy_key in self.settings:
            return self.settings[legacy_key]
            
        return default

    def update_time_and_date(self, time_text: str) -> None:
        self._time_label.setText(time_text)
        
        # Read format from ui -> date_format
        date_fmt = self._get_val("date_format", "dddd, MMM d, yyyy")
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
        # Simple ASCII mapping
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