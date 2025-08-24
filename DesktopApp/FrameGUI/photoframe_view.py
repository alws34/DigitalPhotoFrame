import os
import re
import cv2
import time
import json
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
from Utilities.screen_utils import ScreenController
from Utilities.autoupdate_utils import AutoUpdater
from Utilities.stats_utils import StatsService
from Utilities.MQTT.mqtt_bridge import MqttBridge

from FrameGUI.settings_form import SettingsForm


class PhotoFrameView(tk.Frame, iFrame):
    """
    Tkinter client. Displays frames only. All overlay work is done on the server.
    publish_frame_from_backend schedules direct GUI updates without custom queues/threads.
    """
    def __init__(
        self,
        root: tk.Tk,
        settings: Dict[str, Any],
        desired_width: int,
        desired_height: int,
        settings_path: str = None,   # <-- NEW, default keeps backward-compat
    ) -> None:
        super().__init__(root, bg="black")
        self.root = root
        self.settings = settings
        self.desired_width = desired_width
        self.desired_height = desired_height

        # Resolve an absolute settings path if provided; else fall back to default
        if settings_path:
            self.settings_path = os.path.abspath(settings_path)
        else:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            self.settings_path = os.path.join(base_dir, "photoframe_settings.json")
            
        self.root = root
        self.settings = settings
        self.desired_width = desired_width
        self.desired_height = desired_height

        self.stop_event = threading.Event()
        self._tap_count = 0
        self._last_tap_time = 0.0
        self._long_press_job = None
        self._long_press_duration_ms = 5000

        # Render control variables
        self._tk_photo = None
        self._last_render_time = 0.0
        self._render_in_progress = False
    
        self._init_window()

        base_path = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(base_path, ".."))

        self.label = tk.Label(self, bg="black")
        self.label.pack(fill="both", expand=True)

        # Stats for SettingsForm only
        self.stats = StatsService()
        self.stats_thread = threading.Thread(target=self.stats.loop_update, args=(self.stop_event.is_set,), daemon=True)
        self.stats_thread.start()

        self.base_path = base_path
        self.image_dir = os.path.join(project_root, "Images")

        settings_abs = os.path.join(project_root, "photoframe_settings.json")

        self.backend_port = int(self.settings.get("backend_configs", {}).get("server_port", 5001))
        self.service_name = self.settings.get("service_name", "photoframe")

        # Local in-process server
        self.server = PhotoFrameServer(
            width=self.desired_width,
            height=self.desired_height,
            iframe=self,
            images_dir=self.image_dir,
            settings_path=self.settings_path, 
        )
        threading.Thread(target=self.server.run_photoframe, daemon=True).start()

        # Local Web API facade
        self.api = BackendAPI(
            frame=self.server,
            settings=self.settings,
            image_dir=self.image_dir,
            settings_path=settings_abs
        )
        self.server.m_api = self.api
        threading.Thread(target=self.api.start, daemon=True).start()

        # Screen, autoupdate, MQTT
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
                )
                self.mqtt_bridge.start()
            except Exception as e:
                self.send_log_message(f"MQTT bridge initialization failed: {e}", logging.ERROR)
        else:
            self.send_log_message("MQTT disabled (no host, disabled in settings, or missing MqttBridge).", logging.INFO)

        self.current_frame: Optional[np.ndarray] = None

        # Input bindings
        self.root.bind_all("<Control-c>", lambda _e: self._on_close())
        self.root.bind_all("<ButtonRelease-1>", self._handle_triple_tap)
        self.root.bind("<ButtonPress-1>", self._on_button_press)
        self.root.bind("<ButtonRelease-1>", self._on_button_release)

        self.settings_form: Optional[SettingsForm] = None

    # --------- MQTT helpers ----------
    def _apply_brightness_from_mqtt(self, pct: int) -> bool:
        pct = max(10, min(100, int(pct)))
        ok = self.screen.set_brightness_percent(pct, allow_zero=False)
        if ok:
            self.settings.setdefault("screen", {})["brightness"] = pct
        return ok

    def _restart_service_sync(self):
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
        cpu_pct = None
        ram_pct = None
        ram_used = None
        ram_total = None
        cpu_temp = None
        try:
            lines = (self.stats.cached or "").splitlines()
            if len(lines) >= 1:
                m = re.search(r"(\d+)\s*%", lines[0])
                cpu_pct = int(m.group(1)) if m else None
            if len(lines) >= 2:
                m_pct = re.search(r"(\d+)\s*%", lines[1])
                ram_pct = int(m_pct.group(1)) if m_pct else None
                m_mb = re.search(r"\((\d+)\s*/\s*(\d+)MB\)", lines[1])
                if m_mb:
                    ram_used = int(m_mb.group(1))
                    ram_total = int(m_mb.group(2))
            if len(lines) >= 3:
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

    # --------- Window ----------
    def _init_window(self) -> None:
        self.root.title("Digital Photo Frame V2.0")
        w, h = self.desired_width, self.desired_height
        self.root.geometry(f"{w}x{h}+0+0")
        self.root.attributes("-fullscreen", True)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg="black")
        self.root.config(cursor="none")

    # --------- Rendering (display only) ----------
    def _render_frame(self, frame: np.ndarray) -> None:
        """
        Display-only rendering. The frame is assumed to be final (server already composed).
        Enforces ~30 fps.
        """
        if self._render_in_progress:
            return
        current_time = time.time()
        if current_time - self._last_render_time < (1.0 / 30.0):
            return

        self._render_in_progress = True
        try:
            # Convert BGR -> RGB for Tk
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)

            if self._tk_photo is None:
                self._tk_photo = ImageTk.PhotoImage(pil_image)
                self.label.config(image=self._tk_photo)
                self.label.image = self._tk_photo
            else:
                self._tk_photo = ImageTk.PhotoImage(pil_image)
                self.label.config(image=self._tk_photo)
                self.label.image = self._tk_photo

            self._last_render_time = current_time
        except Exception as e:
            logging.exception(f"render_frame failed: {e}")
        finally:
            self._render_in_progress = False

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

        def on_autoupdate_pull(self=self) -> None:
            def _worker():
                ok, msg = self.autoupdater.pull_now()
                title = "Pull OK" if ok else "Pull failed"
                self.after(0, lambda: messagebox.showinfo(title, msg[:2000]))
            threading.Thread(target=_worker, daemon=True).start()

        def on_restart_service_async(self=self) -> None:
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
        Update the GUI directly from server callbacks.
        Schedules a render on Tk's main loop without intermediate queues or worker threads.
        """
        if self.stop_event.is_set() or frame is None:
            return
        # Keep a reference if you want the latest frame accessible
        self.current_frame = frame
        try:
            # Schedule onto Tk main loop; safe even if server calls from a worker thread.
            self.after_idle(lambda f=frame.copy(): self._render_frame(f))
        except Exception:
            # Window may be closing; swallow to avoid noisy logs during shutdown
            pass

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
