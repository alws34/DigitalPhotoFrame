# Docker Deployment Guide

## Architecture

```
+-------------- Raspberry Pi Host ---------------+
|                                                 |
|  +---- Docker Container -----+                  |
|  |  Python Backend            |   port 5002     |
|  |  (Flask + compositor)      |<----------------|
|  |  React Frontend            |                  |
|  |  (built, served static)    |                  |
|  +----------------------------+                  |
|                                                  |
|  +---- Host Services --------+                   |
|  |  cage (Wayland kiosk)      |                  |
|  |  +- Chromium --kiosk       |---> Display      |
|  |     localhost:5002/frame   |                   |
|  +----------------------------+                   |
|                                                   |
|  /dev/dri -----------> GPU access                 |
|  /sys/class/backlight -> Brightness control       |
|  /dev/input/* --------> Touch (via cage)          |
+---------------------------------------------------+
```

The Docker container runs the Python backend in headless mode and serves the React frontend. On the Pi, a lightweight Wayland compositor (cage) runs Chromium in kiosk mode, pointing at the container's `/frame` page.

**Why this split?** The app code (backend + frontend) changes frequently and ships via Docker. The kiosk browser is a one-time host setup that rarely needs updating. Touch input, GPU, and display are handled natively by the host.

## Quick Start (Mac / Development)

### Prerequisites

- Docker Desktop installed
- The repo cloned locally

### Build and run

```bash
cd DigitalPhotoFrame
docker compose up --build
```

Open in your browser:
- **Admin UI:** http://localhost:5002 (login required)
- **Frame View:** http://localhost:5002/frame (what the kiosk displays)
- **MJPEG Stream:** http://localhost:5002/api/stream

### Stop

```bash
docker compose down
```

### Development workflow

1. Edit Python backend or React frontend code
2. Rebuild: `docker compose up --build`
3. The multi-stage build recompiles the frontend and restarts the backend

For faster frontend iteration during development, run Vite dev server separately:
```bash
cd frontend && npm install && npm run dev
# Frontend at http://localhost:5173, proxied API calls go to the container
```

## Raspberry Pi Deployment

### Prerequisites

- Raspberry Pi 4 or 5 (2GB+ RAM recommended)
- Raspberry Pi OS Bookworm (64-bit recommended)
- Display connected (official Pi display, HDMI, or any other)
- Network connection (Wi-Fi or Ethernet)

### One-Command Install

```bash
git clone https://github.com/alws34/DigitalPhotoFrame.git
cd DigitalPhotoFrame
sudo bash install_docker_kiosk.sh
sudo reboot
```

After reboot, the photo frame starts automatically.

### What the installer does

1. **Installs Docker** and docker compose plugin
2. **Installs cage** (minimal Wayland compositor) and Chromium
3. **Sets up backlight permissions** (udev rules for brightness control)
4. **Builds the Docker container** with Pi device access (GPU, backlight)
5. **Creates a systemd service** (`photoframe-kiosk`) for the kiosk browser
6. **Creates helper scripts** for day-to-day management

### Updating

Pull the latest code and rebuild:

```bash
./update.sh
```

This does: `git pull` + `docker compose up --build` + restart kiosk.

### Managing services

```bash
# View backend logs
./logs.sh

# Restart everything (backend + kiosk)
./restart.sh

# Docker container only
docker compose restart

# Kiosk browser only
sudo systemctl restart photoframe-kiosk

# Stop everything
docker compose down
sudo systemctl stop photoframe-kiosk

# Check status
docker compose ps
sudo systemctl status photoframe-kiosk
```

## Configuration

Settings live in `photoframe_settings.json` (mounted into the container as a volume).

Edit via:
1. **Web UI:** Navigate to http://<pi-ip>:5002/settings (login required)
2. **Direct edit:** Modify the JSON file, then `docker compose restart`

### Important settings for Docker

| Setting | Value | Notes |
|---------|-------|-------|
| `backend_configs.server_port` | `5002` | Set `PHOTOFRAME_PORT` env var to match if changed |
| `backend_configs.host` | `0.0.0.0` | Listen on all interfaces (required in container) |
| `system.image_dir` | `Images` | Relative path, inside the container |

### Images

Place photos in the `Images/` directory. It's mounted as a Docker volume, so files persist across container rebuilds.

```bash
# Copy photos
cp /path/to/photos/*.jpg Images/

# Or upload via the Gallery page in the web UI
```

Supported formats: JPG, PNG, GIF, BMP, WebP, HEIC/HEIF, MOV, MP4

### MQTT (Home Assistant)

If using MQTT, the container may need host networking to reach your broker:

```yaml
# In docker-compose.pi.yml, uncomment:
network_mode: host
```

Or set `mqtt.host` to your broker's IP address (not `localhost`).

## Files Overview

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build (Node frontend + Python backend) |
| `docker-compose.yml` | Base compose config (works on Mac and Pi) |
| `docker-compose.pi.yml` | Pi overlay (GPU, backlight device access) |
| `requirements-docker.txt` | Python deps without PySide6/Qt (lighter) |
| `install_docker_kiosk.sh` | One-command Pi setup (Docker + kiosk browser) |
| `update.sh` | Pull + rebuild + restart |
| `restart.sh` | Restart backend + kiosk |
| `logs.sh` | Tail backend logs |

## Troubleshooting

### Container won't start

```bash
docker compose logs photoframe
```

Common issues:
- Missing `photoframe_settings.json` — copy from example: `cp photoframe_settings.example.json photoframe_settings.json`
- Port 5001 in use — change the port mapping in `docker-compose.yml`

### Kiosk shows black screen

The backend might not be ready. The kiosk service waits up to 60s, but if the first build is slow:

```bash
# Check if backend is up
curl http://localhost:5002/

# Check container status
docker compose ps

# Restart kiosk after backend is ready
sudo systemctl restart photoframe-kiosk
```

### No touch input

Touch is handled by cage on the host. Check your display:
```bash
libinput list-devices
```

### Brightness control not working

The container needs `/sys/class/backlight` mounted. Verify:
```bash
# Check backlight device exists
ls /sys/class/backlight/

# Check permissions (should be group=video, mode=0664)
ls -la /sys/class/backlight/*/brightness

# Ensure Pi user is in video group
groups pi
```

### Rebuilding from scratch

```bash
docker compose down -v          # Remove container + volumes
docker compose up --build       # Full rebuild
sudo systemctl restart photoframe-kiosk
```

## Migrating from bare-metal install

If you previously ran the app using `install_photoframe_service.sh` (systemd + venv):

1. Stop the old service: `sudo systemctl stop PhotoFrame_Desktop_App && sudo systemctl disable PhotoFrame_Desktop_App`
2. Your `Images/` directory and `photoframe_settings.json` are preserved (Docker mounts them)
3. Run the Docker installer: `sudo bash install_docker_kiosk.sh && sudo reboot`
4. The old `env/` venv directory can be deleted after verifying Docker works

## Resource Usage

Typical on Raspberry Pi 4 (2GB):
- **Docker container:** ~150-250 MB RAM (Python backend + compositor)
- **Chromium kiosk:** ~100-150 MB RAM
- **CPU:** 5-15% idle, 30-50% during transitions
- **Disk:** ~500 MB for Docker image (vs ~2.5 GB with PySide6)
