# Digital Photo Frame - Setup & Running Instructions

## Branch Info

All refactoring work is on branch **`claude/ecstatic-ramanujan`** (worktree off `main`).
**`main` is untouched.** Nothing has been committed yet - all changes are unstaged.

To review before merging:
```bash
git diff HEAD                    # see all modifications
git status                       # see new + modified files
```

---

## Prerequisites

- Python 3.9+
- Node.js 18+ (only needed if you want to rebuild the frontend)
- pip packages listed in `requirements.txt`

---

## Quick Start (Production / Deployment on Pi)

The React frontend is **pre-built** into `WebAPI/static/react/`. No Node.js needed on the Pi.

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run with GUI (Raspberry Pi with display)
python app.py --settings photoframe_settings.json

# 3. Run headless (no display, web-only)
python app.py --settings photoframe_settings.json --headless

# Optional: override resolution in headless mode
python app.py --headless --width 1920 --height 1080
```

The web UI will be available at `http://<pi-ip>:5002` (port from `backend_configs.server_port` in settings).

### First-time setup
1. Open `http://<pi-ip>:5002` in a browser
2. You'll be redirected to the signup page
3. Create an account, then log in
4. The React SPA loads with Dashboard, Gallery, and Settings

### SQLite migration
On first startup, if `users.json` or `metadata.json` exist, they'll be automatically migrated to SQLite (`photoframe.db`). The JSON files get renamed to `.migrated` as backup.

---

## Development Setup

### Backend (Flask)

```bash
# Install Python deps (use a venv if you prefer)
python -m venv venv
source venv/bin/activate        # Linux/Mac
pip install -r requirements.txt

# Run the server
python app.py --settings photoframe_settings.json --headless
```

The Flask server runs on the port specified in `photoframe_settings.json` → `backend_configs.server_port` (default: 5002).

### Frontend (React + Vite dev server)

```bash
cd frontend
npm install          # first time only
npm run dev          # starts Vite dev server on http://localhost:5173
```

The Vite dev server proxies API calls to `http://localhost:5002` (configured in `vite.config.ts`). So you need **both** running:

| Terminal 1 (backend) | Terminal 2 (frontend) |
|---|---|
| `python app.py --headless` | `cd frontend && npm run dev` |

Then open `http://localhost:5173` for hot-reload development.

### Rebuilding the frontend for production

```bash
cd frontend
npm run build
```

This outputs to `WebAPI/static/react/`. The Flask server automatically serves the React SPA from there when it detects `WebAPI/static/react/index.html` exists.

---

## Project Structure (after refactoring)

```
DigitalPhotoFrame/
├── app.py                          # Entry point (GUI or headless)
├── config.py                       # Settings defaults
├── photoframe_settings.json        # Runtime config
├── requirements.txt                # Python deps
├── REFACTOR_PROGRESS.md            # Detailed changelog
├── SETUP.md                        # This file
│
├── FrameServer/
│   ├── PhotoFrameServer.py         # Core slideshow engine
│   └── overlay.py                  # Overlay renderer (static/adaptive/inverse)
│
├── WebAPI/
│   ├── __init__.py                 # Flask app factory
│   ├── backend.py                  # Slim Backend orchestrator
│   ├── extensions.py               # Shared AppState singleton
│   ├── middleware.py               # CSRF, security headers, auth decorator
│   ├── routes/
│   │   ├── auth.py                 # Login/signup/logout + JSON API
│   │   ├── images.py               # Image upload/delete/thumbnails/metadata
│   │   ├── pages.py                # SPA catch-all (serves React or Jinja2)
│   │   ├── settings.py             # Settings CRUD + weather
│   │   ├── stream.py               # MJPEG stream, SSE metadata, SSE logs
│   │   └── system.py               # System stats, logs
│   ├── services/
│   │   ├── image_service.py        # HEIC conversion, hashing, thumbnails
│   │   └── stream_service.py       # Frame capture loop, MJPEG encoding
│   ├── db/
│   │   ├── connection.py           # SQLite connection (WAL mode)
│   │   ├── schema.py               # Table definitions
│   │   ├── user_repository.py      # User CRUD
│   │   ├── metadata_repository.py  # Image metadata CRUD
│   │   └── migrate.py              # JSON → SQLite one-time migration
│   ├── WebUtils/
│   │   └── auth_security.py        # UserStore, CSRF, rate limiting
│   ├── static/
│   │   └── react/                  # Built React SPA (committed)
│   └── templates/                  # Legacy Jinja2 templates (still work)
│
├── frontend/                       # React source (dev only)
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx                 # Routes, theme, auth
│   │   ├── api/                    # API client layer
│   │   ├── hooks/                  # useAuth, useSettings, useMetadataStream
│   │   ├── components/             # Layout (sidebar nav)
│   │   └── pages/                  # Login, Signup, Dashboard, Gallery, Settings
│   └── .gitignore                  # Excludes node_modules
│
├── FrameGUI/                       # PySide6 Qt GUI (unchanged)
├── Utilities/                      # MQTT, weather, observer, etc. (unchanged)
└── WebAPI/API.py                   # OLD monolith (kept as backup, can delete)
```

---

## Overlay Color Modes

In Settings → Display → "Overlay Color Mode":

| Mode | Description |
|------|-------------|
| **Static** | Fixed white text (original behavior) |
| **Adaptive** | Picks white or black per text element based on background brightness |
| **Inverse** | Per-pixel color inversion under text for maximum visibility |

---

## API Endpoints Reference

See `REFACTOR_PROGRESS.md` for the full endpoint table.

Key new endpoints for the React SPA:
- `GET /api/csrf` - Get CSRF token
- `GET /api/auth/check` - Check if session is authenticated
- `POST /api/auth/login` - JSON login
- `POST /api/auth/signup` - JSON signup
- `POST /api/auth/logout` - JSON logout
- `GET /api/images` - List all images with metadata (JSON)
