import base64
import logging
import time
import os
import json
import hashlib
from datetime import datetime
from cv2 import imencode
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
import numpy as np

from iFrame import iFrame
if platform.system() == "Linux":
    try:
        import pyheif
        has_pyheif = True
    except ImportError:
        has_pyheif = False
else:
    has_pyheif = False

class ManagerBackend:
    def __init__(self, frame:iFrame, settings):
        self.app = Flask("ManagerBackend")
        CORS(self.app)
        self.app.secret_key = 'supersecretkey'
        self.latest_metadata = {} 
        self.port = settings["server_port"]
        self.host = settings["host"]
        self.IMAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../Images"))
        self.ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.heif'}
        self.SELECTED_COLOR = '#ffcccc'
        self.USER_DATA_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../users.json'))
        self.SETTINGS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../settings.json'))
        self.METADATA_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../metadata.json'))
        self.LOG_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "PhotoFrame.log"))
        self.Frame = frame 
    
        if not os.path.exists(self.USER_DATA_FILE):
            with open(self.USER_DATA_FILE, 'w') as file:
                json.dump({}, file)
        # Ensure metadata file exists
        if not os.path.exists(self.METADATA_FILE):
            with open(self.METADATA_FILE, 'w') as file:
                json.dump({}, file)
        self.setup_routes()

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
        with open(self.USER_DATA_FILE, 'r') as file:
            return json.load(file)

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

    def generate_frame(self):
        """
        Generator to serve MJPEG frames from the live frame.
        Streams the live frame directly without resizing.
        """
        while self.Frame.get_is_running():
            try:
                frame = self.Frame.get_live_frame()
                if isinstance(frame, ndarray) and frame.size > 0:
                    if frame.dtype != np.uint8:
                        frame = frame.astype(np.uint8)

                    # Encode the frame as JPEG
                    _, jpeg = imencode('.jpg', frame)
                    frame = jpeg.tobytes()
                    jpeg_b64 = base64.b64encode(frame).decode('utf-8')
                    metadata = self.latest_metadata
                    json_payload = json.dumps({
                        "image": jpeg_b64,
                        "metadata": metadata
                    })
                    yield json_payload + "\n"
                time.sleep(1 / 30)  # ~10 FPS
            except Exception as e:
                self.Frame.send_log_message(f"JSON stream error: {e}", logger=logging.error)
                time.sleep(0.5)


    def setup_routes(self):
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
            # Load metadata for the first image if available
            latest_metadata = {}
            if images:
                filepath = os.path.join(self.IMAGE_DIR, images[0])
                file_hash = self.compute_image_hash(filepath)
                metadata_db = self.load_metadata_db()
                if file_hash in metadata_db:
                    latest_metadata = metadata_db[file_hash]
            return render_template("index.html", images=images, image_count=image_count, settings=settings, latest_metadata=latest_metadata)

        
        @self.app.route('/live_feed')
        def live_feed():
            if not self.is_authenticated():
                return redirect(url_for('login'))
            return Response(
                stream_with_context(self.generate_frame()),
                mimetype='application/json'
            )
            # # Use our generator instead of returning just one image
            # return Response(
            #     self.generate_frame(), 
            #     mimetype='multipart/x-mixed-replace; boundary=frame'
            # )



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
                        os.remove(file_path)  # Optional: delete the original HEIC
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
            uploader = data.get('uploader')  # Get the uploader from the payload

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
        if has_pyheif:
            heif_file = pyheif.read(heic_path)
            image = Image.frombytes(
                heif_file.mode, heif_file.size, heif_file.data,
                "raw", heif_file.mode, heif_file.stride,
            )
            image.save(output_path, format="JPEG")
        return


    def update_current_metadata(self, metadata):
        """
        Update the latest metadata stored in the backend.
        This method can be called by other parts of your application
        (like PhotoFrameServer.py) to update metadata.
        """
        self.latest_metadata = metadata

    def start(self):
        threading.Thread(
            target=lambda: self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False),
            daemon=True
        ).start()

if __name__ == "__main__":
    backend = ManagerBackend()
    backend.start()
    while True:
        time.sleep(10)
