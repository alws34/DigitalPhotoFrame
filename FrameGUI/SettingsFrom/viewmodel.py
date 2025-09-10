from __future__ import annotations
import sys
import subprocess, threading, json, ast, os, time
from typing import Any, Dict, List, Callable, Tuple
from PySide6 import QtCore
from Utilities.network_utils import get_local_ip
import re 

def _which(name: str) -> str | None:
    try:
        import shutil
        return shutil.which(name)
    except Exception:
        return None

class SettingsViewModel(QtCore.QObject):
    # Signals used by the dialog
    statsChanged        = QtCore.Signal(str, str)             # (ssid, url)
    qrTextChanged       = QtCore.Signal(str)                  # "http://ip:port"
    networksChanged     = QtCore.Signal(list)                 # [ssid,...]
    wifiResult          = QtCore.Signal(bool, str)            # success, message
    maintStatusChanged  = QtCore.Signal(str)                  # footer text
    notificationsChanged= QtCore.Signal(list)                 # [{ts,level,text},...]
    cpuPushed           = QtCore.Signal(float)
    ramPushed           = QtCore.Signal(float)
    tempPushed          = QtCore.Signal(float)

    def __init__(
        self,
        model,
        backend_port: int,
        on_apply_brightness: Callable[[int], bool],
        on_apply_orientation: Callable[[str], bool],
        on_autoupdate_pull: Callable[[], None],
        on_restart_service_async: Callable[[], None],
        wake_screen_worker: Callable[[], None],
        notifications=None,
        parent=None,
    ):
        super().__init__(parent)
        self.model = model
        self.backend_port = backend_port
        self._apply_brightness_cb = on_apply_brightness
        self._apply_orientation_cb= on_apply_orientation
        self._pull_cb             = on_autoupdate_pull
        self._restart_cb          = on_restart_service_async
        self._wake                = wake_screen_worker
        self._notifications       = notifications

    # ---------- Initialization ----------
    def prime(self) -> None:
        ip = get_local_ip()
        ssid = self._get_current_ssid()
        self.statsChanged.emit(ssid, f"http://{ip}:{self.backend_port}")
        self.qrTextChanged.emit(f"http://{ip}:{self.backend_port}")

    # ---------- Maintenance ----------
    def pull_updates(self) -> None:
        self.maintStatusChanged.emit("Pulling updates...")
        def worker():
            ok, err = True, ""
            try:
                self._pull_cb()
            except Exception as e:
                ok, err = False, str(e)
            self.maintStatusChanged.emit("Updates pulled ✓" if ok else f"Update failed: {err}")
        threading.Thread(target=worker, daemon=True).start()

    def restart_service(self) -> None:
        self.maintStatusChanged.emit("Restarting service...")
        def worker():
            ok, err = True, ""
            try:
                self._restart_cb()
            except Exception as e:
                ok, err = False, str(e)
            self.maintStatusChanged.emit("Restart requested ✓" if ok else f"Restart failed: {err}")
        threading.Thread(target=worker, daemon=True).start()

    # ---------- Wi-Fi ----------
    def scan_wifi(self) -> None:
        def worker():
            try:
                if sys.platform.startswith("linux") and _which("nmcli"):
                    ssids = self._scan_wifi_nmcli()
                elif sys.platform == "darwin":
                    ssids = self._scan_wifi_airport()
                else:
                    ssids = []
            except Exception:
                ssids = []
            self.networksChanged.emit(ssids)
        threading.Thread(target=worker, daemon=True).start()

    def connect_wifi(self, ssid: str, password: str) -> None:
        def worker():
            if not ssid:
                self.wifiResult.emit(False, "Please select a network.")
                return
            try:
                if sys.platform.startswith("linux") and _which("nmcli"):
                    ok, msg = self._connect_wifi_nmcli(ssid, password)
                elif sys.platform == "darwin":
                    ok, msg = self._connect_wifi_mac(ssid, password)
                else:
                    ok, msg = False, "Unsupported platform for Wi-Fi connect."
            except Exception as e:
                ok, msg = False, str(e)

            if ok:
                ip = get_local_ip()
                self.statsChanged.emit(ssid, f"http://{ip}:{self.backend_port}")
                self.qrTextChanged.emit(f"http://{ip}:{self.backend_port}")
            self.wifiResult.emit(ok, msg)
        threading.Thread(target=worker, daemon=True).start()

    # ---------- Linux helpers (nmcli) ----------
    def _scan_wifi_nmcli(self) -> list[str]:
        nm = _which("nmcli") or "/usr/bin/nmcli"
        try:
            subprocess.run([nm, "device", "wifi", "rescan"],
                        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
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
            inuse, ssid, sec, sigs = (line.split(":") + ["","","",""])[:4]
            if not ssid:
                continue
            try: sig = int(sigs)
            except: sig = -1
            rows.append((ssid, sig))
        best = {}
        for ssid, sig in rows:
            if ssid and (ssid not in best or sig > best[ssid]):
                best[ssid] = sig
        return [k for k,_ in sorted(best.items(), key=lambda kv: -kv[1])]

    def _connect_wifi_nmcli(self, ssid: str, password: str) -> tuple[bool,str]:
        nm = _which("nmcli") or "nmcli"
        # pick wifi iface
        try:
            out = subprocess.check_output(
                [nm, "-t", "-f", "DEVICE,TYPE,STATE", "device"],
                universal_newlines=True, stderr=subprocess.DEVNULL, timeout=5
            )
            cands = []
            for line in out.splitlines():
                dev, typ, state = (line.split(":") + ["","",""])[:3]
                if typ == "wifi":
                    prio = 0 if state == "connected" else (1 if state == "disconnected" else 2)
                    cands.append((prio, dev))
            cands.sort()
            iface = cands[0][1] if cands else None
        except Exception:
            iface = None
        if not iface:
            return False, "No Wi-Fi interface found."

        try:
            subprocess.run([nm, "radio", "wifi", "on"], check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass

        # discover security to know if password is required
        try:
            scan_out = subprocess.check_output(
                [nm, "-t", "-f", "SSID,SECURITY", "device", "wifi", "list", "ifname", iface],
                universal_newlines=True, stderr=subprocess.DEVNULL, timeout=10
            )
            sec_map = {}
            for line in scan_out.splitlines():
                nm_ssid, nm_sec = (line.split(":") + ["",""])[:2]
                if nm_ssid:
                    sec_map[nm_ssid] = nm_sec
            nm_sec = sec_map.get(ssid, "")
            is_open = (nm_sec == "" or nm_sec == "--")
            hidden_flag = [] if ssid in sec_map else ["hidden", "yes"]
        except Exception:
            is_open = False
            hidden_flag = ["hidden", "yes"]

        if not is_open and not password:
            return False, "Password is required."

        cmd = [nm, "-w", "30", "device", "wifi", "connect", ssid, "ifname", iface] + hidden_flag
        if not is_open:
            cmd += ["password", password]
        try:
            res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=60)
            return True, (res.stdout.strip() or "Connected")
        except subprocess.CalledProcessError as e:
            return False, (e.stdout or "") + "\n" + (e.stderr or "")

    # ---------- macOS helpers ----------
    def _scan_wifi_airport(self) -> list[str]:
        airport = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
        if not os.path.exists(airport):
            return []
        out = subprocess.check_output([airport, "-s"], text=True, stderr=subprocess.DEVNULL, timeout=8)
        rows = []
        for line in out.splitlines()[1:]:
            parts = re.split(r"\s{2,}", line.rstrip())
            if not parts: 
                continue
            ssid = parts[0]
            try:
                rssi = int(parts[2]) if len(parts) > 2 else -999
            except Exception:
                rssi = -999
            rows.append((ssid, rssi))
        best = {}
        for ssid, rssi in rows:
            if ssid and (ssid not in best or rssi > best[ssid]):
                best[ssid] = rssi
        return [k for k,_ in sorted(best.items(), key=lambda kv: -kv[1])]

    def _connect_wifi_mac(self, ssid: str, password: str) -> tuple[bool,str]:
        ns = "/usr/sbin/networksetup"
        if not os.path.exists(ns):
            return False, "networksetup tool not found."
        # find Wi-Fi device (usually en0)
        try:
            out = subprocess.check_output([ns, "-listallhardwareports"], text=True)
            device = None
            port_lines = out.splitlines()
            for i, line in enumerate(port_lines):
                if "Hardware Port: Wi-Fi" in line or "Hardware Port: AirPort" in line:
                    # next lines contain "Device: enX"
                    for j in range(i+1, min(i+4, len(port_lines))):
                        if "Device:" in port_lines[j]:
                            device = port_lines[j].split("Device:")[1].strip()
                            break
                    if device:
                        break
            if not device:
                device = "en0"
        except Exception:
            device = "en0"

        try:
            subprocess.run([ns, "-setairportpower", device, "on"],
                        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass

        # open network: omit password
        cmd = [ns, "-setairportnetwork", device, ssid] + ([password] if password else [])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return True, (r.stdout.strip() or "Connected")
            return False, (r.stdout + "\n" + r.stderr).strip() or "Failed to connect"
        except Exception as e:
            return False, str(e)


    # ---------- Screen ----------
    def apply_brightness(self, pct: int) -> None:
        pct = max(10, min(100, int(pct)))
        ok, err = False, ""
        try:
            res = self._apply_brightness_cb(pct)
            if isinstance(res, tuple) and len(res) >= 1:
                ok = bool(res[0])
                err = str(res[1]) if len(res) > 1 and res[1] is not None else ""
            else:
                ok = bool(res)
        except Exception as e:
            ok, err = False, str(e)

        if ok:
            scr = self.model.ensure_screen_struct()
            scr["brightness"] = pct
            self.model.save()
            self._wake()
            self.maintStatusChanged.emit(f"Brightness set to {pct}%")
        else:
            self.maintStatusChanged.emit(f"Brightness error: {err or 'operation failed'}")


    def apply_orientation(self, value: str) -> None:
        if self._apply_orientation_cb(value):
            scr = self.model.ensure_screen_struct()
            scr["orientation"] = value
            self.model.save()

    def set_schedules(self, schedules: List[Dict[str, Any]]) -> None:
        scr = self.model.ensure_screen_struct()
        scr["schedules"] = schedules
        self.model.mirror_first_enabled_schedule_to_legacy()
        self.model.save()
        self._wake()

    # ---------- Notifications ----------
    def refresh_notifications(self) -> None:
        if not self._notifications:
            self.notificationsChanged.emit([])
            return
        try:
            items = self._notifications.list()
        except Exception:
            items = []
        self.notificationsChanged.emit(items)

    def clear_notifications(self) -> None:
        try:
            if self._notifications:
                self._notifications.clear()
        except Exception:
            pass
        self.refresh_notifications()

    # ---------- Stats (optional psutil loop) ----------
    def start_local_stats(self, interval_ms: int = 1000) -> None:
        try:
            import psutil  # type: ignore

            # One-time prime with a small interval so the first value is meaningful.
            try:
                psutil.cpu_percent(interval=0.15)
            except Exception:
                pass

            self._psutil = psutil  # cache
            self._stats_timer = QtCore.QTimer(self)
            self._stats_timer.timeout.connect(self._push_stats)
            self._stats_timer.start(max(250, int(interval_ms)))
        except Exception:
            # Lightweight fallback if psutil is missing
            self._psutil = None
            self._stats_timer = QtCore.QTimer(self)
            self._stats_timer.timeout.connect(self._push_stats_fallback)
            self._stats_timer.start(max(250, int(interval_ms)))


    def _read_cpu_temp_c(self) -> float:
        """
        Try psutil first with common RPi/Linux keys, then sysfs thermal zones.
        Returns temperature in C, or 0.0 if unavailable.
        """
        # psutil path
        try:
            if getattr(self, "_psutil", None):
                temps = self._psutil.sensors_temperatures()
                # Common keys on Pi and SBCs
                for key in ("cpu-thermal", "cpu_thermal", "coretemp", "k10temp", "soc_thermal"):
                    if key in temps and temps[key]:
                        cur = getattr(temps[key][0], "current", None)
                        if cur is not None:
                            return float(cur)
                # Fallback: first reading in any group
                for arr in temps.values():
                    if arr:
                        cur = getattr(arr[0], "current", None)
                        if cur is not None:
                            return float(cur)
        except Exception:
            pass

        # sysfs path
        try:
            import glob
            for zpath in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
                # Read the type to prefer CPU-like zones
                try:
                    tpath = zpath.replace("/temp", "/type")
                    tname = ""
                    with open(tpath, "r") as tf:
                        tname = tf.read().strip().lower()
                    if "cpu" not in tname and "soc" not in tname and "arm" not in tname:
                        continue
                except Exception:
                    pass
                with open(zpath, "r") as f:
                    raw = f.read().strip()
                # Most kernels expose millidegrees C
                val = float(raw) / (1000.0 if len(raw) > 3 else 1.0)
                if val > 0.0:
                    return val
        except Exception:
            pass

        return 0.0


    def _push_stats(self):
        try:
            if getattr(self, "_psutil", None) is None:
                return  # psutil not available; fallback timer handles updates

            psutil = self._psutil

            # CPU percent since last call (no re-priming here!)
            cpu = float(psutil.cpu_percent(interval=None))

            # RAM percent
            ram = float(psutil.virtual_memory().percent)

            # Temperature
            temp = float(self._read_cpu_temp_c())

            self.cpuPushed.emit(cpu)
            self.ramPushed.emit(ram)
            self.tempPushed.emit(temp)
        except Exception:
            # Never let stats crash the UI loop
            pass

    def _push_stats_fallback(self):
        try:
            import os
            cpu_pct = 0.0
            ncpu = os.cpu_count() or 1
            if hasattr(os, "getloadavg"):
                cpu_pct = max(0.0, min(100.0, (os.getloadavg()[0] / float(ncpu)) * 100.0))

            # RAM %
            ram_pct = 0.0
            if sys.platform == "darwin":
                out = subprocess.check_output(["vm_stat"], text=True)
                kv = dict(re.findall(r"^(.+?):\s+(\d+)\.", out, flags=re.M))
                pages = {k: int(v) for k, v in kv.items()}
                page_sz = int(subprocess.check_output(["sysctl","-n","hw.pagesize"], text=True).strip())
                free = (pages.get("Pages free",0) + pages.get("Pages speculative",0)) * page_sz
                used = (pages.get("Pages active",0) + pages.get("Pages wired down",0) + pages.get("Pages occupied by compressor",0)) * page_sz
                total = free + used
                ram_pct = (used / total * 100.0) if total else 0.0
            elif sys.platform.startswith("linux"):
                with open("/proc/meminfo") as f:
                    info = {}
                    for line in f:
                        k, v = line.split(":", 1)
                        info[k] = int(v.strip().split()[0])  # kB
                total = info.get("MemTotal", 0)
                avail = info.get("MemAvailable", info.get("MemFree", 0))
                used = total - avail
                ram_pct = (used / total * 100.0) if total else 0.0

            self.cpuPushed.emit(float(cpu_pct))
            self.ramPushed.emit(float(ram_pct))
            self.tempPushed.emit(0.0)  # no simple cross-platform sensor
        except Exception:
            pass

    # ---------- helpers ----------
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
