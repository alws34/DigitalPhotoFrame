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
        self.setWindowTitle("Settings")
        self.resize(1000, 720)
        self.setModal(True)

        tabs = QtWidgets.QTabWidget(self); self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(tabs)

        self._stats   = self._build_stats_tab()
        self._wifi    = self._build_wifi_tab()
        self._screen  = self._build_screen_tab()
        self._about   = self._build_about_tab()
        self._notif   = self._build_notifications_tab()
        self._config  = self._build_config_tab()

        tabs.addTab(self._stats,  "Stats")
        tabs.addTab(self._wifi,   "Wi-Fi")
        tabs.addTab(self._screen, "Screen")
        tabs.addTab(self._about,  "About")
        tabs.addTab(self._notif,  "Notifications")
        tabs.addTab(self._config, "Config")

        # wire VM signals
        vm.statsChanged.connect(self._on_stats_changed)
        vm.qrTextChanged.connect(self._on_qr_changed)
        vm.networksChanged.connect(self._set_networks)
        vm.wifiResult.connect(self._wifi_result)
        vm.maintStatusChanged.connect(self._set_maint_status)
        vm.notificationsChanged.connect(self._fill_notifications)
        vm.cpuPushed.connect(self.cpu_graph.push)
        vm.ramPushed.connect(self.ram_graph.push)
        vm.tempPushed.connect(self.tmp_graph.push)

        vm.prime()
        vm.start_local_stats(1000)
        vm.refresh_notifications()
        vm.scan_wifi()

    # ---------- Stats ----------
    def _build_stats_tab(self):
        w = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(w)
        top = QtWidgets.QWidget(); top_l = QtWidgets.QVBoxLayout(top); top_l.setAlignment(QtCore.Qt.AlignHCenter)
        self.ssid_lbl = QtWidgets.QLabel("Wi-Fi: Loading…")
        self.url_lbl  = QtWidgets.QLabel("URL: Loading…")
        self.qr_lbl   = QtWidgets.QLabel()
        self.qr_lbl.setMinimumSize(160,160); self.qr_lbl.setAlignment(QtCore.Qt.AlignCenter)
        for lbl in (self.ssid_lbl, self.url_lbl): lbl.setAlignment(QtCore.Qt.AlignCenter)
        top_l.addWidget(self.ssid_lbl); top_l.addWidget(self.url_lbl); top_l.addWidget(self.qr_lbl)
        lay.addWidget(top)

        # graphs
        g = QtWidgets.QWidget(); gl = QtWidgets.QFormLayout(g)
        self.cpu_graph = Sparkline(maxlen=60); self.ram_graph = Sparkline(maxlen=60); self.tmp_graph = Sparkline(maxlen=60)
        gl.addRow("CPU %", self.cpu_graph)
        gl.addRow("RAM %", self.ram_graph)
        gl.addRow("Temp °C", self.tmp_graph)
        lay.addWidget(g)

        # maintenance
        row = QtWidgets.QHBoxLayout()
        self.pull_btn = QtWidgets.QPushButton("Pull updates now", clicked=self.vm.pull_updates)
        self.restart_btn = QtWidgets.QPushButton("Restart service", clicked=self.vm.restart_service)
        self.maint_status = QtWidgets.QLabel("")
        row.addWidget(self.pull_btn); row.addSpacing(8); row.addWidget(self.restart_btn); row.addSpacing(16); row.addWidget(self.maint_status, 1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

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
        QtWidgets.QMessageBox.information(self, "Wi-Fi" if ok else "Connection failed", msg.strip() or ("OK" if ok else "Unknown error"))

    # ---------- Screen ----------
    def _build_screen_tab(self):
        w = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(w)
        scr = self.model.ensure_screen_struct()

        # Orientation
        box = QtWidgets.QGroupBox("Orientation"); gl = QtWidgets.QGridLayout(box)
        self.orient = QtWidgets.QButtonGroup(self)
        options = [("Normal","normal"),("Left (90)","90"),("Inverted (180)","180"),("Right (270)","270")]
        for i,(label,val) in enumerate(options):
            rb = QtWidgets.QRadioButton(label); self.orient.addButton(rb); rb.setProperty("val", val)
            if scr.get("orientation") == val: rb.setChecked(True)
            gl.addWidget(rb, 0, i)
        apply_btn = QtWidgets.QPushButton("Apply Orientation", clicked=lambda: self.vm.apply_orientation(self._current_orientation()))
        gl.addWidget(apply_btn, 1, 0, 1, len(options))
        v.addWidget(box)

        # Brightness
        bgrp = QtWidgets.QGroupBox("Brightness"); bl = QtWidgets.QGridLayout(bgrp)
        bl.addWidget(QtWidgets.QLabel("Level:"), 0, 0)
        self.b_val = QtWidgets.QLabel(f"{int(scr.get('brightness',100))}%"); bl.addWidget(self.b_val, 0, 2)
        self.b_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.b_scale.setRange(10,100); self.b_scale.setValue(int(scr.get("brightness",100)))
        bl.addWidget(self.b_scale, 0, 1)
        v.addWidget(bgrp)

        # debounce + snap to 10
        self._debounce = QtCore.QTimer(self); self._debounce.setSingleShot(True); self._debounce.timeout.connect(self._apply_brightness_debounced)
        def on_slide(val):
            snapped = max(10, min(100, int(round(val/10.0)*10)))
            if snapped != val:
                self.b_scale.blockSignals(True); self.b_scale.setValue(snapped); self.b_scale.blockSignals(False)
            self.b_val.setText(f"{snapped}%")
            self._debounce.start(150)
        self.b_scale.valueChanged.connect(on_slide)

        # Schedules
        v.addWidget(self._build_schedules_editor())
        v.addStretch(1)
        return w

    def _current_orientation(self) -> str:
        for b in self.orient.buttons():
            if b.isChecked(): return b.property("val")
        return "normal"

    def _apply_brightness_debounced(self):
        self.vm.apply_brightness(int(self.b_scale.value()))

    def _build_schedules_editor(self) -> QtWidgets.QGroupBox:
        scr = self.model.ensure_screen_struct()
        group = QtWidgets.QGroupBox("Auto screen on/off schedules (OFF during each window)")
        outer = QtWidgets.QVBoxLayout(group)

        self._sched_area = QtWidgets.QVBoxLayout(); outer.addLayout(self._sched_area)

        def render():
            # clear
            while self._sched_area.count():
                it = self._sched_area.takeAt(0)
                w = it.widget()
                if w: w.deleteLater()

            for idx, item in enumerate(scr.get("schedules", [])):
                row = QtWidgets.QFrame(); row.setFrameShape(QtWidgets.QFrame.StyledPanel)
                hl = QtWidgets.QHBoxLayout(row)
                enabled = QtWidgets.QCheckBox(); enabled.setChecked(bool(item.get("enabled", False)))
                hl.addWidget(enabled)

                # days
                days_lbl = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
                day_checks = []
                days_box = QtWidgets.QWidget(); db = QtWidgets.QHBoxLayout(days_box); db.setContentsMargins(0,0,0,0)
                chosen = set(int(d) for d in item.get("days", []))
                for d in range(7):
                    cb = QtWidgets.QCheckBox(days_lbl[d]); cb.setChecked(d in chosen); db.addWidget(cb); day_checks.append(cb)
                hl.addWidget(days_box, 1)

                def mk_hour(initial: int):
                    wrap = QtWidgets.QWidget(); gl = QtWidgets.QGridLayout(wrap); gl.setContentsMargins(0,0,0,0)
                    sc = QtWidgets.QSlider(QtCore.Qt.Horizontal); sc.setRange(0,23); sc.setValue(int(initial)%24)
                    lbl = QtWidgets.QLabel(f"{int(initial)%24:02d}:00")
                    def on(v): lbl.setText(f"{int(v)%24:02d}:00")
                    sc.valueChanged.connect(on)
                    gl.addWidget(sc,0,0); gl.addWidget(lbl,0,1)
                    return wrap, sc
                off_w, off_sc = mk_hour(item.get("off_hour", 0))
                on_w,  on_sc  = mk_hour(item.get("on_hour", 7))
                win_lbl = QtWidgets.QLabel("")

                def update_win():
                    win_lbl.setText(f"{off_sc.value():02d}:00 → {on_sc.value():02d}:00")
                update_win()

                hl.addWidget(off_w); hl.addWidget(on_w); hl.addWidget(win_lbl)

                del_btn = QtWidgets.QPushButton("Delete")
                hl.addWidget(del_btn)

                def commit():
                    days = [d for d,cb in enumerate(day_checks) if cb.isChecked()]
                    scr["schedules"][idx] = {
                        "enabled": enabled.isChecked(),
                        "off_hour": int(off_sc.value()),
                        "on_hour":  int(on_sc.value()),
                        "days": days
                    }
                    update_win()
                    self.model.mirror_first_enabled_schedule_to_legacy()
                    self.model.save()
                    self.vm.set_schedules(scr["schedules"])

                enabled.toggled.connect(lambda _=None: commit())
                for cb in day_checks: cb.toggled.connect(lambda _=None: commit())
                off_sc.sliderReleased.connect(lambda _=None: commit())
                on_sc.sliderReleased.connect(lambda _=None: commit())
                del_btn.clicked.connect(lambda _=None, i=idx: (scr["schedules"].pop(i), self.model.save(), render(), self.vm.set_schedules(scr["schedules"])))

                self._sched_area.addWidget(row)

            # add button
            add = QtWidgets.QPushButton("Add schedule")
            add.clicked.connect(lambda: (scr["schedules"].append({
                "enabled": True, "off_hour": 0, "on_hour": 7, "days": [0,1,2,3,4,5,6]
            }), self.model.save(), render(), self.vm.set_schedules(scr["schedules"])))
            self._sched_area.addWidget(add)

        render()
        return group

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
        w = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(w)
        self._cfg_vars = {}  # path tuple -> (widget, type)
        # split top level
        free, nested = {}, {}
        for k, v in (self.model.data.items() if isinstance(self.model.data, dict) else []):
            (nested if isinstance(v, dict) else free)[k] = v

        general = QtWidgets.QGroupBox("General (top-level fields)")
        gform = QtWidgets.QFormLayout(general)
        for key in sorted(free.keys()):
            self._render_scalar_row(gform, key, free[key], (key,))
        layout.addWidget(general)

        if nested:
            nb = QtWidgets.QTabWidget(); layout.addWidget(nb, 1)
            for key in sorted(nested.keys()):
                tab = QtWidgets.QWidget(); tab.setLayout(QtWidgets.QVBoxLayout()); nb.addTab(tab, str(key))
                self._render_dict_into_tab(tab.layout(), str(key), nested[key], (key,))

        btnrow = QtWidgets.QHBoxLayout()
        btnrow.addWidget(QtWidgets.QPushButton("Save", clicked=self._config_save))
        btnrow.addWidget(QtWidgets.QPushButton("Revert", clicked=self._config_revert))
        btnrow.addStretch(1)
        layout.addLayout(btnrow)
        return w

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
            w = QtWidgets.QLineEdit(str(value)); form.addRow(lab, w); self._cfg_vars[path] = (w, "num"); return
        if isinstance(value, list):
            w = QtWidgets.QLineEdit(json.dumps(value)); form.addRow(lab, w); self._cfg_vars[path] = (w, "json"); return
        w = QtWidgets.QLineEdit("" if value is None else str(value)); form.addRow(lab, w); self._cfg_vars[path] = (w, "str")

    def _config_revert(self):
        parent = self.parent()
        idx = self.layout().indexOf(self._config)
        self.layout().removeWidget(self._config)
        self._config.deleteLater()
        self._config = self._build_config_tab()
        self.layout().insertWidget(idx, self._config)

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
        QtWidgets.QMessageBox.information(self, "Saved", "Settings saved.")
