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

from WebAPI.API import Backend as BackendAPI
from FrameServer.PhotoFrameServer import PhotoFrameServer
from iFrame import iFrame

from Utilities.network_utils import get_local_ip
from Utilities.Weather.weather_adapter import build_weather_client
from Utilities.screen_utils import ScreenController
from Utilities.autoupdate_utils import AutoUpdater
from Utilities.stats_utils import StatsService
from Utilities.MQTT.mqtt_bridge import MqttBridge

from FrameGUI.overlay import OverlayRenderer
from FrameGUI.settings_form import SettingsForm


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
        
        self._gui_new_frame_ev = threading.Event()
        self._gui_frame_q = queue.Queue(maxsize=1)  # or maxsize=1 for lowest latency
        self._start_gui_event_pump()
            
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

        self.api = BackendAPI(frame=self.server, settings=self.settings, image_dir=self.image_dir, settings_path = "photoframe_settings.json")
        self.server.m_api = self.api
        threading.Thread(target=self.api.start, daemon=True).start()

        self.screen = ScreenController(self.settings, self.stop_event)
        self.screen.start()
        self.autoupdater = AutoUpdater(self.settings, self.stop_event)
        self.autoupdater.start()

        self.mqtt_bridge: Optional[MqttBridge] = None

        mqtt_settings = self.settings.get("mqtt", {})
        mqtt_enabled = bool(mqtt_settings.get("enabled", False))
        mqtt_host = mqtt_settings.get("host", "").strip()

        if mqtt_enabled and mqtt_host and MqttBridge is not None:
            try:
                self.mqtt_bridge = MqttBridge(
                    view=self,
                    settings=self.settings,
                    #device_name="Digital Photo Frame",
                    #get_state=self._mqtt_state_snapshot,                 # -> dict of current stats
                    #set_brightness=lambda pct: self._apply_brightness_from_mqtt(int(pct)),
                    #pull_update=self.autoupdater.pull_now,               # returns (ok, msg)
                    #restart_service=self._restart_service_sync,          # returns (ok, msg)
                    #stop_service=self._stop_service_sync,                # returns (ok, msg)
                )
                self.mqtt_bridge.start()
            except Exception as e:
                self.send_log_message(f"MQTT bridge initialization failed: {e}", logging.ERROR)
        else:
            self.send_log_message("MQTT disabled (no host, disabled in settings, or missing MqttBridge).", logging.INFO)
                
        self.current_frame: Optional[np.ndarray] = None
        #self.after(33, self._update_display)

        self.root.bind_all("<Control-c>", lambda _e: self._on_close())
        self.root.bind_all("<ButtonRelease-1>", self._handle_triple_tap)
        self.root.bind("<ButtonPress-1>", self._on_button_press)
        self.root.bind("<ButtonRelease-1>", self._on_button_release)

        self.settings_form: Optional[SettingsForm] = None
        
    def _apply_brightness_from_mqtt(self, pct: int) -> bool:
        pct = max(10, min(100, int(pct)))
        ok = self.screen.set_brightness_percent(pct, allow_zero=False)
        if ok:
            self.settings.setdefault("screen", {})["brightness"] = pct
        return ok

    def _restart_service_sync(self):
        """Restart the photoframe systemd service. Return (ok, msg)."""
        try:
            name = self.service_name
            r = subprocess.run(["systemctl", "--user", "status", f"{name}.service"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode in (0, 3):
                cp = subprocess.run(["systemctl", "--user", "restart", f"{name}.service"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            else:
                cp = subprocess.run(["sudo", "systemctl", "restart", f"{name}.service"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            return (cp.returncode == 0), (cp.stdout or "").strip()
        except Exception as e:
            return False, str(e)

    def _stop_service_sync(self):
        """Stop the photoframe systemd service. Return (ok, msg)."""
        try:
            name = self.service_name
            cp = subprocess.run(["sudo", "systemctl", "stop", f"{name}.service"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            return (cp.returncode == 0), (cp.stdout or "").strip()
        except Exception as e:
            return False, str(e)

    def _get_current_ssid(self) -> str:
        try:
            out = subprocess.check_output(
                ["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"],
                universal_newlines=True, stderr=subprocess.DEVNULL, timeout=3
            )
            lines = [l for l in out.splitlines() if l]
            return lines[0] if lines else "N/A"
        except Exception:
            return "N/A"

    def _mqtt_state_snapshot(self) -> dict:
        """
        Build a single dict with everything the bridge should publish:
        IP, Wi-Fi SSID, CPU %, temp, RAM %, RAM used/total, and brightness.
        """
        # Parse the StatsService cached text robustly
        cpu_pct = None
        ram_pct = None
        ram_used = None
        ram_total = None
        cpu_temp = None

        try:
            lines = (self.stats.cached or "").splitlines()
            # CPU: 12%
            if len(lines) >= 1:
                import re
                m = re.search(r"(\d+)\s*%", lines[0])
                cpu_pct = int(m.group(1)) if m else None

            # RAM: 34% (1234/4096MB)
            if len(lines) >= 2:
                import re
                m_pct = re.search(r"(\d+)\s*%", lines[1])
                ram_pct = int(m_pct.group(1)) if m_pct else None
                m_mb = re.search(r"\((\d+)\s*/\s*(\d+)MB\)", lines[1])
                if m_mb:
                    ram_used = int(m_mb.group(1))
                    ram_total = int(m_mb.group(2))

            # CPU Temp: 51.2°C
            if len(lines) >= 3:
                import re
                m = re.search(r"(-?\d+(\.\d+)?)", lines[2])
                cpu_temp = float(m.group(1)) if m else None
        except Exception:
            pass

        return {
            "ip_address": get_local_ip(),
            "wifi_ssid": self._get_current_ssid(),
            "cpu_percent": cpu_pct,
            "cpu_temp_c": cpu_temp,
            "ram_percent": ram_pct,
            "ram_used_mb": ram_used,
            "ram_total_mb": ram_total,
            "screen_brightness": int(self.settings.get("screen", {}).get("brightness", 100)),
            "service_name": self.service_name,
            "device_name": self.settings.get("about", {}).get("text", "Digital Photo Frame"),
        }

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
    # def _update_display(self) -> None:
    #     frame = self.server.get_live_frame()
    #     if frame is not None:
    #         frame = self.overlay.resize_and_letterbox(frame, self.desired_width, self.desired_height)
    #         margins = {
    #             "left": int(self.settings.get("margin_left", 50)),
    #             "bottom": int(self.settings.get("margin_bottom", 50)),
    #             "right": int(self.settings.get("margin_right", 50)),
    #             "spacing": int(self.settings.get("spacing_between", 10)),
    #         }
    #         weather = self.weather_client.data()
    #         frame = self.overlay.render_datetime_and_weather(
    #             frame_bgr=frame,
    #             margins=margins,
    #             weather=weather,
    #             font_color=(255, 255, 255),
    #         )
    #         # if bool(self.settings.get("stats", {}).get("show", False)):
    #         #     frame = self.overlay.render_stats(
    #         #         frame_bgr=frame,
    #         #         text=self.stats.cached,
    #         #         color_name=self.settings.get("stats", {}).get("font_color", "yellow"),
    #         #     )

    #         rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    #         pil_image = Image.fromarray(rgb)
    #         image_tk = ImageTk.PhotoImage(pil_image)
    #         self.label.config(image=image_tk)
    #         self.label.image = image_tk

    #     self.after(33, self._update_display)
    
    def _render_frame(self, frame: np.ndarray) -> None:
        try:
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
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)
            image_tk = ImageTk.PhotoImage(pil_image)
            self.label.config(image=image_tk)
            self.label.image = image_tk
        except Exception:
            logging.exception("render_frame failed")
            
        
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
        
    def publish_frame_from_backend(self, frame):
        """
        Called by the frame server on each new frame.
        Keep only the newest frame, then wake the GUI pump.
        Non-blocking, safe to call from non-Tk threads.
        """
        try:
            while True:
                if not hasattr(self, "_gui_frame_q"):
                    continue 
                self._gui_frame_q.get_nowait() 
        except queue.Empty:
            pass
        try:
            self._gui_frame_q.put_nowait(frame)
        except queue.Full:
            pass
        self._gui_new_frame_ev.set()
        
    # --------- lifecycle ----------
    def stop(self) -> None:
        self.stop_event.set()
        try:
            if hasattr(self, "mqtt_bridge") and self.mqtt_bridge:
                self.mqtt_bridge.stop()
        except Exception:
            pass

    def _on_close(self) -> None:
        self.stop()
        self.root.destroy()

    
    def _start_gui_event_pump(self) -> None:
        """
        Wait on _gui_new_frame_ev and schedule rendering back to the Tk thread.
        Also do a very low-rate idle refresh in case an event is missed.
        """
        idle_fps = int(self.settings.get("backend_configs", {}).get("idle_fps", 1)) or 1
        idle_delay = 1.0 / max(idle_fps, 1)

        def worker():
            last_render = 0.0
            while not self.stop_event.is_set():
                got = self._gui_new_frame_ev.wait(timeout=idle_delay)
                now = time.time()
                if got:
                    self._gui_new_frame_ev.clear()
                    self._post_render_latest_frame()
                    last_render = now
                else:
                    if now - last_render >= idle_delay:
                        self._post_render_latest_frame()
                        last_render = now

        threading.Thread(target=worker, name="GUI-EventPump", daemon=True).start()


    def _post_render_latest_frame(self) -> None:
        """
        Drain to newest frame and render it on the Tk thread.
        Falls back to server.get_live_frame() if queue is empty.
        """
        frame = None
        try:
            while True:
                frame = self._gui_frame_q.get_nowait()
        except queue.Empty:
            pass

        if frame is None:
            frame = self.server.get_live_frame()
        if frame is None:
            return

        self.after(0, lambda f=frame: self._render_frame(f))
