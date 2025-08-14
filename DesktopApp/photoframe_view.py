import os
import re
import cv2
import time
import json
import queue
import threading
import logging
import subprocess
import numpy as np
from typing import Dict, Any, Optional

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from WebServer.API import Backend as BackendAPI
from WebServer.PhotoFrameServer import PhotoFrameServer
from iFrame import iFrame

from utils_net import get_local_ip
from weather_adapter import build_weather_client
from screen_scheduler import ScreenController
from autoupdater import AutoUpdater
from stats_service import StatsService
from overlay import OverlayRenderer
from settings_form import SettingsForm


class PhotoFrameView(tk.Frame, iFrame):
    def __init__(self, root: tk.Tk, settings: Dict[str, Any], desired_width: int, desired_height: int) -> None:
        super().__init__(root, bg="black")
        self.root = root
        self.settings = settings
        self.desired_width = desired_width
        self.desired_height = desired_height

        self.stop_event = threading.Event()
        self._tap_count = 0
        self._last_tap_time = 0.0
        self._long_press_job = None
        self._long_press_duration_ms = 5000

        self._init_window()

        base_path = os.path.dirname(os.path.abspath(__file__))
        self.font_path = os.path.join(base_path, self.settings.get("font_name", "DejaVuSans.ttf"))
        self.overlay = OverlayRenderer(
            font_path=self.font_path,
            time_font_size=int(self.settings.get("time_font_size", 48)),
            date_font_size=int(self.settings.get("date_font_size", 28)),
            stats_font_size=int(self.settings.get("stats", {}).get("font_size", 20)),
            desired_size=(self.desired_width, self.desired_height),
        )

        self.label = tk.Label(self, bg="black")
        self.label.pack(fill="both", expand=True)

        self.weather_client = build_weather_client(self, self.settings)
        self.weather_thread = threading.Thread(target=self._weather_loop, daemon=True)
        self.weather_thread.start()

        self.stats = StatsService()
        self.stats_thread = threading.Thread(target=self.stats.loop_update, args=(self.stop_event.is_set,), daemon=True)
        self.stats_thread.start()

        self.base_path = base_path
        self.image_dir = os.path.join(base_path, "Images")
        self.backend_port = int(self.settings.get("backend_configs", {}).get("server_port", 5001))
        self.service_name = self.settings.get("service_name", "photoframe")

        self.server = PhotoFrameServer(
            width=self.desired_width,
            height=self.desired_height,
            iframe=self,
            images_dir=self.image_dir
        )
        threading.Thread(target=self.server.run_photoframe, daemon=True).start()

        self.api = BackendAPI(frame=self.server, settings=self.settings, image_dir=self.image_dir)
        self.server.m_api = self.api
        threading.Thread(target=self.api.start, daemon=True).start()

        self.screen = ScreenController(self.settings, self.stop_event)
        self.screen.start()
        self.autoupdater = AutoUpdater(self.settings, self.stop_event)
        self.autoupdater.start()

        self.current_frame: Optional[np.ndarray] = None
        self.after(33, self._update_display)

        self.root.bind_all("<Control-c>", lambda _e: self._on_close())
        self.root.bind_all("<ButtonRelease-1>", self._handle_triple_tap)
        self.root.bind("<ButtonPress-1>", self._on_button_press)
        self.root.bind("<ButtonRelease-1>", self._on_button_release)

        self.settings_form: Optional[SettingsForm] = None

    # --------- iFrame logging hook ----------
    def send_log_message(self, msg: str, logger=logging.info) -> None:
        try:
            logger(msg)
        except Exception:
            logging.info(str(msg))

    # --------- Window setup ----------
    def _init_window(self) -> None:
        self.root.title("Digital Photo Frame V2.0")
        w, h = self.desired_width, self.desired_height
        self.root.geometry(f"{w}x{h}+0+0")
        self.root.attributes("-fullscreen", True)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg="black")
        self.root.config(cursor="none")

    # --------- Weather loop ----------
    def _weather_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.weather_client.fetch()
            except Exception:
                logging.exception("weather loop error")
            time.sleep(600)

    # --------- UI update ----------
    def _update_display(self) -> None:
        frame = self.server.get_live_frame()
        if frame is not None:
            frame = self.overlay.resize_and_letterbox(frame, self.desired_width, self.desired_height)
            margins = {
                "left": int(self.settings.get("margin_left", 50)),
                "bottom": int(self.settings.get("margin_bottom", 50)),
                "right": int(self.settings.get("margin_right", 50)),
                "spacing": int(self.settings.get("spacing_between", 10)),
            }
            weather = self.weather_client.data()
            frame = self.overlay.render_datetime_and_weather(
                frame_bgr=frame,
                margins=margins,
                weather=weather,
                font_color=(255, 255, 255),
            )
            # if bool(self.settings.get("stats", {}).get("show", False)):
            #     frame = self.overlay.render_stats(
            #         frame_bgr=frame,
            #         text=self.stats.cached,
            #         color_name=self.settings.get("stats", {}).get("font_color", "yellow"),
            #     )

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)
            image_tk = ImageTk.PhotoImage(pil_image)
            self.label.config(image=image_tk)
            self.label.image = image_tk

        self.after(33, self._update_display)

    # --------- Gestures ----------
    def _on_button_press(self, _event) -> None:
        if self._long_press_job is None:
            self._long_press_job = self.after(self._long_press_duration_ms, self._long_press_detected)

    def _on_button_release(self, _event) -> None:
        if self._long_press_job is not None:
            self.after_cancel(self._long_press_job)
            self._long_press_job = None

    def _long_press_detected(self) -> None:
        logging.info("Long-press detected: shutting down")
        self._on_close()

    def _handle_triple_tap(self, _event) -> None:
        now = time.time()
        if now - self._last_tap_time <= 1.5:
            self._tap_count += 1
        else:
            self._tap_count = 1
        self._last_tap_time = now
        if self._tap_count == 3:
            self._open_settings()
            self._tap_count = 0

    # --------- Settings form ----------
    def _open_settings(self) -> None:
        if self.settings_form and self.settings_form.window().winfo_exists():
            return

        def on_apply_brightness(pct: int) -> bool:
            return self.screen.set_brightness_percent(pct, allow_zero=False)

        def on_apply_orientation(transform: str) -> bool:
            output = self._pick_default_output()
            if not output:
                messagebox.showerror("No display", "Could not detect a Wayland output via wlr-randr.")
                return False
            try:
                subprocess.run(["wlr-randr", "--output", output, "--transform", transform], check=True)
                return True
            except subprocess.CalledProcessError as e:
                messagebox.showerror("Failed to set orientation", str(e))
                return False

        def on_autoupdate_pull() -> None:
            def _worker():
                ok, msg = self.autoupdater.pull_now()
                title = "Pull OK" if ok else "Pull failed"
                self.after(0, lambda: messagebox.showinfo(title, msg[:2000]))
            threading.Thread(target=_worker, daemon=True).start()

        def on_restart_service_async() -> None:
            def _worker():
                try:
                    name = self.service_name
                    r = subprocess.run(["systemctl", "--user", "status", f"{name}.service"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if r.returncode in (0, 3):
                        subprocess.run(["systemctl", "--user", "restart", f"{name}.service"], check=True)
                    else:
                        subprocess.run(["sudo", "systemctl", "restart", f"{name}.service"], check=True)
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Restart failed", str(e)))
            threading.Thread(target=_worker, daemon=True).start()

        self.settings_form = SettingsForm(
            parent=self.root,
            settings=self.settings,
            backend_port=int(self.settings.get("backend_configs", {}).get("server_port", 5001)),
            on_apply_brightness=on_apply_brightness,
            on_apply_orientation=on_apply_orientation,
            on_autoupdate_pull=on_autoupdate_pull,
            on_restart_service_async=on_restart_service_async,
            wake_screen_worker=self.screen.wake,
        )

        self._start_settings_stats_pump(self.settings_form)

    def _start_settings_stats_pump(self, form: SettingsForm) -> None:
        temp_re = re.compile(r"(-?\d+(\.\d+)?)")

        def parse_num(s: str) -> Optional[float]:
            m = temp_re.search(s or "")
            if not m:
                return None
            try:
                return float(m.group(1))
            except Exception:
                return None

        def loop():
            while self.settings_form and form.window().winfo_exists():
                try:
                    s = self.stats.cached.split("\n")
                    cpu_pct = parse_num(s[0]) if len(s) >= 1 else None
                    ram_pct = parse_num(s[1]) if len(s) >= 2 else None
                    tmp_c = parse_num(s[2]) if len(s) >= 3 else None

                    ip = get_local_ip()

                    qr_img = None
                    try:
                        import qrcode
                        qr = qrcode.make(f"http://{ip}:{self.backend_port}")
                        qr = qr.resize((160, 160))
                        qr_img = ImageTk.PhotoImage(qr)
                    except Exception:
                        qr_img = None

                    def apply():
                        if not (self.settings_form and form.window().winfo_exists()):
                            return
                        try:
                            form.cpu_lbl.config(text=s[0] if len(s) > 0 else "CPU: N/A")
                            form.ram_lbl.config(text=s[1] if len(s) > 1 else "RAM: N/A")
                            form.tmp_lbl.config(text=s[2] if len(s) > 2 else "Temp: N/A")
                            form.current_ssid_lbl.config(text=f"Wifi network: {form._get_current_ssid()}")
                            form.ip_lbl.config(text=f"URL: http://{ip}:{self.backend_port}")
                            if qr_img:
                                form.qr_lbl.config(image=qr_img)
                                form.qr_lbl.image = qr_img
                            # push data points into graphs
                            if cpu_pct is not None:
                                form.cpu_graph.push(max(0.0, min(100.0, cpu_pct)))
                            if ram_pct is not None:
                                form.ram_graph.push(max(0.0, min(100.0, ram_pct)))
                            if tmp_c is not None:
                                form.tmp_graph.push(tmp_c)
                        except Exception:
                            pass

                    self.after(0, apply)
                except Exception:
                    logging.exception("settings stats pump failed")
                time.sleep(1)

        threading.Thread(target=loop, daemon=True).start()

    # --------- Output selection ----------
    @staticmethod
    def _list_outputs() -> list:
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

    def _pick_default_output(self) -> Optional[str]:
        outs = self._list_outputs()
        outs.sort(key=lambda n: (0 if n.upper().startswith("DSI") else 1, n))
        return outs[0] if outs else None

    # --------- iFrame impl ----------
    def get_live_frame(self):
        return self.current_frame

    def get_is_running(self):
        return not self.stop_event.is_set()

    def update_images_list(self):
        logging.info("update_images_list called - not used in desktop client")

    def update_frame_to_stream(self, frame):
        self.current_frame = frame

    # --------- lifecycle ----------
    def stop(self) -> None:
        self.stop_event.set()

    def _on_close(self) -> None:
        self.stop()
        self.root.destroy()
