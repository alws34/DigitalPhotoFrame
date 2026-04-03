#!/bin/bash
set -euo pipefail

# ================================================================
# DigitalPhotoFrame - Docker + Chromium Kiosk Installer
# Run on Raspberry Pi OS Bookworm (or later)
# Usage: sudo bash install_docker_kiosk.sh
# ================================================================

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")" && pwd)}"
KIOSK_URL="http://localhost:${PHOTOFRAME_PORT:-5002}/frame"
KIOSK_USER="${KIOSK_USER:-pi}"

echo "============================================"
echo " DigitalPhotoFrame Docker Kiosk Installer"
echo "============================================"
echo ""
echo "App directory: $APP_DIR"
echo "Kiosk URL:     $KIOSK_URL"
echo "Kiosk user:    $KIOSK_USER"
echo ""

# ------------------------------------------------------------------
# 1. Install Docker
# ------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
    echo "[1/6] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$KIOSK_USER"
    echo "  Docker installed. User $KIOSK_USER added to docker group."
else
    echo "[1/6] Docker already installed."
fi

if ! docker compose version &>/dev/null 2>&1; then
    echo "  Installing docker compose plugin..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi

# ------------------------------------------------------------------
# 2. Install kiosk packages
# ------------------------------------------------------------------
echo "[2/6] Installing kiosk packages (cage, chromium)..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    cage \
    chromium-browser \
    fonts-liberation \
    fonts-dejavu

# ------------------------------------------------------------------
# 3. Backlight permissions
# ------------------------------------------------------------------
echo "[3/6] Setting up backlight permissions..."
sudo tee /etc/udev/rules.d/90-backlight.rules >/dev/null <<'UDEV'
SUBSYSTEM=="backlight", GROUP="video", MODE="0664"
UDEV
sudo usermod -aG video "$KIOSK_USER"
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=backlight || true

# ------------------------------------------------------------------
# 4. Build and start Docker container
# ------------------------------------------------------------------
echo "[4/6] Building and starting Docker container..."
cd "$APP_DIR"
mkdir -p Images

if [ ! -f photoframe_settings.json ] && [ -f photoframe_settings.example.json ]; then
    cp photoframe_settings.example.json photoframe_settings.json
    echo "  Created photoframe_settings.json from example."
fi

docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d --build

# ------------------------------------------------------------------
# 5. Create kiosk systemd service
# ------------------------------------------------------------------
echo "[5/6] Creating kiosk browser systemd service..."

KIOSK_UID=$(id -u "$KIOSK_USER")
sudo tee /etc/systemd/system/photoframe-kiosk.service >/dev/null <<EOF
[Unit]
Description=PhotoFrame Chromium Kiosk
Wants=graphical.target docker.service
After=graphical.target docker.service
ConditionPathExists=$APP_DIR

[Service]
Type=simple
User=$KIOSK_USER
Environment=XDG_RUNTIME_DIR=/run/user/$KIOSK_UID
Environment=WLR_LIBINPUT_NO_DEVICES=1

# Wait for backend to be ready (up to 60s)
ExecStartPre=/bin/sh -c 'for i in \$(seq 1 30); do curl -sf http://localhost:${PHOTOFRAME_PORT:-5002}/ >/dev/null 2>&1 && break; sleep 2; done'

ExecStart=/usr/bin/cage -- /usr/bin/chromium-browser \\
    --kiosk \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-session-crashed-bubble \\
    --disable-features=TranslateUI \\
    --check-for-update-interval=31536000 \\
    --disable-component-update \\
    --overscroll-history-navigation=0 \\
    --autoplay-policy=no-user-gesture-required \\
    --no-first-run \\
    --disable-pinch \\
    --enable-features=OverlayScrollbar \\
    $KIOSK_URL

Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable photoframe-kiosk.service

# ------------------------------------------------------------------
# 6. Create helper scripts
# ------------------------------------------------------------------
echo "[6/6] Creating helper scripts..."

cat > "$APP_DIR/update.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail
cd "\$(dirname "\$0")"
echo "Pulling latest changes..."
git pull --ff-only
echo "Rebuilding Docker container..."
docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d --build
echo "Restarting kiosk..."
sudo systemctl restart photoframe-kiosk.service
echo "Update complete!"
SCRIPT
chmod +x "$APP_DIR/update.sh"

cat > "$APP_DIR/restart.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail
cd "\$(dirname "\$0")"
docker compose restart
sudo systemctl restart photoframe-kiosk.service
echo "Restarted."
SCRIPT
chmod +x "$APP_DIR/restart.sh"

cat > "$APP_DIR/logs.sh" <<'SCRIPT'
#!/bin/bash
cd "\$(dirname "\$0")"
docker compose logs -f --tail=100
SCRIPT
chmod +x "$APP_DIR/logs.sh"

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo "============================================"
echo " Installation complete!"
echo "============================================"
echo ""
echo "Backend is running in Docker."
echo "Start the kiosk browser:"
echo "  sudo systemctl start photoframe-kiosk"
echo ""
echo "Helper scripts:"
echo "  ./update.sh    - Pull updates & rebuild"
echo "  ./restart.sh   - Restart everything"
echo "  ./logs.sh      - View backend logs"
echo ""
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo "Admin UI:    http://$LOCAL_IP:5001"
echo "Frame view:  http://$LOCAL_IP:5001/frame"
echo ""
echo "Reboot to apply all changes: sudo reboot"
