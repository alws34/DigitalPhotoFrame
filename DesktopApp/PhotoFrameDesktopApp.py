import io
import json
import logging
import tkinter as tk
import tkinter.ttk as ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import sys
import os
import threading
import psutil
import requests
import cv2
import numpy as np
import time
import socket
import subprocess
import qrcode
import platform
import shutil
import re
from collections import deque
from tkinter import messagebox

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Handlers.weather_handler import weather_handler
from WebServer.API import Backend as BackendAPI
from WebServer.PhotoFrameServer import PhotoFrameServer
from iFrame import iFrame

# region Logging Setup
log_file_path = os.path.join(os.path.dirname(__file__), "AppLog.log")
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO) 
console_formatter = logging.Formatter("%(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)
logging.getLogger().addHandler(console_handler)
logging.info("PhotoFrame application starting...")
# endregion Logging Setup


def get_local_ip():
    """Return the primary LAN IP address, fallback to 127.0.0.1."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

class MJPEGStreamClient:
    def __init__(self, url):
        self.url = url
        self.stream = None

    def get_frames(self):
        try:
            stream = requests.get(self.url, stream=True, timeout=5)
            if stream.status_code != 200:
                print(f"[MJPEGStreamClient] HTTP {stream.status_code}, no stream.")
                yield None
                return

            content_type = stream.headers.get("Content-Type", "")
            if "boundary=" in content_type:
                self.boundary = content_type.split("boundary=")[1]
            else:
                self.boundary = "--frame"

            buffer = b""
            for chunk in stream.iter_content(chunk_size=10240):
                buffer += chunk
                while True:
                    start = buffer.find(b'\xff\xd8')  # JPEG start
                    end = buffer.find(b'\xff\xd9')    # JPEG end
                    if start != -1 and end != -1 and end > start:
                        jpg = buffer[start:end + 2]
                        buffer = buffer[end + 2:]
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            yield frame
                    else:
                        break
        except requests.exceptions.RequestException as e:
            yield None             
    
class PhotoFrame(tk.Frame, iFrame):
    """
    A tkinter frame that fetches frames from an MJPEG server, resizes them,
    and displays the live video stream.
    
    The image handling (fetching and resizing) is decoupled from the frame display.
    """
    def __init__(self, parent, stream_url, desired_width, desired_height, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        #self.stream_url = stream_url
        self.desired_width = desired_width
        self.desired_height = desired_height
        self.triple_tap_count = 0
        self.last_tap_time = 0
        self.show_stats = False #settings.get("stats", {}).get("show", False)
        self.backend_port = settings.get("backend_configs", {}).get("server_port", 5001)
        
        

        self.cached_stats = self.get_system_stats()
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.image_dir = os.path.join(self.base_path, "Images")

        if isinstance(self.parent, tk.Tk):
            self.parent.title("Digital Photo Frame V2.0")
            w, h = self.parent.winfo_screenwidth(), self.parent.winfo_screenheight()
            self.parent.geometry(f"{w}x{h}+0+0")
            self.parent.attributes("-fullscreen", True)
            self.parent.wm_attributes("-topmost", True)
            self.parent.configure(bg="black")
            self.parent.config(cursor="none")
            self.parent.bind_all("<Control-c>", lambda e: self.on_closing())
            # new tapping mode: triple tap opens settings form
            self.parent.bind_all("<ButtonRelease-1>", self.handle_triple_tap)
            self.parent.bind("<ButtonPress-1>",   self._on_button_press)
            self.parent.bind("<ButtonRelease-1>", self._on_button_release)
            self.parent.bind("<ButtonRelease-1>", self._on_tap, add="+")
            self._long_press_job = None
            self._long_press_duration_ms = 5000
        self._tap_count      = 0
        self._last_tap_time  = 0.0
        

        self.font_path = self.base_path + "//" + settings['font_name']
        self.time_font = ImageFont.truetype(self.font_path, settings['time_font_size'])
        self.date_font = ImageFont.truetype(self.font_path, settings['date_font_size'])
        self.font_temp = self.time_font  # reuse
        self.font_desc = self.date_font  # reuse
        stats_font_path = self.font_path
        stats_font_size = settings.get("stats", {}).get("font_size", 20)
        self.stats_font = ImageFont.truetype(stats_font_path, stats_font_size)

        self.label = tk.Label(self, bg='black')
        self.label.pack(fill="both", expand=True)
        
        #self.stream_client = MJPEGStreamClient(self.stream_url)
        self.current_frame = None
        self.stop_event = threading.Event()
        
        # self.fetch_thread = threading.Thread(target=self.frame_fetch_loop, daemon=True)
        # self.fetch_thread.start()

        self.weather_client = weather_handler(frame = self, settings= settings)
        self.weather_thread = threading.Thread(target=self.weather_loop, daemon=True)
        self.weather_thread.start()
        self.stats_thread = threading.Thread(target=self.update_stats_loop, daemon=True)
        self.stats_thread.start()
        
        self.PhotoFrameServer=PhotoFrameServer(
            width = self.desired_width,
            height= self.desired_height,
            iframe= self,
            images_dir=self.image_dir
        )

        threading.Thread(target=self.PhotoFrameServer.run_photoframe, daemon=True).start()
        
        self.BackendAPI = BackendAPI(
            frame=self.PhotoFrameServer,
            settings=settings,
            image_dir=self.image_dir
        )
        self.PhotoFrameServer.m_api = self.BackendAPI

        threading.Thread(target=self.BackendAPI.start, daemon=True).start()

        
        
        self.update_display()

    def send_log_message(self, msg, logger: logging):
        logger(msg)
    
    def _on_tap(self, event):
        """Count rapid consecutive taps; open settings on the third."""
        now = time.time()
        # if this tap is within 1.5s of the last, increment; else reset to 1
        if now - self._last_tap_time <= 1.5:
            self._tap_count += 1
        else:
            self._tap_count = 1
        self._last_tap_time = now

        logging.info(f"Tap #{self._tap_count}")            # debug output
        if self._tap_count == 3:
            logging.info("Triple tap detected – opening settings")
            self.open_settings_form()
            self._tap_count = 0
            
    # ---- long press exit ----
    def _on_button_press(self, event):
        if self._long_press_job is None:
            self._long_press_job = self.after(
                self._long_press_duration_ms,
                self._long_press_detected
            )
    def _on_button_release(self, event):
        if self._long_press_job is not None:
            self.after_cancel(self._long_press_job)
            self._long_press_job = None
    def _long_press_detected(self):
        logging.info("Long-press detected: shutting down")
        self.stop_event.set()
        self.parent.destroy()
        sys.exit(0)

    
    # ---- triple tap opens form ----
    def handle_triple_tap(self, event):
        now = time.time()
        if not hasattr(self, "_last_tap"):
            self._last_tap = now
            self._tap_count = 1
        elif now - self._last_tap < 1.5:
            self._tap_count += 1
        else:
            self._tap_count = 1
        self._last_tap = now
        if self._tap_count == 3:
            self.open_settings_form()
            self._tap_count = 0
    
    
#region SettingsForm
    # ---- settings form ----
    def open_settings_form(self):
        if hasattr(self, "settings_form") and self.settings_form.winfo_exists():
            return

        service_name = getattr(self, "service_name", "photoframe")

        # ------------- helpers: settings path + persistence -------------
        def _settings_path():
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), "photoframe_settings.json")

        def _ensure_screen_struct():
            scr = settings.setdefault("screen", {})
            scr.setdefault("orientation", "normal")
            scr.setdefault("brightness", 100)
            scr.setdefault("schedule_enabled", False)
            scr.setdefault("off_hour", 0)
            scr.setdefault("on_hour", 7)
            return scr

        def _save_settings():
            try:
                with open(_settings_path(), "w") as f:
                    json.dump(settings, f, indent=2)
            except Exception as e:
                messagebox.showerror("Failed to save settings", str(e))

        # ---------------- sparkline (pretty, lightweight) ----------------
        class Sparkline:
            def __init__(self, parent, width=560, height=70, maxlen=60):
                self.width = width
                self.height = height
                self.pad = 6
                self.data = deque(maxlen=maxlen)
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

            def _scaled_points(self):
                if not self.data:
                    return []
                vals = list(self.data)
                vmin = min(vals)
                vmax = max(vals)
                rng = (vmax - vmin) if (vmax > vmin) else 1.0
                w, h, p = self.width, self.height, self.pad
                usable_w = w - 2 * p
                usable_h = h - 2 * p
                n = len(vals)
                pts = []
                for i, v in enumerate(vals):
                    x = p + (i * usable_w / max(1, n - 1))
                    y_norm = (v - vmin) / rng
                    y = h - p - y_norm * usable_h
                    pts.append((x, y))
                return pts, vmin, vmax

            def draw(self):
                c = self.canvas
                c.delete("plot")
                res = self._scaled_points()
                if not res:
                    return
                pts, vmin, vmax = res
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

            def push(self, value):
                try:
                    v = float(value)
                except Exception:
                    return
                self.data.append(v)
                self.draw()

        # ---------------- window ----------------
        form = tk.Toplevel(self.parent)
        self.settings_form = form
        form.withdraw()
        form.title("Settings")
        form.transient(self.parent)
        form.resizable(False, False)
        width, height = 800, 620
        sw, sh = self.parent.winfo_screenwidth(), self.parent.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        form.geometry(f"{width}x{height}+{x}+{y}")
        form.lift()
        form.attributes("-topmost", True)

        notebook = ttk.Notebook(form)
        stats_frame = ttk.Frame(notebook)
        wifi_frame = ttk.Frame(notebook)
        screen_frame = ttk.Frame(notebook)
        about_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Stats")
        notebook.add(wifi_frame, text="Wi-Fi")
        notebook.add(screen_frame, text="Screen")
        notebook.add(about_frame, text="About")
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # ---------------- Stats tab ----------------
        top = ttk.Frame(stats_frame)
        top.pack(fill="x", padx=4, pady=(4, 0))

        graphs_col = ttk.Frame(top)
        graphs_col.pack(anchor="center")

        self.cpu_lbl = ttk.Label(graphs_col, text="CPU: Loading...")
        self.cpu_lbl.pack(anchor="center")
        self.cpu_graph = Sparkline(graphs_col, width=560, height=70, maxlen=60)
        self.cpu_graph.widget().pack(anchor="center", pady=(0, 6))

        self.ram_lbl = ttk.Label(graphs_col, text="RAM: Loading...")
        self.ram_lbl.pack(anchor="center")
        self.ram_graph = Sparkline(graphs_col, width=560, height=70, maxlen=60)
        self.ram_graph.widget().pack(anchor="center", pady=(0, 6))

        self.tmp_lbl = ttk.Label(graphs_col, text="Temp: Loading...")
        self.tmp_lbl.pack(anchor="center")
        self.tmp_graph = Sparkline(graphs_col, width=560, height=70, maxlen=60)
        self.tmp_graph.widget().pack(anchor="center", pady=(0, 6))

        center = ttk.Frame(stats_frame); center.pack(fill="x", pady=(8, 4))
        self.current_ssid_lbl = ttk.Label(center, text="SSID: Loading...")
        self.more_settings_lbl = ttk.Label(center, text="For more settings, configuration and image upload, please scan the QR code with your phone")
        self.ip_lbl = ttk.Label(center, text="URL: Loading...")
        self.qr_lbl = ttk.Label(center)
        self.current_ssid_lbl.pack(anchor="center")
        self.ip_lbl.pack(anchor="center", pady=(2, 6))
        self.qr_lbl.pack(anchor="center")
        self.more_settings_lbl.pack(anchor="center")

        ttk.Frame(stats_frame).pack(fill="both", expand=True)

        footer = ttk.Frame(stats_frame); footer.pack(fill="x", pady=(8, 0))
        ttk.Frame(footer).pack(side="left", fill="x", expand=True)

        def do_stop():
            try:
                subprocess.run(["sudo", "systemctl", "stop", f"{service_name}.service"], check=True)
            except Exception:
                pass
            try:
                self.on_closing()
            except Exception:
                form.destroy()

        def do_restart():
            try:
                subprocess.run(["sudo", "systemctl", "restart", f"{service_name}.service"], check=True)
            except Exception as e:
                messagebox.showerror("Restart failed", str(e))

        ttk.Button(footer, text="Restart Service", command=do_restart).pack(side="right", padx=(0, 8))
        ttk.Button(footer, text="Close (Stop Service)", command=do_stop).pack(side="right")

        # ---------------- helpers for stats ----------------
        def get_current_ssid():
            try:
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"],
                    stderr=subprocess.DEVNULL,
                    universal_newlines=True
                )
                lines = [l for l in out.splitlines() if l]
                return lines[0] if lines else "N/A"
            except Exception:
                return "N/A"

        temp_re = re.compile(r"(-?\d+(\.\d+)?)")
        def parse_num(s):
            m = temp_re.search(s or "")
            if not m:
                return None
            try:
                return float(m.group(1))
            except Exception:
                return None

        def update_stats_loop():
            while getattr(self, "settings_form", None) and form.winfo_exists():
                try:
                    s = self.get_system_stats().split("\n")
                    cpu_pct = parse_num(s[0]) if len(s) >= 1 else None
                    ram_pct = parse_num(s[1]) if len(s) >= 2 else None
                    tmp_c = parse_num(s[2]) if len(s) >= 3 else None

                    ip = get_local_ip()
                    ssid = get_current_ssid()

                    qr = qrcode.make(f"http://{ip}:{self.backend_port}")
                    qr = qr.resize((160, 160), Image.Resampling.LANCZOS)
                    img = ImageTk.PhotoImage(qr)

                    def apply_updates():
                        self.cpu_lbl.config(text=s[0] if len(s) > 0 else "CPU: N/A")
                        self.ram_lbl.config(text=s[1] if len(s) > 1 else "RAM: N/A")
                        self.tmp_lbl.config(text=s[2] if len(s) > 2 else "Temp: N/A")
                        self.current_ssid_lbl.config(text=f"SSID: {ssid}")
                        self.ip_lbl.config(text=f"URL: http://{ip}:{self.backend_port}")
                        self.qr_lbl.config(image=img); self.qr_lbl.image = img
                        if cpu_pct is not None: self.cpu_graph.push(max(0.0, min(100.0, cpu_pct)))
                        if ram_pct is not None: self.ram_graph.push(max(0.0, min(100.0, ram_pct)))
                        if tmp_c is not None: self.tmp_graph.push(tmp_c)
                    form.after(0, apply_updates)
                except Exception:
                    pass
                time.sleep(1)
        threading.Thread(target=update_stats_loop, daemon=True).start()

        # ======================================================
        # Wi-Fi tab (unchanged except custom keyboard)
        # ======================================================
        ttk.Label(wifi_frame, text="Network:").pack(anchor="w", pady=(10, 0))
        ssid_cb = ttk.Combobox(wifi_frame, state="readonly")
        ssid_cb.pack(fill="x")

        pw_frame = ttk.Frame(wifi_frame); pw_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(pw_frame, text="Password:").pack(side="left")
        pwd_ent = ttk.Entry(pw_frame, show="*")
        pwd_ent.pack(side="left", fill="x", expand=True, padx=(5, 0))
        show_pwd_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            pw_frame, text="Show",
            variable=show_pwd_var,
            command=lambda: pwd_ent.config(show="" if show_pwd_var.get() else "*")
        ).pack(side="left", padx=(5, 0))

        btns = ttk.Frame(wifi_frame); btns.pack(fill="x", pady=(8, 0))
        left_btns = ttk.Frame(btns); left_btns.pack(side="left")
        ttk.Frame(btns).pack(side="right", fill="x", expand=True)

        kb_container = ttk.Frame(wifi_frame); kb_container.pack(fill="x", pady=(8, 0))

        class CustomKeyboard:
            def __init__(self, parent, target_entry: tk.Entry):
                self.parent = parent
                self.entry = target_entry
                self.caps = False
                self.shift = False
                self.symbols = False
                self.backspace_job = None
                self.frame = ttk.Frame(parent)
                self.frame.pack(fill="x")
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
                    btn.bind("<ButtonPress-1>", lambda e: self._start_backspace_repeat())
                    btn.bind("<ButtonRelease-1>", lambda e: self._stop_backspace_repeat())
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

        keyboard = CustomKeyboard(kb_container, pwd_ent)

        def scan():
            def _worker():
                try:
                    out = subprocess.check_output(
                        "sudo iwlist wlan0 scanning | grep ESSID",
                        shell=True, universal_newlines=True
                    )
                    ssids = [line.split('ESSID:')[1].strip().strip('\"') for line in out.splitlines()]
                    ssids = sorted(set(filter(None, ssids)))
                except Exception:
                    ssids = []
                form.after(0, lambda: ssid_cb.configure(values=ssids))
            threading.Thread(target=_worker, daemon=True).start()
        scan()

        def connect():
            ssid = ssid_cb.get().strip()
            if not ssid:
                return
            pwd = pwd_ent.get()
            def _worker():
                try:
                    subprocess.run(
                        ["sudo", "nmcli", "device", "wifi", "connect", ssid, "password", pwd],
                        check=True
                    )
                except subprocess.CalledProcessError as e:
                    form.after(0, lambda: messagebox.showerror("Connection Failed", str(e)))
                    return
                new_ip = get_local_ip()
                form.after(0, lambda: (
                    self.current_ssid_lbl.config(text=f"SSID: {ssid}"),
                    self.ip_lbl.config(text=f"URL: http://{new_ip}:{self.backend_port}")
                ))
            threading.Thread(target=_worker, daemon=True).start()

        ttk.Button(left_btns, text="Rescan", command=scan).pack(side="left")
        ttk.Button(left_btns, text="Connect", command=connect).pack(side="left", padx=(8, 0))

        # ======================================================
        # Screen tab (orientation + brightness + schedule) with JSON persistence to main settings
        # ======================================================
        scr_cfg = _ensure_screen_struct()

        # ---- orientation UI ----
        scr_top = ttk.Frame(screen_frame); scr_top.pack(fill="x", pady=(10, 6))
        ttk.Label(scr_top, text="Orientation:").grid(row=0, column=0, sticky="w", padx=(0, 12))
        orient_var = tk.StringVar(value=scr_cfg.get("orientation", "normal"))
        orow = ttk.Frame(scr_top); orow.grid(row=0, column=1, sticky="w")
        for k, v in [("Normal", "normal"), ("Left (90)", "90"), ("Inverted (180)", "180"), ("Right (270)", "270")]:
            ttk.Radiobutton(orow, text=k, value=v, variable=orient_var).pack(side="left", padx=(0, 8))
        apply_orient_btn = ttk.Button(scr_top, text="Apply Orientation"); apply_orient_btn.grid(row=0, column=2, padx=(12, 0))

        # ---- brightness UI (wide, snap 10%) ----
        br_frame = ttk.LabelFrame(screen_frame, text="Brightness"); br_frame.pack(fill="x", pady=(8, 6))
        br_frame.columnconfigure(1, weight=1)
        ttk.Label(br_frame, text="Level:").grid(row=0, column=0, sticky="w", padx=(8, 8), pady=(8, 8))
        br_val_lbl = ttk.Label(br_frame, text=f"{int(scr_cfg.get('brightness', 100))}%"); br_val_lbl.grid(row=0, column=2, sticky="w", padx=(8, 0))

        _snap_lock = {"updating": False}
        def _snap10_and_update(v):
            if _snap_lock["updating"]:
                return
            try:
                raw = float(v)
            except Exception:
                raw = 100.0
            snapped = max(10, min(100, int(round(raw / 10.0) * 10)))
            br_val_lbl.config(text=f"{snapped}%")
            if snapped != int(raw):
                _snap_lock["updating"] = True
                br_scale.set(snapped)
                _snap_lock["updating"] = False

        br_scale = ttk.Scale(
            br_frame,
            from_=10, to=100,
            orient="horizontal",
            length=620,
            command=_snap10_and_update
        )
        br_scale.set(int(scr_cfg.get("brightness", 100)))
        br_scale.grid(row=0, column=1, sticky="we", pady=(8, 8))
        apply_br_btn = ttk.Button(br_frame, text="Apply Brightness"); apply_br_btn.grid(row=0, column=3, padx=(8, 8))

        # ---- auto on/off schedule UI (large sliders, no tiny spinboxes) ----
        sched = ttk.LabelFrame(screen_frame, text="Auto screen on/off (hours only)")
        sched.pack(fill="x", pady=(6, 0))
        for c in (1, 4):  # allow scales to stretch
            sched.columnconfigure(c, weight=1)

        enable_var = tk.BooleanVar(value=bool(scr_cfg.get("schedule_enabled", False)))
        ttk.Checkbutton(sched, text="Enable schedule", variable=enable_var).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        # OFF hour slider
        ttk.Label(sched, text="Turn OFF at:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        off_var = tk.IntVar(value=int(scr_cfg.get("off_hour", 0)))
        off_val_lbl = ttk.Label(sched, text=f"{off_var.get():02d}:00")
        off_val_lbl.grid(row=1, column=2, sticky="w", padx=8, pady=4)

        _off_lock = {"updating": False}
        def _off_snap(v):
            if _off_lock["updating"]:
                return
            try:
                raw = float(v)
            except Exception:
                raw = float(off_var.get())
            snapped = int(round(raw))
            snapped = max(0, min(23, snapped))
            if snapped != int(raw):
                _off_lock["updating"] = True
                off_scale.set(snapped)
                _off_lock["updating"] = False
            off_var.set(snapped)
            off_val_lbl.config(text=f"{snapped:02d}:00")

        off_scale = ttk.Scale(
            sched, from_=0, to=23, orient="horizontal", length=620, command=_off_snap
        )
        off_scale.set(off_var.get())
        off_scale.grid(row=1, column=1, sticky="we", padx=(0, 8), pady=4)

        # ON hour slider
        ttk.Label(sched, text="Turn ON at:").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        on_var = tk.IntVar(value=int(scr_cfg.get("on_hour", 7)))
        on_val_lbl = ttk.Label(sched, text=f"{on_var.get():02d}:00")
        on_val_lbl.grid(row=2, column=2, sticky="w", padx=8, pady=4)

        _on_lock = {"updating": False}
        def _on_snap(v):
            if _on_lock["updating"]:
                return
            try:
                raw = float(v)
            except Exception:
                raw = float(on_var.get())
            snapped = int(round(raw))
            snapped = max(0, min(23, snapped))
            if snapped != int(raw):
                _on_lock["updating"] = True
                on_scale.set(snapped)
                _on_lock["updating"] = False
            on_var.set(snapped)
            on_val_lbl.config(text=f"{snapped:02d}:00")

        on_scale = ttk.Scale(
            sched, from_=0, to=23, orient="horizontal", length=620, command=_on_snap
        )
        on_scale.set(on_var.get())
        on_scale.grid(row=2, column=1, sticky="we", padx=(0, 8), pady=4)

        apply_sched_btn = ttk.Button(sched, text="Apply Schedule")
        apply_sched_btn.grid(row=3, column=0, sticky="w", padx=8, pady=(8, 8))

        # ---- platform helpers: output/backlight + actions ----
        def list_outputs():
            try:
                out = subprocess.check_output(["wlr-randr"], universal_newlines=True, stderr=subprocess.DEVNULL)
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

        def pick_default_output():
            outs = list_outputs()
            outs.sort(key=lambda n: (0 if n.upper().startswith("DSI") else 1, n))
            return outs[0] if outs else None

        def list_backlights():
            base = "/sys/class/backlight"
            if not os.path.isdir(base):
                return []
            devs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
            devs.sort(key=lambda n: (0 if n.startswith("rpi") or "rpi_backlight" in n or "raspberry" in n else 1, n))
            return devs

        def pick_default_backlight():
            bls = list_backlights()
            return bls[0] if bls else None

        def read_brightness(dev):
            base = os.path.join("/sys/class/backlight", dev)
            try:
                with open(os.path.join(base, "max_brightness"), "r") as f:
                    maxb = int(f.read().strip())
                with open(os.path.join(base, "brightness"), "r") as f:
                    cur = int(f.read().strip())
                return cur, maxb
            except Exception:
                return None, None

        def _write_brightness_value(dev, value):
            base = os.path.join("/sys/class/backlight", dev)
            try:
                with open(os.path.join(base, "brightness"), "w") as f:
                    f.write(str(value))
                return True
            except PermissionError:
                cmd = f"echo {value} | sudo tee {os.path.join(base, 'brightness')}"
                try:
                    subprocess.run(cmd, shell=True, check=True)
                    return True
                except subprocess.CalledProcessError as e:
                    messagebox.showerror("Permission required", f"Failed to write brightness.\n\n{e}")
                    return False
            except Exception as e:
                messagebox.showerror("Failed to set brightness", str(e))
                return False

        def set_brightness_percent(dev, percent, allow_zero=False):
            percent = int(percent)
            if not allow_zero:
                percent = max(10, min(100, percent))
            else:
                percent = max(0, min(100, percent))
            base = os.path.join("/sys/class/backlight", dev)
            try:
                with open(os.path.join(base, "max_brightness"), "r") as f:
                    maxb = int(f.read().strip())
                value = 0 if percent == 0 else int(round(percent * maxb / 100.0))
                value = min(maxb, value)
                return _write_brightness_value(dev, value)
            except Exception as e:
                messagebox.showerror("Failed to compute brightness", str(e))
                return False

        def apply_orientation(transform):
            output = pick_default_output()
            if not output:
                messagebox.showerror("No display", "Could not detect a Wayland output via wlr-randr.")
                return False
            try:
                subprocess.run(["wlr-randr", "--output", output, "--transform", transform], check=True)
                return True
            except subprocess.CalledProcessError as e:
                messagebox.showerror("Failed to set orientation", str(e))
                return False

        # ---- persist + wire actions ----
        def on_apply_orientation():
            transform = orient_var.get()
            if apply_orientation(transform):
                scr = _ensure_screen_struct()
                scr["orientation"] = transform
                _save_settings()

        def on_apply_brightness():
            dev = pick_default_backlight()
            if not dev:
                messagebox.showerror("No backlight", "No /sys/class/backlight device found.")
                return
            pct = int(float(br_scale.get()))
            if set_brightness_percent(dev, pct, allow_zero=False):
                scr = _ensure_screen_struct()
                scr["brightness"] = pct
                br_val_lbl.config(text=f"{pct}%")
                _save_settings()

        def on_apply_schedule():
            scr = _ensure_screen_struct()
            scr["schedule_enabled"] = bool(enable_var.get())
            scr["off_hour"] = int(off_var.get()) % 24
            scr["on_hour"] = int(on_var.get()) % 24
            _save_settings()
            if hasattr(self, "_screen_sched_event") and self._screen_sched_event:
                try:
                    self._screen_sched_event.set()
                except Exception:
                    pass

        apply_orient_btn.config(command=on_apply_orientation)
        apply_br_btn.config(command=on_apply_brightness)
        apply_sched_btn.config(command=on_apply_schedule)

        # ---- apply saved on open ----
        def apply_saved_on_open():
            scr = _ensure_screen_struct()
            orient = scr.get("orientation")
            if orient in ("normal", "90", "180", "270"):
                orient_var.set(orient)
                apply_orientation(orient)
            pct = int(scr.get("brightness", 100))
            pct = max(10, min(100, pct))
            br_scale.set(pct)
            br_val_lbl.config(text=f"{pct}%")
            dev = pick_default_backlight()
            if dev:
                set_brightness_percent(dev, pct, allow_zero=False)
            off_scale.set(int(scr.get("off_hour", 0)))
            off_var.set(int(scr.get("off_hour", 0)))
            off_val_lbl.config(text=f"{off_var.get():02d}:00")
            on_scale.set(int(scr.get("on_hour", 7)))
            on_var.set(int(scr.get("on_hour", 7)))
            on_val_lbl.config(text=f"{on_var.get():02d}:00")
        apply_saved_on_open()

        # ---- tiny background scheduler (once per ~30s) ----
        def _hour_now():
            try:
                return int(time.strftime("%H"))
            except Exception:
                return 0

        def _in_off_period(now_h, off_h, on_h):
            if off_h == on_h:
                return False
            if off_h < on_h:
                return off_h <= now_h < on_h
            else:
                return now_h >= off_h or now_h < on_h

        def _screen_power_worker():
            self._screen_power_state = getattr(self, "_screen_power_state", "unknown")
            self._last_user_brightness = None
            ev = self._screen_sched_event
            while True:
                scr = _ensure_screen_struct()
                enabled = bool(scr.get("schedule_enabled", False))
                off_h = int(scr.get("off_hour", 0)) % 24
                on_h  = int(scr.get("on_hour", 7)) % 24
                now_h = _hour_now()

                desired = "off" if (enabled and _in_off_period(now_h, off_h, on_h)) else "on"

                try:
                    dev = pick_default_backlight()
                    if dev:
                        cur, maxb = read_brightness(dev)
                        cur_pct = int(round(cur * 100.0 / maxb)) if (cur is not None and maxb) else None

                        if desired == "off" and self._screen_power_state != "off":
                            self._last_user_brightness = int(settings.get("screen", {}).get("brightness", 100))
                            if cur_pct is not None and cur_pct > 0:
                                self._last_user_brightness = cur_pct
                            set_brightness_percent(dev, 0, allow_zero=True)
                            self._screen_power_state = "off"

                        elif desired == "on" and self._screen_power_state != "on":
                            restore = int(settings.get("screen", {}).get("brightness", 100))
                            if isinstance(self._last_user_brightness, int):
                                restore = max(10, min(100, self._last_user_brightness))
                            set_brightness_percent(dev, restore, allow_zero=False)
                            self._screen_power_state = "on"
                except Exception:
                    pass

                if ev.wait(timeout=30.0):
                    try:
                        ev.clear()
                    except Exception:
                        pass

        if not hasattr(self, "_screen_sched_thread"):
            self._screen_sched_event = threading.Event()
            self._screen_sched_thread = threading.Thread(target=_screen_power_worker, daemon=True)
            self._screen_sched_thread.start()

        # ---------------- About tab ----------------
        about_cfg = settings.get("about", {}) if isinstance(settings, dict) else {}
        about_text = about_cfg.get("text", "Digital Photo Frame")
        about_image_path = about_cfg.get("image_path", "")

        about_outer = ttk.Frame(about_frame)
        about_outer.pack(fill="both", expand=True)

        about_outer.columnconfigure(0, weight=1)
        about_outer.columnconfigure(1, weight=0)
        about_outer.columnconfigure(2, weight=1)
        about_outer.rowconfigure(0, weight=1)
        about_outer.rowconfigure(1, weight=0)
        about_outer.rowconfigure(2, weight=1)

        content = ttk.Frame(about_outer)
        content.grid(row=1, column=1, sticky="n")

        about_lbl = ttk.Label(content, text=about_text, justify="center")
        about_lbl.pack(anchor="center", padx=10, pady=(20, 10))

        def _update_wraplength(evt=None):
            w = max(300, int(content.winfo_width() * 0.9))
            about_lbl.configure(wraplength=w)
        content.bind("<Configure>", _update_wraplength)

        self._about_img_ref = None
        if isinstance(about_image_path, str) and about_image_path:
            try:
                if os.path.isfile(about_image_path):
                    im = Image.open(about_image_path)
                    im.thumbnail((700, 350), Image.Resampling.LANCZOS)
                    self._about_img_ref = ImageTk.PhotoImage(im)
                    ttk.Label(content, image=self._about_img_ref).pack(anchor="center", pady=(0, 20))
            except Exception:
                pass

        form.deiconify()
        form.grab_set()


    
#endregion SettingsForm
   
   
    def weather_loop(self):
        while not self.stop_event.is_set():
            self.weather_client.fetch_weather_data()
            time.sleep(600)  # Every 10 minutes

    def add_stats_to_frame(self, frame):
        font_path = self.font_path
        font_size = settings['stats']['font_size']
        font_color = settings['stats']['font_color']

        color_map = {
            "yellow": (255, 255, 0),
            "white": (255, 255, 255),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255)
        }
        font_color = color_map.get(font_color.lower(), (255, 255, 0))

        pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)
        draw.text((10, 10), self.cached_stats, font=self.stats_font, fill=font_color)

        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    def on_closing(self):
        """Handler for window close event."""
        self.stop_event.set()
        self.parent.destroy()

    def resize_image(self, cv_img):
        """
        Resizes the given OpenCV image to fit within the desired dimensions while
        preserving its aspect ratio. It also centers the resized image on a black background.
        """
        h, w, _ = cv_img.shape
        aspect_ratio = w / h
        desired_aspect = self.desired_width / self.desired_height

        if aspect_ratio > desired_aspect:
            new_w = self.desired_width
            new_h = int(self.desired_width / aspect_ratio)
        else:
            new_h = self.desired_height
            new_w = int(self.desired_height * aspect_ratio)
        
        resized_img = cv2.resize(cv_img, (new_w, new_h))
        
        # Create a black background and center the resized image on it
        background = np.zeros((self.desired_height, self.desired_width, 3), dtype=np.uint8)
        x_offset = (self.desired_width - new_w) // 2
        y_offset = (self.desired_height - new_h) // 2
        background[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized_img
        
        return background
    
    def get_fallback_frame(self, text="Waiting for stream..."):
        """
        Returns a black image with centered white text.
        """
        # Create black background
        img = Image.new('RGB', (self.desired_width, self.desired_height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        font = self.date_font  # Use your existing font
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (self.desired_width - text_width) // 2
        y = (self.desired_height - text_height) // 2

        draw.text((x, y), text, font=font, fill=(255, 255, 255))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


    def frame_fetch_loop(self):
        """
        Continuously fetch frames from the MJPEG client, resize them,
        and update the current_frame variable.
        """
        for frame in self.stream_client.get_frames():
            if self.stop_event.is_set():
                break
            if frame is None:
                self.current_frame = self.get_fallback_frame("Waiting for stream...")
                time.sleep(5)
                break
            resized_frame = self.resize_image(frame)
            self.current_frame = resized_frame
            # Sleep briefly to allow a consistent fetch rate (~30 FPS)
            time.sleep(1/30)

    def update_display(self):
        """
        Periodically updates the tkinter label with the latest frame.
        Pulls directly from the server.iFrame interface.
        """
        frame = self.PhotoFrameServer.get_live_frame()
        if frame is not None:
            overlay_frame = self.add_overlay_text(self.current_frame.copy())
            cv_img_rgb = cv2.cvtColor(overlay_frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(cv_img_rgb)
            image_tk = ImageTk.PhotoImage(pil_image)
            self.label.config(image=image_tk)
            self.label.image = image_tk 
        self.after(33, self.update_display)

    def stop(self):
        """Stops the background frame fetching thread."""
        self.stop_event.set()

    def add_overlay_text(self, frame):
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%d/%m/%y")

        font_path = self.font_path
        time_font_size = settings['time_font_size']
        date_font_size = settings['date_font_size']
        margin_left = settings['margin_left']
        margin_bottom = settings['margin_bottom']
        spacing = settings['spacing_between']
        margin_right = settings.get('margin_right', 50)
        font_color = (255, 255, 255)

        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        # Draw time and date
        time_bbox = draw.textbbox((0, 0), current_time, font=self.time_font)
        date_bbox = draw.textbbox((0, 0), current_date, font=self.date_font)

        x_date = margin_left
        x_time = x_date + (date_bbox[2] - date_bbox[0] - (time_bbox[2] - time_bbox[0])) // 2
        y_date = self.desired_height - margin_bottom
        y_time = y_date - (date_bbox[3] - date_bbox[1]) - spacing

        draw.text((x_time, y_time), current_time, font=self.time_font, fill=font_color)
        draw.text((x_date, y_date), current_date, font=self.date_font, fill=font_color)

        # Draw weather if available
        weather = self.weather_client.get_weather_data()
        icon = self.weather_client.get_weather_icon()

        if weather and icon:
            temp_text = f"{weather['temp']}°{weather['unit']}"
            desc_text = weather['description']

            temp_bbox = draw.textbbox((0, 0), temp_text, font=self.time_font)
            desc_bbox = draw.textbbox((0, 0), desc_text, font=self.font_desc)

            icon_size = 100
            x_icon = self.desired_width - margin_right - icon_size
            y_icon = self.desired_height - margin_bottom - icon_size

            x_temp = x_icon - spacing - (temp_bbox[2] - temp_bbox[0])
            y_temp = y_icon + (icon_size - (temp_bbox[3] - temp_bbox[1])) // 2

            x_desc = x_temp
            y_desc = y_temp + (temp_bbox[3] - temp_bbox[1]) + 10

            icon_resized = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            pil_img.paste(icon_resized, (x_icon, y_icon), icon_resized)
            draw.text((x_temp, y_temp), temp_text, font=self.date_font , fill=font_color)
            draw.text((x_desc, y_desc), desc_text, font=self.date_font, fill=font_color)

        frame_with_text = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        if self.show_stats:
            try:
                frame_with_text = self.add_stats_to_frame(frame_with_text)
            except Exception as e:
                print("Error adding stats to frame:", e)

        return frame_with_text

    def get_system_stats(self):
        #cpu = cv2.getCPUTickCount()
        cpu_usage = int(psutil.cpu_percent(interval=1))

        ram = psutil.virtual_memory()
        ram_used = ram.used // (1024 * 1024)
        ram_total = ram.total // (1024 * 1024)
        ram_percent = ram.percent

        try:
            cpu_temps = psutil.sensors_temperatures().get("cpu_thermal", [])
            cpu_temp = round(cpu_temps[0].current, 1) if cpu_temps else "N/A"
        except Exception:
            cpu_temp = "N/A"

        return f"CPU: {cpu_usage}%\nRAM: {ram_percent}% ({ram_used}/{ram_total}MB)\nCPU Temp: {cpu_temp}°C"

    def update_stats_loop(self):
        while not self.stop_event.is_set():
            self.cached_stats = self.get_system_stats()
            time.sleep(5)


#region iFrame

    def get_live_frame(self):
        return self.current_frame

    
    def get_is_running(self):
        return not self.stop_event.is_set()

    
    def update_images_list(self):
        logging.info("update_images_list called – no action in desktop client")

    
    def update_frame_to_stream(self, frame):
        self.current_frame = frame

#endregion iFrame

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "photoframe_settings.json")
    with open(path, "r") as f:
        settings = json.load(f)

    backend_host = settings.get("backend_configs", {}).get("host", "localhost")
    if backend_host == "0.0.0.0":
        backend_host = "127.0.0.1"    
    backend_port = settings.get("backend_configs", {}).get("server_port", 5001)
    print(backend_host)
    print(backend_port)
    STREAM_URL = f"http://{backend_host}:{backend_port}/stream"

    os.environ["DISPLAY"] = ":0"
    root = tk.Tk()
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    mjpeg_frame = PhotoFrame(root, stream_url=STREAM_URL, desired_width=screen_width, desired_height=screen_height)
    mjpeg_frame.pack(fill="both", expand=True)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        mjpeg_frame.stop()
        root.destroy()