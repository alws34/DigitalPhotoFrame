import logging
import subprocess
import shutil
import sys
from typing import Optional

class HardwareManager:
    """
    Handles hardware interactions like screen orientation and brightness.
    """
    @staticmethod
    def list_outputs() -> list[str]:
        try:
            out = subprocess.check_output(
                ["wlr-randr"], universal_newlines=True,
                stderr=subprocess.DEVNULL, timeout=3
            )
        except Exception:
            return []
        names: list[str] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith(" "):
                continue
            name = line.split()[0]
            if name not in names:
                names.append(name)
        return names

    @staticmethod
    def pick_default_output() -> Optional[str]:
        outs = HardwareManager.list_outputs()
        outs.sort(key=lambda n: (0 if n.upper().startswith("DSI") else 1, n))
        return outs[0] if outs else None

    @staticmethod
    def apply_orientation(transform: str) -> bool:
        """
        On Linux/Wayland, call wlr-randr to rotate the display.
        On other platforms this is a no-op so the app runs everywhere.
        """
        if sys.platform != "linux":
            logging.info("Orientation change (%s) ignored on non-Linux platform.", transform)
            return True

        if shutil.which("wlr-randr") is None:
            logging.warning("wlr-randr not found in PATH; skipping orientation change.")
            return True

        output = HardwareManager.pick_default_output()
        if not output:
            logging.warning("No Wayland outputs reported by wlr-randr; skipping orientation change.")
            return True

        try:
            subprocess.run(
                ["wlr-randr", "--output", output, "--transform", transform],
                check=True,
            )
            logging.info("Orientation set to %s on output %s", transform, output)
            return True
        except subprocess.CalledProcessError as e:
            logging.exception("Failed to set orientation via wlr-randr: %s", e)
            return False

    @staticmethod
    def apply_brightness(screen_ctrl, pct: int) -> bool:
        """
        Applies brightness using the provided screen controller.
        """
        try:
            pct = max(10, min(100, int(pct)))
            if not screen_ctrl or not hasattr(screen_ctrl, "set_brightness_percent") or not callable(screen_ctrl.set_brightness_percent):
                return False
            ok = screen_ctrl.set_brightness_percent(pct, allow_zero=False)
            return bool(ok)
        except Exception as e:
            logging.error("Brightness error: %s", str(e))
            return False
