#!/bin/bash

set -e

APP_DIR="/home/pi/Desktop/DigitalPhotoFrame/DesktopApp"
VENV_DIR="$APP_DIR/env"
SERVICE_NAME="PhotoFrame_Desktop_App"
PYTHON="$VENV_DIR/bin/python"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo "📦 Creating virtual environment..."
python3 -m venv "$VENV_DIR"

echo "📥 Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install \
    pillow \
    requests \
    numpy \
    opencv-python-headless \
    opencv-python\
    psutil\
    flask\
    flask_cors\
    watchdog\
    requests\
    pyheif\


echo "🛠 Creating systemd service..."

sudo tee "$SERVICE_PATH" > /dev/null <<EOF
[Unit]
Description=Photo Frame Desktop App
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Desktop/DigitalPhotoFrame/DesktopApp
ExecStart=/home/pi/Desktop/DigitalPhotoFrame/DesktopApp/env/bin/python /home/pi/Desktop/DigitalPhotoFrame/DesktopApp/PhotoFrameDesktopApp.py
Restart=always
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
[Install]
WantedBy=graphical.target
EOF

echo "🔄 Reloading systemd and enabling service..."
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo "✅ Starting $SERVICE_NAME service..."
sudo systemctl start "$SERVICE_NAME"

echo "🎉 Done! The photo frame should now launch at boot and be running in fullscreen."
