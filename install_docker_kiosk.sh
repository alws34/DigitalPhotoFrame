#!/bin/bash
set -euo pipefail

# ================================================================
# DigitalPhotoFrame - Docker Installer
# Run on Raspberry Pi OS Bookworm (or later)
# Usage: sudo bash install_docker_kiosk.sh
#
# This installer sets up the pygame-in-container approach:
#   - The Docker container runs pygame/SDL2 directly.
#   - SDL2 renders to the display via DRM/KMS (no desktop needed)
#     or via Wayland passthrough (Pi OS desktop).
#   - No browser or Chromium kiosk is required for local display.
#
# NOTE: If you also want a browser-based remote viewing page
# (/frame), that still works over HTTP without any extra host
# packages — just open http://<pi-ip>:5002/frame in a browser
# on another device.  To run a full Chromium kiosk on the Pi
# itself for the remote-view page, install cage + chromium-browser
# manually (they are NOT installed by this script).
# ================================================================

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")" && pwd)}"
FRAME_USER="${FRAME_USER:-pi}"

echo "============================================"
echo " DigitalPhotoFrame Docker Installer"
echo "============================================"
echo ""
echo "App directory: $APP_DIR"
echo "Frame user:    $FRAME_USER"
echo ""

# ------------------------------------------------------------------
# 1. Install Docker
# ------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
    echo "[1/5] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$FRAME_USER"
    echo "  Docker installed. User $FRAME_USER added to docker group."
else
    echo "[1/5] Docker already installed."
fi

if ! docker compose version &>/dev/null 2>&1; then
    echo "  Installing docker compose plugin..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi

# Enable Docker to start on boot — the container itself handles the
# display, so no separate kiosk service is needed.
sudo systemctl enable docker

# ------------------------------------------------------------------
# 2. Display access: video group + DRM/KMS permissions
# ------------------------------------------------------------------
echo "[2/5] Configuring display access..."

# Add the user to the video group so they can access /dev/dri (DRM)
# and /sys/class/backlight without root.
sudo usermod -aG video "$FRAME_USER"

# Backlight udev rule — lets the video group adjust brightness.
sudo tee /etc/udev/rules.d/90-backlight.rules >/dev/null <<'UDEV'
SUBSYSTEM=="backlight", GROUP="video", MODE="0664"
UDEV
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=backlight || true

echo "  User $FRAME_USER added to 'video' group."
echo "  Backlight udev rule written."
echo ""
echo "  Display access notes:"
echo "    DRM/KMS (no desktop): SDL2 opens /dev/dri directly."
echo "      The container receives /dev/dri and /dev/input via"
echo "      docker-compose.pi.yml. No extra host setup needed."
echo "    Wayland (Pi OS Bookworm desktop): The Wayland socket is"
echo "      bind-mounted into the container. Ensure the socket path"
echo "      matches XDG_RUNTIME_DIR and WAYLAND_DISPLAY (defaults:"
echo "      /run/user/1000 and wayland-1). Force the backend with:"
echo "        SDL_VIDEODRIVER=wayland  (desktop)"
echo "        SDL_VIDEODRIVER=kmsdrm   (no desktop / DRM direct)"

# ------------------------------------------------------------------
# 3. Build and start Docker container
# ------------------------------------------------------------------
echo "[3/5] Building and starting Docker container..."
cd "$APP_DIR"
mkdir -p Images

if [ ! -f photoframe_settings.json ] && [ -f photoframe_settings.example.json ]; then
    cp photoframe_settings.example.json photoframe_settings.json
    echo "  Created photoframe_settings.json from example."
fi

docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d --build

# ------------------------------------------------------------------
# 4. Create helper scripts
# ------------------------------------------------------------------
echo "[4/5] Creating helper scripts..."

cat > "$APP_DIR/update.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Pulling latest changes..."
git pull --ff-only
echo "Rebuilding Docker container..."
docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d --build
echo "Update complete!"
SCRIPT
chmod +x "$APP_DIR/update.sh"

cat > "$APP_DIR/restart.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
docker compose -f docker-compose.yml -f docker-compose.pi.yml restart
echo "Restarted."
SCRIPT
chmod +x "$APP_DIR/restart.sh"

cat > "$APP_DIR/logs.sh" <<'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
docker compose logs -f --tail=100
SCRIPT
chmod +x "$APP_DIR/logs.sh"

# ------------------------------------------------------------------
# 5. Verify container is running
# ------------------------------------------------------------------
echo "[5/5] Checking container status..."
docker compose -f docker-compose.yml -f docker-compose.pi.yml ps

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo "============================================"
echo " Installation complete!"
echo "============================================"
echo ""
echo "The photoframe container is running and will restart"
echo "automatically on boot (Docker is enabled via systemd)."
echo ""
echo "To start the container manually (e.g. after a reboot):"
echo "  cd $APP_DIR"
echo "  docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d"
echo ""
echo "Helper scripts:"
echo "  ./update.sh    - Pull updates & rebuild"
echo "  ./restart.sh   - Restart the container"
echo "  ./logs.sh      - View container logs"
echo ""
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo "Admin UI (any device on LAN): http://$LOCAL_IP:${PHOTOFRAME_PORT:-5002}"
echo "Remote frame view:            http://$LOCAL_IP:${PHOTOFRAME_PORT:-5002}/frame"
echo ""
echo "Note: a reboot is recommended to apply group membership changes"
echo "(video group) and ensure all udev rules take effect."
echo "  sudo reboot"
