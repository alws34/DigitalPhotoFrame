from __future__ import annotations

import io
import json as _json
from typing import Any, Dict

import qrcode
from PySide6 import QtCore, QtGui, QtWidgets

from Utilities.config_store import save_settings as _cs_save

from .viewmodel import SettingsViewModel
from .widgets import Sparkline


class SettingsModel:
    """Thin model wrapper around the settings dict + helpers."""
    def __init__(self, settings: Dict[str, Any], settings_path: str | None = None):
        self._settings = settings
        self._path = settings_path
        # Ensure the new structure exists immediately on load
        self.ensure_defaults()

    # ---- basic access ----
    @property
    def data(self) -> Dict[str, Any]:
        return self._settings

    def save(self, path: str | None = None) -> None:
        """Persist settings via config_store (SQLite + sentinel)."""
        _cs_save(self._settings)

    # ---- structural helpers ----
    def ensure_defaults(self) -> None:
        """Guarantees the new nested structure exists."""
        # 1. System
        sys = self._settings.setdefault("system", {})
        sys.setdefault("service_name", "PhotoFrame_Desktop_App")
        sys.setdefault("image_dir", "Images")

        # 2. Playback
        pb = self._settings.setdefault("playback", {})
        pb.setdefault("animation_duration", 10)
        pb.setdefault("delay_between_images", 30)
        pb.setdefault("animation_fps", 30)

        # 3. Effects
        eff = self._settings.setdefault("effects", {})
        eff.setdefault("allow_translucent_background", True)
        eff.setdefault("background_opacity", 0.4)
        eff.setdefault("shadow_opacity", 0.85)

        # 4. UI
        ui = self._settings.setdefault("ui", {})
        ui.setdefault("font_name", "arial.ttf")
        ui.setdefault("date_format", "dddd, MMM d, yyyy")
        # Sub-objects in UI
        ui.setdefault("margins", {"left": 50, "right": 50, "top": 50, "bottom": 50})
        ui.setdefault(
            "text_shadow", {"alpha": 200, "blur": 10, "offset_x": 2, "offset_y": 2}
        )
        # Keep compatibility with legacy spacing key location.
        margins = ui.get("margins", {})
        if (
            isinstance(margins, dict)
            and "spacing_between" not in ui
            and "spacing" in margins
        ):
            ui["spacing_between"] = margins.get("spacing")

        # 5. Screen (complex struct)
        self.ensure_screen_struct()

    def ensure_screen_struct(self) -> Dict[str, Any]:
        scr = self._settings.setdefault("screen", {})
        scr.setdefault("orientation", "normal")
        scr.setdefault("brightness", 100)
        scr.setdefault("schedule_enabled", False)
        scr.setdefault("off_hour", 0)
        scr.setdefault("on_hour", 7)
        if "schedules" not in scr or not isinstance(scr["schedules"], list):
            scr["schedules"] = [
                {"enabled": False, "off_hour": 0, "on_hour": 7,
                 "days": [0, 1, 2, 3, 4, 5, 6]}
            ]
        return scr

    def mirror_first_enabled_schedule_to_legacy(self) -> None:
        scr = self.ensure_screen_struct()
        enabled = [s for s in scr.get("schedules", []) if s.get("enabled")]
        if enabled:
            first = enabled[0]
            scr["schedule_enabled"] = True
            scr["off_hour"] = int(first.get("off_hour", 0)) % 24
            scr["on_hour"] = int(first.get("on_hour", 7)) % 24
        else:
            scr["schedule_enabled"] = False


class SettingsDialog(QtWidgets.QDialog):
    """
    Main settings dialog (View).
    Fully compatible with deeply nested JSON settings structures.
    Dynamic tabs rendered from config_store with hot-reload support.
    """
    _hot_reload_signal = QtCore.Signal(dict)

    def __init__(self, vm: SettingsViewModel, model: SettingsModel, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.model = model

        self._apply_safe_theme()

        self.setWindowTitle("Settings")
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.resize(min(800, screen.width() - 40),
                    min(600, screen.height() - 40))
        self.setModal(True)

        self.setLayout(QtWidgets.QVBoxLayout())
        self._tabs = QtWidgets.QTabWidget(self)
        self.layout().addWidget(self._tabs)
        self._pending_changes: dict = {}

        # Pinned System tab (stats/QR/graphs)
        stats_tab = self._build_stats_tab()
        self._tabs.addTab(self._wrap_scroll(stats_tab), "System")

        # Dynamic settings tabs
        from Utilities.config_store import load_settings
        current_settings = load_settings()
        self._build_dynamic_tabs(current_settings)

        # Save button
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        self.layout().addWidget(save_btn)

        # Wire stats signals
        vm.statsChanged.connect(self._on_stats_changed)
        vm.qrTextChanged.connect(self._on_qr_changed)
        vm.maintStatusChanged.connect(self._set_maint_status)
        vm.cpuPushed.connect(self.cpu_graph.push)
        vm.ramPushed.connect(self.ram_graph.push)
        vm.tempPushed.connect(self.tmp_graph.push)
        vm.cpuPushed.connect(lambda v: self.cpu_val.setText(f"{v:.0f}%"))
        vm.ramPushed.connect(lambda v: self.ram_val.setText(f"{v:.1f}%"))
        vm.tempPushed.connect(lambda v: self.tmp_val.setText(f"{v:.1f} C"))

        # Hot reload via Qt signal (thread-safe)
        self._hot_reload_signal.connect(self._refresh_from_settings)
        from Utilities.config_events import on_settings_changed
        on_settings_changed(self._on_hot_reload)

        vm.prime()
        vm.start_local_stats(1000)
        self._set_version_label()

    def _wrap_scroll(self, widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        """Helper to make any tab scrollable."""
        sc = QtWidgets.QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QtWidgets.QFrame.NoFrame)
        sc.setWidget(widget)
        return sc

    def _apply_safe_theme(self) -> None:
        """Force a clean, high-contrast theme to ensure readability on frame buffers."""
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        try:
            self.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
        except Exception:
            pass
        self.setFont(QtGui.QFont("DejaVu Sans", 10))

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window,           QtGui.QColor(245, 245, 245))
        pal.setColor(QtGui.QPalette.WindowText,       QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Base,             QtGui.QColor(255, 255, 255))
        pal.setColor(QtGui.QPalette.AlternateBase,    QtGui.QColor(240, 240, 240))
        pal.setColor(QtGui.QPalette.Text,             QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Button,           QtGui.QColor(230, 230, 230))
        pal.setColor(QtGui.QPalette.ButtonText,       QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Highlight,        QtGui.QColor(0, 120, 215))
        pal.setColor(QtGui.QPalette.HighlightedText,  QtCore.Qt.white)
        self.setPalette(pal)

        self.setStyleSheet("""
            QWidget { background: #f5f5f5; color: #000000; }
            QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: #ffffff; color: #000000;
            }
            QPushButton {
                background: #e6e6e6; color: #000000;
                border: 1px solid #c9c9c9; padding: 6px 10px;
                min-width: 44px; min-height: 36px;
            }
            QPushButton:disabled { color: #666666; }
            QGroupBox { border: 1px solid #cfcfcf; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QTabWidget::pane { border: 1px solid #cfcfcf; }
            QTabBar::tab { padding: 6px 10px; }
            QHeaderView::section { background: #efefef; padding: 3px; border: 1px solid #cfcfcf; }
            QTableView, QTableWidget { background: #ffffff; }
            QCheckBox, QRadioButton { color: #000000; }
        """)

    def _show_msg(self, title: str, text: str) -> None:
        safe_title = title or "Message"
        safe_text = text or ""

        # Always expose messages in the status label as a safe fallback.
        try:
            self.vm.maintStatusChanged.emit(f"{safe_title}: {safe_text}")
        except Exception:
            pass

        # Some Qt platform plugins can crash when opening modal dialogs.
        try:
            platform_name = (QtWidgets.QApplication.platformName() or "").lower()
        except Exception:
            platform_name = ""
        if platform_name in {"offscreen", "minimal", "linuxfb", "eglfs"}:
            return

        try:
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle(safe_title)
            msg.setText(safe_text)
            msg.setIcon(QtWidgets.QMessageBox.Warning)
            msg.exec()
        except Exception:
            pass

    # =========================================================================
    # TAB: SYSTEM (stats/QR/graphs)
    # =========================================================================
    def _build_stats_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)

        # QR and Info Area
        top = QtWidgets.QWidget()
        top_l = QtWidgets.QVBoxLayout(top)
        top_l.setAlignment(QtCore.Qt.AlignHCenter)
        self.ssid_lbl = QtWidgets.QLabel("Wi-Fi: Loading...")
        self.url_lbl = QtWidgets.QLabel("URL: Loading...")
        self.ssid_lbl.setWordWrap(True)
        self.url_lbl.setWordWrap(True)
        self.qr_lbl = QtWidgets.QLabel()
        self.qr_lbl.setMinimumSize(160, 160)
        self.qr_lbl.setAlignment(QtCore.Qt.AlignCenter)

        for lbl in (self.ssid_lbl, self.url_lbl):
            lbl.setAlignment(QtCore.Qt.AlignCenter)
        top_l.addWidget(self.ssid_lbl)
        top_l.addWidget(self.url_lbl)
        top_l.addWidget(self.qr_lbl)

        # Version label
        self.version_lbl = QtWidgets.QLabel("")
        self.version_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.version_lbl.setObjectName("version_lbl")
        top_l.addWidget(self.version_lbl)

        lay.addWidget(top)

        # Graphs
        g = QtWidgets.QWidget()
        gl = QtWidgets.QFormLayout(g)
        policy = getattr(QtWidgets.QFormLayout, "WrapAllRows",
                 getattr(QtWidgets.QFormLayout, "WrapLongRows",
                         QtWidgets.QFormLayout.DontWrapRows))
        gl.setRowWrapPolicy(policy)
        gl.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        def row(w_graph_attr: str, init_text: str) -> QtWidgets.QWidget:
            wrap = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(wrap)
            hl.setContentsMargins(0, 0, 0, 0)
            graph = Sparkline(maxlen=60)
            setattr(self, w_graph_attr, graph)
            val_lbl = QtWidgets.QLabel(init_text)
            val_lbl.setMinimumWidth(56)
            val_lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            setattr(self, w_graph_attr.replace("_graph", "_val"), val_lbl)
            hl.addWidget(graph, 1)
            hl.addWidget(val_lbl, 0)
            return wrap

        self.cpu_graph = Sparkline(maxlen=60)
        self.ram_graph = Sparkline(maxlen=60)
        self.tmp_graph = Sparkline(maxlen=60)
        gl.addRow("CPU %",  row("cpu_graph", "0%"))
        gl.addRow("RAM %",  row("ram_graph", "0%"))
        gl.addRow("Temp C", row("tmp_graph", "0.0 C"))
        lay.addWidget(g)

        # Maintenance Buttons
        maint_row = QtWidgets.QHBoxLayout()
        self.pull_btn = QtWidgets.QPushButton("Pull updates now", clicked=self.vm.pull_updates)
        self.restart_btn = QtWidgets.QPushButton("Restart service", clicked=self.vm.restart_service)
        self.maint_status = QtWidgets.QLabel("")
        self.maint_status.setWordWrap(True)
        maint_row.addWidget(self.pull_btn)
        maint_row.addSpacing(8)
        maint_row.addWidget(self.restart_btn)
        maint_row.addSpacing(16)
        maint_row.addWidget(self.maint_status, 1)
        lay.addLayout(maint_row)
        lay.addStretch(1)
        return w

    def _set_version_label(self) -> None:
        try:
            data = self.model.data if isinstance(self.model.data, dict) else {}
            # Check nested "about" then root
            about = data.get("about", {}) if isinstance(data.get("about", {}), dict) else {}
            ver = about.get("version") or data.get("version") or "N/A"
            if hasattr(self, "version_lbl") and self.version_lbl is not None:
                self.version_lbl.setText(f"Version: {ver}")
        except Exception:
            pass

    @QtCore.Slot(str, str)
    def _on_stats_changed(self, ssid: str, url: str):
        self.ssid_lbl.setText(f"Wi-Fi: {ssid}")
        self.url_lbl.setText(f"URL: {url}")

    @QtCore.Slot(str)
    def _on_qr_changed(self, text: str):
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qimg = QtGui.QImage.fromData(buf.getvalue(), "PNG")
        self.qr_lbl.setPixmap(
            QtGui.QPixmap.fromImage(qimg).scaled(
                160, 160, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            )
        )

    @QtCore.Slot(str)
    def _set_maint_status(self, s: str):
        self.maint_status.setText(s)

    # =========================================================================
    # showEvent / resizeEvent
    # =========================================================================
    def showEvent(self, e):
        super().showEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)

    # =========================================================================
    # DYNAMIC SETTINGS TABS
    # =========================================================================
    def _build_dynamic_tabs(self, settings: dict) -> None:
        SKIP = {"about"}
        for key, section in settings.items():
            if key in SKIP or not isinstance(section, dict):
                continue
            tab_label = key.replace("_", " ").title()
            widget = self._build_section_widget(section, parent_key=key)
            self._tabs.addTab(self._wrap_scroll(widget), tab_label)

    def _build_section_widget(self, section: dict, parent_key: str) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        for key, value in section.items():
            label = key.replace("_", " ").title()
            input_widget = self._make_input_widget(key, value, parent_key)
            if input_widget:
                form.addRow(label, input_widget)
        return widget

    def _make_input_widget(self, key: str, value, parent_key: str) -> QtWidgets.QWidget | None:
        def on_bool(state, k=key, pk=parent_key):
            self._pending_changes.setdefault(pk, {})[k] = bool(state)

        def on_int(val, k=key, pk=parent_key):
            self._pending_changes.setdefault(pk, {})[k] = int(val)

        def on_float(val, k=key, pk=parent_key):
            self._pending_changes.setdefault(pk, {})[k] = float(val)

        def on_str(text, k=key, pk=parent_key):
            self._pending_changes.setdefault(pk, {})[k] = text

        if isinstance(value, bool):
            w = QtWidgets.QCheckBox()
            w.setChecked(value)
            w.stateChanged.connect(on_bool)
            return w

        if isinstance(value, int):
            w = QtWidgets.QSpinBox()
            w.setRange(-9999999, 9999999)
            w.setValue(value)
            w.valueChanged.connect(on_int)
            return w

        if isinstance(value, float):
            w = QtWidgets.QDoubleSpinBox()
            w.setRange(-9999999.0, 9999999.0)
            w.setDecimals(3)
            w.setValue(value)
            w.valueChanged.connect(on_float)
            return w

        if isinstance(value, str):
            w = QtWidgets.QLineEdit(value)
            w.textChanged.connect(on_str)
            return w

        if isinstance(value, dict):
            w = QtWidgets.QGroupBox()
            layout = QtWidgets.QVBoxLayout(w)
            inner = self._build_section_widget(value, parent_key=f"{parent_key}.{key}")
            layout.addWidget(inner)
            return w

        w = QtWidgets.QPlainTextEdit(_json.dumps(value, indent=2))
        w.setFixedHeight(80)
        return w

    def _save_settings(self) -> None:
        from Utilities.config_store import load_settings, save_settings
        current = load_settings()
        for section_key, changes in self._pending_changes.items():
            if "." in section_key:
                parts = section_key.split(".")
                target = current
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = changes
            else:
                if isinstance(current.get(section_key), dict):
                    current[section_key].update(changes)
                else:
                    current[section_key] = changes
        save_settings(current)
        self._pending_changes.clear()

    def _on_hot_reload(self, new_data: dict) -> None:
        self._hot_reload_signal.emit(new_data)

    @QtCore.Slot(dict)
    def _refresh_from_settings(self, new_data: dict) -> None:
        while self._tabs.count() > 1:
            self._tabs.removeTab(1)
        self._build_dynamic_tabs(new_data)
        self._pending_changes.clear()
