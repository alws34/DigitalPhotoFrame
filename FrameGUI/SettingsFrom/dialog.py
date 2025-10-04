from __future__ import annotations
from typing import Any, Dict, List, Tuple
from PySide6 import QtCore, QtGui, QtWidgets
from .model import SettingsModel
from .viewmodel import SettingsViewModel
from .widgets import Sparkline, OnScreenKeyboard
import qrcode, io, json
from PIL import Image, ImageSequence

class SettingsDialog(QtWidgets.QDialog):
    """Main settings dialog (View)."""
    def __init__(self, vm: SettingsViewModel, model: SettingsModel, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.model = model

        # Force a readable theme JUST for this dialog + children.
        self._apply_safe_theme()

        self.setWindowTitle("Settings")
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.resize(min(800, screen.width() - 40),
                    min(600, screen.height() - 40))
        self.setModal(True)

        tabs = QtWidgets.QTabWidget(self); self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(tabs)

        # Build tabs EXACTLY like before (these set attributes like self.cpu_graph)
        self._stats   = self._build_stats_tab()
        self._wifi    = self._build_wifi_tab()
        self._screen  = self._build_screen_tab()
        self._about   = self._build_about_tab()
        self._notif   = self._build_notifications_tab()
        self._config  = self._build_config_tab()

        # Wrap each tab in a scroll area so small screens do not overflow
        tabs.addTab(self._wrap_scroll(self._stats),  "Stats")
        tabs.addTab(self._wrap_scroll(self._wifi),   "Wi-Fi")
        tabs.addTab(self._wrap_scroll(self._screen), "Screen")
        tabs.addTab(self._wrap_scroll(self._notif),  "Notifications")
        tabs.addTab(self._wrap_scroll(self._config), "Config")
        tabs.addTab(self._wrap_scroll(self._about),  "About")

        # wire VM signals (all attributes still exist as in original)
        vm.statsChanged.connect(self._on_stats_changed)
        vm.qrTextChanged.connect(self._on_qr_changed)
        vm.networksChanged.connect(self._set_networks)
        vm.wifiResult.connect(self._wifi_result)
        vm.maintStatusChanged.connect(self._set_maint_status)
        vm.notificationsChanged.connect(self._fill_notifications)
        vm.cpuPushed.connect(self.cpu_graph.push)
        vm.ramPushed.connect(self.ram_graph.push)
        vm.tempPushed.connect(self.tmp_graph.push)
        vm.cpuPushed.connect(lambda v: self.cpu_val.setText(f"{v:.0f}%"))
        vm.ramPushed.connect(lambda v: self.ram_val.setText(f"{v:.0f}%"))
        vm.tempPushed.connect(lambda v: self.tmp_val.setText(f"{v:.1f} C"))

        vm.prime()
        vm.start_local_stats(1000)
        vm.refresh_notifications()
        vm.scan_wifi()
        self._set_version_label()
        
    def _wrap_scroll(self, widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        """Make any tab scrollable to fit 800x480 without overlapping."""
        sc = QtWidgets.QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QtWidgets.QFrame.NoFrame)
        sc.setWidget(widget)
        return sc

    def _apply_safe_theme(self) -> None:
        """Make the dialog readable regardless of system theme."""
        # Ensure stylesheet backgrounds paint
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        # Force Fusion style on this dialog only
        try:
            self.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
        except Exception:
            pass

        # Known-good font (DejaVu Sans usually installed on Pi)
        # If missing, Qt picks a fallback automatically.
        self.setFont(QtGui.QFont("DejaVu Sans", 10))

        # Light palette
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window,           QtGui.QColor(245, 245, 245))
        pal.setColor(QtGui.QPalette.WindowText,       QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Base,             QtGui.QColor(255, 255, 255))
        pal.setColor(QtGui.QPalette.AlternateBase,    QtGui.QColor(240, 240, 240))
        pal.setColor(QtGui.QPalette.Text,             QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Button,           QtGui.QColor(230, 230, 230))
        pal.setColor(QtGui.QPalette.ButtonText,       QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.ToolTipBase,      QtGui.QColor(255, 255, 220))
        pal.setColor(QtGui.QPalette.ToolTipText,      QtCore.Qt.black)
        pal.setColor(QtGui.QPalette.Highlight,        QtGui.QColor(0, 120, 215))
        pal.setColor(QtGui.QPalette.HighlightedText,  QtCore.Qt.white)
        self.setPalette(pal)

        # Local stylesheet for the whole dialog subtree
        self.setStyleSheet("""
            /* base */
            QWidget { background: #f5f5f5; color: #000000; }
            /* inputs */
            QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: #ffffff; color: #000000;
            }
            /* buttons */
            QPushButton {
                background: #e6e6e6; color: #000000;
                border: 1px solid #c9c9c9; padding: 6px 10px; /* larger padding for touch */
                min-width: 44px; min-height: 36px;           /* touch target */
            }
            QPushButton:disabled { color: #666666; }
            /* group boxes */
            QGroupBox {
                border: 1px solid #cfcfcf; margin-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 3px;
            }
            /* tabs */
            QTabWidget::pane { border: 1px solid #cfcfcf; }
            QTabBar::tab { padding: 6px 10px; }
            /* tables */
            QHeaderView::section { background: #efefef; padding: 3px; border: 1px solid #cfcfcf; }
            QTableView, QTableWidget { background: #ffffff; }
            /* check/radio text color */
            QCheckBox, QRadioButton { color: #000000; }
        """)

    def _show_msg(self, title: str, text: str) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title or "Message")
        dlg.setModal(True)
        dlg.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        dlg.setStyle(self.style())          # inherit Fusion
        dlg.setPalette(self.palette())      # inherit light palette
        dlg.setStyleSheet(self.styleSheet())# inherit stylesheet

        icon = QtWidgets.QLabel()
        icon.setPixmap(self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning).pixmap(32, 32))

        lbl = QtWidgets.QLabel(text or "")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        btn = QtWidgets.QPushButton("OK")
        btn.clicked.connect(dlg.accept)

        lay = QtWidgets.QGridLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setHorizontalSpacing(10)
        lay.addWidget(icon, 0, 0, QtCore.Qt.AlignTop)
        lay.addWidget(lbl, 0, 1)
        lay.addWidget(btn, 1, 0, 1, 2, QtCore.Qt.AlignRight)

        dlg.resize(420, dlg.sizeHint().height())
        dlg.exec()

    # ---------- Stats ----------
    def _build_stats_tab(self):
        w = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(w)
        top = QtWidgets.QWidget(); top_l = QtWidgets.QVBoxLayout(top); top_l.setAlignment(QtCore.Qt.AlignHCenter)
        self.ssid_lbl = QtWidgets.QLabel("Wi-Fi: Loading...")
        self.url_lbl  = QtWidgets.QLabel("URL: Loading...")
        self.ssid_lbl.setWordWrap(True)
        self.url_lbl.setWordWrap(True)
        self.qr_lbl   = QtWidgets.QLabel()
        self.qr_lbl.setMinimumSize(160,160); self.qr_lbl.setAlignment(QtCore.Qt.AlignCenter)
        
        for lbl in (self.ssid_lbl, self.url_lbl): lbl.setAlignment(QtCore.Qt.AlignCenter)
        top_l.addWidget(self.ssid_lbl)
        top_l.addWidget(self.url_lbl)
        top_l.addWidget(self.qr_lbl)

        # NEW: version label under the QR
        self.version_lbl = QtWidgets.QLabel("")
        self.version_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.version_lbl.setObjectName("version_lbl")
        top_l.addWidget(self.version_lbl)

        lay.addWidget(top)

        # graphs
        g = QtWidgets.QWidget(); gl = QtWidgets.QFormLayout(g)
        # Allow labels/rows to wrap on narrow widths so nothing overlaps
        policy = getattr(QtWidgets.QFormLayout, "WrapAllRows",
                 getattr(QtWidgets.QFormLayout, "WrapLongRows",
                         QtWidgets.QFormLayout.DontWrapRows))
        gl.setRowWrapPolicy(policy)
        gl.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        def row(w_graph_attr: str, init_text: str) -> QtWidgets.QWidget:
            wrap = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(wrap); hl.setContentsMargins(0,0,0,0)
            graph = Sparkline(maxlen=60)
            setattr(self, w_graph_attr, graph)
            val_lbl = QtWidgets.QLabel(init_text)
            val_lbl.setMinimumWidth(56)
            val_lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            # store label handle next to graph name, e.g. cpu_val, ram_val, tmp_val
            setattr(self, w_graph_attr.replace("_graph", "_val"), val_lbl)
            hl.addWidget(graph, 1)
            hl.addWidget(val_lbl, 0)
            return wrap

        self.cpu_graph = Sparkline(maxlen=60); self.ram_graph = Sparkline(maxlen=60); self.tmp_graph = Sparkline(maxlen=60)
        gl.addRow("CPU %",  row("cpu_graph", "0%"))
        gl.addRow("RAM %",  row("ram_graph", "0%"))
        gl.addRow("Temp C", row("tmp_graph", "0.0 C"))
        lay.addWidget(g)

        # maintenance
        row = QtWidgets.QHBoxLayout()
        self.pull_btn = QtWidgets.QPushButton("Pull updates now", clicked=self.vm.pull_updates)
        self.restart_btn = QtWidgets.QPushButton("Restart service", clicked=self.vm.restart_service)
        self.maint_status = QtWidgets.QLabel("")
        self.maint_status.setWordWrap(True)
        row.addWidget(self.pull_btn); row.addSpacing(8); row.addWidget(self.restart_btn); row.addSpacing(16); row.addWidget(self.maint_status, 1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _set_version_label(self) -> None:
        try:
            data = self.model.data if isinstance(self.model.data, dict) else {}
            about = data.get("about", {}) if isinstance(data.get("about", {}), dict) else {}
            ver = data.get("version") or about.get("version") or "N/A"
            if hasattr(self, "version_lbl") and self.version_lbl is not None:
                self.version_lbl.setText(f"Version: {ver}")
        except Exception:
            pass

    @QtCore.Slot(str,str)
    def _on_stats_changed(self, ssid: str, url: str):
        self.ssid_lbl.setText(f"Wi-Fi: {ssid}")
        self.url_lbl.setText(f"URL: {url}")

    @QtCore.Slot(str)
    def _on_qr_changed(self, text: str):
        img = qrcode.make(text)
        buf = io.BytesIO(); img.save(buf, format="PNG")
        qimg = QtGui.QImage.fromData(buf.getvalue(), "PNG")
        self.qr_lbl.setPixmap(QtGui.QPixmap.fromImage(qimg).scaled(160,160, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    @QtCore.Slot(str)
    def _set_maint_status(self, s: str): self.maint_status.setText(s)

    # ---------- Wi-Fi ----------
    def _build_wifi_tab(self):
        w = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(w)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Network:"))
        self.ssid_cb = QtWidgets.QComboBox(); self.ssid_cb.setEditable(False)
        row.addWidget(self.ssid_cb, 1)
        v.addLayout(row)

        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Password:"))
        self.pwd = QtWidgets.QLineEdit(); self.pwd.setEchoMode(QtWidgets.QLineEdit.Password)
        row2.addWidget(self.pwd, 1)
        self.show_pw = QtWidgets.QCheckBox("Show")
        self.show_pw.toggled.connect(lambda on: self.pwd.setEchoMode(QtWidgets.QLineEdit.Normal if on else QtWidgets.QLineEdit.Password))
        row2.addWidget(self.show_pw)
        v.addLayout(row2)

        row3 = QtWidgets.QHBoxLayout()
        self.rescan = QtWidgets.QPushButton("Rescan", clicked=self.vm.scan_wifi)
        self.connect = QtWidgets.QPushButton("Connect", clicked=lambda: self.vm.connect_wifi(self.ssid_cb.currentText().strip(), self.pwd.text()))
        row3.addWidget(self.rescan); row3.addWidget(self.connect)
        v.addLayout(row3)

        # on-screen keyboard
        kb = OnScreenKeyboard(); v.addWidget(kb)
        def on_key(k: str):
            if k == "Backspace":
                self.pwd.backspace(); return
            if k == "Left":
                self.pwd.cursorBackward(False, 1); return
            if k == "Right":
                self.pwd.cursorForward(False, 1); return
            if k == "Space":
                self.pwd.insert(" "); return
            if k in ("Tab","Enter"): return
            self.pwd.insert(k)
        kb.keyPressed.connect(on_key)
        v.addStretch(1)
        return w

    @QtCore.Slot(list)
    def _set_networks(self, ssids: list):
        self.ssid_cb.clear()
        self.ssid_cb.addItems(ssids)

    @QtCore.Slot(bool,str)
    def _wifi_result(self, ok: bool, msg: str):
        self._show_msg("Wi-Fi" if ok else "Connection failed",
                   msg.strip() or ("OK" if ok else "Unknown error"))

    # ---------- Screen ----------
    def _build_screen_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setSpacing(10)

        # Touch-friendly sizing inside this tab
        w.setStyleSheet("""
            QCheckBox::indicator { width: 28px; height: 28px; }
            QRadioButton::indicator { width: 26px; height: 26px; }
            QPushButton { min-height: 40px; }
            QToolButton { min-height: 52px; min-width: 64px; padding: 8px 14px; }
            QComboBox, QLineEdit { min-height: 36px; }
            QLabel.valueLabel { font-weight: bold; }
        """)

        scr = self.model.ensure_screen_struct()

        # --- Orientation (unchanged functionally) ---
        box = QtWidgets.QGroupBox("Orientation")
        gl = QtWidgets.QGridLayout(box)
        self.orient = QtWidgets.QButtonGroup(self)
        options = [("Normal","normal"),("Left (90)","90"),("Inverted (180)","180"),("Right (270)","270")]
        for i,(label,val) in enumerate(options):
            rb = QtWidgets.QRadioButton(label)
            self.orient.addButton(rb)
            rb.setProperty("val", val)
            if scr.get("orientation") == val:
                rb.setChecked(True)
            gl.addWidget(rb, 0, i)
        apply_btn = QtWidgets.QPushButton("Apply Orientation",
                                        clicked=lambda: self.vm.apply_orientation(self._current_orientation()))
        gl.addWidget(apply_btn, 1, 0, 1, len(options))
        v.addWidget(box)

        # --- Brightness (STEPper buttons) ---
        bgrp = QtWidgets.QGroupBox("Brightness")
        bl = QtWidgets.QHBoxLayout(bgrp)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(12)

        self.b_minus = QtWidgets.QToolButton()
        self.b_minus.setText("-")
        self.b_minus.setAutoRepeat(True)
        self.b_minus.setAutoRepeatDelay(300)
        self.b_minus.setAutoRepeatInterval(120)

        self.b_plus = QtWidgets.QToolButton()
        self.b_plus.setText("+")
        self.b_plus.setAutoRepeat(True)
        self.b_plus.setAutoRepeatDelay(300)
        self.b_plus.setAutoRepeatInterval(120)

        # >>> ADD: enlarge +/- text <<<
        btn_font = QtGui.QFont(self.font().family(), 30, QtGui.QFont.Bold) 
        self.b_minus.setFont(btn_font)
        self.b_plus.setFont(btn_font)

        self.b_val = QtWidgets.QLabel(f"{int(scr.get('brightness', 100))}%")
        f = self.b_val.font(); f.setPointSize(max(35, f.pointSize() + 2)); f.setBold(True)
        self.b_val.setFont(f)
        self.b_val.setAlignment(QtCore.Qt.AlignCenter)
        self.b_val.setMinimumWidth(72)

        bl.addStretch(1)
        bl.addWidget(self.b_minus, 0)
        bl.addWidget(self.b_val,   0)
        bl.addWidget(self.b_plus,  0)
        bl.addStretch(1)
        v.addWidget(bgrp)

        # debounce timer
        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._apply_brightness_debounced)

        # handlers
        self.b_minus.clicked.connect(lambda: self._brightness_step(-10))
        self.b_plus.clicked.connect(lambda: self._brightness_step(+10))

        # status line
        self.b_status = QtWidgets.QLabel("")
        self.b_status.setWordWrap(True)
        self.vm.maintStatusChanged.connect(self.b_status.setText)
        v.addWidget(self.b_status)

        # --- Schedules ---
        v.addWidget(self._build_schedules_editor(), 1)  # give it stretch to favor scrolling

        v.addStretch(0)
        return w

    def _current_orientation(self) -> str:
        for b in self.orient.buttons():
            if b.isChecked():
                return b.property("val") or "normal"
        return "normal"

    def _brightness_step(self, delta: int) -> None:
        try:
            cur = int(self.b_val.text().rstrip("%").strip())
        except Exception:
            cur = 100
        new = max(10, min(100, ((cur + delta + 5) // 10) * 10))
        if new != cur:
            self.b_val.setText(f"{new}%")
            self._debounce.start(150)

    def _apply_brightness_debounced(self):
        try:
            pct = int(self.b_val.text().rstrip("%").strip())
        except Exception:
            pct = 100
        self.vm.apply_brightness(int(pct))

    # --- scrollable, stacked schedule editor -----------------------------------
    def _build_schedules_editor(self) -> QtWidgets.QGroupBox:
        scr = self.model.ensure_screen_struct()
        group = QtWidgets.QGroupBox("Auto screen on/off schedules")
        outer = QtWidgets.QVBoxLayout(group)
        outer.setSpacing(10)
        outer.setContentsMargins(8, 8, 8, 8)

        # Master toggle
        master = QtWidgets.QCheckBox("Enable scheduling (screen is OFF during each window)")
        master.setChecked(bool(scr.get("schedule_enabled", False)))
        def on_master(on: bool):
            scr["schedule_enabled"] = bool(on)
            self.model.save()
            self.vm.maintStatusChanged.emit("Scheduling enabled" if on else "Scheduling disabled")
            self._set_sched_rows_enabled(on)
        master.toggled.connect(on_master)
        outer.addWidget(master)

        # Scroll area for all schedules (touch friendly)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        outer.addWidget(scroll, 1)  # take available space

        container = QtWidgets.QWidget()
        self._sched_container = QtWidgets.QVBoxLayout(container)
        self._sched_container.setSpacing(10)
        self._sched_container.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)

        # Render rows
        def render():
            # clear container
            while self._sched_container.count():
                item = self._sched_container.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            schedules = scr.get("schedules", [])

            for idx, item in enumerate(schedules):
                block = QtWidgets.QFrame()
                block.setFrameShape(QtWidgets.QFrame.StyledPanel)
                block.setStyleSheet("QFrame { background: #ffffff; border: 1px solid #cfcfcf; border-radius: 6px; }")
                col = QtWidgets.QVBoxLayout(block)
                col.setSpacing(8)
                col.setContentsMargins(8, 8, 8, 8)

                # Row 0: enabled + delete
                r0 = QtWidgets.QHBoxLayout()
                enabled = QtWidgets.QCheckBox("Enabled")
                enabled.setChecked(bool(item.get("enabled", False)))
                del_btn = QtWidgets.QPushButton("Delete")
                r0.addWidget(enabled, 0)
                r0.addStretch(1)
                r0.addWidget(del_btn, 0)
                col.addLayout(r0)

                # Row 1: days as big toggle buttons
                days_lbls = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
                chosen = set(int(d) for d in item.get("days", []))
                days_wrap = QtWidgets.QWidget()
                days = QtWidgets.QGridLayout(days_wrap)
                days.setContentsMargins(0,0,0,0)
                days.setHorizontalSpacing(6)
                days.setVerticalSpacing(6)
                day_buttons: List[QtWidgets.QToolButton] = []
                for d, name in enumerate(days_lbls):
                    btn = QtWidgets.QToolButton()
                    btn.setText(name)
                    btn.setCheckable(True)
                    btn.setChecked(d in chosen)
                    btn.setMinimumSize(72, 44)
                    btn.setStyleSheet("""
                        QToolButton { border: 1px solid #c0c0c0; border-radius: 6px; }
                        QToolButton:checked { background: #d0e8ff; border-color: #7fb3ff; }
                    """)
                    day_buttons.append(btn)
                    # grid 4 columns to avoid cramming on narrow screens
                    days.addWidget(btn, d // 4, d % 4)
                col.addWidget(QtWidgets.QLabel("Days:"))
                col.addWidget(days_wrap)

                # Row 2: time selectors (two vertical columns), large dials
                time_row = QtWidgets.QHBoxLayout()
                time_row.setSpacing(16)

                def time_col(title: str, init_val: int):
                    wrap = QtWidgets.QVBoxLayout()
                    wrap.setSpacing(6)
                    wrap.addWidget(QtWidgets.QLabel(title))
                    dial = QtWidgets.QDial()
                    dial.setRange(0, 23)
                    dial.setWrapping(True)
                    dial.setNotchesVisible(True)
                    dial.setFixedSize(120, 120)
                    dial.setValue(int(init_val) % 24)
                    lbl = QtWidgets.QLabel(f"{dial.value():02d}:00")
                    lf = lbl.font(); lf.setPointSize(max(13, lf.pointSize() + 1)); lf.setBold(True)
                    lbl.setFont(lf)
                    lbl.setAlignment(QtCore.Qt.AlignHCenter)
                    wrap.addWidget(dial, 0, QtCore.Qt.AlignHCenter)
                    wrap.addWidget(lbl, 0, QtCore.Qt.AlignHCenter)
                    return wrap, dial, lbl

                off_col, off_dial, off_lbl = time_col("Off at:", item.get("off_hour", 0))
                on_col,  on_dial,  on_lbl  = time_col("On at:",  item.get("on_hour", 7))

                time_row.addLayout(off_col, 1)
                time_row.addStretch(1)
                time_row.addLayout(on_col, 1)
                col.addLayout(time_row)

                # Row 3: summary
                summary = QtWidgets.QLabel(f"{off_dial.value():02d}:00 -> {on_dial.value():02d}:00")
                sf = summary.font(); sf.setBold(True); summary.setFont(sf)
                summary.setAlignment(QtCore.Qt.AlignCenter)
                col.addWidget(summary)

                # Commit logic
                def update_labels():
                    off_lbl.setText(f"{off_dial.value():02d}:00")
                    on_lbl.setText(f"{on_dial.value():02d}:00")
                    summary.setText(f"{off_dial.value():02d}:00 -> {on_dial.value():02d}:00")

                def commit(i=idx):
                    days_sel = [d for d,btn in enumerate(day_buttons) if btn.isChecked()]
                    scr["schedules"][i] = {
                        "enabled": enabled.isChecked(),
                        "off_hour": int(off_dial.value()),
                        "on_hour":  int(on_dial.value()),
                        "days": days_sel
                    }
                    self.model.mirror_first_enabled_schedule_to_legacy()
                    self.model.save()
                    self.vm.set_schedules(scr["schedules"])
                    update_labels()

                enabled.toggled.connect(lambda _=None, i=idx: commit(i))
                for d_btn in day_buttons:
                    d_btn.toggled.connect(lambda _=None, i=idx: commit(i))
                off_dial.valueChanged.connect(lambda _=None, i=idx: commit(i))
                on_dial.valueChanged.connect(lambda _=None, i=idx: commit(i))

                del_btn.clicked.connect(lambda _=None, i=idx: (
                    scr["schedules"].pop(i),
                    self.model.save(),
                    render(),
                    self.vm.set_schedules(scr["schedules"])
                ))

                self._sched_container.addWidget(block)

            # Add schedule button (inside the scrollable area)
            add = QtWidgets.QPushButton("Add schedule")
            add.clicked.connect(lambda: (
                scr["schedules"].append({
                    "enabled": True, "off_hour": 0, "on_hour": 7, "days": [0,1,2,3,4,5,6]
                }),
                self.model.save(),
                render(),
                self.vm.set_schedules(scr["schedules"])
            ))
            self._sched_container.addWidget(add)
            self._sched_container.addStretch(1)  # keep items stacked top-to-bottom

        render()
        # respect master toggle state for row enablement
        self._set_sched_rows_enabled(master.isChecked())
        return group

    def _set_sched_rows_enabled(self, on: bool) -> None:
        # enable/disable all schedule blocks and the Add button
        lay = self._sched_container
        for i in range(lay.count()):
            it = lay.itemAt(i)
            w = it.widget()
            if w:
                w.setEnabled(on)

    # ---------- About ----------
    def _build_about_tab(self):
        w = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(w)
        about = self.model.data.get("about", {}) if isinstance(self.model.data, dict) else {}
        text = about.get("text","Digital Photo Frame")
        img_path = about.get("image_path","")
        lbl = QtWidgets.QLabel(text); lbl.setWordWrap(True); lbl.setAlignment(QtCore.Qt.AlignHCenter)
        v.addWidget(lbl)
        self._about_img_refs = None
        if isinstance(img_path, str) and img_path and QtCore.QFileInfo(img_path).isFile():
            try:
                im = Image.open(img_path)
                if getattr(im, "is_animated", False):
                    frames = [f.copy().resize((300,300), Image.Resampling.LANCZOS) for f in ImageSequence.Iterator(im)]
                    self._about_img_refs = [self._to_qpix(fr) for fr in frames]
                    pic = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter); v.addWidget(pic)
                    def animate(i=0):
                        pic.setPixmap(self._about_img_refs[i])
                        QtCore.QTimer.singleShot(im.info.get("duration", 100), lambda: animate((i+1)%len(self._about_img_refs)))
                    animate()
                else:
                    pix = self._to_qpix(im.resize((300,300), Image.Resampling.LANCZOS))
                    v.addWidget(QtWidgets.QLabel(pixmap=pix, alignment=QtCore.Qt.AlignCenter))
            except Exception:
                pass
        v.addStretch(1)
        
        footer = QtWidgets.QLabel("Created by: alws34 \nhttps://github.com/alws34/")
        footer.setAlignment(QtCore.Qt.AlignHCenter)
        footer.setWordWrap(True)
        footer.setObjectName("about_footer")
        footer.setStyleSheet("color: #666666; font-size: 11px;")
        v.addWidget(footer)

        return w

    @staticmethod
    def _to_qpix(pil_img) -> QtGui.QPixmap:
        buf = io.BytesIO(); pil_img.save(buf, format="PNG"); qimg = QtGui.QImage.fromData(buf.getvalue(), "PNG")
        return QtGui.QPixmap.fromImage(qimg)

    # ---------- Notifications ----------
    def _build_notifications_tab(self):
        w = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(w)
        self.notif = QtWidgets.QTableWidget(0, 3)
        self.notif.setHorizontalHeaderLabels(["TS","LEVEL","TEXT"])
        self.notif.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.notif)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QPushButton("Refresh", clicked=self.vm.refresh_notifications))
        row.addWidget(QtWidgets.QPushButton("Clear", clicked=self.vm.clear_notifications))
        row.addStretch(1)
        v.addLayout(row)
        return w

    @QtCore.Slot(list)
    def _fill_notifications(self, items: list):
        self.notif.setRowCount(0)
        for it in items:
            r = self.notif.rowCount(); self.notif.insertRow(r)
            self.notif.setItem(r,0, QtWidgets.QTableWidgetItem(str(it.get("ts",""))))
            self.notif.setItem(r,1, QtWidgets.QTableWidgetItem(str(it.get("level",""))))
            self.notif.setItem(r,2, QtWidgets.QTableWidgetItem(str(it.get("text",""))))

    # ---------- Config (generic JSON editor) ----------
    def _build_config_tab(self):
        outer = QtWidgets.QWidget()
        ov = QtWidgets.QVBoxLayout(outer)
        ov.setContentsMargins(6, 6, 6, 6)
        ov.setSpacing(8)

        self._cfg_vars = {}

        # Split top-level keys
        free, nested = {}, {}
        for k, v in (self.model.data.items() if isinstance(self.model.data, dict) else []):
            (nested if isinstance(v, dict) else free)[k] = v

        # Vertical splitter -> top ("General") and bottom ("Nested tabs")
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self._config_splitter = splitter  # <- store for show/resize control

        # --- top: General (scrollable) ---
        gen_scroll = QtWidgets.QScrollArea()
        gen_scroll.setWidgetResizable(True)
        gen_wrap = QtWidgets.QWidget()
        gen_scroll.setWidget(gen_wrap)
        gen_v = QtWidgets.QVBoxLayout(gen_wrap)
        gen_v.setContentsMargins(6, 6, 6, 6)
        gen_v.setSpacing(8)

        general = QtWidgets.QGroupBox("General (top-level fields)")
        gform = QtWidgets.QFormLayout(general)
        gform.setRowWrapPolicy(QtWidgets.QFormLayout.DontWrapRows)
        gform.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        gform.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        gform.setFormAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        gform.setHorizontalSpacing(10)
        gform.setVerticalSpacing(6)
        for key in sorted(free.keys()):
            self._render_scalar_row(gform, key, free[key], (key,))
        gen_v.addWidget(general)

        splitter.addWidget(gen_scroll)

        # --- bottom: nested tabs (each page scrollable) ---
        tabs_container = QtWidgets.QWidget()
        tc_v = QtWidgets.QVBoxLayout(tabs_container)
        tc_v.setContentsMargins(0, 0, 0, 0)
        tc_v.setSpacing(0)

        nb = QtWidgets.QTabWidget()
        tc_v.addWidget(nb, 1)

        if nested:
            for key in sorted(nested.keys()):
                page_scroll = QtWidgets.QScrollArea()
                page_scroll.setWidgetResizable(True)
                page = QtWidgets.QWidget()
                page_scroll.setWidget(page)

                page_v = QtWidgets.QVBoxLayout(page)
                page_v.setContentsMargins(6, 6, 6, 6)
                page_v.setSpacing(8)

                self._render_dict_into_tab(page_v, str(key), nested[key], (key,))
                page_v.addStretch(1)

                nb.addTab(page_scroll, str(key))

        splitter.addWidget(tabs_container)

        # Equal stretch; exact 50/50 is applied in show/resize hooks
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        ov.addWidget(splitter, 1)

        # Buttons pinned at bottom
        btnrow = QtWidgets.QHBoxLayout()
        btnrow.addWidget(QtWidgets.QPushButton("Save", clicked=self._config_save))
        btnrow.addWidget(QtWidgets.QPushButton("Revert", clicked=self._config_revert))
        btnrow.addStretch(1)
        ov.addLayout(btnrow)

        return outer

    def _set_config_splitter_50_50(self) -> None:
        try:
            sp = getattr(self, "_config_splitter", None)
            if sp is None:
                return
            # If sizes are not set yet, default to equal halves
            total = sum(sp.sizes()) or max(2, sp.height())
            sp.setSizes([total // 2, total - (total // 2)])
        except Exception:
            pass

    def showEvent(self, e: QtGui.QShowEvent) -> None:
        super().showEvent(e)
        # After first show, enforce 50/50 once the widget has a size
        QtCore.QTimer.singleShot(0, self._set_config_splitter_50_50)

    def resizeEvent(self, e: QtGui.QResizeEvent) -> None:
        super().resizeEvent(e)
        # Keep the 50/50 ratio on user/in-code resizes
        self._set_config_splitter_50_50()

    # NOTE: The following three helper definitions were duplicated in your file.
    # Keeping them as-is to preserve behavior and avoid refactors.

    def _render_dict_into_tab(self, layout: QtWidgets.QVBoxLayout, title: str, data: dict, path: tuple):
        free, nested = {}, {}
        for k, v in data.items():
            (nested if isinstance(v, dict) else free)[k] = v

        sect = QtWidgets.QGroupBox(f"{title} fields")
        form = QtWidgets.QFormLayout(sect)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.DontWrapRows)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        form.setFormAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        for key in sorted(free.keys()):
            self._render_scalar_row(form, key, free[key], path + (key,))
        layout.addWidget(sect)

        if nested:
            sub_nb = QtWidgets.QTabWidget()
            sub_nb.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            layout.addWidget(sub_nb, 1)

            for key in sorted(nested.keys()):
                sub_scroll = QtWidgets.QScrollArea()
                sub_scroll.setWidgetResizable(True)
                sub_page = QtWidgets.QWidget()
                sub_scroll.setWidget(sub_page)

                sub_v = QtWidgets.QVBoxLayout(sub_page)
                sub_v.setContentsMargins(6, 6, 6, 6)
                sub_v.setSpacing(8)

                self._render_dict_into_tab(sub_v, str(key), nested[key], path + (key,))
                sub_v.addStretch(1)

                sub_nb.addTab(sub_scroll, str(key))

    def _render_dict_into_tab(self, layout: QtWidgets.QVBoxLayout, title: str, data: dict, path: tuple):
        free, nested = {}, {}
        for k, v in data.items():
            (nested if isinstance(v, dict) else free)[k] = v

        sect = QtWidgets.QGroupBox(f"{title} fields")
        form = QtWidgets.QFormLayout(sect)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.DontWrapRows)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        form.setFormAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

        for key in sorted(free.keys()):
            self._render_scalar_row(form, key, free[key], path + (key,))
        layout.addWidget(sect)

        if nested:
            # nested groups as sub-tabs, also scrollable
            nb = QtWidgets.QTabWidget()
            layout.addWidget(nb, 1)
            for key in sorted(nested.keys()):
                sub_scroll = QtWidgets.QScrollArea()
                sub_scroll.setWidgetResizable(True)
                sub_page = QtWidgets.QWidget()
                sub_scroll.setWidget(sub_page)

                sub_v = QtWidgets.QVBoxLayout(sub_page)
                sub_v.setContentsMargins(6, 6, 6, 6)
                sub_v.setSpacing(8)

                self._render_dict_into_tab(sub_v, str(key), nested[key], path + (key,))
                sub_v.addStretch(1)

                nb.addTab(sub_scroll, str(key))

    def _render_dict_into_tab(self, layout: QtWidgets.QVBoxLayout, title: str, data: dict, path: tuple):
        free, nested = {}, {}
        for k, v in data.items():
            (nested if isinstance(v, dict) else free)[k] = v

        sect = QtWidgets.QGroupBox(f"{title} fields"); form = QtWidgets.QFormLayout(sect)
        for key in sorted(free.keys()):
            self._render_scalar_row(form, key, free[key], path + (key,))
        layout.addWidget(sect)

        if nested:
            nb = QtWidgets.QTabWidget(); layout.addWidget(nb, 1)
            for key in sorted(nested.keys()):
                tab = QtWidgets.QWidget(); tab.setLayout(QtWidgets.QVBoxLayout()); nb.addTab(tab, str(key))
                self._render_dict_into_tab(tab.layout(), str(key), nested[key], path + (key,))

    def _render_scalar_row(self, form: QtWidgets.QFormLayout, label: str, value: object, path: tuple):
        lab = QtWidgets.QLabel(label)
        if isinstance(value, bool):
            w = QtWidgets.QCheckBox(); w.setChecked(bool(value)); form.addRow(lab, w); self._cfg_vars[path] = (w, "bool"); return
        if isinstance(value, int) or isinstance(value, float):
            w = QtWidgets.QLineEdit(str(value))
            w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            form.addRow(lab, w); self._cfg_vars[path] = (w, "num"); return
        if isinstance(value, list):
            w = QtWidgets.QLineEdit(json.dumps(value))
            w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            form.addRow(lab, w); self._cfg_vars[path] = (w, "json"); return
        w = QtWidgets.QLineEdit("" if value is None else str(value))
        w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        form.addRow(lab, w); self._cfg_vars[path] = (w, "str")

    def _config_revert(self):
        try:
            # find the QTabWidget hosting the pages
            tabs = None
            for child in self.findChildren(QtWidgets.QTabWidget):
                tabs = child
                break
            if not tabs:
                return

            # locate the "Config" tab by title
            idx = next((i for i in range(tabs.count()) if tabs.tabText(i) == "Config"), -1)
            if idx < 0:
                return

            # rebuild the page and re-wrap it in a scroll area
            new_cfg = self._build_config_tab()
            self._config = new_cfg
            tabs.removeTab(idx)
            tabs.insertTab(idx, self._wrap_scroll(new_cfg), "Config")
            tabs.setCurrentIndex(idx)
        except Exception as e:
            self._show_msg("Error", f"Failed to revert config: {e}")

    def _config_save(self):
        # collect values and save
        def set_by_path(obj, path, value):
            cur = obj
            for p in path[:-1]: cur = cur[p]
            cur[path[-1]] = value

        import ast, json as _json
        for path, (w, t) in self._cfg_vars.items():
            if t == "bool":
                val = w.isChecked()
            elif t == "num":
                s = w.text().strip()
                try: val = int(s) if s.isdigit() or (s and s[0] in "+-" and s[1:].isdigit()) else float(s)
                except Exception: val = 0
            elif t == "json":
                s = w.text().strip()
                try: val = _json.loads(s) if s else []
                except Exception:
                    try: val = ast.literal_eval(s)
                    except Exception: val = s
            else:
                val = w.text()
            set_by_path(self.model.data, path, val)

            self.model.mirror_first_enabled_schedule_to_legacy()
            self.model.save()
            self._set_version_label()  # refresh Version label if it changed
            self._show_msg("Saved", "Settings saved.")
