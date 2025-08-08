#!/bin/bash
set -euo pipefail

APP_DIR="/home/pi/Desktop/DigitalPhotoFrame/DesktopApp"
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

echo "[0/8] Installing NetworkManager + polkit (if missing)..."
sudo apt-get update
sudo apt-get install -y network-manager policykit-1

echo "[0.1/8] Enabling NetworkManager and making sure it's running..."
sudo systemctl enable NetworkManager
sudo systemctl restart NetworkManager

echo "[0.2/8] Creating polkit rule to allow 'pi' to control Wi-Fi without sudo..."
sudo tee "$POLKIT_RULE" >/dev/null <<'EOF'
/* Allow user 'pi' to scan and connect Wi-Fi via NetworkManager without password */
polkit.addRule(function(action, subject) {
  if (subject.isInGroup("pi") || subject.user == "pi") {
    if (action.id == "org.freedesktop.NetworkManager.wifi.scan") return polkit.Result.YES;
    if (action.id == "org.freedesktop.NetworkManager.network-control") return polkit.Result.YES;
    if (action.id == "org.freedesktop.NetworkManager.settings.modify.own") return polkit.Result.YES;
  }
});
EOF

echo "[0.3/8] Reloading polkit (best effort)..."
sudo systemctl restart polkit || true

echo "[1/8] Installing OS packages required by the app..."
sudo apt-get install -y \
  python3 python3-venv python3-dev python3-tk python3-pip \
  libatlas-base-dev libopenjp2-7 libjpeg-dev zlib1g-dev \
  libxcb-render0 libxcb-shm0 libxkbcommon-x11-0 \
  libheif1 libheif-dev fonts-dejavu ca-certificates curl git

echo "[2/8] Creating virtual environment at $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

echo "[3/8] Upgrading pip/setuptools/wheel..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel

echo "[4/8] Installing Python dependencies from $REQS_FILE ..."
if [ ! -f "$REQS_FILE" ]; then
  echo "requirements.txt not found at $REQS_FILE"
  exit 1
fi
"$VENV_DIR/bin/pip" install -r "$REQS_FILE"

XAUTH_LINE=""
if [ -f "/home/pi/.Xauthority" ]; then
  XAUTH_LINE="Environment=XAUTHORITY=/home/pi/.Xauthority"
fi

echo "[5/8] Writing system service to $SERVICE_PATH ..."
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

# Wait until a display socket and user bus exist (boot-time readiness)
ExecStartPre=/bin/sh -c 'until [ -S /tmp/.X11-unix/X0 ] || [ -S /run/user/1000/wayland-0 ]; do sleep 1; done'
ExecStartPre=/bin/sh -c 'until [ -S /run/user/1000/bus ]; do sleep 1; done'

ExecStart=$PYTHON $APP_DIR/PhotoFrameDesktopApp.py
Restart=always
RestartSec=3
TimeoutStartSec=0

# Environment for GUI apps (Tk / XWayland / Wayland)
Environment=HOME=/home/pi
Environment=DISPLAY=:0
$XAUTH_LINE
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
Environment=PYTHONUNBUFFERED=1
SyslogIdentifier=photoframe
StandardOutput=journal
StandardError=journal

# Hardening (relaxed so we can still read user files under /home/pi)
NoNewPrivileges=yes
ProtectSystem=full
ProtectHome=no

[Install]
WantedBy=graphical.target
EOF

echo "[6/8] Reloading and enabling service..."
sudo systemctl daemon-reload
# ensure old symlinks (e.g., multi-user.target) are replaced with graphical.target
sudo systemctl disable "$SERVICE_NAME" || true
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo "[7/8] Status:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true

echo "[8/8] Quick nmcli self-test (no sudo):"
IFACE=$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi"{print $1; exit}')
if [ -n "$IFACE" ]; then
  echo " - Wi-Fi interface: $IFACE"
  nmcli device wifi rescan ifname "$IFACE" || echo "!!! rescan failed (polkit not active yet?)"
  nmcli -t -f IN-USE,SSID,SECURITY,SIGNAL device wifi list ifname "$IFACE" | head -n 5 || true
else
  echo "No Wi-Fi interface detected."
fi

echo "[9/8] Creating Desktop control scripts..."
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
echo "Done."
echo "Manage with:"
echo "  sudo systemctl status  $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo systemctl stop    $SERVICE_NAME"
echo
echo "Desktop scripts created:"
echo "  $START_SH"
echo "  $STOP_SH"
echo "  $RESTART_SH"
