# Docker + Pi Display Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Docker container display the photo frame on a Pi OS Bookworm desktop (Wayland) exactly as the native app does.

**Architecture:** Fix `docker-compose.pi.yml` to pass Wayland socket and env vars correctly. Update `Dockerfile` to include Wayland client libs and fix the healthcheck. Add `PF_DB_PATH` env var so the container's SQLite DB persists to a named volume.

**Tech Stack:** Docker Compose v2, SDL2, Wayland, Python 3.11-slim.

**Dependency:** Plan 1 (Config DB) must be complete — this plan removes the JSON-file healthcheck that Plan 1 eliminates.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `docker-compose.pi.yml` | Fix Wayland socket, add group_add, hardcode paths |
| Modify | `docker-compose.yml` | Add `PF_DB_PATH` env var and `/data` named volume |
| Modify | `Dockerfile` | Add Wayland libs, fix healthcheck, add PF_DB_PATH default |

---

## Task 1: Fix `docker-compose.pi.yml`

**Files:**
- Modify: `docker-compose.pi.yml`

- [ ] **Step 1: Read current file**

```bash
cat docker-compose.pi.yml
```

- [ ] **Step 2: Replace contents**

Replace `docker-compose.pi.yml` entirely with:

```yaml
# Pi overlay: docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d
# Requires: Pi OS Bookworm desktop (Wayland/labwc). User must be in 'video' and 'render' groups.
services:
  photoframe:
    group_add:
      - video
      - render
    devices:
      - /dev/dri:/dev/dri
      - /dev/input:/dev/input
    volumes:
      - /sys/class/backlight:/sys/class/backlight
      - /run/user/1000:/run/user/1000
    environment:
      - WAYLAND_DISPLAY=wayland-1
      - XDG_RUNTIME_DIR=/run/user/1000
      - SDL_VIDEODRIVER=wayland
      - SDL_WAYLAND_CHECK_LIVE_RESIZE=0
    # Uncomment for MQTT / mDNS:
    # network_mode: host
```

Key changes vs old file:
- Removed shell-expansion volume paths (`${XDG_RUNTIME_DIR:-...}`) — Docker Compose resolves these on host, not container
- Hardcoded `/run/user/1000` (Pi default UID 1000)
- Added `group_add: [video, render]` for DRI access
- Added `SDL_VIDEODRIVER=wayland` to prevent SDL falling back to offscreen

- [ ] **Step 3: Commit**

```bash
git add docker-compose.pi.yml
git commit -m "fix: docker-compose.pi.yml - hardcode Wayland socket path, add group_add and SDL_VIDEODRIVER"
```

---

## Task 2: Update base `docker-compose.yml` for DB volume

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Read current file**

```bash
cat docker-compose.yml
```

- [ ] **Step 2: Add `/data` named volume and `PF_DB_PATH`**

In the `services.photoframe` section, ensure these are present:

```yaml
services:
  photoframe:
    build: .
    restart: unless-stopped
    volumes:
      - photoframe_images:/app/Images
      - photoframe_data:/data
    environment:
      - PF_DB_PATH=/data/photoframe.db
    ports:
      - "5002:5002"
    command: ["--display", "pygame"]

volumes:
  photoframe_images:
  photoframe_data:
```

Adjust existing volume/port/command entries to match — don't duplicate entries that already exist, just add `PF_DB_PATH` to environment and `photoframe_data:/data` to volumes and `photoframe_data:` to top-level volumes.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add /data named volume and PF_DB_PATH env var to docker-compose"
```

---

## Task 3: Update `Dockerfile`

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Add Wayland client libraries to apt deps**

In the `RUN apt-get update` block, add after `libsdl2-ttf-2.0-0`:
```dockerfile
    libwayland-client0 \
    libwayland-egl1 \
    libwayland-cursor0 \
    libxkbcommon0 \
```

- [ ] **Step 2: Fix healthcheck — remove JSON file dependency**

Replace current HEALTHCHECK:
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:5002/ || exit 1
```

This requires `curl` (already installed). Remove the old Python-based healthcheck that read `photoframe_settings.json`.

- [ ] **Step 3: Add `PF_DB_PATH` default ENV**

After the `WORKDIR /app` line, add:
```dockerfile
ENV PF_DB_PATH=/data/photoframe.db
```

- [ ] **Step 4: Ensure `/data` directory created**

In the `RUN mkdir -p` line, add `/data`:
```dockerfile
RUN mkdir -p /app/Images /data
```

- [ ] **Step 5: Update VOLUME declaration**

```dockerfile
VOLUME ["/app/Images", "/data"]
```

- [ ] **Step 6: Build and verify (on dev machine)**

```bash
docker build -t photoframe-test .
docker run --rm photoframe-test python -c "
import os
print('PF_DB_PATH:', os.environ.get('PF_DB_PATH'))
from Utilities.config_store import load_settings
d = load_settings()
print('settings OK — playback:', d.get('playback'))
"
```
Expected: Prints `PF_DB_PATH: /data/photoframe.db` and settings dict.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile
git commit -m "fix: Dockerfile - add Wayland libs, fix healthcheck, add PF_DB_PATH env"
```

---

## Task 4: Pi deployment verification

This task runs **on the Raspberry Pi**, not the dev machine.

- [ ] **Step 1: Confirm user is in video/render groups**

```bash
groups $USER
```
If `video` or `render` missing:
```bash
sudo usermod -aG video,render $USER
# Log out and back in
```

- [ ] **Step 2: Confirm Wayland socket exists**

```bash
ls -la /run/user/1000/wayland-1
```
Expected: socket file exists.

- [ ] **Step 3: Pull / build and start**

```bash
docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d --build
```

- [ ] **Step 4: Check logs**

```bash
docker compose logs -f photoframe
```
Expected: `[PhotoFrame] Pygame display ...x... Settings: ...` and no SDL errors.

If you see `SDL_GetDisplayBounds(): No video target` — SDL couldn't connect to Wayland. Run:
```bash
docker compose exec photoframe bash -c "echo \$WAYLAND_DISPLAY \$XDG_RUNTIME_DIR"
```
Both should print non-empty values. If empty, check that `/run/user/1000/wayland-1` exists on host and the volume mount worked.

- [ ] **Step 5: Verify web UI accessible**

From another device on same network:
```
http://<pi-ip>:5002/
```
Expected: Login page loads.

- [ ] **Step 6: Note any remaining issues in a git commit message**

```bash
git commit --allow-empty -m "chore: Pi display verification complete — [describe result]"
```
