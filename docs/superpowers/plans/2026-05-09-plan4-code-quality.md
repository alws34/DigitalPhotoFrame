# Code Quality Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete dead files, enforce module boundaries, reduce file sizes, rename ambiguous symbols. No behavior changes.

**Architecture:** Surgical removals and renames only. `app.py` shrinks to dispatch-only. `Backend` → `APIServer`. All old static templates removed.

**Tech Stack:** Python, Ruff, ESLint.

**Dependency:** Plans 1, 2, 3 must be complete (files deleted in those plans are prerequisites here).

---

## File Map

| Action | Path | Reason |
|--------|------|--------|
| Delete | `iFrame.py` | Dead abstract base — never imported outside FrameServer |
| Delete | `WebAPI/templates/` | Replaced by React build |
| Delete | `WebAPI/static/scripts.js` `styles.css` `signup.js` | Replaced by React build |
| Delete | `users.json` | Migrated to DB in Plan 1 |
| Delete | `foss_env/` | Unused second venv |
| Extract | `app.py` → `app_modes.py` | `_run_headless`, `_run_pygame`, `_run_gui` |
| Rename | `Backend` → `APIServer` in `WebAPI/API.py` | Clearer name |
| Enforce | Module boundary: no `FrameServer` ↔ `WebAPI` cross-imports | Circular import risk |

---

## Task 1: Delete dead static files

**Files:**
- Delete: `WebAPI/templates/`, `WebAPI/static/scripts.js`, `WebAPI/static/styles.css`, `WebAPI/static/signup.js`, `WebAPI/static/styles.mobile.css`

- [ ] **Step 1: Verify Flask no longer serves these templates**

```bash
grep -rn "render_template\|templates/" WebAPI/ --include="*.py"
```
If any `render_template` calls remain, update them to serve React's `index.html` instead before deleting.

- [ ] **Step 2: Delete**

```bash
git rm -r WebAPI/templates/
git rm WebAPI/static/scripts.js WebAPI/static/styles.css WebAPI/static/signup.js 2>/dev/null || true
git rm WebAPI/static/styles.mobile.css 2>/dev/null || true
```

- [ ] **Step 3: Run tests**

```bash
env/bin/python -m pytest -v
```
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete legacy templates and static files — replaced by React build"
```

---

## Task 2: Delete `iFrame.py`

**Files:**
- Delete: `iFrame.py`
- Modify: Any file importing `iFrame`

- [ ] **Step 1: Find all imports**

```bash
grep -rn "from iFrame import\|import iFrame" --include="*.py" .
```

- [ ] **Step 2: Inline the abstract base**

`iFrame.py` defines a minimal abstract base class. Move its content directly into `FrameServer/PhotoFrameServer.py` as a local class, or replace with `abc.ABC` directly. Typical content:

```python
# iFrame.py contains roughly:
class iFrame:
    def display_frame(self, frame): raise NotImplementedError
    def get_is_running(self): raise NotImplementedError
    def stop(self): raise NotImplementedError
```

In `FrameServer/PhotoFrameServer.py`, replace `from iFrame import iFrame` with:

```python
from abc import ABC, abstractmethod

class iFrame(ABC):
    @abstractmethod
    def display_frame(self, frame): ...
    @abstractmethod
    def get_is_running(self) -> bool: ...
    @abstractmethod
    def stop(self): ...
```

Update all other files that import `iFrame` to import from `FrameServer.PhotoFrameServer` instead:
```python
from FrameServer.PhotoFrameServer import iFrame
```

- [ ] **Step 3: Delete and verify**

```bash
git rm iFrame.py
env/bin/python -m pytest -v
```
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: inline iFrame ABC into PhotoFrameServer, delete iFrame.py"
```

---

## Task 3: Delete `users.json` and `foss_env/`

- [ ] **Step 1: Verify `users.json` migration is complete**

```bash
env/bin/python -c "
from WebAPI.database import get_db, init_db
init_db()
with get_db() as conn:
    count = conn.cursor().execute('SELECT COUNT(*) FROM users').fetchone()[0]
    print(f'Users in DB: {count}')
"
```
Expected: count > 0 (or 0 if no users created yet — that's OK too, migration ran).

- [ ] **Step 2: Delete**

```bash
git rm users.json 2>/dev/null || echo "users.json already gone"
git rm -rf foss_env/ 2>/dev/null || echo "foss_env already gone"
```

- [ ] **Step 3: Add to .gitignore**

```bash
echo "foss_env/" >> .gitignore
git add .gitignore
```

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete users.json (migrated to DB) and foss_env/ (unused venv)"
```

---

## Task 4: Extract `app_modes.py` from `app.py`

**Files:**
- Create: `app_modes.py`
- Modify: `app.py`

- [ ] **Step 1: Create `app_modes.py`**

Move `_run_headless`, `_run_pygame`, `_run_gui`, and `_restart_program` out of `app.py` into new `app_modes.py`:

```python
# app_modes.py
"""Display-mode runners. Called from app.py dispatch."""
from __future__ import annotations
import os, sys, threading, time
from typing import Any, Dict, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _restart_program() -> None:
    print("[PhotoFrame] Restarting...")
    os.execl(sys.executable, sys.executable, *sys.argv)


def run_headless(settings: Dict[str, Any], width: Optional[int], height: Optional[int]) -> None:
    from FrameServer.PhotoFrameServer import PhotoFrameServer
    from WebAPI.API import APIServer
    from Utilities.autoupdate_utils import AutoUpdater

    backend_cfg = settings.get("backend_configs", {})
    w = width or int(backend_cfg.get("stream_width", 1920))
    h = height or int(backend_cfg.get("stream_height", 1080))
    images_dir = settings.get("system", {}).get("image_dir")

    stop_event = threading.Event()
    au_cfg = settings.get("autoupdate", {})
    updater = AutoUpdater(stop_event=stop_event, interval_sec=3600,
                          restart_service_async=_restart_program,
                          auto_restart_on_update=au_cfg.get("enabled", True))
    updater.start()

    srv = PhotoFrameServer(width=w, height=h, iframe=None, images_dir=images_dir)
    backend = APIServer(frame=srv, image_dir=images_dir)
    backend.updater = updater
    threading.Thread(target=backend.start, daemon=True).start()
    srv.m_api = backend
    threading.Thread(target=srv.run_photoframe, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        try: srv.stop_services()
        except Exception: pass


def run_pygame(settings: Dict[str, Any]) -> None:
    from FrameGUI.photoframe_view_pygame import PhotoFramePygame
    from FrameServer.PhotoFrameServer import PhotoFrameServer
    from WebAPI.API import APIServer
    from Utilities.MQTT.mqtt_bridge import MqttBridge
    from Utilities.autoupdate_utils import AutoUpdater

    images_dir = settings.get("system", {}).get("image_dir")
    view = PhotoFramePygame(settings=settings)
    sw, sh = view.width, view.height

    srv = PhotoFrameServer(width=sw, height=sh, iframe=view, images_dir=images_dir)
    backend = APIServer(frame=srv, image_dir=images_dir)
    threading.Thread(target=backend.start, daemon=True).start()
    srv.m_api = backend

    stop_event = threading.Event()
    au_cfg = settings.get("autoupdate", {})
    updater = AutoUpdater(stop_event=stop_event, interval_sec=1800,
                          restart_service_async=_restart_program,
                          auto_restart_on_update=au_cfg.get("enabled", True))
    updater.start()
    backend.updater = updater

    mqtt = MqttBridge(view=view, settings=settings)
    mqtt.start()
    threading.Thread(target=srv.run_photoframe, daemon=True).start()

    try:
        while view.get_is_running() and srv.get_is_running():
            if not view.process_events():
                break
            view.render_pending_frame()
            time.sleep(0.016)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        for obj in (mqtt, srv, view):
            try: obj.stop()
            except Exception: pass


def run_gui(settings: Dict[str, Any]) -> None:
    from PySide6 import QtCore, QtGui, QtWidgets
    from FrameGUI.photoframe_view_qt import PhotoFrameQtWidget
    from FrameServer.PhotoFrameServer import PhotoFrameServer
    from WebAPI.API import APIServer
    from Utilities.MQTT.mqtt_bridge import MqttBridge
    from Utilities.autoupdate_utils import AutoUpdater
    import signal

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DontUseNativeDialogs, True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    screen = app.primaryScreen()
    if not screen:
        print("[PhotoFrame] No display. Falling back to headless.", file=sys.stderr)
        run_headless(settings, None, None)
        return

    images_dir = settings.get("system", {}).get("image_dir")
    avail = screen.availableGeometry()
    sw, sh = max(1, avail.width()), max(1, avail.height())

    view = PhotoFrameQtWidget(settings=settings)
    view.showFullScreen()

    srv = PhotoFrameServer(width=sw, height=sh, iframe=view, images_dir=images_dir)
    backend = APIServer(frame=srv, image_dir=images_dir)
    threading.Thread(target=backend.start, daemon=True).start()
    srv.m_api = backend

    stop_event = threading.Event()
    au_cfg = settings.get("autoupdate", {})
    updater = AutoUpdater(stop_event=stop_event, interval_sec=1800,
                          restart_service_async=_restart_program,
                          auto_restart_on_update=au_cfg.get("enabled", True))
    updater.start()

    mqtt = MqttBridge(view=view, settings=settings)
    mqtt.start()
    view.backend = backend
    view.mqtt = mqtt
    view.updater = updater

    def _on_quit():
        stop_event.set()
        try: mqtt.stop()
        except Exception: pass
        try: srv.stop_services()
        except Exception: pass
    app.aboutToQuit.connect(_on_quit)

    threading.Thread(target=srv.run_photoframe, daemon=True).start()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec())
```

- [ ] **Step 2: Rewrite `app.py` as dispatch-only**

```python
#!/usr/bin/env python3
"""Digital Photo Frame — entry point."""
from __future__ import annotations
import argparse, os, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _abs_path(p: str) -> str:
    return p if os.path.isabs(p) else os.path.abspath(os.path.join(BASE_DIR, p))

def main() -> None:
    p = argparse.ArgumentParser(description="Digital Photo Frame")
    p.add_argument("--settings", default="photoframe_settings.json")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--display", choices=["pygame", "qt"])
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    args = p.parse_args()

    from Utilities.config_store import load_settings
    from Utilities import config_events
    settings = load_settings(json_path=_abs_path(args.settings))
    config_events.start_watcher()

    from app_modes import run_headless, run_pygame, run_gui

    if args.headless:
        run_headless(settings, args.width, args.height)
    elif args.display == "pygame":
        run_pygame(settings)
    elif args.display == "qt":
        run_gui(settings)
    else:
        try:
            import pygame  # noqa: F401
            run_pygame(settings)
        except ImportError:
            run_gui(settings)

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify**

```bash
env/bin/python app.py --headless &
sleep 3 && curl -s http://localhost:5002/ | head -3
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add app.py app_modes.py
git commit -m "refactor: extract display-mode runners into app_modes.py, app.py is now dispatch-only"
```

---

## Task 5: Rename `Backend` → `APIServer`

**Files:**
- Modify: `WebAPI/API.py`
- Modify: `app_modes.py`
- Modify: any other file that imports `Backend`

- [ ] **Step 1: Find all references**

```bash
grep -rn "Backend\b" --include="*.py" .
```

- [ ] **Step 2: Rename class in `WebAPI/API.py`**

```bash
# Rename class definition and any self-references
sed -i '' 's/class Backend(/class APIServer(/g' WebAPI/API.py
```

- [ ] **Step 3: Update all importers**

In every file that has `from WebAPI.API import Backend`:
```python
from WebAPI.API import APIServer
```

Replace `Backend(` with `APIServer(` in construction calls.

- [ ] **Step 4: Run tests**

```bash
env/bin/python -m pytest -v
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add WebAPI/API.py app_modes.py
git commit -m "refactor: rename Backend → APIServer for clarity"
```

---

## Task 6: Enforce module boundaries via Ruff

- [ ] **Step 1: Run Ruff**

```bash
env/bin/python -m ruff check . --select E,W,F,I
```

Fix any reported issues.

- [ ] **Step 2: Verify no FrameServer ↔ WebAPI cross-imports**

```bash
grep -rn "from WebAPI" FrameServer/ --include="*.py"
grep -rn "from FrameServer" WebAPI/ --include="*.py"
```
Expected: No results. If any found, replace with `config_store`/`config_events` calls.

- [ ] **Step 3: Verify no FrameGUI ↔ WebAPI cross-imports**

```bash
grep -rn "from WebAPI" FrameGUI/ --include="*.py"
grep -rn "from FrameGUI" WebAPI/ --include="*.py"
```
Expected: No results.

- [ ] **Step 4: Full test suite**

```bash
env/bin/python -m pytest -v
env/bin/python -m ruff check .
cd frontend && npm run lint && npm run build
```
Expected: All clean.

- [ ] **Step 5: Commit**

```bash
git add -p
git commit -m "refactor: enforce module boundaries, fix Ruff violations"
```

---

## Task 7: Final verification

- [ ] **Run all checks**

```bash
env/bin/python -m pytest -v
env/bin/python -m ruff check .
cd frontend && npm run lint && npm run build
```

- [ ] **Headless smoke test**

```bash
env/bin/python app.py --headless &
sleep 3
curl -s http://localhost:5002/ | head -5
kill %1
```

- [ ] **Confirm deleted file list**

```bash
git log --diff-filter=D --name-only --pretty="" | sort | uniq
```
Confirm: `Settings.py`, `iFrame.py`, `FrameGUI/SettingsFrom/model.py`, `users.json`, `WebAPI/templates/*` all appear.

- [ ] **Tag completion**

```bash
git tag v2.0.0-refactor
```
