#!/bin/bash
set -euo pipefail

APP_DIR="/home/pi/Desktop/DigitalPhotoFrame"
ROOT_DIR="/home/pi/Desktop/DigitalPhotoFrame"
REQS_FILE="$ROOT_DIR/requirements.txt"
VENV_DIR="$APP_DIR/env"
PYTHON="$VENV_DIR/bin/python"
SERVICE_NAME="PhotoFrame_Desktop_App"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
POLKIT_RULE="/etc/polkit-1/rules.d/45-allow-nm-wifi-for-pi.rules"
DESKTOP_DIR="/home/pi/Desktop"
START_SH="$DESKTOP_DIR/StartPhotoFrame.sh"
STOP_SH="$DESKTOP_DIR/StopPhotoFrame.sh"
RESTART_SH="$DESKTOP_DIR/RestartPhotoFrame.sh"
UDEV_BACKLIGHT_RULE="/etc/udev/rules.d/90-backlight.rules"

echo "[0/10] Installing NetworkManager + polkit (if missing)..."
sudo apt-get update
sudo apt-get install -y network-manager policykit-1

echo "[0.1/10] Enabling NetworkManager and making sure it's running..."
sudo systemctl enable NetworkManager
sudo systemctl restart NetworkManager

echo "[0.2/10] Creating polkit rule to allow members of 'netdev' to manage Wi-Fi without sudo..."
sudo tee "$POLKIT_RULE" >/dev/null <<'EOF'
/* Allow Wi-Fi scan/connect and system connection changes for netdev group */
polkit.addRule(function(action, subject) {
  if (subject.isInGroup("netdev")) {
    switch (action.id) {
      case "org.freedesktop.NetworkManager.wifi.scan":
      case "org.freedesktop.NetworkManager.enable-disable-wifi":
      case "org.freedesktop.NetworkManager.network-control":
      case "org.freedesktop.NetworkManager.settings.modify.system":
      case "org.freedesktop.NetworkManager.wifi.share.open":
      case "org.freedesktop.NetworkManager.wifi.share.protected":
        return polkit.Result.YES;
    }
  }
});
EOF

echo "[0.21/10] Adding 'pi' to netdev and video groups (video needed for backlight)..."
sudo usermod -aG netdev pi
sudo usermod -aG video pi

echo "[0.3/10] Reloading polkit (best effort)..."
sudo systemctl restart polkit || true

echo "[1/10] Installing OS packages required by the app..."
sudo apt-get install -y \
  python3 python3-venv python3-dev python3-tk python3-pip \
  libatlas-base-dev libopenjp2-7 libjpeg-dev zlib1g-dev \
  libxcb-render0 libxcb-shm0 libxkbcommon-x11-0 libxcb-cursor0 \
  libheif1 libheif-dev fonts-dejavu ca-certificates curl git \
  wlr-randr

echo "[1.1/10] Installing Qt Wayland runtime bits..."
sudo apt-get install -y \
  qt6-wayland qt6-qpa-plugins qt6-gtk-platformtheme \
  fonts-dejavu fonts-liberation

echo "[1.2/10] Applying udev rule for backlight write access (sysfs fallback path)..."
sudo tee "$UDEV_BACKLIGHT_RULE" >/dev/null <<'EOF'
# Make backlight writable by the 'video' group for non-root user sessions
SUBSYSTEM=="backlight", GROUP="video", MODE="0664"
EOF

echo "[1.3/10] Reloading udev rules and triggering backlight..."
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=backlight || true

echo "[2/10] Creating virtual environment at $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

echo "[3/10] Upgrading pip/setuptools/wheel..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel

echo "[4/10] Installing Python dependencies from $REQS_FILE ..."
if [ ! -f "$REQS_FILE" ]; then
  echo "requirements.txt not found at $REQS_FILE"
  exit 1
fi
"$VENV_DIR/bin/pip" install -r "$REQS_FILE"

XAUTH_LINE=""
if [ -f "/home/pi/.Xauthority" ]; then
  XAUTH_LINE="Environment=XAUTHORITY=/home/pi/.Xauthority"
fi

echo "[5/10] Writing system service to $SERVICE_PATH ..."
sudo tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=Photo Frame Desktop App (system-wide)
Wants=network-online.target user@1000.service
After=network-online.target systemd-user-sessions.service user@1000.service

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=$APP_DIR

# Wait until Wayland socket and user bus exist
ExecStartPre=/bin/sh -c 'until [ -S /run/user/1000/wayland-0 ]; do sleep 1; done'
ExecStartPre=/bin/sh -c 'until [ -S /run/user/1000/bus ]; do sleep 1; done'

# Launch
ExecStart=$PYTHON $APP_DIR/app.py

Restart=always
RestartSec=3
TimeoutStartSec=0

# GUI env for Wayland
Environment=HOME=/home/pi
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
Environment=WAYLAND_DISPLAY=wayland-0
Environment=QT_QPA_PLATFORM=wayland

# Prevent broken themes from forcing black-on-black palettes
Environment=QT_QPA_PLATFORMTHEME=
Environment=QT_STYLE_OVERRIDE=

# Reasonable DPI defaults
Environment=QT_AUTO_SCREEN_SCALE_FACTOR=1
Environment=QT_ENABLE_HIGHDPI_SCALING=1

# Optional: silence benign Wayland warnings in journal
Environment=QT_LOGGING_RULES=qt.qpa.wayland.warning=false

# Logging
SyslogIdentifier=photoframe
StandardOutput=journal
StandardError=journal

# Security model (unchanged)
NoNewPrivileges=no
ProtectSystem=off
ProtectHome=no
CapabilityBoundingSet=CAP_CHOWN CAP_FOWNER CAP_DAC_OVERRIDE
AmbientCapabilities=CAP_CHOWN CAP_FOWNER CAP_DAC_OVERRIDE
UMask=002
EOF

echo "[5.1/10] Adding polkit rule for service restarts..."
sudo tee /etc/polkit-1/rules.d/46-allow-photoframe-restart.rules >/dev/null <<'EOF'
/* Allow pi to manage ONLY PhotoFrame_Desktop_App.service */
polkit.addRule(function(action, subject) {
  if (action.id == "org.freedesktop.systemd1.manage-units" &&
      subject.user == "pi") {
    var unit = action.lookup("unit");
    var verb = action.lookup("verb");
    var okVerbs = ["start", "stop", "restart", "reload"];
    if (unit == "PhotoFrame_Desktop_App.service" &&
        okVerbs.indexOf(verb) >= 0) {
      return polkit.Result.YES;
    }
  }
});
EOF

echo "[5.2/10] Reloading polkit..."
sudo systemctl restart polkit || true

echo "[6/10] Reloading and enabling service..."
sudo systemctl daemon-reload
sudo systemctl disable "$SERVICE_NAME" || true
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo "[7/10] Status:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true

echo "[8/10] Quick runtime self-tests (no sudo)..."

# Wi-Fi nmcli smoke test
IFACE=$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi"{print $1; exit}')
if [ -n "\$IFACE" ]; then
  echo " - Wi-Fi interface: \$IFACE"
  nmcli device wifi rescan ifname "\$IFACE" || echo "!!! rescan failed (polkit not active yet?)"
  nmcli -t -f IN-USE,SSID,SECURITY,SIGNAL device wifi list ifname "\$IFACE" | head -n 5 || true
else
  echo "No Wi-Fi interface detected."
fi

# Brightness path tests (non-fatal)
if [ -n "\$WAYLAND_DISPLAY" ] || [ -S /run/user/1000/wayland-0 ]; then
  echo " - Wayland detected, wlr-randr present? $(command -v wlr-randr || echo 'no')"
  if command -v wlr-randr >/dev/null 2>&1; then
    echo "   Outputs:"
    wlr-randr || true
  fi
fi

if ls /sys/class/backlight/*/brightness >/dev/null 2>&1; then
  echo " - Backlight sysfs present. Permissions:"
  ls -l /sys/class/backlight/*/brightness || true
else
  echo " - No /sys/class/backlight device (likely external monitor via HDMI/DP)."
fi

echo "[9/10] Creating Desktop control scripts..."
mkdir -p "$DESKTOP_DIR"

cat > "$START_SH" <<EOSTART
#!/bin/bash
set -e
echo "Starting $SERVICE_NAME..."
sudo systemctl start "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager -l | sed -n '1,10p' || true
EOSTART

cat > "$STOP_SH" <<EOSTOP
#!/bin/bash
set -e
echo "Stopping $SERVICE_NAME..."
sudo systemctl stop "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager -l | sed -n '1,10p' || true
EOSTOP

cat > "$RESTART_SH" <<EORESTART
#!/bin/bash
set -e
echo "Restarting $SERVICE_NAME..."
sudo systemctl restart "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager -l | sed -n '1,10p' || true
EORESTART

chmod +x "$START_SH" "$STOP_SH" "$RESTART_SH"

echo
echo "[10/10] Done."
echo "Manage with:"
echo "  sudo systemctl status  $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo systemctl stop    $SERVICE_NAME"
echo
echo "Desktop scripts created:"
echo "  $START_SH"
echo "  $STOP_SH"
echo "  $RESTART_SH"
echo
echo "Notes:"
echo " - Brightness uses Wayland (wlr-randr) when available."
echo " - Sysfs fallback works if /sys/class/backlight exists and 'pi' is in the 'video' group (rule installed)."
