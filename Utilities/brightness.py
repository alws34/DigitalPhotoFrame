# utils/brightness.py
import os
import glob
import subprocess

def _which(name: str) -> str | None:
    try:
        import shutil
        return shutil.which(name)
    except Exception:
        return None

def _detect_wlr_output() -> str | None:
    """Return the focused output (or the first enabled) from wlr-randr."""
    exe = _which("wlr-randr")
    if not exe:
        return None
    try:
        out = subprocess.check_output([exe], text=True, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        return None

    current = None
    first = None
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("Outputs"):
            continue
        # Example:
        # DP-1 "LG" (focused) enabled, mode 2560x1440 @ 59.95 Hz, ...
        parts = line.split()
        name = parts[0]
        if first is None:
            first = name
        if "(focused)" in line or "enabled" in line:
            current = name
            if "(focused)" in line:
                break
    return current or first

def _set_wlr_brightness(percent: int) -> tuple[bool, str]:
    exe = _which("wlr-randr")
    if not exe:
        return False, "wlr-randr not found"
    out_name = _detect_wlr_output()
    if not out_name:
        return False, "no Wayland output found"
    # clamp 10..100 to 0.10..1.00, never 0
    pct = max(10, min(100, int(percent)))
    bri = max(0.10, min(1.00, pct / 100.0))
    try:
        subprocess.run([exe, "--output", out_name, "--brightness", f"{bri:.2f}"],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, (e.stderr or e.stdout or "wlr-randr failed").strip()
    except Exception as e:
        return False, str(e)

def _set_sysfs_brightness(percent: int) -> tuple[bool, str]:
    """Write /sys/class/backlight/*/brightness. Requires write permission."""
    try:
        dirs = sorted(glob.glob("/sys/class/backlight/*"))
        if not dirs:
            return False, "no /sys/class/backlight device"
        path = dirs[0]
        with open(os.path.join(path, "max_brightness")) as f:
            maxb = int(f.read().strip())
        target = max(1, min(maxb, int(round(maxb * (max(10, min(100, int(percent))) / 100.0)))))
        try:
            with open(os.path.join(path, "brightness"), "w") as f:
                f.write(str(target))
            return True, ""
        except PermissionError:
            return False, "permission denied writing /sys/class/backlight; add udev rule or use Wayland path"
    except Exception as e:
        return False, str(e)

def _set_xrandr_brightness(percent: int) -> tuple[bool, str]:
    exe = _which("xrandr")
    if not exe:
        return False, "xrandr not found"
    try:
        out = subprocess.check_output([exe, "--verbose"], text=True, stderr=subprocess.DEVNULL, timeout=3)
    except Exception as e:
        return False, str(e)
    name = None
    for line in out.splitlines():
        if line and not line.startswith(" "):
            name = line.split()[0]
            break
    if not name:
        return False, "no X output"
    bri = max(0.10, min(1.00, (max(10, min(100, int(percent)))) / 100.0))
    try:
        subprocess.run([exe, "--output", name, "--brightness", f"{bri:.2f}"],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, (e.stderr or e.stdout or "xrandr failed").strip()
    except Exception as e:
        return False, str(e)

def set_brightness_percent(percent: int) -> tuple[bool, str]:
    """
    Public API used by SettingsViewModel.on_apply_brightness.
    Returns (ok, error_message). Never shows any GUI dialogs.
    """
    if os.environ.get("WAYLAND_DISPLAY"):
        ok, err = _set_wlr_brightness(percent)
        if ok:
            return True, ""
        # fall through
    # Try sysfs (works for DSI panels; needs write permission)
    ok, err = _set_sysfs_brightness(percent)
    if ok:
        return True, ""
    # Finally, try X11 if running under X
    if os.environ.get("DISPLAY"):
        ok2, err2 = _set_xrandr_brightness(percent)
        if ok2:
            return True, ""
        return False, f"{err}; {err2}"
    return False, err
