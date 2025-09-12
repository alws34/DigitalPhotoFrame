
import subprocess
from typing import Optional, TYPE_CHECKING
from PySide6 import QtCore

class ScreenScheduler(QtCore.QObject):
    """
    Periodically evaluates settings['screen']['schedules'] and toggles the panel.
    Uses screen_ctrl.sleep()/wake() when available, else wlr-randr off/on.
    """
    stateChanged = QtCore.Signal(bool)  # True=OFF(asleep), False=ON(awake)

    def __init__(self, owner: "PhotoFrameQtWidget", interval_ms: int = 30000):
        super().__init__(owner)
        self._owner = owner
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(max(5000, int(interval_ms)))
        self._is_off: Optional[bool] = None  # unknown at start

        # do an immediate evaluation shortly after start
        QtCore.QTimer.singleShot(1000, self._tick)

    # ---------- core evaluation ----------
    def _tick(self) -> None:
        try:
            scr = (self._owner.settings or {}).get("screen", {}) or {}
            now = QtCore.QDateTime.currentDateTime()
            should_off = self._should_be_off(scr, now)
        except Exception:
            # fail safe: keep current state
            return

        if self._is_off is None or bool(should_off) != bool(self._is_off):
            self._apply(should_off)

    @staticmethod
    def _hour_in_window(hour: int, off_h: int, on_h: int) -> bool:
        # Normalize
        hour = int(hour) % 24
        off_h = int(off_h) % 24
        on_h  = int(on_h) % 24
        if off_h == on_h:
            return False  # degenerate => disabled
        if off_h < on_h:
            # Same-day window: [off_h, on_h)
            return off_h <= hour < on_h
        # Overnight window: [off_h..23] U [0..on_h)
        return hour >= off_h or hour < on_h

    def _should_be_off(self, scr: dict, now: QtCore.QDateTime) -> bool:
        # Prefer multi-schedule. If none enabled, honor legacy fields.
        wd = now.date().dayOfWeek() % 7  # Qt: Mon=1..Sun=7, convert to 0..6
        hour = now.time().hour()

        schedules = scr.get("schedules", [])
        any_enabled = False
        for item in schedules if isinstance(schedules, list) else []:
            if not item or not item.get("enabled"):
                continue
            any_enabled = True
            days = item.get("days", [0,1,2,3,4,5,6])
            if wd not in {int(d) % 7 for d in days}:
                continue
            off_h = item.get("off_hour", scr.get("off_hour", 0))
            on_h  = item.get("on_hour",  scr.get("on_hour", 7))
            if self._hour_in_window(hour, off_h, on_h):
                return True

        if not any_enabled and scr.get("schedule_enabled", False):
            # Legacy single window, every day
            off_h = scr.get("off_hour", 0)
            on_h  = scr.get("on_hour", 7)
            return self._hour_in_window(hour, off_h, on_h)

        return False

    # ---------- actuation ----------
    def _apply(self, off: bool) -> None:
        self._is_off = bool(off)

        if off:
            if getattr(self._owner, "screen_ctrl", None) and hasattr(self._owner.screen_ctrl, "sleep"):
                try:
                    self._owner.screen_ctrl.sleep()
                except Exception:
                    self._fallback_dpms(False)  # False means "turn off output"
            else:
                self._fallback_dpms(False)
        else:
            if getattr(self._owner, "screen_ctrl", None) and hasattr(self._owner.screen_ctrl, "wake"):
                try:
                    self._owner.screen_ctrl.wake()
                except Exception:
                    self._fallback_dpms(True)   # True means "turn on output"
            else:
                self._fallback_dpms(True)

        self.stateChanged.emit(self._is_off)

    def _fallback_dpms(self, on: bool) -> None:
        """
        Last-resort using wlr-randr on Wayland. No-ops if not available.
        """
        try:
            output = self._owner._pick_default_output()
            if not output:
                return
            cmd = ["wlr-randr", "--output", output, "--on" if on else "--off"]
            subprocess.run(cmd, timeout=5, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    # public surface if you want to retrigger after settings changes
    def recheck_now(self) -> None:
        QtCore.QTimer.singleShot(0, self._tick)
