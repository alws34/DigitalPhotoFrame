# Dockerize DigitalPhotoFrame with Chromium Kiosk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace PySide6 fullscreen GUI with a Chromium kiosk browser, Dockerize the Python backend + React frontend for easy deployment and updates on Raspberry Pi.

**Architecture:** The Python backend runs in headless mode inside a Docker container, serving the React frontend (including a new fullscreen FrameView page). On the Pi host, a minimal Wayland compositor (cage) runs Chromium in kiosk mode pointing at the container's web server. Updates ship via `docker pull && docker-compose up -d`.

**Tech Stack:** Docker, docker-compose, Python 3.11, Flask, OpenCV (headless), React/Vite, Chromium kiosk, cage (Wayland compositor), supervisord (optional)

---

### Task 1: Add FrameView Kiosk Page to React Frontend

**Files:**
- Create: `frontend/src/pages/FrameView.jsx`
- Modify: `frontend/src/App.jsx`

This page is what Chromium kiosk will display. It shows the MJPEG stream fullscreen with no UI chrome. The compositor already renders overlays (date/time/weather) into the stream, so this page is intentionally minimal.

- [ ] **Step 1: Create FrameView.jsx**

```jsx
// frontend/src/pages/FrameView.jsx
import { useEffect } from 'react';

export default function FrameView() {
  useEffect(() => {
    // Hide cursor after 3s of inactivity
    let timer;
    const hide = () => { document.body.style.cursor = 'none'; };
    const show = () => {
      document.body.style.cursor = 'default';
      clearTimeout(timer);
      timer = setTimeout(hide, 3000);
    };
    document.addEventListener('mousemove', show);
    hide();
    return () => {
      document.removeEventListener('mousemove', show);
      clearTimeout(timer);
      document.body.style.cursor = 'default';
    };
  }, []);

  return (
    <div style={{
      width: '100vw',
      height: '100vh',
      background: '#000',
      overflow: 'hidden',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      <img
        src="/api/stream"
        alt=""
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
        }}
      />
    </div>
  );
}
```

- [ ] **Step 2: Add /frame route to App.jsx**

Add `FrameView` import and a public route (no auth required) for `/frame`:

```jsx
import FrameView from './pages/FrameView';

// Inside <Routes>, add BEFORE the auth-wrapped routes:
<Route path="/frame" element={<FrameView />} />
```

- [ ] **Step 3: Build and verify**

```bash
cd /Users/alon/Desktop/Projects/DigitalPhotoFrame/frontend && npm run build
```

Expected: Build succeeds, `frontend/dist/` is updated.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/FrameView.jsx frontend/src/App.jsx frontend/dist/
git commit -m "feat: add /frame kiosk display page for Chromium kiosk mode"
```

---

### Task 2: Make app.py Work Without PySide6 in Headless Mode

**Files:**
- Modify: `app.py`

Currently `app.py` imports PySide6 at the top level (line 19), which crashes headless mode when PySide6 isn't installed (e.g., in Docker). Move Qt imports inside `_run_gui()`.

- [ ] **Step 1: Refactor app.py imports**

Remove the top-level PySide6 import and the `_apply_safe_theme` / `_SettingsSizer` classes that depend on Qt. Move them inside `_run_gui()`. Keep non-Qt imports at the top.

The key changes:
1. Remove `from PySide6 import QtCore, QtGui, QtWidgets` from line 19
2. Remove `QtWidgets.QApplication.setAttribute(...)` from line 25
3. Move `_apply_safe_theme()` and `_SettingsSizer` class inside `_run_gui()`
4. Add conditional Qt imports inside `_run_gui()`

After refactoring, the top of `app.py` should only import standard library + non-Qt project modules. All PySide6 usage is deferred to `_run_gui()`.

- [ ] **Step 2: Verify headless mode works without PySide6**

```bash
cd /Users/alon/Desktop/Projects/DigitalPhotoFrame
env/bin/python -c "
import sys
# Simulate PySide6 not being installed
sys.modules['PySide6'] = None
sys.modules['PySide6.QtCore'] = None
sys.modules['PySide6.QtGui'] = None
sys.modules['PySide6.QtWidgets'] = None
# This import should succeed
from app import _run_headless, _load_settings, _abs_path
print('OK: app.py loads without PySide6')
"
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "refactor: defer PySide6 imports to GUI mode so headless works without Qt"
```

---

### Task 3: Create Docker Requirements File

**Files:**
- Create: `requirements-docker.txt`

Strip PySide6 and Qt-related packages. Use `opencv-python-headless` instead of `opencv-python` (smaller, no X11 deps).

- [ ] **Step 1: Create requirements-docker.txt**

```
blinker==1.9.0
certifi==2026.2.25
charset-normalizer==3.4.4
click==8.3.1
Flask==3.1.3
flask-cors==6.0.2
idna==3.11
itsdangerous==2.2.0
Jinja2==3.1.6
MarkupSafe==3.0.3
numpy==2.4.2
opencv-python-headless==4.13.0.92
pillow==12.1.1
pillow_heif==1.3.0
psutil==7.2.2
requests==2.32.5
SQLAlchemy==2.0.48
tqdm==4.67.3
typing_extensions==4.15.0
urllib3==2.6.3
watchdog==6.0.0
Werkzeug==3.1.6
paho-mqtt>=1.6.0,<3.0
```

Note: `paho-mqtt` added explicitly (was missing from requirements.txt but used by mqtt_bridge.py). PySide6, PySide6_Addons, PySide6_Essentials, shiboken6, qasync all removed.

- [ ] **Step 2: Commit**

```bash
git add requirements-docker.txt
git commit -m "feat: add Docker-specific requirements without PySide6/Qt deps"
```

---

### Task 4: Create Dockerfile

**Files:**
- Create: `Dockerfile`

Multi-stage build: Stage 1 builds the React frontend, Stage 2 sets up the Python runtime.

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# ==============================================================
# Stage 1: Build React frontend
# ==============================================================
FROM node:20-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ==============================================================
# Stage 2: Python runtime (headless — no PySide6/Qt)
# ==============================================================
FROM python:3.11-slim

LABEL maintainer="DigitalPhotoFrame"
LABEL description="Digital Photo Frame - headless backend + React frontend"

WORKDIR /app

# System dependencies for OpenCV, Pillow, pillow-heif
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libjpeg62-turbo \
    libopenjp2-7 \
    libheif1 \
    libde265-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt

# Copy application code
COPY app.py config.py Settings.py iFrame.py pyproject.toml ./
COPY FrameServer/ ./FrameServer/
COPY WebAPI/ ./WebAPI/
COPY Utilities/ ./Utilities/
COPY arial.ttf ./

# Copy built frontend from stage 1
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

# Create default directories
RUN mkdir -p /app/Images /data

# Settings and images are expected as volumes
VOLUME ["/app/Images", "/data"]

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5001/api/auth/me || exit 1

ENTRYPOINT ["python", "app.py", "--headless"]
```

- [ ] **Step 2: Create .dockerignore**

```
env/
.git/
.github/
.claude/
__pycache__/
*.pyc
*.pyo
node_modules/
frontend/node_modules/
frontend/dist/
docs/
Tests/
*.log
*.db
*.bak
config_backups/
_thumbs/
.ruff_cache/
.pytest_cache/
*.egg-info/
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add multi-stage Dockerfile for headless backend + React frontend"
```

---

### Task 5: Create docker-compose.yml

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.pi.yml` (Pi-specific overrides with device mounts)

- [ ] **Step 1: Create docker-compose.yml (base — works on Mac and Pi)**

```yaml
services:
  photoframe:
    build: .
    container_name: photoframe
    restart: unless-stopped
    ports:
      - "5001:5001"
    volumes:
      - ./Images:/app/Images
      - ./photoframe_settings.json:/app/photoframe_settings.json
      - photoframe-data:/data
    environment:
      - PHOTOFRAME_SECRET_KEY=${PHOTOFRAME_SECRET_KEY:-change-me-in-production}
    # healthcheck is defined in Dockerfile

volumes:
  photoframe-data:
```

- [ ] **Step 2: Create docker-compose.pi.yml (Pi overlay with device access)**

```yaml
# Usage: docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d
services:
  photoframe:
    devices:
      - /dev/dri:/dev/dri                    # GPU access
    volumes:
      - /sys/class/backlight:/sys/class/backlight  # Brightness control
    # Network host mode gives MQTT and mDNS access without port mapping
    # Uncomment if you need MQTT or local network discovery:
    # network_mode: host
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml docker-compose.pi.yml
git commit -m "feat: add docker-compose configs for dev (Mac) and production (Pi)"
```

---

### Task 6: Create Pi Kiosk Setup Script

**Files:**
- Create: `install_docker_kiosk.sh`

This script sets up the Raspberry Pi host to:
1. Install Docker
2. Install cage (Wayland kiosk compositor) + Chromium
3. Create systemd services for the kiosk browser and Docker app
4. Set up backlight permissions

- [ ] **Step 1: Create install_docker_kiosk.sh**

```bash
#!/bin/bash
set -euo pipefail

# ================================================================
# DigitalPhotoFrame - Docker + Chromium Kiosk Installer
# Run on a fresh Raspberry Pi OS (Bookworm or later)
# ================================================================

APP_DIR="${APP_DIR:-/home/pi/DigitalPhotoFrame}"
KIOSK_URL="http://localhost:5001/frame"
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
# 1. Install Docker (if not present)
# ------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
    echo "[1/6] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$KIOSK_USER"
    echo "  Docker installed. User $KIOSK_USER added to docker group."
    echo "  NOTE: Log out and back in for group changes to take effect."
else
    echo "[1/6] Docker already installed."
fi

# Install docker-compose plugin if missing
if ! docker compose version &>/dev/null 2>&1; then
    echo "  Installing docker-compose plugin..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi

# ------------------------------------------------------------------
# 2. Install kiosk dependencies
# ------------------------------------------------------------------
echo "[2/6] Installing kiosk packages (cage, chromium)..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    cage \
    chromium-browser \
    fonts-liberation \
    fonts-dejavu

# ------------------------------------------------------------------
# 3. Backlight permissions (same as original installer)
# ------------------------------------------------------------------
echo "[3/6] Setting up backlight permissions..."
UDEV_RULE="/etc/udev/rules.d/90-backlight.rules"
sudo tee "$UDEV_RULE" >/dev/null <<'UDEV'
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

# Create images dir if missing
mkdir -p Images

# Copy example settings if no settings exist
if [ ! -f photoframe_settings.json ]; then
    if [ -f photoframe_settings.example.json ]; then
        cp photoframe_settings.example.json photoframe_settings.json
        echo "  Created photoframe_settings.json from example."
    fi
fi

docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d --build

# ------------------------------------------------------------------
# 5. Create kiosk systemd service
# ------------------------------------------------------------------
echo "[5/6] Creating kiosk browser systemd service..."

KIOSK_SERVICE="/etc/systemd/system/photoframe-kiosk.service"
sudo tee "$KIOSK_SERVICE" >/dev/null <<EOF
[Unit]
Description=PhotoFrame Chromium Kiosk
Wants=graphical.target docker.service
After=graphical.target docker.service
ConditionPathExists=$APP_DIR

[Service]
Type=simple
User=$KIOSK_USER
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u "$KIOSK_USER")
Environment=WLR_LIBINPUT_NO_DEVICES=1

# Wait for the backend to be ready
ExecStartPre=/bin/sh -c 'for i in \$(seq 1 30); do curl -sf http://localhost:5001/ >/dev/null 2>&1 && break; sleep 2; done'

# cage launches a minimal Wayland compositor, chromium runs inside it
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

cat > "$APP_DIR/update.sh" <<'UPDATE'
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Pulling latest changes..."
git pull --ff-only
echo "Rebuilding Docker container..."
docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d --build
echo "Restarting kiosk..."
sudo systemctl restart photoframe-kiosk.service
echo "Update complete!"
UPDATE
chmod +x "$APP_DIR/update.sh"

cat > "$APP_DIR/restart.sh" <<'RESTART'
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
docker compose restart
sudo systemctl restart photoframe-kiosk.service
echo "Restarted."
RESTART
chmod +x "$APP_DIR/restart.sh"

cat > "$APP_DIR/logs.sh" <<'LOGS'
#!/bin/bash
cd "$(dirname "$0")"
docker compose logs -f --tail=100
LOGS
chmod +x "$APP_DIR/logs.sh"

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo "============================================"
echo " Installation complete!"
echo "============================================"
echo ""
echo "The photo frame backend is running in Docker."
echo "The kiosk browser will start on next reboot,"
echo "or start it now with:"
echo ""
echo "  sudo systemctl start photoframe-kiosk"
echo ""
echo "Manage the app:"
echo "  $APP_DIR/update.sh    - Pull updates & rebuild"
echo "  $APP_DIR/restart.sh   - Restart everything"
echo "  $APP_DIR/logs.sh      - View backend logs"
echo ""
echo "Admin UI:    http://$(hostname -I | awk '{print $1}'):5001"
echo "Frame view:  http://$(hostname -I | awk '{print $1}'):5001/frame"
echo ""
echo "If this is the first run, reboot to apply group changes:"
echo "  sudo reboot"
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x install_docker_kiosk.sh
git add install_docker_kiosk.sh
git commit -m "feat: add Pi kiosk installer (Docker + cage + Chromium)"
```

---

### Task 7: Create DOCKER.md Documentation

**Files:**
- Create: `DOCKER.md`

Full documentation covering Mac development, Pi deployment, and troubleshooting.

- [ ] **Step 1: Create DOCKER.md**

Complete documentation with sections:
- Quick Start (Mac development)
- Raspberry Pi Deployment
- Architecture overview
- Configuration
- Updating
- Troubleshooting
- Device access (backlight, touch, GPU)

- [ ] **Step 2: Commit**

```bash
git add DOCKER.md
git commit -m "docs: add Docker deployment guide for Mac dev and Pi production"
```

---

### Task 8: Rebuild Frontend and Verify

- [ ] **Step 1: Install deps and build**

```bash
cd /Users/alon/Desktop/Projects/DigitalPhotoFrame/frontend
npm install
npm run build
npm run lint
```

- [ ] **Step 2: Test Docker build locally (Mac)**

```bash
cd /Users/alon/Desktop/Projects/DigitalPhotoFrame
docker compose build
docker compose up -d
# Verify: curl http://localhost:5001/ should return HTML
# Verify: http://localhost:5001/frame should show the frame view
docker compose down
```

- [ ] **Step 3: Final commit with built frontend**

```bash
git add frontend/dist/
git commit -m "build: rebuild frontend with FrameView kiosk page"
```
