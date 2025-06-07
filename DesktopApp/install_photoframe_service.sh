#!/bin/bash
set -e

APP_DIR="/home/pi/Desktop/DigitalPhotoFrame/DesktopApp"
VENV_DIR="$APP_DIR/env"
SERVICE_NAME="PhotoFrame_Desktop_App"
PYTHON="$VENV_DIR/bin/python"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
DESKTOP_SCRIPT="/home/pi/Desktop/StartPhotoFrame.sh"

echo "📦 Creating virtual environment..."
python3 -m venv "$VENV_DIR"

echo "📥 Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install \
    pillow \
    requests \
    numpy \
    opencv-python-headless \
    opencv-python \
    psutil \
    flask \
    flask_cors \
    watchdog \
    pyheif

echo "🛠 Creating systemd service..."
sudo tee "$SERVICE_PATH" > /dev/null <<EOF
[Unit]
Description=Photo Frame Desktop App
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON $APP_DIR/PhotoFrameDesktopApp.py
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
sudo systemctl start "$SERVICE_NAME"

echo "📄 Creating Desktop launcher script at $DESKTOP_SCRIPT..."
cat > "$DESKTOP_SCRIPT" <<EOL
#!/bin/bash
# Launcher for PhotoFrame Desktop App
# Starts the systemd service
if systemctl --user is-active --quiet "$SERVICE_NAME"; then
    echo "PhotoFrame is already running."
else
    systemctl --user start "$SERVICE_NAME"
    echo "Starting PhotoFrame service..."
fi
EOL

sudo chmod +x "$DESKTOP_SCRIPT"
echo "✅ Launcher created and made executable."

echo "🎉 Done! The photo frame service is installed and you can start it via the Desktop icon."
