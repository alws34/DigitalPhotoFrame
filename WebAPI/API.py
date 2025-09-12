import shutil
import time
import os
import json
import hashlib
from datetime import datetime
from queue import Queue, Full, Empty
from threading import Thread, Event
import cv2
from flask import Flask, Response, jsonify, request, redirect, url_for, send_from_directory, render_template, flash, session, send_file, stream_with_context
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
from iFrame import iFrame
from concurrent.futures import ThreadPoolExecutor
from WebAPI.WebUtils.auth_security import UserStore, ensure_csrf, validate_csrf, RateLimiter

if platform.system() == "Linux" or platform.system() == "Darwin":
    try:
        import pyheif
        has_pyheif = True
    except ImportError:
        has_pyheif = False
else:
    has_pyheif = False

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
        self.METADATA_FILE  = self.set_absolute_paths("metadata.json")
        self.LOG_FILE_PATH  = self.set_absolute_paths("PhotoFrame.log")
        self.WEATHER_CACHE  = self.set_absolute_paths("weather_cache.json")
        
        self._users = UserStore(self.USER_DATA_FILE)
        
        self._rl_login  = RateLimiter(limit=10, window_sec=60)   # 10 attempts/min/IP
        self._rl_signup = RateLimiter(limit=5, window_sec=300)   # 5 attempts/5min/IP

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


        # Now pull required keys with safe defaults
        backend_cfg = (
            self.settings.get("backend_configs")
            if isinstance(self.settings, dict) else
            getattr(self.settings, "get", lambda *_: {})("backend_configs")
        ) or {}
        self.app.secret_key = env_secret or backend_cfg.get("supersecretkey", "CHANGE_ME")
        self.stream_h = int(backend_cfg.get("stream_height", 1080))
        self.stream_w = int(backend_cfg.get("stream_width", 1920))
        self.port     = int(backend_cfg.get("server_port", 5001))
        self.host     = str(backend_cfg.get("host", "0.0.0.0"))

        self.ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".heif"}
        self.SELECTED_COLOR = "#ffcccc"

        self.latest_metadata = {}
        self._metadata_lock = threading.Lock()
        self._ensure_storage_files()

        # Encoding quality default
        self.encoding_quality = int(
            (self.settings.get("image_quality_encoding") if isinstance(self.settings, dict) else 80) or 80
        )

        self._jpeg_queue   = Queue(maxsize=30)
        self._new_frame_ev = Event()
        self._stop_event   = Event()

        self.executor = ThreadPoolExecutor(max_workers=2)
        self.setup_routes()
        Thread(target=self._capture_loop, daemon=True).start()

    def _client_ip(self) -> str:
        # honor reverse proxy if you have one (ensure you trust it)
        return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()

    def _rotate_session(self, username: str, uid: str, role: str) -> None:
        # Clear, set new identity, and new CSRF
        session.clear()
        session["uid"] = uid
        session["user"] = username
        session["role"] = role
        # regenerate csrf
        from WebAPI.WebUtils.auth_security import ensure_csrf
        ensure_csrf(session)

    def _require_csrf(self) -> None:
        from WebAPI.WebUtils.auth_security import validate_csrf
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not validate_csrf(session, token):
            # Keep message generic
            raise PermissionError("Invalid request")
   

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
        

    def _capture_loop(self):
        """
        Producer: encodes new frames when signaled; otherwise re-sends the last
        encoded JPEG at idle_stream_fps so clients do not time out.
        """
        # How often to push a frame when the content is static (no transitions).
        # Configure in backend_configs.idle_fps; default to 5.
        idle_fps = float(self.settings.get("backend_configs", {}).get("idle_fps", 5)) or 5.0
        interval = 1.0 / max(0.1, idle_fps)

        last_jpeg = None
        next_deadline = time.perf_counter()

        print(f"[Backend] capture loop started (idle_fps={idle_fps})")

        while not self._stop_event.is_set() and self.Frame.get_is_running():
            # Wait for either: a new-frame event, or the next idle tick
            timeout = max(0.0, next_deadline - time.perf_counter())
            got_new = self._new_frame_ev.wait(timeout=timeout)
            if got_new:
                self._new_frame_ev.clear()
                # Try to encode the fresh frame immediately
                frame = self.Frame.get_live_frame()
                if isinstance(frame, ndarray) and frame.size:
                    ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.encoding_quality])
                    if ok:
                        last_jpeg = jpg.tobytes()

            # On schedule (or after new frame) push something so the queue never dries up
            now = time.perf_counter()
            if now >= next_deadline:
                if last_jpeg is None:
                    # Bootstrap: encode the current frame once
                    frame = self.Frame.get_live_frame()
                    if isinstance(frame, ndarray) and frame.size:
                        ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.encoding_quality])
                        if ok:
                            last_jpeg = jpg.tobytes()

                if last_jpeg is not None:
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

                # schedule next tick
                next_deadline = now + interval


           
    def _encode_and_queue(self, frame: ndarray):
        success, jpg = cv2.imencode('.jpg', frame,
                                [cv2.IMWRITE_JPEG_QUALITY, self.encoding_quality])
        if not success:
            return
        data = jpg.tobytes()
        try:
            self._jpeg_queue.put_nowait(data)
        except Full:
            _ = self._jpeg_queue.get_nowait()
            self._jpeg_queue.put_nowait(data)


    def load_settings(self):
        try:
            with open(self.SETTINGS_FILE, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            # Do not crash the API if settings file is missing; start with empty/defaults
            print(f"[Backend] Settings file not found: {self.SETTINGS_FILE}. Starting with empty settings.")
            return {}
        except json.JSONDecodeError as e:
            print(f"[Backend] Invalid JSON in settings file {self.SETTINGS_FILE}: {e}. Starting with empty settings.")
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
        return '.' in filename and Path(filename).suffix.lower() in self.ALLOWED_EXTENSIONS

    def get_images_from_directory(self):
        return [entry.name for entry in Path(self.IMAGE_DIR).iterdir() if entry.is_file() and self.allowed_file(entry.name)]

    def load_users(self):
        try:
            with open(self.USER_DATA_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            users = {}
            self.save_users(users)
            return users

    def save_users(self, users):
        with open(self.USER_DATA_FILE, 'w') as file:
            json.dump(users, file, indent=4)

    def is_authenticated(self) -> bool:
        return "uid" in session and "user" in session

    def load_metadata_db(self):
        try:
            with open(self.METADATA_FILE, 'r', encoding='utf-8') as f:
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
            with open(self.METADATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Backend] save_metadata_db failed: {e}")
            
        
    def compute_image_hash(self, image_path):
        hash_obj = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    # Moved out of setup_routes to become a class method
    def update_image_metadata(self, image_path):
        """
        Updates the metadata database for an image.
        If the image hash already exists, it reads the existing entry without overwriting user-updated fields.
        If the image hash is not present, it creates a new entry.
        """
        metadata_file = self.METADATA_FILE
        image_hash = self.compute_image_hash(image_path)
        new_entry = {
            "hash": image_hash,
            "filename": os.path.basename(image_path),
            "uploader": "unknown",
            "date_added": datetime.now().isoformat(),
            "caption": ""
        }
        try:
            # Load existing metadata from the JSON file
            if os.path.exists(metadata_file) and os.path.getsize(metadata_file) > 0:
                with open(metadata_file, "r") as f:
                    data = json.load(f)
            else:
                data = {}

            # Only write a new entry if the image hash does not exist
            if image_hash in data:
                entry = data[image_hash]
            else:
                data[image_hash] = new_entry
                with open(metadata_file, "w") as f:
                    json.dump(data, f, indent=4)
                entry = new_entry
        except Exception as e:
            # Log error if needed and fall back to new_entry
            print(f"Error updating image DB: {e}")
            entry = new_entry

        self.update_current_metadata(entry)

    def mjpeg_stream(self, screen_w, screen_h):
        boundary_line = b"--frame\r\n"
        while self.Frame.get_is_running():
            data = self._jpeg_queue.get()  # block; producer ticks at idle_fps
            yield (boundary_line +
                b"Content-Type: image/jpeg\r\n" +
                f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") +
                data + b"\r\n")

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
            import numpy as np
            img = np.zeros((max(120, min(h, 360)), max(160, min(w, 640)), 3), dtype="uint8")
            # Gray background with text
            img[:] = (32, 32, 32)
            cv2.putText(img, "Waiting for frames...", (10, 50), cv2.FONT_HERSHEY_SIMPLEX,
                        0.9, (200, 200, 200), 2, cv2.LINE_AA)
            ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                return jpg.tobytes()
        except Exception as e:
            print(f"[Backend] heartbeat build failed: {e}")
        # Fallback tiny JPEG header if something goes wrong (still valid image)
        return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                b"\xff\xdb\x00C\x00" + b"\x08"*64 + b"\xff\xc0\x00\x11\x08\x00\x10\x00\x10\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
                b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
                b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00" + b"\x00"*10 + b"\xff\xd9")


    def setup_routes(self):   
           
        @self.app.context_processor
        def inject_csrf():
            from WebAPI.WebUtils.auth_security import ensure_csrf
            return {"csrf_token": lambda: ensure_csrf(session)}
        
        
        @self.app.before_request
        def _csrf_for_all_posts():
            # Only enforce for state-changing requests
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                try:
                    self._require_csrf()
                except Exception:
                    # JSON/fetch -> JSON 400; normal form -> flash + redirect
                    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                        return jsonify({"error": "Bad request."}), 400
                    flash("Invalid request.", "error")
                    return redirect(request.referrer or url_for("index"))


        @self.app.after_request
        def add_security_headers(resp):
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["Referrer-Policy"] = "same-origin"
            # A relaxed CSP for your app (tighten as needed)
            resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob: http: https:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none';"
            return resp
        
        @self.app.route('/stream')
        def stream():
            default_w, default_h = 1920, 1080
            try:
                w = int(request.args.get('width', default_w))
                h = int(request.args.get('height', default_h))
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
            import numpy as np
            boundary_line = b"--frame\r\n"
            def gen():
                w, h = 640, 360
                t = 0
                while True:
                    # animated color bars with timecode
                    bars = np.zeros((h, w, 3), dtype="uint8")
                    for i, c in enumerate([(255,0,0),(0,255,0),(0,0,255),(255,255,0),(0,255,255),(255,0,255)]):
                        x0 = int(i*w/6)
                        x1 = int((i+1)*w/6)
                        bars[:, x0:x1, :] = c
                    cv2.putText(bars, f"TEST STREAM t={t}", (10, h-20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20,20,20), 2, cv2.LINE_AA)
                    ok, jpg = cv2.imencode(".jpg", bars, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    data = jpg.tobytes() if ok else b""
                    yield (boundary_line +
                        b"Content-Type: image/jpeg\r\n" +
                        f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") +
                        data + b"\r\n")
                    t += 1
                    time.sleep(0.2)
            return Response(gen(),
                            mimetype="multipart/x-mixed-replace; boundary=frame",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

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
                    cpu_temp = round(
                        cpu_temps[0].current, 1) if cpu_temps else "N/A"
                except Exception:
                    cpu_temp = "N/A"

                return f"CPU: {cpu_usage}%\\nRAM: {ram_percent}% ({ram_used}/{ram_total}MB)\\nCPU Temp: {cpu_temp}°C"
            except Exception as e:
                return "Stats unavailable", 500

        @self.app.route('/settings')
        def serve_settings():
            try:
                with open(self.SETTINGS_FILE, 'r') as f:
                    return jsonify(json.load(f))
            except Exception as e:
                return jsonify({"error": "Failed to read settings", "details": str(e)}), 500

        @self.app.route("/current_weather")
        def current_weather():
            try:
                with open(self.SETTINGS_FILE) as f:
                    settings = json.load(f)

                api_key = settings.get("weather_api_key")
                location_key = settings.get("location_key")

                if not api_key or not location_key:
                    return jsonify({
                        "temp": "N/A",
                        "unit": "C",
                        "description": "Weather unavailable",
                        "icon_url": None
                    }), 400

                # Try live fetch
                url = f"http://dataservice.accuweather.com/currentconditions/v1/{location_key}?apikey={api_key}&details=true"

                try:
                    response = requests.get(url)
                    data = response.json()

                    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
                        raise ValueError("Unexpected API response")

                    w = data[0]
                    temp = w.get("Temperature", {}).get(
                        "Metric", {}).get("Value")
                    unit = w.get("Temperature", {}).get(
                        "Metric", {}).get("Unit", "C")
                    description = w.get("WeatherText", "")
                    icon = int(w.get("WeatherIcon", 0))
                    icon_url = f"https://developer.accuweather.com/sites/default/files/{icon:02d}-s.png"

                    weather = {
                        "temp": round(temp) if isinstance(temp, (int, float)) else "N/A",
                        "unit": unit,
                        "description": description,
                        "icon_url": icon_url
                    }

                    with open(self.WEATHER_CACHE, "w") as f:
                        json.dump({
                            "timestamp": datetime.now().isoformat(),
                            "weather_data": weather
                        }, f)

                    print("INFO - Weather icon successfully fetched.")
                    return jsonify(weather)

                except Exception as live_error:
                    print("ERROR - Weather fetch failed:", live_error)

                    # Fallback to cache
                    if os.path.exists(self.WEATHER_CACHE):
                        with open(self.WEATHER_CACHE) as f:
                            cached = json.load(f)
                            weather = cached.get("weather_data", {})
                            # Build icon_url if it's not cached already
                            if "icon_url" not in weather and "icon" in weather:
                                icon = weather["icon"]
                                weather[
                                    "icon_url"] = f"https://developer.accuweather.com/sites/default/files/{icon:02d}-s.png"

                            if all(k in weather for k in ("temp", "unit", "description", "icon_url")):
                                print(
                                    "INFO - Serving weather from fallback cache:", weather)
                                return jsonify(weather), 200

                    return jsonify({
                        "temp": "N/A",
                        "unit": "C",
                        "description": "Weather unavailable",
                        "icon_url": None
                    }), 503

            except Exception as e:
                print("ERROR - Unexpected exception in weather route:", e)
                return jsonify({
                    "temp": "N/A",
                    "unit": "C",
                    "description": "Weather unavailable",
                    "icon_url": None
                }), 500

        @self.app.route("/current_metadata")
        def current_metadata():
            with self._metadata_lock:
                return jsonify(self.latest_metadata or {})

        @self.app.route('/metadata_stream')
        def metadata_stream():
            def gen():
                last = None
                while True:
                    with self._metadata_lock:
                        meta = self.latest_metadata
                    if meta != last:
                        yield f"data: {json.dumps(meta)}\n\n"
                        last = meta.copy()
                    time.sleep(0.1)
            return Response(gen(), mimetype='text/event-stream')

        @self.app.route('/upload_with_metadata', methods=['POST'])
        def upload_with_metadata():
            if not self.is_authenticated():
                return redirect(url_for('login'))
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

                # Read uploader and caption
                caption = request.form.get(f"caption_{idx}", "").strip()
                uploader = request.form.get(f"uploader_{idx}", "").strip()

                temp_path = os.path.join(self.IMAGE_DIR, original_filename)
                try:
                    file.save(temp_path)
                except Exception as e:
                    self.Frame.send_log_message(f"{e}")
                    return jsonify({"message": f"{e}"}), 500

                final_path = temp_path
                if ext in ('.heic', '.heif'):
                    jpeg_path = os.path.splitext(final_path)[0] + ".jpg"
                    self.convert_heic_to_jpeg(final_path, jpeg_path)
                    final_path = jpeg_path
                    original_filename = os.path.basename(jpeg_path)

                # Hash after the file exists on disk
                file_hash = self.compute_image_hash(final_path)

                metadata = {
                    "hash": file_hash,
                    "caption": caption,
                    "uploader": uploader,
                    "date_added": datetime.utcnow().isoformat(),
                    "filename": original_filename
                }
                metadata_db[file_hash] = metadata

            self.save_metadata_db(metadata_db)
            self.Frame.update_images_list()
            return jsonify({"message": "Upload successful"}), 200

        @self.app.route("/thumb/<path:filename>")
        def thumb(filename):
            if not self.is_authenticated():
                return redirect(url_for('login'))

            # Only allow files that exist under IMAGE_DIR (prevents path tricks)
            src_path = os.path.join(self.IMAGE_DIR, filename)
            if not (os.path.isfile(src_path) and os.path.commonpath([self.IMAGE_DIR, os.path.realpath(src_path)]) == os.path.realpath(self.IMAGE_DIR)):
                return jsonify({"error": "File not found"}), 404

            try:
                w = int(request.args.get("w", 320))
                w = max(64, min(w, 1920))
            except Exception:
                w = 320

            dst_path = self._thumb_path(filename, w)

            try:
                # (re)generate when missing or source is newer
                if (not os.path.exists(dst_path)) or (os.path.getmtime(dst_path) < os.path.getmtime(src_path)):
                    self._make_thumb(src_path, dst_path, w)
            except Exception:
                # fallback to original if thumb creation fails
                return send_from_directory(self.IMAGE_DIR, filename)

            resp = send_file(dst_path, mimetype="image/webp", conditional=True)
            resp.headers["Cache-Control"] = "public, max-age=2592000, immutable"
            return resp


        @self.app.route('/signup', methods=['GET', 'POST'])
        def signup():
            from WebAPI.WebUtils.auth_security import EMAIL_RE, USERNAME_RE, password_policy_ok
            if request.method == 'POST':
                # Rate limit
                if not self._rl_signup.allow(self._client_ip()):
                    flash('Please wait before trying again.', 'error')
                    return redirect(url_for('signup'))

                # CSRF
                try:
                    self._require_csrf()
                except Exception:
                    flash('Invalid request.', 'error')
                    return redirect(url_for('signup'))

                email = (request.form.get('email') or '').strip().lower()
                username = (request.form.get('username') or '').strip()
                password = request.form.get('password') or ''

                # Specific message for password only (signup UX); keep others generic
                if not password_policy_ok(password):
                    flash('Password does not meet policy. Use 10+ chars and include at least 3 of: lowercase, uppercase, digits, symbols.', 'error')
                    # Render again with 400 so client JS can trigger shake without a full redirect if you switch to fetch later
                    return render_template('signup.html', email=request.args.get('email', ''), username=request.args.get('username', ''))

                if not (EMAIL_RE.match(email) and USERNAME_RE.match(username)):
                    flash('Invalid input.', 'error')
                    return redirect(url_for('signup'))

                try:
                    uid = self._users.create_user(email=email, username=username, password=password, role='user')
                except ValueError:
                    flash('Cannot create account.', 'error')
                    return redirect(url_for('signup'))
                except Exception:
                    flash('Cannot create account.', 'error')
                    return redirect(url_for('signup'))

                flash('Signup successful. Please log in.', 'success')
                return redirect(url_for('login'))

            return render_template('signup.html')

        @self.app.route('/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'POST':
                # Rate limit
                if not self._rl_login.allow(self._client_ip()):
                    # generic
                    flash('Invalid credentials.')
                    return redirect(url_for('login'))

                # CSRF
                try:
                    self._require_csrf()
                except Exception:
                    flash('Invalid credentials.')
                    return redirect(url_for('login'))

                identity = (request.form.get('email_or_username') or '').strip()
                password = request.form.get('password') or ''
                user = self._users.verify_login(identity, password)
                if not user or not user.get("is_active", True):
                    flash('Invalid credentials.')
                    return redirect(url_for('login'))

                self._rotate_session(user["username"], user["uid"], user.get("role", "user"))
                flash('Login successful!')
                return redirect(url_for('index'))
            return render_template("login.html")

        @self.app.route('/logout', methods=['POST', 'GET'])
        def logout():
            # Require CSRF only for POST; GET remains for convenience but you can force POST only
            if request.method == "POST":
                try:
                    self._require_csrf()
                except Exception:
                    pass
            session.clear()
            flash('You have been logged out.')
            return redirect(url_for('login'))


        @self.app.route('/')
        def index():
            if not self.is_authenticated():
                return redirect(url_for('login'))
            images = self.get_images_from_directory()
            image_count = len(images)
            settings = self.load_settings()
            latest_metadata = {}
            if images:
                filepath = os.path.join(self.IMAGE_DIR, images[0])
                file_hash = self.compute_image_hash(filepath)
                metadata_db = self.load_metadata_db()
                if file_hash in metadata_db:
                    latest_metadata = metadata_db[file_hash]
            username = session.get('user', 'Guest')
            return render_template("index.html", images=images, image_count=image_count,
                                   settings=settings, latest_metadata=latest_metadata,
                                   username=username)

        @self.app.route("/get_latest_metadata")
        def latest_metadata():
            return jsonify(self.latest_metadata)

        @self.app.route('/save_settings', methods=['POST'])
        def save_settings_route():
            if not self.is_authenticated():
                return redirect(url_for('login'))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400
            try:
                new_settings = {}
                form_data = request.form.to_dict(flat=True)
                for key, value in form_data.items():
                    if '[' in key and ']' in key:
                        parent_key, sub_key = key.split('[', 1)
                        sub_key = sub_key.rstrip(']')
                        if parent_key not in new_settings:
                            new_settings[parent_key] = {}
                        if value.lower() in ['true', 'on']:
                            value = True
                        elif value.lower() in ['false', 'off']:
                            value = False
                        elif value.isdigit():
                            value = int(value)
                        new_settings[parent_key][sub_key] = value
                    else:
                        if value.lower() in ['true', 'on']:
                            value = True
                        elif value.lower() in ['false', 'off']:
                            value = False
                        elif value.isdigit():
                            value = int(value)
                        new_settings[key] = value
                self.save_settings(new_settings)
                flash('Settings updated successfully.')
            except Exception as e:
                flash(f'Failed to update settings: {e}')
            return redirect(url_for('index'))

        @self.app.route('/images/<filename>')
        def serve_image(filename):
            if not self.is_authenticated():
                return redirect(url_for('login'))
            return send_from_directory(self.IMAGE_DIR, filename)

        @self.app.route('/upload', methods=['POST'])
        def upload_files():
            if not self.is_authenticated():
                return redirect(url_for('login'))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400
            if 'file[]' not in request.files:
                flash('No file part')
                return redirect(url_for('index'))
            files = request.files.getlist('file[]')
            for file in files:
                if file and self.allowed_file(file.filename):
                    file_path = os.path.join(self.IMAGE_DIR, file.filename)
                    file_extension = Path(file.filename).suffix.lower()
                    file.save(file_path)
                    if file_extension in {'.heic', '.heif'}:
                        jpeg_path = os.path.splitext(file_path)[0] + ".jpg"
                        self.convert_heic_to_jpeg(file_path, jpeg_path)
                        # Optional: delete the original HEIC
                        os.remove(file_path)
                        file_path = jpeg_path
                    self.store_image_metadata(file_path)
            return redirect(url_for('index'))

        @self.app.route('/delete/<filename>', methods=['POST'])
        def delete_image(filename):
            if not self.is_authenticated():
                return redirect(url_for('login'))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400
            try:
                os.remove(os.path.join(self.IMAGE_DIR, filename))
                flash(f'File {filename} successfully deleted.')
            except FileNotFoundError:
                flash(f'File {filename} not found.')
            return redirect(url_for('index'))

        @self.app.route('/download/<filename>')
        def download_image(filename):
            if not self.is_authenticated():
                return redirect(url_for('login'))
            return send_from_directory(self.IMAGE_DIR, filename, as_attachment=True)

        @self.app.route('/delete_selected', methods=['POST'])
        def delete_selected():
            if not self.is_authenticated():
                return redirect(url_for('login'))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400
            selected_files = request.form.getlist('selected_files')
            for filename in selected_files:
                try:
                    os.remove(os.path.join(self.IMAGE_DIR, filename))
                    flash(f'File {filename} successfully deleted.')
                except FileNotFoundError:
                    flash(f'File {filename} not found.')
            return redirect(url_for('index'))

        @self.app.route('/download_selected', methods=['POST'])
        def download_selected():
            if not self.is_authenticated():
                return redirect(url_for('login'))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400
            selected_files = request.form.getlist('selected_files')
            if not selected_files:
                flash('No files selected for download.')
                return redirect(url_for('index'))
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for filename in selected_files:
                    filepath = os.path.join(self.IMAGE_DIR, filename)
                    if os.path.isfile(filepath):
                        zipf.write(filepath, arcname=filename)
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                download_name='selected_images.zip',
                as_attachment=True
            )

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

        @self.app.route('/clear_logs', methods=['POST'])
        def clear_logs():
            if not self.is_authenticated():
                return redirect(url_for('login'))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400
            try:
                with open(self.LOG_FILE_PATH, 'w') as log_file:
                    log_file.truncate(0)
                return jsonify({"message": "Log file cleared successfully."}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route('/image_metadata')
        def get_image_metadata():
            filename = request.args.get('filename')
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

        @self.app.route('/update_metadata', methods=['POST'])
        def update_metadata():
            if not self.is_authenticated():
                return redirect(url_for('login'))
            try:
                self._require_csrf()
            except Exception:
                return jsonify({"error": "Bad request."}), 400
            data = request.get_json(force=True, silent=True) or {}
            file_hash = data.get('hash')
            caption = data.get('caption', "")
            # Get the uploader from the payload
            uploader = data.get('uploader')

            if not file_hash:
                return jsonify({"error": "Hash not provided."}), 400

            metadata_db = self.load_metadata_db()

            if file_hash not in metadata_db:
                return jsonify({"error": "Metadata not found for this hash."}), 404

            metadata_db[file_hash]['caption'] = caption
            if uploader is not None:
                metadata_db[file_hash]['uploader'] = uploader

            self.save_metadata_db(metadata_db)

            self.latest_metadata = metadata_db[file_hash]
            return jsonify({"message": "Metadata updated successfully."})

    def convert_heic_to_jpeg(self, heic_path, output_path):
        if not has_pyheif:
            return
        heif_file = pyheif.read(heic_path)
        image = Image.frombytes(
            heif_file.mode, heif_file.size, heif_file.data,
            "raw", heif_file.mode, heif_file.stride,
        )
        image.save(output_path, format="JPEG")
        os.remove(heic_path)

    def update_current_metadata(self, metadata):
        """
        Update the latest metadata stored in the backend.
        This method can be called by other parts of your application
        (like PhotoFrameServer.py) to update metadata.
        """
        with self._metadata_lock:
            self.latest_metadata = metadata

    def start(self):
        self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False, threaded=True)
        # threading.Thread(
        #     target=lambda: self.app.run(
        #         host=self.host, port=self.port, debug=False, use_reloader=False, threaded=True),
        #     daemon=True
        # ).start()


if __name__ == "__main__":
    backend = Backend()
    backend.start()
    while True:
        time.sleep(10)
