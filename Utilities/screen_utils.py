import os
import time
import logging
import threading
import subprocess
from typing import Dict, Optional, Tuple


class ScreenController:
    def __init__(self, settings: Dict, stop_event: threading.Event) -> None:
        self._settings = settings
        self._stop = stop_event
        self._state = "unknown"
        self._event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # Public API
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def wake(self) -> None:
        self._event.set()

    def set_brightness_percent(self, percent: int, allow_zero: bool = False) -> bool:
        dev = self._pick_default_backlight()
        if not dev:
            return False
        return self._set_brightness_percent(dev, percent, allow_zero=allow_zero)

    # Internal scheduling
    def _screen_cfg(self) -> Dict:
        scr = self._settings.setdefault("screen", {})
        scr.setdefault("orientation", "normal")
        scr.setdefault("brightness", 100)
        scr.setdefault("schedule_enabled", False)
        scr.setdefault("off_hour", 0)
        scr.setdefault("on_hour", 7)
        return scr

    def _worker(self) -> None:
        last_user_brightness = None
        ev = self._event

        while not self._stop.is_set():
            try:
                scr = self._screen_cfg()
                enabled = bool(scr.get("schedule_enabled", False))
                off_h = int(scr.get("off_hour", 0)) % 24
                on_h = int(scr.get("on_hour", 7)) % 24
                now_h = self._hour_now()

                desired = "off" if (enabled and self._in_off_period(now_h, off_h, on_h)) else "on"

                dev = self._pick_default_backlight()
                if not dev:
                    if ev.wait(timeout=30.0):
                        ev.clear()
                    continue

                cur, maxb = self._read_brightness(dev)
                cur_pct = int(round(cur * 100.0 / maxb)) if (cur is not None and maxb) else None

                if desired == "off" and self._state != "off":
                    last_user_brightness = cur_pct if cur_pct is not None else int(scr.get("brightness", 100))
                    self._set_brightness_percent(dev, 0, allow_zero=True)
                    self._state = "off"

                elif desired == "on" and self._state != "on":
                    restore = int(scr.get("brightness", 100))
                    restore = max(10, min(100, restore))
                    self._set_brightness_percent(dev, restore, allow_zero=False)
                    self._state = "on"

            except Exception:
                logging.exception("screen worker tick failed")

            if ev.wait(timeout=30.0):
                ev.clear()

    # Helpers
    @staticmethod
    def _hour_now() -> int:
        try:
            return int(time.strftime("%H"))
        except Exception:
            return 0

    @staticmethod
    def _in_off_period(now_h: int, off_h: int, on_h: int) -> bool:
        now_h %= 24; off_h %= 24; on_h %= 24
        if off_h == on_h:
            return False
        if off_h < on_h:
            return off_h <= now_h < on_h
        return now_h >= off_h or now_h < on_h

    @staticmethod
    def _list_backlights() -> list:
        base = "/sys/class/backlight"
        if not os.path.isdir(base):
            return []
        devs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
        devs.sort(key=lambda n: (0 if n.startswith("rpi") or "rpi_backlight" in n or "raspberry" in n else 1, n))
        return devs

    def _pick_default_backlight(self) -> Optional[str]:
        bls = self._list_backlights()
        return bls[0] if bls else None

    @staticmethod
    def _read_brightness(dev: str) -> Tuple[Optional[int], Optional[int]]:
        base = os.path.join("/sys/class/backlight", dev)
        try:
            with open(os.path.join(base, "max_brightness"), "r") as f:
                maxb = int(f.read().strip())
            with open(os.path.join(base, "brightness"), "r") as f:
                cur = int(f.read().strip())
            return cur, maxb
        except Exception:
            return None, None

    @staticmethod
    def _write_brightness_value(dev: str, value: int) -> bool:
        base = os.path.join("/sys/class/backlight", dev)
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

    def _set_brightness_percent(self, dev: str, percent: int, allow_zero: bool = False) -> bool:
        percent = int(percent)
        percent = max(0 if allow_zero else 10, min(100, percent))
        cur, maxb = self._read_brightness(dev)
        if maxb in (None, 0):
            return False
        value = 0 if percent == 0 else int(round(percent * maxb / 100.0))
        value = min(maxb, value)
        return self._write_brightness_value(dev, value)
