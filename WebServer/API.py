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
from PIL import Image
import threading
from flask_cors import CORS
from iFrame import iFrame
from concurrent.futures import ThreadPoolExecutor

if platform.system() == "Linux" or platform.system() == "Darwin":
    try:
        import pyheif
        has_pyheif = True
    except ImportError:
        has_pyheif = False
else:
    has_pyheif = False


class Backend:
    def __init__(self, frame: iFrame, settings, image_dir=None):    
        base = Path(__file__).parent
        self.app = Flask(
            __name__,
            template_folder=str(base / "./templates"),
            static_folder=str(base / "./static"),
        )
        CORS(self.app)
        self.app.secret_key =settings["backend_configs"]["supersecretkey"] 
        self.latest_metadata = {}

        self.stream_h = settings["backend_configs"]["stream_height"]
        self.stream_w = settings["backend_configs"]["stream_width"]
        
        self.port = settings["backend_configs"]["server_port"]
        self.host = settings["backend_configs"]["host"]
        self.IMAGE_DIR = image_dir if image_dir is not None else self.set_absolute_paths("Images")
        
        self.ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg',
                                   '.gif', '.bmp', '.tiff', '.webp', '.heic', '.heif'}
        self.SELECTED_COLOR = '#ffcccc'

        self.USER_DATA_FILE = self.set_absolute_paths('users.json')
        self.SETTINGS_FILE = self.set_absolute_paths('settings.json')
        self.METADATA_FILE = self.set_absolute_paths('metadata.json')
        self.LOG_FILE_PATH = self.set_absolute_paths("PhotoFrame.log")
        self.WEATHER_CACHE = "weather_cache.json"
        
        self.Frame = frame
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        self._metadata_lock = threading.Lock()
        os.makedirs(self.IMAGE_DIR, exist_ok=True)
        
        self.settings = self.load_settings()
        self.encoding_quality = self.settings.get("image_quality_encoding", 80)
        
        if not os.path.exists(self.USER_DATA_FILE):
            with open(self.USER_DATA_FILE, 'w') as file:
                json.dump({}, file)
        if not os.path.exists(self.METADATA_FILE):
            with open(self.METADATA_FILE, 'w') as file:
                json.dump({}, file)
        
        self._jpeg_queue   = Queue(maxsize=30)
        self._new_frame_ev = Event()
        self._stop_event   = Event()
        
        self.setup_routes()
        Thread(target=self._capture_loop, daemon=True).start()
        
        

    def set_absolute_paths(self, path):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), path))
    

    def _capture_loop(self):
        """
        Encode every new frame as it arrives. When no frame arrives for
        `idle_delay` seconds, re-send the last JPEG so that newcomers
        still see something without re-encoding.
        """
        idle_fps   = self.settings["backend_configs"].get("idle_fps", 1)
        idle_delay = 1.0 / max(idle_fps, 1)

        last_jpeg  = None

        while not self._stop_event.is_set() and self.Frame.get_is_running():

            got_new = self._new_frame_ev.wait(timeout=idle_delay)
            if got_new:
                self._new_frame_ev.clear()

                frame = self.Frame.get_live_frame()
                if isinstance(frame, ndarray) and frame.size:
                    ok, jpg = cv2.imencode(
                        '.jpg', frame,
                        [cv2.IMWRITE_JPEG_QUALITY, self.encoding_quality]
                    )
                    if ok:
                        last_jpeg = jpg.tobytes()

            if last_jpeg is None:
                time.sleep(0.1)
                continue

            try:
                self._jpeg_queue.put(last_jpeg, timeout=0.5)
            except Full:
                _ = self._jpeg_queue.get_nowait()
                self._jpeg_queue.put_nowait(last_jpeg)
                
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
        with open(self.SETTINGS_FILE, 'r') as file:
            return json.load(file)

    def save_settings(self, data):
        with open(self.SETTINGS_FILE, 'w') as file:
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

    def is_authenticated(self):
        if 'user' not in session:
            flash('You need to be logged in to access the image gallery.')
            return False
        return True

    # Metadata management
    def load_metadata_db(self):
        try:
            with open(self.METADATA_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error loading metadata DB: {e}")
            return {}

    def save_metadata_db(self, data):
        with open(self.METADATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)

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
        boundary = (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    b'Cache-Control: no-cache\r\n\r\n')
        while self.Frame.get_is_running():
            try:
                data = self._jpeg_queue.get(timeout=None)  # blocks until new data
            except Empty:
                continue  # (or break, if you want to end the stream)
            yield boundary + data + b'\r\n'
                
    def setup_routes(self):      
        @self.app.route('/stream')
        def stream():
            default_w, default_h = 1920, 1080
            try:
                w = int(request.args.get('width', default_w))
                h = int(request.args.get('height', default_h))
            except ValueError:
                w, h = default_w, default_h
            generator = stream_with_context(self.mjpeg_stream(w, h))
            return Response(
                generator,
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
  
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
            uploaded_files = request.files.getlist("file[]")
            if not uploaded_files:
                return jsonify({"message": "No files uploaded"}), 400

            metadata_db = self.load_metadata_db()

            for idx, file in enumerate(uploaded_files):
                if file.filename == "":
                    continue

                original_filename = file.filename
                ext = os.path.splitext(original_filename)[1].lower()

                if ext not in self.ALLOWED_EXTENSIONS:
                    continue

                # Read uploader and caption
                caption = request.form.get(f"caption_{idx}", "").strip()
                uploader = request.form.get(f"uploader_{idx}", "").strip()

                # Save temporarily to compute hash
                temp_dir = os.path.join(self.IMAGE_DIR, "_temp")
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, original_filename)
                file.save(temp_path)

                # Compute file hash
                file_hash = self.compute_image_hash(temp_path)

                # Final destination
                final_path = os.path.join(self.IMAGE_DIR, original_filename)

                # Move to image directory (overwrite if exists)
                shutil.move(temp_path, final_path)

                # Convert HEIC/HEIF if needed
                if ext in ['.heic', '.heif']:
                    jpeg_path = os.path.splitext(final_path)[0] + ".jpg"
                    self.convert_heic_to_jpeg(final_path, jpeg_path)
                    os.remove(final_path)
                    final_path = jpeg_path
                    original_filename = os.path.basename(jpeg_path)

                # Save metadata (hash-keyed)
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

        @self.app.route('/signup', methods=['GET', 'POST'])
        def signup():
            if request.method == 'POST':
                email = request.form['email']
                username = request.form['username']
                password = request.form['password']
                users = self.load_users()
                if email in users:
                    flash('Email is already registered.')
                    return redirect(url_for('signup'))
                users[email] = {
                    'username': username,
                    'password': generate_password_hash(password)
                }
                self.save_users(users)
                flash('Signup successful. Please log in.')
                return redirect(url_for('login'))
            return render_template("signup.html")

        @self.app.route('/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'POST':
                email_or_username = request.form['email_or_username']
                password = request.form['password']
                users = self.load_users()
                user = None
                for e, u in users.items():
                    if e == email_or_username or u.get('username') == email_or_username:
                        user = u
                        break
                if user and check_password_hash(user['password'], password):
                    session['user'] = user.get('username')
                    flash('Login successful!')
                    return redirect(url_for('index'))
                else:
                    flash('Invalid credentials. Please try again.')
                    return redirect(url_for('login'))
            return render_template("login.html")

        @self.app.route('/logout')
        def logout():
            session.pop('user', None)
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
            data = request.get_json()
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
