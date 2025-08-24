import os
import re
import json
import qrcode
import threading
import subprocess
from typing import Callable, Dict, Any, List, Tuple
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox

from Utilities.network_utils import get_local_ip


class SettingsForm:
    """
    Settings dialog with:
      - Stats tab (labels + sparklines + QR)
      - Wi-Fi tab (scan/connect + on-screen keyboard)
      - Screen tab (orientation, live brightness, multi-schedules)
      - About tab
    """
    def __init__(
        self,
        parent: tk.Tk,
        settings: Dict[str, Any],
        backend_port: int,
        on_apply_brightness: Callable[[int], bool],
        on_apply_orientation: Callable[[str], bool],
        on_autoupdate_pull: Callable[[], None],
        on_restart_service_async: Callable[[], None],
        wake_screen_worker: Callable[[], None],
        settings_path: str | None = None, 
        notifications = None,
    ) -> None:
        self.parent = parent
        self.settings = settings
        self.backend_port = backend_port
        self._on_apply_brightness = on_apply_brightness
        self._on_apply_orientation = on_apply_orientation
        self._on_autoupdate_pull = on_autoupdate_pull
        self._on_restart_service_async = on_restart_service_async
        self._wake = wake_screen_worker
        self._settings_path = settings_path
        self._brightness_debounce_job = None
        self.notifications = notifications

        self.form: tk.Toplevel = tk.Toplevel(self.parent)
        self.form.withdraw()
        self.form.title("Settings")
        self.form.transient(self.parent)
        self.form.resizable(False, False)

        sw, sh = self.parent.winfo_screenwidth(), self.parent.winfo_screenheight()
        margin_w = int(sw * 0.1)
        margin_h = int(sh * 0.1)
        width = max(600, sw - margin_w)
        height = max(400, sh - margin_h)
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.form.geometry(f"{width}x{height}+{x}+{y}")
        self.form.lift()
        self.form.attributes("-topmost", True)

        self._build_ui()
        self.form.deiconify()
        try:
            self.form.grab_set()
        except Exception:
            pass

    def window(self) -> tk.Toplevel:
        return self.form

    # ----------------- Shared screen cfg helpers -----------------
    def _ensure_screen_struct(self) -> Dict[str, Any]:
        scr = self.settings.setdefault("screen", {})
        scr.setdefault("orientation", "normal")
        scr.setdefault("brightness", 100)
        scr.setdefault("schedule_enabled", False)
        scr.setdefault("off_hour", 0)
        scr.setdefault("on_hour", 7)
        # multi-schedule list
        if "schedules" not in scr or not isinstance(scr["schedules"], list):
            scr["schedules"] = [{
                "enabled": False,
                "off_hour": 0,
                "on_hour": 7,
                "days": [0,1,2,3,4,5,6]  # Mon..Sun (tm_wday)
            }]
        return scr

    def _mirror_first_enabled_schedule_to_legacy(self, scr: Dict[str, Any]) -> None:
        sch = [s for s in scr.get("schedules", []) if s.get("enabled")]
        if sch:
            first = sch[0]
            scr["schedule_enabled"] = True
            scr["off_hour"] = int(first.get("off_hour", 0)) % 24
            scr["on_hour"]  = int(first.get("on_hour", 7)) % 24
        else:
            scr["schedule_enabled"] = False

    def _save_settings(self) -> None:
        try:
            if self._settings_path and os.path.isabs(self._settings_path):
                path = self._settings_path
            else:
                # fall back to DesktopApp/photoframe_settings.json
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                path = os.path.join(base_dir, "photoframe_settings.json")
            with open(path, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            messagebox.showerror("Failed to save settings", str(e))
            
            
    # ----------------- UI shell -----------------
    def _build_ui(self) -> None:
        nb = ttk.Notebook(self.form)
        self.nb = nb 
        
        self.stats_tab = ttk.Frame(nb)
        self.wifi_tab = ttk.Frame(nb)
        self.screen_tab = ttk.Frame(nb)
        self.about_tab = ttk.Frame(nb)
        self.notif_tab = ttk.Frame(nb)
       
        
        nb.add(self.stats_tab, text="Stats")
        nb.add(self.wifi_tab, text="Wi-Fi")
        nb.add(self.screen_tab, text="Screen")
        nb.add(self.about_tab, text="About")
        nb.add(self.notif_tab, text="Notifications")
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        self._stats_root  = self._make_scrollable(self.stats_tab)
        self._wifi_root   = self._make_scrollable(self.wifi_tab)
        self._screen_root = self._make_scrollable(self.screen_tab)
        self._about_root  = self._make_scrollable(self.about_tab)
        self._notif_root  = self._make_scrollable(self.notif_tab)

        self._build_stats_tab()
        self._build_wifi_tab()
        self._build_screen_tab()
        self._build_about_tab()
        self._build_notifications_tab()
        self._apply_saved_on_open()
        
        
    def _on_tab_changed(self, event):
        try:
            nb = event.widget
            current_tab = nb.nametowidget(nb.select())
            if current_tab is self.notif_tab:
                self._refresh_notifications()
        except Exception:
            pass
    # ----------------- Stats tab -----------------
    class Sparkline:
        def __init__(self, parent, width=560, height=70, maxlen=60):
            self.width = width
            self.height = height
            self.pad = 6
            self.data: List[float] = []
            self.maxlen = maxlen
            self.canvas = tk.Canvas(
                parent, width=width, height=height,
                highlightthickness=1, highlightbackground="#bdbdbd", bg="#ffffff"
            )
            self._draw_grid()

        def widget(self):
            return self.canvas

        def _draw_grid(self):
            c = self.canvas
            c.delete("grid")
            w, h, p = self.width, self.height, self.pad
            c.create_rectangle(0.5, 0.5, w-0.5, h-0.5, outline="#e0e0e0", tags="grid")
            for i in range(1, 5):
                x = p + i * (w - 2*p) / 5.0
                c.create_line(x, p, x, h - p, fill="#f0f0f0", tags="grid")
            for i in range(1, 3):
                y = p + i * (h - 2*p) / 3.0
                c.create_line(p, y, w - p, y, fill="#f0f0f0", tags="grid")

        def _scaled_points(self) -> Tuple[List[Tuple[float,float]], float, float]:
            if not self.data:
                return [], 0.0, 1.0
            vals = list(self.data)
            vmin = min(vals)
            vmax = max(vals)
            rng = (vmax - vmin) if vmax > vmin else 1.0
            w, h, p = self.width, self.height, self.pad
            usable_w = w - 2 * p
            usable_h = h - 2 * p
            n = len(vals)
            pts: List[Tuple[float,float]] = []
            for i, v in enumerate(vals):
                x = p + (i * usable_w / max(1, n - 1))
                y_norm = (v - vmin) / rng
                y = h - p - y_norm * usable_h
                pts.append((x, y))
            return pts, vmin, vmax

        def draw(self):
            c = self.canvas
            c.delete("plot")
            pts, vmin, vmax = self._scaled_points()
            if len(pts) < 2:
                return
            area = [(pts[0][0], self.height - self.pad)] + pts + [(pts[-1][0], self.height - self.pad)]
            flat_area = [coord for pt in area for coord in pt]
            c.create_polygon(*flat_area, fill="#e8f2ff", outline="", tags="plot")
            flat = [coord for pt in pts for coord in pt]
            c.create_line(*flat, width=2, fill="#1976d2", tags="plot")
            x_last, y_last = pts[-1]
            r = 2.5
            c.create_oval(x_last - r, y_last - r, x_last + r, y_last + r, fill="#1e88e5", outline="", tags="plot")
            p = self.pad
            c.create_text(self.width - p + 2, self.height - p, text=f"{vmin:.0f}", anchor="se", fill="#9e9e9e", font=("TkDefaultFont", 8), tags="plot")
            c.create_text(self.width - p + 2, p, text=f"{vmax:.0f}", anchor="ne", fill="#9e9e9e", font=("TkDefaultFont", 8), tags="plot")

        def push(self, value: float):
            try:
                v = float(value)
            except Exception:
                return
            self.data.append(v)
            if len(self.data) > self.maxlen:
                self.data = self.data[-self.maxlen:]
            self.draw()

    def _build_stats_tab(self) -> None:
        root = self._stats_root 
        center = ttk.Frame(root)
        center.pack(fill="x", pady=(8, 4))
        self.current_ssid_lbl = ttk.Label(center, text="Wifi network: Loading...")
        self.ip_lbl = ttk.Label(center, text="URL: Loading...")
        self.qr_lbl = ttk.Label(center)
        self.current_ssid_lbl.pack(anchor="center")
        self.ip_lbl.pack(anchor="center", pady=(2, 6))
        self.qr_lbl.pack(anchor="center")

        graphs_col = ttk.Frame(root); graphs_col.pack(anchor="center", pady=(10, 0))
        self.cpu_lbl = ttk.Label(graphs_col, text="CPU: Loading..."); self.cpu_lbl.pack(anchor="center")
        self.cpu_graph = self.Sparkline(graphs_col, width=560, height=70, maxlen=60); self.cpu_graph.widget().pack(anchor="center", pady=(0, 6))
        self.ram_lbl = ttk.Label(graphs_col, text="RAM: Loading..."); self.ram_lbl.pack(anchor="center")
        self.ram_graph = self.Sparkline(graphs_col, width=560, height=70, maxlen=60); self.ram_graph.widget().pack(anchor="center", pady=(0, 6))
        self.tmp_lbl = ttk.Label(graphs_col, text="Temp: Loading..."); self.tmp_lbl.pack(anchor="center")
        self.tmp_graph = self.Sparkline(graphs_col, width=560, height=70, maxlen=60); self.tmp_graph.widget().pack(anchor="center", pady=(0, 6))

        # Maintenance
        maint = ttk.Frame(root); maint.pack(fill="x", pady=(8, 6))
        self.pull_btn = ttk.Button(maint, text="Pull updates now", command=self._pull_updates_clicked)
        self.pull_btn.pack(side="left")

        self.restart_btn = ttk.Button(maint, text="Restart service", command=self._restart_clicked)
        self.restart_btn.pack(side="left", padx=8)

        # Tiny status label to show progress/result
        self.maint_status = ttk.Label(maint, text="", foreground="#888")
        self.maint_status.pack(side="left", padx=12)
        
    # ----------------- Wi-Fi tab -----------------
    class CustomKeyboard:
        def __init__(self, parent, target_entry: tk.Entry):
            self.parent = parent
            self.entry = target_entry
            self.caps = False
            self.shift = False
            self.symbols = False
            self.backspace_job = None
            self.frame = ttk.Frame(parent)
            self.frame.pack(fill="x", pady=(8, 0))
            for i in range(15):
                self.frame.columnconfigure(i, weight=1)
            for i in range(6):
                self.frame.rowconfigure(i, weight=0)
            self._build_rows()

        def _letters_rows(self):
            row0 = ["`","1","2","3","4","5","6","7","8","9","0","-","=","Backspace"]
            row1 = ["Tab","q","w","e","r","t","y","u","i","o","p","[","]","\\"]
            row2 = ["Caps","a","s","d","f","g","h","j","k","l",";","'","Enter"]
            row3 = ["Shift","z","x","c","v","b","n","m",",",".","/","Shift"]
            row4 = ["123/#","Space","Left","Right"]
            return [row0,row1,row2,row3,row4]

        def _symbols_rows(self):
            row0 = ["~","!","@","#","$","%","^","&","*","(",")","_","+","Backspace"]
            row1 = ["Tab","q","w","e","r","t","y","u","i","o","p","{","}","|"]
            row2 = ["Caps","a","s","d","f","g","h","j","k","l",":","\"","Enter"]
            row3 = ["Shift","z","x","c","v","b","n","m","<",">","?","Shift"]
            row4 = ["ABC","Space","Left","Right"]
            return [row0,row1,row2,row3,row4]

        def _build_rows(self):
            for child in self.frame.winfo_children():
                child.destroy()
            rows = self._symbols_rows() if self.symbols else self._letters_rows()
            c = 0
            for key in rows[0]:
                w = self._make_key(key, width=4)
                span = 2 if key == "Backspace" else 1
                w.grid(row=0, column=c, columnspan=span, sticky="nsew", padx=2, pady=2); c += span
            c = 0
            for key in rows[1]:
                span = 2 if key == "Tab" else 1
                w = self._make_key(key, width=4 if key != "Tab" else 6)
                w.grid(row=1, column=c, columnspan=span, sticky="nsew", padx=2, pady=2); c += span
            c = 0
            for key in rows[2]:
                span = 2 if key in ("Caps","Enter") else 1
                w = self._make_key(key, width=4 if key not in ("Caps","Enter") else 7)
                w.grid(row=2, column=c, columnspan=span, sticky="nsew", padx=2, pady=2); c += span
            c = 0
            for key in rows[3]:
                span = 2 if key == "Shift" else 1
                w = self._make_key(key, width=4 if key != "Shift" else 7)
                w.grid(row=3, column=c, columnspan=span, sticky="nsew", padx=2, pady=2); c += span
            sym_key, space_label, left_label, right_label = rows[4]
            self._make_key(sym_key, width=6).grid(row=4, column=0, columnspan=2, sticky="nsew", padx=2, pady=2)
            self._make_key(space_label, width=30).grid(row=4, column=2, columnspan=10, sticky="nsew", padx=2, pady=2)
            self._make_key(left_label, width=4).grid(row=4, column=12, sticky="nsew", padx=2, pady=2)
            self._make_key(right_label, width=4).grid(row=4, column=13, sticky="nsew", padx=2, pady=2)

        def _make_key(self, label, width=4):
            btn = tk.Button(self.frame, text=self._display_label(label), width=width, height=2,
                            command=lambda l=label: self._on_key_press(l))
            if label == "Backspace":
                btn.bind("<ButtonPress-1>", lambda _e: self._start_backspace_repeat())
                btn.bind("<ButtonRelease-1>", lambda _e: self._stop_backspace_repeat())
            return btn

        def _display_label(self, label):
            if label in ("Space","Enter","Tab","Backspace","Left","Right","Caps","Shift","123/#","ABC"):
                return label
            ch = label
            if not self.symbols:
                ch = ch.upper() if (self.shift ^ self.caps) else ch.lower()
            return ch

        def _insert(self, s):
            e = self.entry
            try:
                idx = e.index(tk.INSERT)
                e.insert(idx, s)
            except Exception:
                e.insert(tk.END, s)

        def _backspace_once(self):
            e = self.entry
            try:
                idx = e.index(tk.INSERT)
                if idx > 0:
                    e.delete(idx-1)
            except Exception:
                pass

        def _start_backspace_repeat(self):
            self._backspace_once()
            self._schedule_backspace(250)

        def _schedule_backspace(self, delay):
            self._cancel_backspace_timer()
            self.backspace_job = self.frame.after(delay, self._backspace_repeat)

        def _backspace_repeat(self):
            self._backspace_once()
            self._schedule_backspace(50)

        def _stop_backspace_repeat(self):
            self._cancel_backspace_timer()

        def _cancel_backspace_timer(self):
            if self.backspace_job:
                try:
                    self.frame.after_cancel(self.backspace_job)
                except Exception:
                    pass
                self.backspace_job = None

        def _move_cursor(self, delta):
            e = self.entry
            try:
                idx = e.index(tk.INSERT)
                new_idx = max(0, idx + delta)
                e.icursor(new_idx)
            except Exception:
                pass

        def _on_key_press(self, label):
            if label in ("123/#","ABC"):
                self.symbols = not self.symbols; self.shift = False; self._build_rows(); return
            if label == "Caps":
                self.caps = not self.caps; self._build_rows(); return
            if label == "Shift":
                self.shift = not self.shift; self._build_rows(); return
            if label == "Space":
                self._insert(" "); self._after_char(); return
            if label == "Tab":
                self._insert("\t"); self._after_char(); return
            if label == "Enter":
                return
            if label == "Backspace":
                self._backspace_once(); return
            if label == "Left":
                self._move_cursor(-1); return
            if label == "Right":
                self._move_cursor(+1); return
            ch = self._display_label(label)
            self._insert(ch); self._after_char()

        def _after_char(self):
            if self.shift:
                self.shift = False
                self._build_rows()

    def _build_wifi_tab(self) -> None:
        root = self._wifi_root
        ttk.Label(root, text=f"Network:").pack(anchor="w", pady=(10, 0))
        self.ssid_cb = ttk.Combobox(root, state="readonly")
        self.ssid_cb.pack(fill="x")

        pw_frame = ttk.Frame(root); pw_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(pw_frame, text="Password:").pack(side="left")
        self.pwd_ent = ttk.Entry(pw_frame, show="*")
        self.pwd_ent.pack(side="left", fill="x", expand=True, padx=(5, 0))
        show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            pw_frame, text="Show",
            variable=show_var,
            command=lambda: self.pwd_ent.config(show="" if show_var.get() else "*")
        ).pack(side="left", padx=(5, 0))

        btns = ttk.Frame(root); btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Rescan", command=self._scan_async).pack(side="left")
        ttk.Button(btns, text="Connect", command=self._connect_async).pack(side="left", padx=(8, 0))

        # On-screen keyboard
        self.keyboard = self.CustomKeyboard(root, self.pwd_ent)

        self._scan_async()

    # ----------------- Screen tab -----------------
    def _build_screen_tab(self) -> None:
        scr = self._ensure_screen_struct()
        root = self._screen_root 
        
        top = ttk.Frame(root); top.pack(fill="x", pady=(10, 6))
        ttk.Label(top, text="Orientation:").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.orient_var = tk.StringVar(value=scr.get("orientation", "normal"))
        orow = ttk.Frame(top); orow.grid(row=0, column=1, sticky="w")
        for k, v in [("Normal", "normal"), ("Left (90)", "90"), ("Inverted (180)", "180"), ("Right (270)", "270")]:
            ttk.Radiobutton(orow, text=k, value=v, variable=self.orient_var).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="Apply Orientation", command=self._apply_orientation).grid(row=0, column=2, padx=(12, 0))

        br = ttk.LabelFrame(root, text="Brightness"); br.pack(fill="x", pady=(8, 6))
        br.columnconfigure(1, weight=1)
        ttk.Label(br, text="Level:").grid(row=0, column=0, sticky="w", padx=(8, 8), pady=(8, 8))
        self.br_val_lbl = ttk.Label(br, text=f"{int(scr.get('brightness', 100))}%")
        self.br_val_lbl.grid(row=0, column=2, sticky="w", padx=(8, 0))

        self._snap_lock = {"updating": False}
        def _snap_and_live_apply(v: str) -> None:
            if self._snap_lock["updating"]:
                return
            try:
                raw = float(v)
            except Exception:
                raw = float(self.br_scale.get())
            snapped = max(10, min(100, int(round(raw / 10.0) * 10)))
            self.br_val_lbl.config(text=f"{snapped}%")
            if snapped != int(raw):
                self._snap_lock["updating"] = True
                self.br_scale.set(snapped)
                self._snap_lock["updating"] = False
            # Debounce actual apply
            if self._brightness_debounce_job is not None:
                try:
                    self.form.after_cancel(self._brightness_debounce_job)
                except Exception:
                    pass
            self._brightness_debounce_job = self.form.after(150, lambda: self._apply_brightness(snapped))

        self.br_scale = ttk.Scale(br, from_=10, to=100, orient="horizontal", length=620, command=_snap_and_live_apply)
        self.br_scale.set(int(scr.get("brightness", 100)))
        self.br_scale.grid(row=0, column=1, sticky="we", pady=(8, 8))

        # Multi-schedule editor
        sched_frame = ttk.LabelFrame(root, text="Auto screen on/off schedules (any matching schedule turns screen OFF during its window)")
        sched_frame.pack(fill="both", expand=True, pady=(6, 0))
        sched_frame.columnconfigure(0, weight=1)

        self._build_schedules_ui(sched_frame)

        
    def _make_scrollable(self, parent: tk.Widget) -> ttk.Frame:
        """
        Turn a tab into a full-height scrollable viewport.
        Return the inner frame; build the tab UI into that.
        """
        # Use grid so it fills exactly the tab area
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        container = ttk.Frame(parent)
        container.grid(row=0, column=0, sticky="nsew")

        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")

        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Keep inner width equal to the visible canvas width
        def _on_canvas_config(event):
            try:
                canvas.itemconfigure(win, width=event.width)
            except Exception:
                pass
        canvas.bind("<Configure>", _on_canvas_config)

        # Update scrollregion whenever inner size changes
        def _on_inner_config(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_config)

        # Mouse wheel: bind when cursor enters, unbind when leaves
        def _bind_wheel(_e=None):
            canvas.bind_all("<MouseWheel>", on_wheel_win)
            canvas.bind_all("<Button-4>", on_wheel_x11_up)
            canvas.bind_all("<Button-5>", on_wheel_x11_down)
        def _unbind_wheel(_e=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        def on_wheel_win(e):      # Windows/macOS
            # macOS sometimes uses small delta; this normalizes reasonably
            delta = int(e.delta/120) if e.delta else 0
            canvas.yview_scroll(-delta, "units")
        def on_wheel_x11_up(_e):  # Linux X11
            canvas.yview_scroll(-1, "units")
        def on_wheel_x11_down(_e):
            canvas.yview_scroll(1, "units")

        # Only capture wheel while the pointer is over this canvas
        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        return inner



    def _bind_mousewheel(self, widget: tk.Widget):
        # Windows / Linux
        widget.bind_all("<MouseWheel>", lambda e: widget.yview_scroll(-1 * int(e.delta/120), "units"))
        widget.bind_all("<Button-4>",   lambda e: widget.yview_scroll(-1, "units"))   # X11 up
        widget.bind_all("<Button-5>",   lambda e: widget.yview_scroll( 1, "units"))   # X11 down
        # macOS (sometimes delta is different); above usually suffices


    def _pull_updates_clicked(self) -> None:
        # Disable button, show status, run in background
        try:
            self.pull_btn.state(["disabled"])
            self.maint_status.config(text="Pulling updates...")
        except Exception:
            pass

        def _worker():
            ok = True
            try:
                self._on_autoupdate_pull()  # user-provided callable
            except Exception as e:
                ok = False
                err = str(e)
            finally:
                def _ui():
                    try:
                        self.pull_btn.state(["!disabled"])
                        self.maint_status.config(text="Updates pulled ✓" if ok else f"Update failed: {err}")
                    except Exception:
                        pass
                self.form.after(0, _ui)

        threading.Thread(target=_worker, daemon=True).start()


    def _restart_clicked(self) -> None:
        # Disable both buttons because the app may go away
        try:
            self.restart_btn.state(["disabled"])
            self.pull_btn.state(["disabled"])
            self.maint_status.config(text="Restarting service...")
        except Exception:
            pass

        def _worker():
            ok = True
            err = ""
            try:
                # user-provided callable should *not* block indefinitely
                self._on_restart_service_async()
            except Exception as e:
                ok = False
                err = str(e)
            finally:
                def _ui():
                    # After restart call returns, re-enable (if process didn’t exit)
                    try:
                        self.restart_btn.state(["!disabled"])
                        self.pull_btn.state(["!disabled"])
                        self.maint_status.config(text="Restart requested ✓" if ok else f"Restart failed: {err}")
                    except Exception:
                        pass
                self.form.after(0, _ui)

        threading.Thread(target=_worker, daemon=True).start()


    def _build_schedules_ui(self, parent: ttk.Frame) -> None:
        scr_cfg = self._ensure_screen_struct()
        days_labels = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

        rows_container = ttk.Frame(parent)
        rows_container.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        rows_container.columnconfigure(0, weight=1)

        def render():
            for child in rows_container.winfo_children():
                child.destroy()

            header = ttk.Frame(rows_container)
            header.grid(row=0, column=0, sticky="we")
            ttk.Label(header, text="Enabled", width=8).grid(row=0, column=0, padx=(0,8))
            ttk.Label(header, text="Days").grid(row=0, column=1, padx=(0,8))
            ttk.Label(header, text="OFF at").grid(row=0, column=2, padx=(0,8))
            ttk.Label(header, text="ON at").grid(row=0, column=3, padx=(0,8))
            ttk.Label(header, text="Window").grid(row=0, column=4, padx=(0,8))
            ttk.Label(header, text="").grid(row=0, column=5)

            for idx, item in enumerate(scr_cfg.get("schedules", []), start=1):
                row = ttk.Frame(rows_container)
                row.grid(row=idx, column=0, sticky="we", pady=4)
                row.columnconfigure(1, weight=1)

                enabled_var = tk.BooleanVar(value=bool(item.get("enabled", False)))
                ttk.Checkbutton(row, variable=enabled_var).grid(row=0, column=0, padx=(0,8))

                days_frame = ttk.Frame(row); days_frame.grid(row=0, column=1, sticky="w", padx=(0,8))
                day_vars: List[tk.BooleanVar] = []
                chosen = set(int(d) for d in item.get("days", []))
                for d in range(7):
                    v = tk.BooleanVar(value=(d in chosen))
                    cb = ttk.Checkbutton(days_frame, text=days_labels[d], variable=v)
                    cb.pack(side="left", padx=2)
                    day_vars.append(v)

                def mk_hour_cell(parent, init_val, on_change):
                    cell = ttk.Frame(parent)
                    cell.columnconfigure(0, weight=1)
                    sc = ttk.Scale(cell, from_=0, to=23, orient="horizontal", length=180)
                    sc.grid(row=0, column=0, sticky="we")
                    lbl = ttk.Label(cell, text=f"{int(init_val):02d}:00")
                    lbl.grid(row=0, column=1, sticky="w", padx=(6,0))

                    var = tk.IntVar(value=int(init_val))
                    lock = {"updating": False}

                    def snap(v):
                        if lock["updating"]: return
                        try: raw = float(v)
                        except: raw = float(var.get())
                        snapped = int(round(raw))
                        snapped = max(0, min(23, snapped))
                        if snapped != int(raw):
                            lock["updating"] = True
                            sc.set(snapped)
                            lock["updating"] = False
                        var.set(snapped)
                        lbl.config(text=f"{snapped:02d}:00")
                        try: on_change()
                        except Exception: pass

                    sc.configure(command=snap)
                    sc.set(int(init_val))
                    return cell, sc, var, lbl

                off = int(item.get("off_hour", 0)) % 24
                on  = int(item.get("on_hour", 7)) % 24

                window_lbl = ttk.Label(row, text=f"{off:02d}:00 -> {on:02d}:00")
                window_lbl.grid(row=0, column=4, sticky="w", padx=(0,8))

                def update_summary():
                    window_lbl.config(text=f"{int(off_var.get()):02d}:00 -> {int(on_var.get()):02d}:00")

                off_cell, off_sc, off_var, _ = mk_hour_cell(row, off, update_summary)
                on_cell,  on_sc,  on_var,  _ = mk_hour_cell(row, on,  update_summary)
                off_cell.grid(row=0, column=2, sticky="we", padx=(0,8))
                on_cell.grid(row=0, column=3, sticky="we", padx=(0,8))

                def delete_schedule(i=idx-1):
                    try:
                        scr_cfg["schedules"].pop(i)
                    except Exception:
                        pass
                    self._mirror_first_enabled_schedule_to_legacy(scr_cfg)
                    self._save_settings()
                    render()
                    self._wake()

                ttk.Button(row, text="Delete", command=delete_schedule).grid(row=0, column=5)

                def commit_row(i=idx-1):
                    days = [d for d, v in enumerate(day_vars) if v.get()]
                    scr_cfg["schedules"][i] = {
                        "enabled": bool(enabled_var.get()),
                        "off_hour": int(off_var.get()),
                        "on_hour": int(on_var.get()),
                        "days": days
                    }
                    self._mirror_first_enabled_schedule_to_legacy(scr_cfg)
                    self._save_settings()
                    self._wake()
                    update_summary()

                enabled_var.trace_add("write", lambda *_: commit_row())
                for v in day_vars: v.trace_add("write", lambda *_: commit_row())
                off_sc.bind("<ButtonRelease-1>", lambda _e: commit_row())
                on_sc.bind("<ButtonRelease-1>",  lambda _e: commit_row())

                update_summary()

        def add_schedule():
            scr_cfg["schedules"].append({
                "enabled": True,
                "off_hour": 0,
                "on_hour": 7,
                "days": [0,1,2,3,4,5,6]
            })
            self._mirror_first_enabled_schedule_to_legacy(scr_cfg)
            self._save_settings()
            render()
            self._wake()

        render()
        add_row = ttk.Frame(parent); add_row.grid(row=1, column=0, sticky="we", padx=8, pady=(0,8))
        ttk.Button(add_row, text="Add schedule", command=add_schedule).pack(side="left")

    # ----------------- About tab -----------------
    def _build_about_tab(self) -> None:
        root = self._about_root 
        about_cfg = self.settings.get("about", {}) if isinstance(self.settings, dict) else {}
        about_text = about_cfg.get("text", "Digital Photo Frame")
        about_image_path = about_cfg.get("image_path", "")

        # Outer 3x3 grid to keep content centered
        outer = ttk.Frame(root)
        outer.pack(fill="both", expand=True)
        for c in (0, 1, 2):
            outer.columnconfigure(c, weight=1 if c != 1 else 0)
        for r in (0, 1, 2):
            outer.rowconfigure(r, weight=1 if r != 1 else 0)

        # Center content container
        content = ttk.Frame(outer)
        content.grid(row=1, column=1, sticky="n")
        title_lbl = ttk.Label(content, text=about_text, justify="center")
        title_lbl.pack(anchor="center", padx=10, pady=(20, 10))

        # Keep the description nicely wrapped as the dialog resizes
        def _update_wraplength(_evt=None):
            try:
                w = max(300, int(content.winfo_width() * 0.9))
                title_lbl.configure(wraplength=w)
            except Exception:
                pass
        content.bind("<Configure>", _update_wraplength)

        # Optional image (static or animated)
        self._about_img_ref = None
        if isinstance(about_image_path, str) and about_image_path:
            try:
                if os.path.isfile(about_image_path):
                    from PIL import ImageSequence  # local import for GIF support
                    im = Image.open(about_image_path)
                    if getattr(im, "is_animated", False):
                        frames = [
                            frame.copy().resize((250, 250), Image.Resampling.LANCZOS)
                            for frame in ImageSequence.Iterator(im)
                        ]
                        self._about_img_ref = [ImageTk.PhotoImage(f) for f in frames]
                        gif_lbl = ttk.Label(content)
                        gif_lbl.pack(anchor="center", pady=(0, 20))

                        def _animate(frame_idx=0):
                            gif_lbl.configure(image=self._about_img_ref[frame_idx])
                            next_idx = (frame_idx + 1) % len(self._about_img_ref)
                            gif_lbl.after(im.info.get("duration", 100), _animate, next_idx)

                        _animate()
                    else:
                        im = im.resize((300, 300), Image.Resampling.LANCZOS)
                        self._about_img_ref = ImageTk.PhotoImage(im)
                        ttk.Label(content, image=self._about_img_ref).pack(anchor="center", pady=(0, 20))
            except Exception:
                self.logger.exception("Failed to load About image")

        # ----------------- Notifications -----------------

    # ----------------- Notifications tab -----------------    
    def _build_notifications_tab(self) -> None:
        root = self._notif_root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # list area
        frame = ttk.Frame(root)
        frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        cols = ("ts", "level", "text")
        self.notif_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        for c, w in (("ts", 150), ("level", 80), ("text", 600)):
            self.notif_tree.heading(c, text=c.upper())
            self.notif_tree.column(c, width=w, stretch=(c == "text"))
        self.notif_tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.notif_tree.yview)
        self.notif_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")

        # actions
        actions = ttk.Frame(root)
        actions.grid(row=1, column=0, sticky="we", padx=8, pady=(0,8))
        ttk.Button(actions, text="Refresh", command=self._refresh_notifications).pack(side="left")
        ttk.Button(actions, text="Clear", command=self._clear_notifications).pack(side="left", padx=6)

        self._refresh_notifications()

    def _refresh_notifications(self):
        try:
            for i in self.notif_tree.get_children():
                self.notif_tree.delete(i)
            for it in self.notifications.list():
                self.notif_tree.insert("", "end", values=(it["ts"], it["level"], it["text"]))
        except Exception:
            pass

    def _clear_notifications(self):
        try:
            self.notifications.clear()
            self._refresh_notifications()
            # also hide the badge in the main window
            try:
                self.parent.after(0, getattr(self.parent, "_update_notification_badge", lambda: None))
            except Exception:
                pass
        except Exception:
            pass

    def focus_notifications_tab(self):
        try:
            nb = self.form.nametowidget(self.form.winfo_children()[0])  # the Notebook
            # find the index of notif_tab
            tabs = nb.tabs()
            for i, t in enumerate(tabs):
                if nb.nametowidget(t) is self.notif_tab:
                    nb.select(i)
                    break
            self._refresh_notifications()
        except Exception:
            pass


    # ----------------- Apply/Init -----------------
    def _apply_saved_on_open(self) -> None:
        scr = self._ensure_screen_struct()
        orient = scr.get("orientation")
        if orient in ("normal", "90", "180", "270"):
            self.orient_var.set(orient)
            self._on_apply_orientation(orient)

        pct = max(10, min(100, int(scr.get("brightness", 100))))
        self.br_scale.set(pct)
        self.br_val_lbl.config(text=f"{pct}%")
        self._on_apply_brightness(pct)

        ip = get_local_ip()
        self.current_ssid_lbl.config(text=f"Wifi network: {self._get_current_ssid()}")
        self.ip_lbl.config(text=f"URL: http://{ip}:{self.backend_port}")
        self._update_qr(ip)

    def _apply_brightness(self, pct: int) -> None:
        if self._on_apply_brightness(int(pct)):
            scr = self._ensure_screen_struct()
            scr["brightness"] = max(10, min(100, int(pct)))
            self._save_settings()
            self._wake()

    def _apply_orientation(self) -> None:
        transform = self.orient_var.get()
        if self._on_apply_orientation(transform):
            scr = self._ensure_screen_struct()
            scr["orientation"] = transform
            self._save_settings()

    def _update_qr(self, ip: str) -> None:
        img = qrcode.make(f"http://{ip}:{self.backend_port}")
        img = img.resize((160, 160))
        tk_img = ImageTk.PhotoImage(img)
        self.qr_lbl.config(image=tk_img)
        self.qr_lbl.image = tk_img

    # ----------------- Wi-Fi plumbing -----------------
    def _scan_async(self) -> None:
        def _worker():
            nm = _shutil_which("nmcli") or "/usr/bin/nmcli"
            ssids: List[str] = []
            try:
                try:
                    subprocess.run([nm, "device", "wifi", "rescan"], check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                except Exception:
                    pass

                out = subprocess.check_output(
                    [nm, "-t", "-f", "IN-USE,SSID,SECURITY,SIGNAL", "device", "wifi", "list"],
                    universal_newlines=True, stderr=subprocess.DEVNULL, timeout=8
                )
                rows = []
                for line in out.splitlines():
                    if not line:
                        continue
                    parts = (line.split(":") + ["", "", "", ""])[:4]
                    inuse, ssid, sec, sigs = parts
                    if not ssid:
                        continue
                    try:
                        sig = int(sigs)
                    except Exception:
                        sig = -1
                    rows.append((ssid, sec, sig, inuse))

                by_ssid = {}
                for ssid, sec, sig, inuse in rows:
                    cur = by_ssid.get(ssid)
                    if cur is None or sig > cur[1]:
                        by_ssid[ssid] = (sec, sig, inuse)

                ordered = sorted(by_ssid.items(), key=lambda kv: -kv[1][1])
                ssids = [ssid for ssid, (_sec, _sig, _inuse) in ordered]
            except Exception:
                ssids = []

            def ui():
                try:
                    self.ssid_cb["values"] = ssids
                except Exception:
                    pass
                if ssids and not self.ssid_cb.get():
                    try:
                        self.ssid_cb.current(0)
                    except Exception:
                        pass

            self.form.after(0, ui)

        threading.Thread(target=_worker, daemon=True).start()

    def _connect_async(self) -> None:
        def _worker():
            ssid = (self.ssid_cb.get() or "").strip()
            if not ssid:
                self.form.after(0, lambda: messagebox.showerror("Connection failed", "Please select a network."))
                return
            pwd = self.pwd_ent.get()

            nm = _shutil_which("nmcli") or "nmcli"
            try:
                out = subprocess.check_output(
                    [nm, "-t", "-f", "DEVICE,TYPE,STATE", "device"],
                    universal_newlines=True, stderr=subprocess.DEVNULL, timeout=5
                )
                iface = None
                cands = []
                for line in out.splitlines():
                    if not line:
                        continue
                    dev, typ, state = (line.split(":") + ["", "", ""])[:3]
                    if typ == "wifi":
                        prio = 0 if state == "connected" else (1 if state == "disconnected" else 2)
                        cands.append((prio, dev))
                cands.sort()
                iface = cands[0][1] if cands else None
            except Exception:
                iface = None

            if not iface:
                self.form.after(0, lambda: messagebox.showerror("Connection failed", "No Wi-Fi interface found."))
                return

            try:
                subprocess.run([nm, "radio", "wifi", "on"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except Exception:
                pass

            try:
                scan_out = subprocess.check_output(
                    [nm, "-t", "-f", "SSID,SECURITY", "device", "wifi", "list", "ifname", iface],
                    universal_newlines=True, stderr=subprocess.DEVNULL, timeout=10
                )
                sec_map = {}
                for line in scan_out.splitlines():
                    if not line:
                        continue
                    p = (line.split(":") + ["", ""])[:2]
                    nm_ssid, nm_sec = p
                    if nm_ssid:
                        sec_map[nm_ssid] = nm_sec
                nm_sec = sec_map.get(ssid, "")
                is_open = (nm_sec == "" or nm_sec == "--")
                hidden_flag = [] if ssid in sec_map else ["hidden", "yes"]
            except Exception:
                is_open = False
                hidden_flag = ["hidden", "yes"]

            cmd = [nm, "-w", "30", "device", "wifi", "connect", ssid, "ifname", iface] + hidden_flag
            if not is_open:
                if not pwd:
                    self.form.after(0, lambda: messagebox.showerror("Connection failed", "Password is required."))
                    return
                cmd += ["password", pwd]

            def run_connect():
                try:
                    res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, timeout=60)
                    return True, (res.stdout.strip() or res.stderr.strip())
                except subprocess.CalledProcessError as e:
                    return False, (e.stdout or "") + "\n" + (e.stderr or "")

            ok, msg = run_connect()
            if not ok:
                self.form.after(0, lambda: messagebox.showerror("Connection failed", msg.strip() or "Unknown error"))
                return

            new_ip = get_local_ip()
            self.form.after(0, lambda: (
                self.current_ssid_lbl.config(text=f"Wifi network: {ssid}"),
                self.ip_lbl.config(text=f"URL: http://{new_ip}:{self.backend_port}")
            ))

        threading.Thread(target=_worker, daemon=True).start()

    @staticmethod
    def _get_current_ssid() -> str:
        try:
            out = subprocess.check_output(
                ["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"],
                stderr=subprocess.DEVNULL, universal_newlines=True
            )
            lines = [l for l in out.splitlines() if l]
            return lines[0] if lines else "N/A"
        except Exception:
            return "N/A"


def _shutil_which(name: str) -> str:
    try:
        import shutil
        return shutil.which(name) or ""
    except Exception:
        return ""
