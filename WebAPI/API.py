import shutil
import time
import os
import json
import hashlib
from datetime import datetime
from queue import Queue, Full, Empty
from threading import Thread, Event
from tqdm import tqdm

import cv2
from flask import (
    Flask,
    Response,
    jsonify,
    request,
    redirect,
    url_for,
    send_from_directory,
    render_template,
    flash,
    session,
    send_file,
    stream_with_context,
)
from numpy import ndarray
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import io
import zipfile
import platform
import requests
from PIL import Image, ImageOps
import threading
from flask_cors import CORS
import numpy as np
from numpy import ndarray
from iFrame import iFrame
from concurrent.futures import ThreadPoolExecutor
from WebAPI.WebUtils.auth_security import UserStore, ensure_csrf, validate_csrf, RateLimiter

# ---------------------------------------------------------------------
# HEIC support
# ---------------------------------------------------------------------

has_pillow_heif = False
has_pyheif = False

if platform.system() in ("Linux", "Darwin"):
    # pillow-heif >= 0.13: use register_heif_opener()
    try:
        from pillow_heif import register_heif_opener  # type: ignore

        register_heif_opener()
        has_pillow_heif = True
        print("[Backend] HEIF/HEIC plugin registered successfully (pillow-heif).")
    except Exception as e:
        print(f"[Backend] Could not register HEIF/HEIC plugin: {e}")
        has_pillow_heif = False

    # pyheif is optional, used only where you explicitly call it
    try:
        import pyheif  # type: ignore

        has_pyheif = True
    except ImportError:
        has_pyheif = False
else:
    # Windows or others: disable HEIF support here
    has_pillow_heif = False
    has_pyheif = False



# ---------------------------------------------------------------------
# Helpers for nested form parsing
# ---------------------------------------------------------------------

def _parse_value(s: str):
    if isinstance(s, bool):
        return s
    if not isinstance(s, str):
        return s
    v = s.strip()
    # checkbox pattern: "true"/"false", "on"/"off"
    if v.lower() in ("true", "on"):
        return True
    if v.lower() in ("false", "off"):
        return False
    # int
    try:
        if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
            return int(v)
    except Exception:
        pass
    # float
    try:
        return float(v)
    except Exception:
        return v


def _split_bracketed(key: str):
    # "a[b][c]" -> ["a","b","c"], "arr[0]" -> ["arr","0"]
    parts = []
    i = 0
    while i < len(key):
        j = key.find("[", i)
        if j == -1:
            parts.append(key[i:])
            break
        parts.append(key[i:j])
        k = key.find("]", j + 1)
        parts.append(key[j + 1:k])
        i = k + 1
    return [p for p in parts if p != ""]


def _assign_path(root, parts, value):
    """
    Assign value into root following parts (list). Numeric parts become list indices.
    Auto-creates dicts or lists as needed. Supports deep nesting.
    """
    cur = root
    for idx, part in enumerate(parts):
        is_last = idx == len(parts) - 1
        # list index?
        is_int = False
        try:
            i_part = int(part)
            is_int = True
        except Exception:
            i_part = None

        if is_last:
            if is_int:
                if not isinstance(cur, list):
                    # Caller should ensure containers are created correctly earlier.
                    # We do not try to repair arbitrary shape here.
                    return
                # ensure size
                while len(cur) <= i_part:
                    cur.append(None)
                cur[i_part] = value
            else:
                if isinstance(cur, list):
                    # Ambiguous, but treat as dict-like by appending a new dict with single key
                    cur.append({part: value})
                else:
                    cur[part] = value
            return

        # Not last: descend and create container if missing
        if is_int:
            # we need a list here
            if part == "" and isinstance(cur, list):
                nxt = {}
                cur.append(nxt)
                cur = nxt
                continue
            if not isinstance(cur, list):
                return
            while len(cur) <= i_part:
                cur.append({})
            if not isinstance(cur[i_part], (dict, list)):
                cur[i_part] = {}
            cur = cur[i_part]
        else:
            # dict branch
            if not isinstance(cur, dict):
                return
            if part not in cur or not isinstance(cur[part], (dict, list)):
                # Heuristic: if next token is int -> list; else dict
                nxt_is_int = False
                if idx + 1 < len(parts):
                    try:
                        _ = int(parts[idx + 1])
                        nxt_is_int = True
                    except Exception:
                        pass
                cur[part] = [] if nxt_is_int else {}
            cur = cur[part]


# ---------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------

class Backend:
    def __init__(self, frame: iFrame, settings, image_dir=None, settings_path=None):
        base = Path(__file__).parent
        self.app = Flask(
            __name__,
            template_folder=str(base / "./templates"),
            static_folder=str(base / "./static"),
        )
        CORS(self.app, supports_credentials=True)

        env_secret = os.getenv("PHOTOFRAME_SECRET_KEY")
        self.app.config.update(
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SECURE=False,  # set True when served over HTTPS or behind TLS terminator
            SESSION_COOKIE_SAMESITE="Lax",
            PERMANENT_SESSION_LIFETIME=3600,  # seconds
        )

        # Resolve paths early (do not depend on settings yet)
        self.USER_DATA_FILE = self.set_absolute_paths("users.json")
        self.METADATA_FILE = self.set_absolute_paths("metadata.json")
        self.LOG_FILE_PATH = self.set_absolute_paths("PhotoFrame.log")
        self.WEATHER_CACHE = self.set_absolute_paths("weather_cache.json")

        self._users = UserStore(self.USER_DATA_FILE)

        self._rl_login = RateLimiter(limit=10, window_sec=60)   # 10 attempts/min/IP
        self._rl_signup = RateLimiter(limit=5, window_sec=300)  # 5 attempts/5min/IP

        # Keep frame early for capture loop
        self.Frame = frame

        # Decide where to read/write settings.json
        if settings_path:
            self.SETTINGS_FILE = self.set_absolute_paths(settings_path)
        else:
            self.SETTINGS_FILE = self.set_absolute_paths("photoframe_settings.json")

        # Load settings: prefer the object passed from the server
        if settings:
            self.settings = settings
        else:
            self.settings = self.load_settings()

        # Compute IMAGE_DIR only after self.settings exists
        img_cfg = (
            image_dir
            or (self.settings.get("image_dir") if isinstance(self.settings, dict) else None)
            or (self.settings.get("images_dir") if isinstance(self.settings, dict) else None)
            or "Images"
        )
        self.IMAGE_DIR = self._resolve_dir(img_cfg)
        os.makedirs(self.IMAGE_DIR, exist_ok=True)
        print(f"[Backend] Using IMAGE_DIR = {self.IMAGE_DIR}")
        self.THUMB_DIR = os.path.join(os.path.dirname(self.IMAGE_DIR), "_thumbs")
        os.makedirs(self.THUMB_DIR, exist_ok=True)

        # Optional override for log file path from settings
        try:
            cfg_log_path = None
            if isinstance(self.settings, dict):
                cfg_log_path = self.settings.get("log_file_path")
            if cfg_log_path:
                # accept absolute path as-is; resolve relative via set_absolute_paths
                self.LOG_FILE_PATH = (
                    cfg_log_path
                    if os.path.isabs(cfg_log_path)
                    else self.set_absolute_paths(cfg_log_path)
                )
                # Ensure the file exists so /logs does not 404 if the directory is valid
                log_dir = os.path.dirname(self.LOG_FILE_PATH)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir, exist_ok=True)
                if not os.path.exists(self.LOG_FILE_PATH):
                    with open(self.LOG_FILE_PATH, "a", encoding="utf-8"):
                        pass
        except Exception as e:
            print(f"[Backend] Could not apply log_file_path override: {e}")

        # Now pull required keys with safe defaults
        backend_cfg = (
            self.settings.get("backend_configs")
            if isinstance(self.settings, dict)
            else getattr(self.settings, "get", lambda *_: {})("backend_configs")
        ) or {}
        self.app.secret_key = env_secret or backend_cfg.get("supersecretkey", "CHANGE_ME")
        self.stream_h = int(backend_cfg.get("stream_height", 1080))
        self.stream_w = int(backend_cfg.get("stream_width", 1920))
        self.port = int(backend_cfg.get("server_port", 5001))
        self.host = str(backend_cfg.get("host", "0.0.0.0"))

        self.ALLOWED_EXTENSIONS = {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".tiff",
            ".webp",
            ".heic",
            ".heif",
        }
        self.SELECTED_COLOR = "#ffcccc"

        self.latest_metadata = {}
        self._metadata_lock = threading.Lock()
        self._ensure_storage_files()
        self._normalize_existing_heic_images()

        # Encoding quality default
        self.encoding_quality = int(
            (self.settings.get("image_quality_encoding") if isinstance(self.settings, dict) else 80)
            or 80
        )

        self._jpeg_queue = Queue(maxsize=30)
        self._new_frame_ev = Event()
        self._stop_event = Event()

        self.executor = ThreadPoolExecutor(max_workers=2)
        self.setup_routes()
        Thread(target=self._capture_loop, daemon=True).start()

    # -----------------------------------------------------------------
    # Frame handling helpers
    # -----------------------------------------------------------------

    def _sanitize_frame(self, frame):
        """
        Normalize a frame to a uint8 BGR ndarray or return None if invalid.
        """
        if frame is None:
            return None

        if not isinstance(frame, np.ndarray):
            print(f"[Backend] _sanitize_frame: unexpected frame type: {type(frame)}")
            return None

        if frame.dtype == object:
            print(f"[Backend] _sanitize_frame: bad dtype=object, shape={frame.shape}")
            return None

        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        if frame.dtype != np.uint8:
            try:
                frame = frame.astype(np.uint8)
            except Exception as e:
                print(f"[Backend] _sanitize_frame: cannot cast dtype {frame.dtype} to uint8: {e}")
                return None

        return frame

    def _client_ip(self) -> str:
        # honor reverse proxy if you have one (ensure you trust it)
        return (
            request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
            .split(",")[0]
            .strip()
        )

    def _rotate_session(self, username: str, uid: str, role: str) -> None:
        # Clear, set new identity, and new CSRF
        session.clear()
        session["uid"] = uid
        session["user"] = username
        session["role"] = role
        ensure_csrf(session)

    def _require_csrf(self) -> None:
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not validate_csrf(session, token):
            # Keep message generic
            raise PermissionError("Invalid request")

    # -----------------------------------------------------------------
    # Paths and storage
    # -----------------------------------------------------------------

    def _resolve_dir(self, p: str) -> str:
        pth = Path(p).expanduser()
        if not pth.is_absolute():
            app_root = Path(__file__).resolve().parents[1]  # project root (two levels up)
            pth = app_root / pth
        return str(pth)

    def set_absolute_paths(self, path: str) -> str:
        if os.path.isabs(path):
            return os.path.abspath(path)
        base = os.path.dirname(os.path.dirname(__file__))  # DesktopApp root
        return os.path.abspath(os.path.join(base, path))

    def _ensure_storage_files(self) -> None:
        os.makedirs(self.IMAGE_DIR, exist_ok=True)

        for path, default in [
            (self.USER_DATA_FILE, {}),
            (self.METADATA_FILE, {}),
            (self.SETTINGS_FILE, {}),
            (self.LOG_FILE_PATH, ""),
        ]:
            try:
                d = os.path.dirname(path)
                if d and not os.path.exists(d):
                    os.makedirs(d, exist_ok=True)
                if not os.path.exists(path):
                    with open(path, "w", encoding="utf-8") as f:
                        if isinstance(default, dict):
                            json.dump(default, f, indent=4)
                        else:
                            f.write(default)
            except Exception as e:
                print(f"[Backend] Could not initialize {path}: {e}")

    # -----------------------------------------------------------------
    # Capture loop
    # -----------------------------------------------------------------

    def _is_valid_frame(self, frame) -> bool:
        if not isinstance(frame, ndarray):
            return False
        if frame.dtype == object:
            print(f"[Backend] _capture_loop: got dtype=object, shape={frame.shape}, skipping")
            return False
        if frame.ndim not in (2, 3):
            print(f"[Backend] _capture_loop: unexpected ndim={frame.ndim}, shape={frame.shape}")
            return False
        return True

    def _capture_loop(self):
        idle_fps = float(self.settings.get("backend_configs", {}).get("idle_fps", 5)) or 5.0
        interval = 1.0 / max(0.1, idle_fps)

        last_jpeg = self._make_heartbeat_jpeg(self.stream_w, self.stream_h)
        next_deadline = time.perf_counter()

        print(f"[Backend] capture loop started (idle_fps={idle_fps})")

        while not self._stop_event.is_set() and self.Frame.get_is_running():
            timeout = max(0.0, next_deadline - time.perf_counter())
            got_new = self._new_frame_ev.wait(timeout=timeout)
            if got_new:
                self._new_frame_ev.clear()
                frame = self.Frame.get_live_frame()
                # try:
                #     print(
                #         f"[Backend] got frame: type={type(frame)}, "
                #         f"dtype={getattr(frame, 'dtype', None)}, "
                #         f"shape={getattr(frame, 'shape', None)}"
                #     )
                # except Exception:
                #     pass

                if self._is_valid_frame(frame):
                    if frame.ndim == 2:
                        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                    elif frame.ndim == 3 and frame.shape[2] == 4:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    if frame.dtype != np.uint8:
                        try:
                            frame = frame.astype(np.uint8)
                        except Exception as e:
                            print(f"[Backend] cannot cast frame dtype {frame.dtype} to uint8: {e}")
                            frame = None

                    if frame is not None:
                        ok, jpg = cv2.imencode(
                            ".jpg",
                            frame,
                            [cv2.IMWRITE_JPEG_QUALITY, self.encoding_quality],
                        )
                        if ok:
                            last_jpeg = jpg.tobytes()

            now = time.perf_counter()
            if now >= next_deadline:
                # Always have something to send
                if last_jpeg is None:
                    last_jpeg = self._make_heartbeat_jpeg(self.stream_w, self.stream_h)

                try:
                    self._jpeg_queue.put_nowait(last_jpeg)
                except Full:
                    try:
                        _ = self._jpeg_queue.get_nowait()
                    except Exception:
                        pass
                    try:
                        self._jpeg_queue.put_nowait(last_jpeg)
                    except Exception:
                        pass

                next_deadline = now + interval

    def _encode_and_queue(self, frame: ndarray):
        frame = self._sanitize_frame(frame)
        if frame is None:
            return
        success, jpg = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, self.encoding_quality],
        )
        if not success:
            return
        data = jpg.tobytes()
        try:
            self._jpeg_queue.put_nowait(data)
        except Full:
            _ = self._jpeg_queue.get_nowait()
            self._jpeg_queue.put_nowait(data)

    # -----------------------------------------------------------------
    # Settings / users / metadata
    # -----------------------------------------------------------------

    def load_settings(self):
        try:
            with open(self.SETTINGS_FILE, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            print(
                f"[Backend] Settings file not found: {self.SETTINGS_FILE}. "
                f"Starting with empty settings."
            )
            return {}
        except json.JSONDecodeError as e:
            print(
                f"[Backend] Invalid JSON in settings file {self.SETTINGS_FILE}: {e}. "
                f"Starting with empty settings."
            )
            return {}
        except Exception as e:
            print(f"[Backend] Unexpected error reading settings: {e}. Starting with empty settings.")
            return {}

    def save_settings(self, data):
        if not os.path.exists(self.SETTINGS_FILE):
            os.makedirs(os.path.dirname(self.SETTINGS_FILE), exist_ok=True)

        with open(self.SETTINGS_FILE, "w") as file:
            json.dump(data, file, indent=4)

    def allowed_file(self, filename):
        return "." in filename and Path(filename).suffix.lower() in self.ALLOWED_EXTENSIONS

    def get_images_from_directory(self):
        return [
            entry.name
            for entry in Path(self.IMAGE_DIR).iterdir()
            if entry.is_file() and self.allowed_file(entry.name)
        ]

    def load_users(self):
        try:
            with open(self.USER_DATA_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            users = {}
            self.save_users(users)
            return users

    def save_users(self, users):
        with open(self.USER_DATA_FILE, "w") as file:
            json.dump(users, file, indent=4)

    def is_authenticated(self) -> bool:
        return "uid" in session and "user" in session

    def load_metadata_db(self):
        try:
            with open(self.METADATA_FILE, "r", encoding="utf-8") as f:
                if os.path.getsize(self.METADATA_FILE) == 0:
                    return {}
                return json.load(f)
        except FileNotFoundError:
            # Create file and return empty
            self._ensure_storage_files()
            return {}
        except json.JSONDecodeError:
            print(f"[Backend] metadata.json is invalid JSON. Resetting to empty dict.")
            try:
                with open(self.METADATA_FILE, "w", encoding="utf-8") as f:
                    json.dump({}, f)
            except Exception:
                pass
            return {}
        except Exception as e:
            print(f"[Backend] load_metadata_db failed: {e}")
            return {}

    def save_metadata_db(self, data):
        try:
            d = os.path.dirname(self.METADATA_FILE)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Backend] save_metadata_db failed: {e}")

    def compute_image_hash(self, image_path):
        hash_obj = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    # -----------------------------------------------------------------
    # Metadata update APIs (shared with older code)
    # -----------------------------------------------------------------

    def update_image_metadata(self, image_path):
        """
        Updates the metadata database for an image.
        If the image hash already exists, it reads the existing entry without overwriting
        user-updated fields. If the image hash is not present, it creates a new entry.
        """
        metadata_file = self.METADATA_FILE
        image_hash = self.compute_image_hash(image_path)
        new_entry = {
            "hash": image_hash,
            "filename": os.path.basename(image_path),
            "uploader": "unknown",
            "date_added": datetime.now().isoformat(),
            "caption": "",
        }

        try:
            # Load existing metadata from the JSON file
            if os.path.exists(metadata_file) and os.path.getsize(metadata_file) > 0:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {}

            # Only write a new entry if the image hash does not exist
            if image_hash in data:
                entry = data[image_hash]
            else:
                data[image_hash] = new_entry
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                entry = new_entry
        except Exception as e:
            print(f"Error updating image DB: {e}")
            entry = new_entry

        self.update_current_metadata(entry)

    def store_image_metadata(self, image_path):
        """
        Backwards-compatible wrapper for older code paths that used
        store_image_metadata(). Delegates to update_image_metadata().
        """
        self.update_image_metadata(image_path)

    # -----------------------------------------------------------------
    # Streaming helpers
    # -----------------------------------------------------------------

    def mjpeg_stream(self, screen_w, screen_h):
        boundary_line = b"--frame\r\n"
        while self.Frame.get_is_running():
            data = self._jpeg_queue.get()  # block; producer ticks at idle_fps
            yield (
                boundary_line
                + b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
                + data
                + b"\r\n"
            )

    def _thumb_path(self, filename: str, w: int) -> str:
        base, _ = os.path.splitext(filename)
        safe = base.replace(os.sep, "_")
        return os.path.join(self.THUMB_DIR, f"{safe}_w{w}.webp")

    def _make_thumb(self, src_path: str, dst_path: str, w: int) -> None:
        with Image.open(src_path) as im:
            # honor EXIF orientation
            im = ImageOps.exif_transpose(im)
            # resize preserving aspect ratio
            ratio = w / float(im.width)
            h = max(1, int(im.height * ratio))
            im = im.resize((w, h), Image.Resampling.LANCZOS)
            # write as WEBP for small thumbs
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            im.save(dst_path, "WEBP", quality=75, method=6)

    def _make_heartbeat_jpeg(self, w, h):
        """
        Return a small 'no frame' JPEG so the client keeps the stream open.
        """
        try:
            img = np.zeros(
                (max(120, min(h, 360)), max(160, min(w, 640)), 3),
                dtype="uint8",
            )
            # Gray background with text
            img[:] = (32, 32, 32)
            cv2.putText(
                img,
                "Waiting for frames...",
                (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (200, 200, 200),
                2,
                cv2.LINE_AA,
            )
            ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                return jpg.tobytes()
        except Exception as e:
            print(f"[Backend] heartbeat build failed: {e}")
        # Fallback tiny JPEG header if something goes wrong
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00"
            + b"\x08" * 64
            + b"\xff\xc0\x00\x11\x08\x00\x10\x00\x10\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
            b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00"
            + b"\x00" * 10
            + b"\xff\xd9"
        )

    # -----------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------

    def setup_routes(self):
        @self.app.context_processor
        def inject_csrf():
            return {"csrf_token": lambda: ensure_csrf(session)}

        @self.app.before_request
        def _csrf_for_all_posts():
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                # allow this one POST endpoint without CSRF
                if request.path == "/heic_preview":
                    return None
                try:
                    self._require_csrf()
                except Exception:
                    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                        return jsonify({"error": "Bad request."}), 400
                    flash("Invalid request.", "error")
                    return redirect(request.referrer or url_for("index"))

        @self.app.after_request
        def add_security_headers(resp):
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["Referrer-Policy"] = "same-origin"
            resp.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' data: blob: http: https:; "
                "script-src 'self' https://unpkg.com 'unsafe-eval' 'wasm-unsafe-eval'; "
                "worker-src 'self' blob:; "
                "connect-src 'self' blob:; "
                "style-src 'self' 'unsafe-inline'; "
                "frame-ancestors 'none';"
            )
            return resp

        @self.app.route("/stream")
        def stream():
            default_w, default_h = 1920, 1080
            try:
                w = int(request.args.get("width", default_w))
                h = int(request.args.get("height", default_h))
            except ValueError:
                w, h = default_w, default_h

            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
            return Response(
                stream_with_context(self.mjpeg_stream(w, h)),
                mimetype="multipart/x-mixed-replace; boundary=frame",
                headers=headers,
                direct_passthrough=True,
            )

        @self.app.route("/stream_test")
        def stream_test():
            boundary_line = b"--frame\r\n"

            def gen():
                w, h = 640, 360
                t = 0
                while True:
                    bars = np.zeros((h, w, 3), dtype="uint8")
                    for i, c in enumerate(
                        [
                            (255, 0, 0),
                            (0, 255, 0),
                            (0, 0, 255),
                            (255, 255, 0),
                            (0, 255, 255),
                            (255, 0, 255),
                        ]
                    ):
                        x0 = int(i * w / 6)
                        x1 = int((i + 1) * w / 6)
                        bars[:, x0:x1, :] = c
                    cv2.putText(
                        bars,
                        f"TEST STREAM t={t}",
                        (10, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (20, 20, 20),
                        2,
                        cv2.LINE_AA,
                    )
                    ok, jpg = cv2.imencode(".jpg", bars, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    data = jpg.tobytes() if ok else b""
                    yield (
                        boundary_line
                        + b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
                        + data
                        + b"\r\n"
                    )
                    t += 1
                    time.sleep(0.2)

            return Response(
                gen(),
                mimetype="multipart/x-mixed-replace; boundary=frame",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        @self.app.route("/heic_preview", methods=["POST"])
        def heic_preview():
            if not self.is_authenticated():
                return jsonify({"error": "unauthorized"}), 401

            f = request.files.get("file")
            if f is None:
                return jsonify({"error": "no file"}), 400

            data = f.read()
            if not data:
                return jsonify({"error": "empty file"}), 400

            # Try Pillow with pillow-heif only.
            # We explicitly DO NOT fallback to pyheif (it is broken in this env).
            try:
                if "has_pillow_heif" in globals() and has_pillow_heif:
                    img = Image.open(io.BytesIO(data))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    buf.seek(0)
                    return send_file(buf, mimetype="image/jpeg")
            except Exception as e:
                # Pillow + pillow-heif failed
                return jsonify({"error": f"server HEIC decode unavailable: {e}"}), 501

            # No pillow-heif installed / registered
            return jsonify({"error": "server HEIC decode unavailable"}), 501


        @self.app.route("/system_stats")
        def system_stats():
            import psutil

            try:
                cpu_usage = int(psutil.cpu_percent(interval=None))
                ram = psutil.virtual_memory()
                ram_used = ram.used // (1024 * 1024)
                ram_total = ram.total // (1024 * 1024)
                ram_percent = ram.percent
                try:
                    cpu_temps = psutil.sensors_temperatures().get("cpu_thermal", [])
                    cpu_temp = round(cpu_temps[0].current, 1) if cpu_temps else "N/A"
                except Exception:
                    cpu_temp = "N/A"

                return (
                    f"CPU: {cpu_usage}%\n"
                    f"RAM: {ram_percent}% ({ram_used}/{ram_total}MB)\n"
                    f"CPU Temp: {cpu_temp}C"
                )
            except Exception:
                return "Stats unavailable", 500

        @self.app.route("/settings")
        def serve_settings():
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    return jsonify(json.load(f))
            except Exception as e:
                return jsonify({"error": "Failed to read settings", "details": str(e)}), 500

        @self.app.route("/current_weather")
        def current_weather():
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    settings = json.load(f)

                api_key = settings.get("weather_api_key")
                location_key = settings.get("location_key")

                if not api_key or not location_key:
                    return jsonify(
                        {
                            "temp": "N/A",
                            "unit": "C",
                            "description": "Weather unavailable",
                            "icon_url": None,
                        }
                    ), 400

                url = (
                    f"http://dataservice.accuweather.com/currentconditions/v1/"
                    f"{location_key}?apikey={api_key}&details=true"
                )

                try:
                    response = requests.get(url)
                    data = response.json()

                    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
                        raise ValueError("Unexpected API response")

                    w = data[0]
                    temp = w.get("Temperature", {}).get("Metric", {}).get("Value")
                    unit = w.get("Temperature", {}).get("Metric", {}).get("Unit", "C")
                    description = w.get("WeatherText", "")
                    icon = int(w.get("WeatherIcon", 0))
                    icon_url = (
                        "https://developer.accuweather.com/sites/default/files/"
                        f"{icon:02d}-s.png"
                    )

                    weather = {
                        "temp": round(temp) if isinstance(temp, (int, float)) else "N/A",
                        "unit": unit,
                        "description": description,
                        "icon_url": icon_url,
                    }

                    with open(self.WEATHER_CACHE, "w") as f:
                        json.dump(
                            {
                                "timestamp": datetime.now().isoformat(),
                                "weather_data": weather,
                            },
                            f,
                        )

                    print("INFO - Weather icon successfully fetched.")
                    return jsonify(weather)

                except Exception as live_error:
                    print("ERROR - Weather fetch failed:", live_error)

                    # Fallback to cache
                    if os.path.exists(self.WEATHER_CACHE):
                        with open(self.WEATHER_CACHE, "r") as f:
                            cached = json.load(f)
                            weather = cached.get("weather_data", {})
                            if "icon_url" not in weather and "icon" in weather:
                                icon = weather["icon"]
                                weather["icon_url"] = (
                                    "https://developer.accuweather.com/sites/default/files/"
                                    f"{icon:02d}-s.png"
                                )

                            if all(
                                k in weather
                                for k in ("temp", "unit", "description", "icon_url")
                            ):
                                print(
                                    "INFO - Serving weather from fallback cache:",
                                    weather,
                                )
                                return jsonify(weather), 200

                    return jsonify(
                        {
                            "temp": "N/A",
                            "unit": "C",
                            "description": "Weather unavailable",
                            "icon_url": None,
                        }
                    ), 503

            except Exception as e:
                print("ERROR - Unexpected exception in weather route:", e)
                return jsonify(
                    {
                        "temp": "N/A",
                        "unit": "C",
                        "description": "Weather unavailable",
                        "icon_url": None,
                    }
                ), 500

        @self.app.route("/current_metadata")
        def current_metadata():
            with self._metadata_lock:
                return jsonify(self.latest_metadata or {})

        @self.app.route("/metadata_stream")
        def metadata_stream():
            def gen():
                last = None
                while True:
                    with self._metadata_lock:
                        meta = self.latest_metadata
                    if meta != last:
                        yield f"data: {json.dumps(meta)}\n\n"
                        last = meta.copy() if isinstance(meta, dict) else meta
                    time.sleep(0.1)

            return Response(gen(), mimetype="text/event-stream")

        @self.app.route("/upload_with_metadata", methods=["POST"])
        def upload_with_metadata():
            if not self.is_authenticated():
                return redirect(url_for("login"))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400

            uploaded_files = request.files.getlist("file[]")
            if not uploaded_files:
                return jsonify({"message": "No files uploaded"}), 400

            metadata_db = self.load_metadata_db()

            for idx, file in enumerate(uploaded_files):
                if not file or file.filename == "":
                    continue

                original_filename = file.filename
                ext = os.path.splitext(original_filename)[1].lower()
                if ext not in self.ALLOWED_EXTENSIONS:
                    continue

                caption = request.form.get(f"caption_{idx}", "").strip()
                uploader = request.form.get(f"uploader_{idx}", "").strip()

                temp_path = os.path.join(self.IMAGE_DIR, original_filename)
                try:
                    file.save(temp_path)
                except Exception as e:
                    self.Frame.send_log_message(f"{e}")
                    return jsonify({"message": f"{e}"}), 500

                final_path = temp_path
                if ext in (".heic", ".heif"):
                    # Always normalize HEIC/HEIF to PNG on disk
                    png_path = os.path.splitext(final_path)[0] + ".png"
                    final_path = self.convert_heic_to_png(final_path, png_path)
                    original_filename = os.path.basename(final_path)


                file_hash = self.compute_image_hash(final_path)

                metadata = {
                    "hash": file_hash,
                    "caption": caption,
                    "uploader": uploader,
                    "date_added": datetime.utcnow().isoformat(),
                    "filename": original_filename,
                }
                metadata_db[file_hash] = metadata

            self.save_metadata_db(metadata_db)
            self.Frame.update_images_list()
            return jsonify({"message": "Upload successful"}), 200

        @self.app.route("/thumb/<path:filename>")
        def thumb(filename):
            if not self.is_authenticated():
                return redirect(url_for("login"))

            src_path = os.path.join(self.IMAGE_DIR, filename)
            root_real = os.path.realpath(self.IMAGE_DIR)
            path_real = os.path.realpath(src_path)
            if not (os.path.isfile(src_path) and os.path.commonpath([root_real, path_real]) == root_real):
                return jsonify({"error": "File not found"}), 404

            try:
                w = int(request.args.get("w", 320))
                w = max(64, min(w, 1920))
            except Exception:
                w = 320

            dst_path = self._thumb_path(filename, w)

            try:
                if (not os.path.exists(dst_path)) or (
                    os.path.getmtime(dst_path) < os.path.getmtime(src_path)
                ):
                    self._make_thumb(src_path, dst_path, w)
            except Exception:
                return send_from_directory(self.IMAGE_DIR, filename)

            resp = send_file(dst_path, mimetype="image/webp", conditional=True)
            resp.headers["Cache-Control"] = "public, max-age=2592000, immutable"
            return resp

        @self.app.route("/signup", methods=["GET", "POST"])
        def signup():
            from WebAPI.WebUtils.auth_security import EMAIL_RE, USERNAME_RE, password_policy_ok

            if request.method == "POST":
                if not self._rl_signup.allow(self._client_ip()):
                    flash("Please wait before trying again.", "error")
                    return redirect(url_for("signup"))

                try:
                    self._require_csrf()
                except Exception:
                    flash("Invalid request.", "error")
                    return redirect(url_for("signup"))

                email = (request.form.get("email") or "").strip().lower()
                username = (request.form.get("username") or "").strip()
                password = request.form.get("password") or ""

                if not password_policy_ok(password):
                    flash(
                        "Password does not meet policy. Use 10+ chars and include at least 3 of: "
                        "lowercase, uppercase, digits, symbols.",
                        "error",
                    )
                    return render_template(
                        "signup.html",
                        email=request.args.get("email", ""),
                        username=request.args.get("username", ""),
                    )

                if not (EMAIL_RE.match(email) and USERNAME_RE.match(username)):
                    flash("Invalid input.", "error")
                    return redirect(url_for("signup"))

                try:
                    uid = self._users.create_user(
                        email=email,
                        username=username,
                        password=password,
                        role="user",
                    )
                except ValueError:
                    flash("Cannot create account.", "error")
                    return redirect(url_for("signup"))
                except Exception:
                    flash("Cannot create account.", "error")
                    return redirect(url_for("signup"))

                flash("Signup successful. Please log in.", "success")
                return redirect(url_for("login"))

            return render_template("signup.html")

        @self.app.route("/login", methods=["GET", "POST"])
        def login():
            if request.method == "POST":
                if not self._rl_login.allow(self._client_ip()):
                    flash("Invalid credentials.")
                    return redirect(url_for("login"))

                try:
                    self._require_csrf()
                except Exception:
                    flash("Invalid credentials.")
                    return redirect(url_for("login"))

                identity = (request.form.get("email_or_username") or "").strip()
                password = request.form.get("password") or ""
                user = self._users.verify_login(identity, password)
                if not user or not user.get("is_active", True):
                    flash("Invalid credentials.")
                    return redirect(url_for("login"))

                self._rotate_session(user["username"], user["uid"], user.get("role", "user"))
                flash("Login successful!")
                return redirect(url_for("index"))
            return render_template("login.html")

        @self.app.route("/logout", methods=["POST", "GET"])
        def logout():
            if request.method == "POST":
                try:
                    self._require_csrf()
                except Exception:
                    pass
            session.clear()
            flash("You have been logged out.")
            return redirect(url_for("login"))

        @self.app.route("/")
        def index():
            if not self.is_authenticated():
                return redirect(url_for("login"))

            images = self.get_images_from_directory()
            image_count = len(images)
            settings = self.load_settings()

            metadata_db = self.load_metadata_db()

            def _date_for_filename(fn: str) -> str:
                for meta in metadata_db.values():
                    if meta.get("filename") == fn and meta.get("date_added"):
                        return meta["date_added"]
                fp = os.path.join(self.IMAGE_DIR, fn)
                try:
                    ts = os.path.getmtime(fp)
                    return datetime.fromtimestamp(ts).isoformat()
                except Exception:
                    return ""

            images_data = [{"name": fn, "date_added": _date_for_filename(fn)} for fn in images]

            latest_metadata = {}
            if images:
                first = images[0]
                entry = None
                for meta in metadata_db.values():
                    if meta.get("filename") == first:
                        entry = meta
                        break
                if entry:
                    latest_metadata = entry

            username = session.get("user", "Guest")
            return render_template(
                "index.html",
                images=images,
                images_data=images_data,
                image_count=image_count,
                settings=settings,
                latest_metadata=latest_metadata,
                username=username,
            )

        @self.app.route("/get_latest_metadata")
        def latest_metadata():
            return jsonify(self.latest_metadata)

        @self.app.route("/save_settings", methods=["POST"])
        def save_settings_route():
            if not self.is_authenticated():
                return redirect(url_for("login"))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400

            try:
                nested = {}

                for k in request.form:
                    if k == "csrf_token":
                        continue
                    values = request.form.getlist(k)
                    for v in values:
                        parts = _split_bracketed(k)
                        _assign_path(nested, parts, _parse_value(v))

                self.save_settings(nested)
                flash("Settings updated successfully.")
            except Exception as e:
                flash(f"Failed to update settings: {e}")
            return redirect(url_for("index"))

        @self.app.route("/images/<path:filename>")
        def serve_image(filename):
            if not self.is_authenticated():
                return redirect(url_for("login"))
            return send_from_directory(self.IMAGE_DIR, filename)

        @self.app.route("/upload", methods=["POST"])
        def upload_files():
            if not self.is_authenticated():
                return redirect(url_for("login"))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400

            if "file[]" not in request.files:
                flash("No file part")
                return redirect(url_for("index"))

            files = request.files.getlist("file[]")
            for file in files:
                if file and self.allowed_file(file.filename):
                    file_path = os.path.join(self.IMAGE_DIR, file.filename)
                    file_extension = Path(file.filename).suffix.lower()
                    file.save(file_path)
                    if file_extension in {".heic", ".heif"}:
                        # Normalize HEIC/HEIF to PNG and delete the HEIC
                        png_path = os.path.splitext(file_path)[0] + ".png"
                        file_path = self.convert_heic_to_png(file_path, png_path)
                    self.store_image_metadata(file_path)
            return redirect(url_for("index"))


        @self.app.route("/delete/<filename>", methods=["POST"])
        def delete_image(filename):
            if not self.is_authenticated():
                return redirect(url_for("login"))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400

            try:
                os.remove(os.path.join(self.IMAGE_DIR, filename))
                flash(f"File {filename} successfully deleted.")
            except FileNotFoundError:
                flash(f"File {filename} not found.")
            return redirect(url_for("index"))

        @self.app.route("/download/<filename>")
        def download_image(filename):
            if not self.is_authenticated():
                return redirect(url_for("login"))
            return send_from_directory(self.IMAGE_DIR, filename, as_attachment=True)

        @self.app.route("/delete_selected", methods=["POST"])
        def delete_selected():
            if not self.is_authenticated():
                return redirect(url_for("login"))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400

            selected_files = request.form.getlist("selected_files")
            for filename in selected_files:
                try:
                    os.remove(os.path.join(self.IMAGE_DIR, filename))
                    flash(f"File {filename} successfully deleted.")
                except FileNotFoundError:
                    flash(f"File {filename} not found.")
            return redirect(url_for("index"))

        @self.app.route("/download_selected", methods=["POST"])
        def download_selected():
            if not self.is_authenticated():
                return redirect(url_for("login"))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400

            selected_files = request.form.getlist("selected_files")
            if not selected_files:
                flash("No files selected for download.")
                return redirect(url_for("index"))

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for filename in selected_files:
                    filepath = os.path.join(self.IMAGE_DIR, filename)
                    if os.path.isfile(filepath):
                        zipf.write(filepath, arcname=filename)
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                download_name="selected_images.zip",
                as_attachment=True,
            )

        @self.app.route("/download_logs")
        def download_logs():
            try:
                return send_file(
                    self.LOG_FILE_PATH,
                    as_attachment=True,
                    download_name="PhotoFrame.log",
                )
            except FileNotFoundError:
                return jsonify({"error": "Log file not found"}), 404
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/logs", methods=["GET"])
        def get_logs():
            try:
                with open(self.LOG_FILE_PATH, "r") as log_file:
                    logs = log_file.readlines()
                return jsonify({"logs": logs}), 200
            except FileNotFoundError:
                return jsonify({"error": "Log file not found"}), 404
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/stream_logs")
        def stream_logs():
            def generate_logs():
                with open(self.LOG_FILE_PATH, "r") as log_file:
                    log_file.seek(0)
                    for line in log_file:
                        yield f"data: {line}\n\n"
                    log_file.seek(0, os.SEEK_END)
                    while True:
                        line = log_file.readline()
                        if line:
                            yield f"data: {line}\n\n"
                        time.sleep(1)

            return Response(generate_logs(), content_type="text/event-stream")

        @self.app.route("/clear_logs", methods=["POST"])
        def clear_logs():
            if not self.is_authenticated():
                return redirect(url_for("login"))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400

            try:
                with open(self.LOG_FILE_PATH, "w") as log_file:
                    log_file.truncate(0)
                return jsonify({"message": "Log file cleared successfully."}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/image_metadata")
        def get_image_metadata():
            filename = request.args.get("filename")
            if not filename:
                return jsonify({"error": "Filename not provided."}), 400

            filepath = os.path.join(self.IMAGE_DIR, filename)
            if not os.path.exists(filepath):
                return jsonify({"error": "File not found."}), 404

            metadata_db = self.load_metadata_db()

            # Try to find metadata by filename
            for meta in metadata_db.values():
                if meta.get("filename") == filename:
                    return jsonify(meta)

            # If metadata does not exist, add it and then return it
            self.store_image_metadata(filepath)
            metadata_db = self.load_metadata_db()
            file_hash = self.compute_image_hash(filepath)
            return jsonify(metadata_db.get(file_hash, {}))

        @self.app.route("/update_metadata", methods=["POST"])
        def update_metadata():
            if not self.is_authenticated():
                return redirect(url_for("login"))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400

            data = request.get_json(force=True, silent=True) or {}
            file_hash = data.get("hash")
            caption = data.get("caption", "")
            uploader = data.get("uploader")

            if not file_hash:
                return jsonify({"error": "Hash not provided."}), 400

            metadata_db = self.load_metadata_db()

            if file_hash not in metadata_db:
                return jsonify({"error": "Metadata not found for this hash."}), 404

            metadata_db[file_hash]["caption"] = caption
            if uploader is not None:
                metadata_db[file_hash]["uploader"] = uploader

            self.save_metadata_db(metadata_db)

            self.latest_metadata = metadata_db[file_hash]
            return jsonify({"message": "Metadata updated successfully."})

    # -----------------------------------------------------------------
    # HEIC conversion
    # -----------------------------------------------------------------

    def _normalize_existing_heic_images(self) -> None:
        """
        Scan IMAGE_DIR for any .heic/.heif files and convert them to PNG.
        New PNG keeps the same basename, original HEIC is removed on success.
        Also ensures metadata is stored for the converted image.

        This runs once at backend startup and prints a tqdm progress bar.
        """
        try:
            img_dir = Path(self.IMAGE_DIR)
            if not img_dir.is_dir():
                print(f"[Backend] IMAGE_DIR does not exist or is not a directory: {img_dir}")
                return

            # Collect all HEIC/HEIF files recursively
            heic_files = [
                p for p in img_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in (".heic", ".heif")
            ]

            if not heic_files:
                print(f"[Backend] No HEIC/HEIF images to normalize under {img_dir}.")
                return

            print(
                f"[Backend] Normalizing {len(heic_files)} HEIC/HEIF image(s) "
                f"to PNG under {img_dir}..."
            )

            for entry in tqdm(heic_files, desc="HEIC->PNG", unit="img"):
                heic_path = str(entry)
                png_path = os.path.splitext(heic_path)[0] + ".png"

                # This uses your convert_heic_to_png(), which already:
                #  - uses pillow-heif if available
                #  - does NOT fallback to pyheif
                #  - deletes the HEIC on success
                out_path = self.convert_heic_to_png(heic_path, png_path)

                # If conversion succeeded (path changed and file exists),
                # ensure metadata exists for the new PNG.
                if out_path != heic_path and os.path.exists(out_path):
                    try:
                        self.store_image_metadata(out_path)
                    except Exception as e:
                        print(f"[Backend] Could not update metadata for {out_path}: {e}")

            print("[Backend] HEIC normalization complete.")

        except Exception as e:
            print(f"[Backend] normalize_existing_heic_images failed: {e}")


    def convert_heic_to_png(self, heic_path: str, output_path: str | None = None) -> str:
        """
        Convert HEIC/HEIF to PNG using pillow-heif (if available).
        On success, removes the original HEIC file and returns the PNG path.
        On failure, keeps the original HEIC file and returns the original path.
        """
        if output_path is None:
            base, _ = os.path.splitext(heic_path)
            output_path = base + ".png"

        # 1) Try Pillow with pillow-heif registration
        try:
            if "has_pillow_heif" in globals() and has_pillow_heif:
                img = Image.open(heic_path)
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass
                img = img.convert("RGB")
                img.save(output_path, format="PNG")
                os.remove(heic_path)
                print(f"[Backend] Converted HEIC -> PNG: {heic_path} -> {output_path}")
                return output_path
        except Exception as e:
            print(f"[Backend] HEIC->PNG via Pillow failed: {e}")

        # Do NOT fall back to pyheif – your environment is broken there.
        print("[Backend] HEIC conversion unavailable; keeping original file.")
        return heic_path

    # -----------------------------------------------------------------
    # Metadata broadcast
    # -----------------------------------------------------------------

    def update_current_metadata(self, metadata):
        """
        Update the latest metadata stored in the backend.
        This method can be called by other parts of your application
        (like PhotoFrameServer.py) to update metadata.
        """
        with self._metadata_lock:
            self.latest_metadata = metadata

    # -----------------------------------------------------------------
    # Start server
    # -----------------------------------------------------------------

    def start(self):
        self.app.run(
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )


if __name__ == "__main__":
    # For direct debugging; in production app.py will construct Backend(frame=...)
    backend = Backend(frame=None, settings={})  # frame/settings will be overridden in real usage
    backend.start()
    while True:
        time.sleep(10)
