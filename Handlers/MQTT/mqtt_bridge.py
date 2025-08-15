import json
import logging
import platform
import socket
import subprocess
import threading
import time
from typing import Optional, TYPE_CHECKING, Any

import psutil

try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None
    
if TYPE_CHECKING:
    from paho.mqtt.client import Client as MqttClient
else:
    MqttClient = Any

try:
    from utils_net import get_local_ip as _get_local_ip_util
except Exception:
    _get_local_ip_util = None


class MqttBridge:
    """
    MQTT bridge for PhotoFrameView (new architecture).

    Publishes (state topic JSON):
      ip, cpu_usage, cpu_temp_c, ram_percent, ram_used_mb, ram_total_mb,
      wifi_ssid, uptime_s, brightness

    Home Assistant discovery entities:
      - Sensors for all stats above
      - number: Screen Brightness (10..100)
      - button: Pull Update
      - switch: Service (ON=start, OFF=stop)
      - button: Restart Service (extra)

    Settings (settings['mqtt']):
      enabled: true|false
      host: "192.168.1.10"
      port: 1883
      username: ""         (optional)
      password: ""         (optional)
      tls: false           (optional)
      client_id: "photoframe-<hostname>" (optional)
      base_topic: "photoframe"           (optional)
      discovery: true
      discovery_prefix: "homeassistant"  (optional)
      interval_seconds: 1
      retain_config: true
    """

    # ---------- lifecycle ----------
    def __init__(self, view, settings: dict):
        self.view = view
        self.settings = settings or {}
        self.cfg = (self.settings.get("mqtt") or {}).copy()

        self.enabled = bool(self.cfg.get("enabled", False))
        self.host = self.cfg.get("host", "127.0.0.1")
        self.port = int(self.cfg.get("port", 1883))
        self.username = (self.cfg.get("username") or None)
        self.password = (self.cfg.get("password") or None)
        self.tls = bool(self.cfg.get("tls", False))

        node = (platform.node() or "device").lower()
        self.client_id = self.cfg.get("client_id") or f"photoframe-{node}"
        self.base_topic = self._clean_topic(self.cfg.get("base_topic") or "photoframe")
        self.discovery = bool(self.cfg.get("discovery", True))
        self.discovery_prefix = self._clean_topic(self.cfg.get("discovery_prefix") or "homeassistant")
        self.retain_config = bool(self.cfg.get("retain_config", True))
        self.interval = int(self.cfg.get("interval_seconds", 10))

        self.device_name = "Digital Photo Frame"
        self.service_name = self.settings.get("service_name", "photoframe")
        self.device_id = self.client_id

        # topics
        self.t_avail = f"{self.base_topic}/{self.device_id}/status"
        self.t_state = f"{self.base_topic}/{self.device_id}/state"
        self.t_brightness_state = f"{self.base_topic}/{self.device_id}/brightness"
        self.t_service_state = f"{self.base_topic}/{self.device_id}/service_state"
        self.t_cmd_brightness = f"{self.base_topic}/{self.device_id}/cmd/brightness"
        #self.t_cmd_update = f"{self.base_topic}/{self.device_id}/cmd/update"
        #self.t_cmd_restart = f"{self.base_topic}/{self.device_id}/cmd/restart"
        #self.t_cmd_service = f"{self.base_topic}/{self.device_id}/cmd/service"

        self.client: Optional[MqttClient] = None
        self.connected = False
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._start_ts = time.time()

    def start(self):
        if not self.enabled:
            self._log("MQTT disabled; not starting.", logging.INFO)
            return
        if mqtt is None:
            self._log("paho-mqtt not installed. Run: pip install paho-mqtt", logging.ERROR)
            return
        if self.thread and self.thread.is_alive():
            return

        try:
            self.client = mqtt.Client(client_id=self.client_id, clean_session=True)
        except TypeError:
            self.client = mqtt.Client(client_id=self.client_id)
            
        if self.username:
            self.client.username_pw_set(self.username, self.password or None)
        if self.tls:
            try:
                self.client.tls_set()
            except Exception as e:
                self._log(f"TLS setup failed: {e}", logging.ERROR)

        # LWT
        self.client.will_set(self.t_avail, payload="offline", qos=1, retain=True)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        try:
            self.client.connect_async(self.host, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            self._log(f"MQTT connect failed: {e}", logging.ERROR)
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._log("MQTT bridge started.", logging.info)

    def stop(self):
        self.stop_event.set()
        try:
            if self.client:
                self._publish(self.t_avail, "offline", retain=True)
                self.client.loop_stop()
                self.client.disconnect()
        except Exception:
            pass
    def _async(self, fn, *args, **kwargs):
        threading.Thread(target=lambda: fn(*args, **kwargs), daemon=True).start()
    
    # ---------- callbacks ----------
    def _on_connect(self, _c, _u, _f, rc):
        self.connected = (rc == 0)
        if not self.connected:
            self._log(f"MQTT connect rc={rc}", logging.ERROR)
            return

        self._log("Connected to MQTT broker.", logging.INFO)
        self._publish(self.t_avail, "online", retain=True)

        # subscribe commands
        self.client.subscribe(self.t_cmd_brightness, qos=1)

        if self.discovery:
            self._publish_discovery_all()

        # initial states
        self._publish_immediate_states()

    def _on_disconnect(self, _c, _u, rc):
        self.connected = False
        if rc != 0:
            self._log(f"Unexpected disconnect rc={rc}", logging.WARNING)

    def _on_message(self, _c, _u, msg):
        topic = msg.topic
        payload = (msg.payload or b"").decode("utf-8", "ignore").strip()
        self._log(f"RX {topic} = {payload}", logging.INFO)

        if topic == self.t_cmd_brightness:
            self._async(self._handle_cmd_brightness, payload)
        elif topic == self.t_cmd_update:
            self._async(self._handle_cmd_update)
        elif topic == self.t_cmd_restart:
            self._async(self._handle_cmd_restart)
        elif topic == self.t_cmd_service:
            self._async(self._handle_cmd_service, payload)

    # ---------- worker ----------
    def _run(self):
        while not self.stop_event.is_set():
            try:
                if self.connected:
                    self._publish_stats()
                    self._publish_brightness_state()
                    self._publish_service_state()
            except Exception as e:
                self._log(f"tick failed: {e}", logging.ERROR)
            self.stop_event.wait(self.interval)

    # ---------- discovery ----------
    def _publish_discovery_all(self):
        dev = self._device_payload()
        dp = self.discovery_prefix
        did = self.device_id

        def pub(topic, payload):
            body = json.dumps(payload)
            self._log(f"Publish discovery: {topic} -> {body}", logging.INFO)
            self._publish(topic, body, retain=self.retain_config)

        # Helper: only include state_class if not None
        def sensor(object_id, name, vt, unit=None, device_class=None, icon=None, state_class=None, extra=None, unique_suffix=""):
            uid = f"{did}_{object_id}{unique_suffix}"
            cfg = {
                "name": name,
                "unique_id": uid,
                "state_topic": self.t_state,
                "availability_topic": self.t_avail,
                "value_template": vt,
                "device": dev,
            }
            if unit is not None:
                cfg["unit_of_measurement"] = unit
            if device_class:
                cfg["device_class"] = device_class
            if state_class:  # ← key change: only add for numeric sensors
                cfg["state_class"] = state_class
            if icon:
                cfg["icon"] = icon
            if isinstance(extra, dict):
                cfg.update(extra)
            pub(f"{dp}/sensor/{did}/{object_id}/config", cfg)

        # Controls
        number_brightness = {
            "name": "Screen Brightness",
            "unique_id": f"{did}_screen_brightness",
            "state_topic": self.t_brightness_state,
            "command_topic": self.t_cmd_brightness,
            "availability_topic": self.t_avail,
            "min": 10,
            "max": 100,
            "step": 10,
            "unit_of_measurement": "%",
            "mode": "slider",
            "device": dev,
            "icon": "mdi:brightness-6",
        }
        pub(f"{dp}/number/{did}/screen_brightness/config", number_brightness)

        # button_update = {
        #     "name": "Pull Update",
        #     "unique_id": f"{did}_pull_update",
        #     "command_topic": self.t_cmd_update,
        #     "availability_topic": self.t_avail,
        #     "device": dev,
        #     "icon": "mdi:update",
        # }
        # pub(f"{dp}/button/{did}/pull_update/config", button_update)

        # button_restart = {
        #     "name": "Restart Service",
        #     "unique_id": f"{did}_restart_service",
        #     "command_topic": self.t_cmd_restart,
        #     "availability_topic": self.t_avail,
        #     "device": dev,
        #     "icon": "mdi:restart",
        # }
        # pub(f"{dp}/button/{did}/restart_service/config", button_restart)

        # switch_service = {
        #     "name": "Service",
        #     "unique_id": f"{did}_service",
        #     "state_topic": self.t_service_state,
        #     "command_topic": self.t_cmd_service,
        #     "availability_topic": self.t_avail,
        #     "payload_on": "ON",
        #     "payload_off": "OFF",
        #     "device": dev,
        #     "icon": "mdi:application-cog",
        # }
        # pub(f"{dp}/switch/{did}/service/config", switch_service)

        # Sensors from state JSON
        sensor(
            "ip", "IP Address", "{{ value_json.ip }}",
            icon="mdi:ip",
            extra={"entity_category": "diagnostic"},
            unique_suffix="_v2"       # forces HA to create fresh entities
        )
        sensor("cpu", "CPU Usage", "{{ value_json.cpu_usage }}", unit="%", device_class="power_factor")
        sensor("cputemp", "CPU Temperature", "{{ value_json.cpu_temp_c }}", unit="°C", device_class="temperature")
        sensor("ram_pct", "RAM Usage", "{{ value_json.ram_percent }}", unit="%", device_class="power_factor")
        sensor("ram_used", "RAM Used", "{{ value_json.ram_used_mb }}", unit="MB", icon="mdi:memory")
        sensor("ram_total", "RAM Total", "{{ value_json.ram_total_mb }}", unit="MB", icon="mdi:memory")
        sensor("ssid", "Wi-Fi SSID", "{{ value_json.wifi_ssid }}",
            icon="mdi:wifi",
            extra={"entity_category": "diagnostic"},
            unique_suffix="_v2")
        sensor("uptime", "Uptime", "{{ value_json.uptime_s }}", unit="s", icon="mdi:timer-outline")
        sensor("brightness", "Screen Brightness", "{{ value_json.brightness }}", unit="%", icon="mdi:brightness-6")

    def _device_payload(self):
        sw = "PhotoFrame 2.0"
        try:
            v = self.settings.get("version") or ""
            if v:
                sw = f"{sw} ({v})"
        except Exception:
            pass
        return {
            "identifiers": [self.device_id],
            "name": self.device_name,
            "manufacturer": "PhotoFrame",
            "model": "Digital Photo Frame",
            "sw_version": sw,
        }

    # ---------- state + stats ----------
    def _publish_immediate_states(self):
        self._publish_brightness_state()
        self._publish_service_state()
        self._publish_stats()

    def _publish_stats(self):
        self._publish(self.t_state, json.dumps(self._stats()), qos=1, retain=False)

    def _stats(self):
        ip = str(self._get_local_ip() or "")
        cpu_pct = int(psutil.cpu_percent(interval=0))
        ram = psutil.virtual_memory()
        ram_used = ram.used // (1024 * 1024)
        ram_total = ram.total // (1024 * 1024)
        ram_percent = int(ram.percent)

        # CPU temperature (try common sensors)
        try:
            temps = psutil.sensors_temperatures() or {}
            cand = None
            for k in ("cpu_thermal", "coretemp", "soc_thermal"):
                if k in temps and temps[k]:
                    cand = temps[k][0]
                    break
            cpu_temp = round(float(cand.current), 1) if cand else None
        except Exception:
            cpu_temp = None

        ssid = str(self._get_current_ssid() or "")
        brightness = self._read_brightness_percent()
        obj = {
            "ip": ip,
            "cpu_usage": cpu_pct,
            "cpu_temp_c": cpu_temp,
            "ram_percent": ram_percent,
            "ram_used_mb": ram_used,
            "ram_total_mb": ram_total,
            "wifi_ssid": ssid,
            "uptime_s": int(time.time() - self._start_ts),
            "brightness": brightness,
        }
        #print(obj)
        return obj

    # ---------- brightness ----------
    def _read_brightness_percent(self) -> Optional[int]:
        # Prefer ScreenController if it exposes a reader
        try:
            sc = getattr(self.view, "screen", None)
            if sc and hasattr(sc, "read_brightness_percent"):
                pct = sc.read_brightness_percent()
                if pct is not None:
                    return int(pct)
        except Exception:
            pass
        # Fallback: read from /sys/class/backlight
        try:
            dev = self._pick_default_backlight()
            if not dev:
                return None
            cur, maxb = self._read_brightness_values(dev)
            if not maxb:
                return None
            pct = int(round(cur * 100.0 / maxb))
            pct = max(0, min(100, pct))
            if pct and pct < 10:
                pct = 10
            return pct
        except Exception:
            return None

    def _publish_brightness_state(self):
        pct = self._read_brightness_percent()
        if pct is not None:
            self._publish(self.t_brightness_state, str(pct), qos=1, retain=True)

    def _handle_cmd_brightness(self, payload: str):
        try:
            pct = int(float(payload))
        except Exception:
            self._log(f"Bad brightness payload: {payload!r}", logging.WARNING)
            return
        pct = max(10, min(100, pct))
        try:
            sc = getattr(self.view, "screen", None)
            if sc and hasattr(sc, "set_brightness_percent"):
                ok = bool(sc.set_brightness_percent(pct, allow_zero=False))
                if not ok:
                    self._log("ScreenController refused brightness change.", logging.WARNING)
                self._publish_brightness_state()
                return
        except Exception as e:
            self._log(f"ScreenController set_brightness failed: {e}", logging.ERROR)

        # Fallback direct write
        try:
            dev = self._pick_default_backlight()
            if not dev:
                self._log("No backlight device found.", logging.ERROR)
                return
            _ = self._write_brightness_percent(dev, pct)
            self._publish_brightness_state()
        except Exception as e:
            self._log(f"Fallback brightness write failed: {e}", logging.ERROR)

    # ---------- update / service ----------
    def _handle_cmd_update(self):
        try:
            au = getattr(self.view, "autoupdater", None)
            if au and hasattr(au, "pull_now"):
                ok, msg = au.pull_now()
                lvl = logging.INFO if ok else logging.WARNING
                self._log(f"Pull update {'OK' if ok else 'FAILED'}: {msg[:300]}", lvl)
                return
        except Exception as e:
            self._log(f"AutoUpdater pull_now error: {e}", logging.ERROR)

        # Fallback: try git pull in app dir
        try:
            res = subprocess.run(
                ["git", "-C", self._repo_path(), "pull", "--ff-only"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120
            )
            ok = (res.returncode == 0)
            msg = res.stdout.strip()
            lvl = logging.INFO if ok else logging.WARNING
            self._log(f"git pull {'OK' if ok else 'FAILED'}: {msg[:300]}", lvl)
        except Exception as e:
            self._log(f"git pull fallback error: {e}", logging.ERROR)

    def _handle_cmd_restart(self):
        try:
            self._restart_service(self.service_name)
        except Exception as e:
            self._log(f"Restart service error: {e}", logging.ERROR)

    def _handle_cmd_service(self, payload: str):
        target = (payload or "").strip().upper()
        if target not in ("ON", "OFF"):
            self._log(f"Unknown service payload: {payload!r}", logging.WARNING)
            return

        name = self.service_name

        if target == "OFF":
            # 1) tell HA we’re going offline
            try:
                mi = self.client.publish(self.t_avail, "offline", qos=1, retain=True)
                mi.wait_for_publish(timeout=1.0)
            except Exception:
                pass

            # 2) disconnect cleanly so the broker doesn't show 'connection lost'
            try:
                self.client.disconnect()
                self.client.loop_stop()   # stop network loop
            except Exception:
                pass

            # 3) now actually stop the unit
            try:
                self._stop_service(name)
            except Exception as e:
                self._log(f"Stop service error: {e}", logging.ERROR)
            return

        # target == "ON"
        try:
            if not self._is_service_running(name):
                self._start_service(name)
            # let things settle and then republish state
            self._delayed_publish_service_state()
        except Exception as e:
            self._log(f"Start service error: {e}", logging.ERROR)

    def _delayed_publish_service_state(self, delay: float = 1.5):
        def _w():
            time.sleep(delay)
            try:
                self._publish_service_state()
            except Exception:
                pass
        threading.Thread(target=_w, daemon=True).start()


    def _publish_service_state(self):
        state = "ON" if self._is_service_running(self.service_name) else "OFF"
        self._publish(self.t_service_state, state, qos=1, retain=True)

    # ---------- helpers: backlight ----------
    def _list_backlights(self):
        import os
        base = "/sys/class/backlight"
        if not os.path.isdir(base):
            return []
        devs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
        # prefer rpi-like first
        devs.sort(key=lambda n: (0 if ("rpi" in n or "rasp" in n) else 1, n))
        return devs

    def _pick_default_backlight(self) -> Optional[str]:
        devs = self._list_backlights()
        return devs[0] if devs else None

    def _read_brightness_values(self, dev):
        import os
        base = f"/sys/class/backlight/{dev}"
        try:
            with open(os.path.join(base, "max_brightness"), "r") as f:
                maxb = int(f.read().strip())
            with open(os.path.join(base, "brightness"), "r") as f:
                cur = int(f.read().strip())
            return cur, maxb
        except Exception:
            return None, None

    def _write_brightness_percent(self, dev, pct: int) -> bool:
        import os
        base = f"/sys/class/backlight/{dev}"
        try:
            with open(os.path.join(base, "max_brightness"), "r") as f:
                maxb = int(f.read().strip())
        except Exception:
            return False
        pct = max(10, min(100, int(pct)))
        value = int(round(pct * maxb / 100.0))
        path = os.path.join(base, "brightness")
        try:
            with open(path, "w") as f:
                f.write(str(value))
            return True
        except PermissionError:
            cmd = f"echo {value} | sudo tee {path}"
            try:
                subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except subprocess.CalledProcessError:
                return False
        except Exception:
            return False

    # ---------- helpers: system ----------
    def _repo_path(self):
        import os
        return self.settings.get("autoupdate", {}).get("repo_path", os.path.dirname(__file__))

    def _is_user_service(self, name) -> bool:
        try:
            r = subprocess.run(
                ["systemctl", "--user", "status", f"{name}.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2
            )
            return r.returncode in (0, 3)
        except Exception:
            return False

    def _is_service_running(self, name) -> bool:
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", f"{name}.service"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=3
            )
            if r.returncode == 0 and (r.stdout or "").strip() == "active":
                return True
        except Exception:
            pass
        try:
            r = subprocess.run(
                ["systemctl", "is-active", f"{name}.service"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=3
            )
            return r.returncode == 0 and (r.stdout or "").strip() == "active"
        except Exception:
            return False

    def _restart_service(self, name):
        if self._is_user_service(name):
            subprocess.run(["systemctl", "--user", "restart", f"{name}.service"], check=False)
        else:
            subprocess.run(["sudo", "systemctl", "restart", f"{name}.service"], check=False)

    def _start_service(self, name):
        if self._is_user_service(name):
            subprocess.run(["systemctl", "--user", "start", f"{name}.service"], check=False)
        else:
            subprocess.run(["sudo", "systemctl", "start", f"{name}.service"], check=False)

    def _stop_service(self, name):
        if self._is_user_service(name):
            subprocess.run(["systemctl", "--user", "stop", f"{name}.service"], check=False)
        else:
            subprocess.run(["sudo", "systemctl", "stop", f"{name}.service"], check=False)

    def _get_local_ip(self) -> str:
        if _get_local_ip_util:
            try:
                return _get_local_ip_util()
            except Exception:
                pass
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def _get_current_ssid(self) -> str:
        try:
            r = subprocess.check_output(
                ["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"],
                stderr=subprocess.DEVNULL, universal_newlines=True, timeout=4
            )
            lines = [l for l in r.splitlines() if l]
            return lines[0] if lines else "N/A"
        except Exception:
            return "N/A"

    # ---------- mqtt helpers ----------
    def _publish(self, topic, payload, qos=1, retain=False):
        if not self.client:
            return
        try:
            self.client.publish(topic, payload=payload, qos=qos, retain=retain)
        except Exception as e:
            self._log(f"Publish error {topic}: {e}", logging.ERROR)

    @staticmethod
    def _clean_topic(t: str) -> str:
        return "/".join(p for p in (t or "").split("/") if p)

    def _log(self, msg, lvl=logging.INFO):
        try:
            self.view.send_log_message(f"[MQTT] {msg}", lvl)
        except Exception:
            logging.log(lvl, f"[MQTT] {msg}")
