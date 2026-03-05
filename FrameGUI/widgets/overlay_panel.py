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
        self.mt = int(margins.get("top", self.mb))

        # Shadows (ui -> text_shadow -> blur/offset/alpha)
        shadow_cfg = ui_cfg.get("text_shadow", {})
        self.shadow_blur = int(shadow_cfg.get("blur", 16))
        self.shadow_x = int(shadow_cfg.get("offset_x", 2))
        self.shadow_y = int(shadow_cfg.get("offset_y", 2))
        self.shadow_alpha = int(shadow_cfg.get("alpha", 230))
        self.shadow_color = QtGui.QColor(0, 0, 0, self.shadow_alpha)

        # Spacing
        self.spacing_val = int(ui_cfg.get("spacing_between", margins.get("spacing", 50)))

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

        # Shadows
        s_radius = int(self.shadow_blur * dpr)
        s_dx = int(self.shadow_x * dpr)
        s_dy = int(self.shadow_y * dpr)

        UIFactory.apply_shadow(self._time_label, s_radius,
                               s_dx, s_dy, self.shadow_color)
        UIFactory.apply_shadow(self._date_label, s_radius,
                               s_dx, s_dy, self.shadow_color)

        pad = max(4, s_radius // 2)
        self._time_label.setContentsMargins(pad, pad, pad, pad)
        self._date_label.setContentsMargins(pad, pad, pad, pad)

        self._left_container = UIFactory.create_widget(
            QtWidgets.QWidget, self, style_sheet="background: transparent;")
        self._left_container.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        left_layout = UIFactory.layout(
            QtWidgets.QVBoxLayout, self._left_container, spacing=self.spacing_val)
        left_layout.addWidget(self._time_label, 0, QtCore.Qt.AlignHCenter)
        left_layout.addWidget(self._date_label, 0, QtCore.Qt.AlignHCenter)

        # -- Weather --
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

        self._weather_widget.setContentsMargins(pad, pad, pad, pad)
        UIFactory.apply_shadow(self._weather_widget,
                               s_radius, s_dx, s_dy, self.shadow_color)

        # Main Layout using margins from settings
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

        # Keep layout references for runtime hot-reload updates.
        self._left_layout = left_layout
        self._weather_col_layout = weather_col
        self._weather_cond_row_layout = cond_row
        self._main_layout = main
        self._last_weather_data: Dict[str, Any] = {}

        # Re-apply all visual settings so hot-reload and startup use one path.
        self.apply_settings(self.settings)

    @staticmethod
    def _as_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _view_size(self) -> tuple[int, int]:
        w = int(self.width())
        h = int(self.height())
        if (w <= 0 or h <= 0) and self.parentWidget() is not None:
            pw = self.parentWidget().width()
            ph = self.parentWidget().height()
            if pw > w:
                w = int(pw)
            if ph > h:
                h = int(ph)
        if w <= 0 or h <= 0:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                if w <= 0:
                    w = int(geo.width())
                if h <= 0:
                    h = int(geo.height())
        return max(1, w), max(1, h)

    def _fit_font_sizes(self, time_px: int, date_px: int, spacing: int) -> tuple[int, int]:
        w, h = self._view_size()
        avail_h = max(120, h - self.mt - self.mb)
        # Keep bottom overlay within ~55% of usable height to avoid clipping.
        max_block_h = int(avail_h * 0.55)
        block_h = max(1, time_px + date_px + max(0, spacing))
        if block_h > max_block_h:
            scale = max_block_h / float(block_h)
            time_px = max(12, int(time_px * scale))
            date_px = max(10, int(date_px * scale))

        # Ensure the time line fits horizontally.
        max_time_w = max(120, int((w - self.ml - self.mr) * 0.60))
        test_size = int(time_px)
        while test_size > 12:
            f = QtGui.QFont(self.font_name)
            f.setPixelSize(test_size)
            f.setBold(True)
            f.setKerning(False)
            f.setStyleHint(QtGui.QFont.Monospace, QtGui.QFont.PreferDefault)
            f.setFixedPitch(True)
            if QtGui.QFontMetrics(f).horizontalAdvance("88:88:88") <= max_time_w:
                break
            test_size -= 1
        time_px = max(12, test_size)
        if date_px >= time_px:
            date_px = max(10, int(time_px * 0.7))
        return time_px, date_px

    def apply_settings(self, settings: Dict[str, Any] | None = None) -> None:
        if isinstance(settings, dict):
            self.settings = settings
        ui_cfg = self.settings.get("ui", {}) if isinstance(self.settings, dict) else {}
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}

        self.font_name = UIFactory.load_font(ui_cfg.get("font_name", "Arial"))
        self.time_px = self._as_int(ui_cfg.get("time_font_size", 120), 120)
        self.date_px = self._as_int(ui_cfg.get("date_font_size", 80), 80)
        self.weather_num_px = self.time_px
        self.weather_desc_px = self.date_px

        margins = ui_cfg.get("margins", {})
        if not isinstance(margins, dict):
            margins = {}
        self.ml = self._as_int(margins.get("left", 80), 80)
        self.mr = self._as_int(margins.get("right", 50), 50)
        self.mb = self._as_int(margins.get("bottom", 30), 30)
        self.mt = self._as_int(margins.get("top", self.mb), self.mb)

        shadow_cfg = ui_cfg.get("text_shadow", {})
        if not isinstance(shadow_cfg, dict):
            shadow_cfg = {}
        self.shadow_blur = self._as_int(shadow_cfg.get("blur", 16), 16)
        self.shadow_x = self._as_int(shadow_cfg.get("offset_x", 2), 2)
        self.shadow_y = self._as_int(shadow_cfg.get("offset_y", 2), 2)
        self.shadow_alpha = max(0, min(255, self._as_int(shadow_cfg.get("alpha", 230), 230)))
        self.shadow_color = QtGui.QColor(0, 0, 0, self.shadow_alpha)

        self.spacing_val = self._as_int(
            ui_cfg.get("spacing_between", margins.get("spacing", 50)),
            50,
        )
        self.spacing_val = max(0, self.spacing_val)
        self.time_px, self.date_px = self._fit_font_sizes(self.time_px, self.date_px, self.spacing_val)
        self.weather_num_px = self.time_px
        self.weather_desc_px = self.date_px

        # Fonts
        UIFactory.apply_font(self._time_label, self.font_name, self.time_px, bold=True)
        time_font = self._time_label.font()
        time_font.setKerning(False)
        time_font.setStyleHint(QtGui.QFont.Monospace, QtGui.QFont.PreferDefault)
        time_font.setFixedPitch(True)
        self._time_label.setFont(time_font)
        UIFactory.apply_font(self._date_label, self.font_name, self.date_px, bold=False)
        UIFactory.apply_font(self._weather_num, self.font_name, self.weather_num_px, bold=True)
        UIFactory.apply_font(self._weather_emoji, self.font_name, self.weather_desc_px, bold=True)
        UIFactory.apply_font(self._weather_desc, self.font_name, self.weather_desc_px, bold=False)

        # Shadow + padding
        dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()
        s_radius = int(self.shadow_blur * dpr)
        s_dx = int(self.shadow_x * dpr)
        s_dy = int(self.shadow_y * dpr)
        UIFactory.apply_shadow(self._time_label, s_radius, s_dx, s_dy, self.shadow_color)
        UIFactory.apply_shadow(self._date_label, s_radius, s_dx, s_dy, self.shadow_color)
        UIFactory.apply_shadow(self._weather_widget, s_radius, s_dx, s_dy, self.shadow_color)
        pad = max(4, s_radius // 2)
        self._time_label.setContentsMargins(pad, pad, pad, pad)
        self._date_label.setContentsMargins(pad, pad, pad, pad)
        self._weather_widget.setContentsMargins(pad, pad, pad, pad)

        # Layout metrics
        self._left_layout.setSpacing(self.spacing_val)
        self._weather_col_layout.setSpacing(max(6, self.weather_desc_px // 4))
        self._weather_cond_row_layout.setSpacing(max(8, self.weather_desc_px // 4))
        self._main_layout.setContentsMargins(self.ml, self.mt, self.mr, self.mb)

        # Keep weather visible in the desktop layout.
        self._weather_widget.setVisible(True)

        # Refresh live text with current settings.
        self.update_time_and_date(self._time_label.text())
        self.update_weather(self._last_weather_data)
        self.updateGeometry()
        self.update()

    def update_time_and_date(self, time_text: str) -> None:
        self._time_label.setText(time_text)
        ui_cfg = self.settings.get("ui", {})
        date_fmt = ui_cfg.get("date_format", "dddd, MMM d, yyyy")
        self._date_label.setText(QtCore.QDate.currentDate().toString(date_fmt))

        # Fix width jitter without clipping digits.
        fm = QtGui.QFontMetrics(self._time_label.font())
        time_text = time_text or "00:00:00"
        text_w = max(fm.horizontalAdvance("88:88:88"), fm.horizontalAdvance(time_text))
        cm = self._time_label.contentsMargins()
        shadow_pad = max(2, int(self.shadow_blur * 0.5))
        w = text_w + cm.left() + cm.right() + shadow_pad
        self._time_label.setFixedWidth(w)

    def update_weather(self, data: dict) -> None:
        data = data or {}
        self._last_weather_data = dict(data) if isinstance(data, dict) else {}
        temp = data.get("temp", "")
        unit = data.get("unit", "")
        self._weather_num.setText(
            f"{round(temp) if isinstance(temp, (int, float)) else temp} °{unit}")
        self._weather_desc.setText(str(data.get("description", "") or ""))

        icon_id = data.get("icon")
        symbol = self._accuweather_symbol(
            icon_id) if isinstance(icon_id, int) else ""
        self._weather_emoji.setText(symbol)
        self._weather_emoji.setVisible(bool(symbol))

    def _accuweather_symbol(self, icon_id: int) -> str:
        # Simple ASCII mapping
        if icon_id in (1, 2, 33, 34):
            return "o"
        if icon_id in (3, 4, 35, 36, 6, 7):
            return "o"
        if icon_id in (11, 20):
            return "~"
        if icon_id in (12, 13, 14, 18, 26, 39, 40):
            return "r"
        if icon_id in (15, 41, 42):
            return "t"
        if icon_id in (22, 29):
            return "*"
        return ""

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        try:
            self.apply_settings(self.settings)
        except Exception:
            pass
