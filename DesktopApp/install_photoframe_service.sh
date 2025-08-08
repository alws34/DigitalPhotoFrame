#!/bin/bash
set -euo pipefail

APP_DIR="/home/pi/Desktop/DigitalPhotoFrame/DesktopApp"
ROOT_DIR="/home/pi/Desktop/DigitalPhotoFrame"
REQS_FILE="$ROOT_DIR/requirements.txt"
VENV_DIR="$APP_DIR/env"
SERVICE_NAME="PhotoFrame_Desktop_App"
PYTHON="$VENV_DIR/bin/python"
USER_SERVICE_DIR="/home/pi/.config/systemd/user"
SERVICE_PATH="$USER_SERVICE_DIR/${SERVICE_NAME}.service"
DESKTOP_SCRIPT="/home/pi/Desktop/StartPhotoFrame.sh"

echo "[1/7] Updating apt and installing system packages..."
sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-pip \
  python3-venv \
  python3-dev \
  python3-tk \
  libatlas-base-dev \
  libopenjp2-7 \
  libjpeg-dev \
  zlib1g-dev \
  libxcb-render0 \
  libxcb-shm0 \
  libxkbcommon-x11-0 \
  libheif1 \
  libheif-dev \
  fonts-dejavu \
  ca-certificates \
  curl \
  git

echo "[2/7] Creating virtual environment at $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

echo "[3/7] Upgrading pip/setuptools/wheel..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel

echo "[4/7] Installing Python dependencies from $REQS_FILE ..."
if [ ! -f "$REQS_FILE" ]; then
  echo "requirements.txt not found at $REQS_FILE"
  exit 1
fi
# Use piwheels automatically on RPi; just install the file as-is
"$VENV_DIR/bin/pip" install -r "$REQS_FILE"

# Optional: pin opencv headless if GUI-less; your app uses Tkinter and ImageTk, so keep default
# If you ever get QT-related import issues, prefer headless:
# "$VENV_DIR/bin/pip" install --upgrade opencv-python-headless

echo "[5/7] Creating user systemd service..."
mkdir -p "$USER_SERVICE_DIR"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Photo Frame Desktop App (User)
Wants=graphical-session.target
After=graphical-session.target network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON $APP_DIR/PhotoFrameDesktopApp.py
Restart=always
RestartSec=3
# Wayland/X11 env so Tkinter can display
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
Environment=XDG_RUNTIME_DIR=/run/user/1000
# Unbuffered logs
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

echo "[6/7] Enabling user service..."
# Allow user services to run at boot without login
if ! loginctl show-user pi | grep -q "Linger=yes"; then
  sudo loginctl enable-linger pi
fi

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"

echo "[7/7] Creating Desktop launcher script at $DESKTOP_SCRIPT ..."
cat > "$DESKTOP_SCRIPT" <<'EOL'
#!/bin/bash
SERVICE_NAME="PhotoFrame_Desktop_App"
if systemctl --user is-active --quiet "$SERVICE_NAME"; then
  echo "PhotoFrame is already running."
else
  systemctl --user start "$SERVICE_NAME"
  echo "Starting PhotoFrame service..."
fi
EOL
chmod +x "$DESKTOP_SCRIPT"

echo "Done. Service: $SERVICE_NAME"
echo "Manage with: systemctl --user status|start|stop $SERVICE_NAME"
