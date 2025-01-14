import time
from flask import Flask, Response, jsonify, request, redirect, url_for, send_from_directory, render_template, flash, session, send_file
import os
import json
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import io
import zipfile

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for session management and flash messages

# Directory where images are stored
IMAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../Images"))

# Allowed image extensions
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}

# Color for selected image highlight
SELECTED_COLOR = '#ffcccc'  # Light red, adjust as needed

# Path to the JSON file for storing user data
USER_DATA_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../DesktopApp/users.json'))
SETTINGS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../DesktopApp/settings.json'))

LOG_FILE_PATH = "PhotoFrame.log"

def load_settings():
    with open(SETTINGS_FILE, 'r') as file:
        return json.load(file)

def save_settings(data):
    with open(SETTINGS_FILE, 'w') as file:
        json.dump(data, file, indent=4)
        
# Ensure user data file exists
if not os.path.exists(USER_DATA_FILE):
    with open(USER_DATA_FILE, 'w') as file:
        json.dump({}, file)

def allowed_file(filename):
    return '.' in filename and Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def get_images_from_directory(directory: str):
    images = [entry.name for entry in Path(directory).iterdir() if entry.is_file() and allowed_file(entry.name)]
    return images

def load_users():
    with open(USER_DATA_FILE, 'r') as file:
        return json.load(file)

def save_users(users):
    with open(USER_DATA_FILE, 'w') as file:
        json.dump(users, file, indent=4)

def is_authenticated():
    if 'user' not in session:
        flash('You need to be logged in to access the image gallery.')
        return False
    return True

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']

        users = load_users()

        if email in users:
            flash('Email is already registered.')
            return redirect(url_for('signup'))

        users[email] = {
            'username': username,
            'password': generate_password_hash(password)
        }
        save_users(users)
        flash('Signup successful. Please log in.')
        return redirect(url_for('login'))

    return render_template("signup.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_or_username = request.form['email_or_username']
        password = request.form['password']

        users = load_users()

        user = next((u for e, u in users.items() if e == email_or_username or u['username'] == email_or_username), None)

        if user and check_password_hash(user['password'], password):
            session['user'] = user['username']
            flash('Login successful!')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials. Please try again.')
            return redirect(url_for('login'))

    return render_template("login.html")

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not is_authenticated():
        return redirect(url_for('login'))

    images = get_images_from_directory(IMAGE_DIR)
    image_count = len(images)
    settings = load_settings()  # Load settings for the modal

    return render_template("index.html", images=images, image_count=image_count, settings=settings)


@app.route('/save_settings', methods=['POST'])
def save_settings_route():
    try:
        new_settings = {}
        form_data = request.form.to_dict(flat=True)

        for key, value in form_data.items():
            # Handle nested keys (e.g., "mjpeg_server[allow_mjpeg_server]")
            if '[' in key and ']' in key:
                parent_key, sub_key = key.split('[', 1)
                sub_key = sub_key.rstrip(']')
                if parent_key not in new_settings:
                    new_settings[parent_key] = {}
                # Convert "on"/"off" or empty strings to boolean or appropriate types
                if value.lower() in ['true', 'on']:
                    value = True
                elif value.lower() in ['false', 'off']:
                    value = False
                elif value.isdigit():
                    value = int(value)
                new_settings[parent_key][sub_key] = value
            else:
                # Convert "on"/"off" or empty strings to boolean or appropriate types
                if value.lower() in ['true', 'on']:
                    value = True
                elif value.lower() in ['false', 'off']:
                    value = False
                elif value.isdigit():
                    value = int(value)
                new_settings[key] = value

        # Save the reconstructed settings JSON
        save_settings(new_settings)
        flash('Settings updated successfully.')
    except Exception as e:
        flash(f'Failed to update settings: {e}')
    return redirect(url_for('index'))

@app.route('/images/<filename>')
def serve_image(filename):
    if not is_authenticated():
        return redirect(url_for('login'))
    return send_from_directory(IMAGE_DIR, filename)

@app.route('/upload', methods=['POST'])
def upload_files():
    if not is_authenticated():
        return redirect(url_for('login'))

    if 'file[]' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))

    files = request.files.getlist('file[]')
    for file in files:
        if file and allowed_file(file.filename):
            file.save(os.path.join(IMAGE_DIR, file.filename))
    flash('Files successfully uploaded.')
    return redirect(url_for('index'))

@app.route('/delete/<filename>', methods=['POST'])
def delete_image(filename):
    if not is_authenticated():
        return redirect(url_for('login'))

    try:
        os.remove(os.path.join(IMAGE_DIR, filename))
        flash(f'File {filename} successfully deleted.')
    except FileNotFoundError:
        flash(f'File {filename} not found.')
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_image(filename):
    if not is_authenticated():
        return redirect(url_for('login'))

    return send_from_directory(IMAGE_DIR, filename, as_attachment=True)

@app.route('/delete_selected', methods=['POST'])
def delete_selected():
    if not is_authenticated():
        return redirect(url_for('login'))

    selected_files = request.form.getlist('selected_files')
    for filename in selected_files:
        try:
            os.remove(os.path.join(IMAGE_DIR, filename))
            flash(f'File {filename} successfully deleted.')
        except FileNotFoundError:
            flash(f'File {filename} not found.')
    return redirect(url_for('index'))

@app.route('/download_selected', methods=['POST'])
def download_selected():
    if not is_authenticated():
        return redirect(url_for('login'))

    selected_files = request.form.getlist('selected_files')
    if not selected_files:
        flash('No files selected for download.')
        return redirect(url_for('index'))

    # Create an in-memory BytesIO buffer to write our ZIP archive into.
    zip_buffer = io.BytesIO()
    
    # Create a new zip file in the BytesIO buffer
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filename in selected_files:
            # Build the full path; add the file to the zip if it exists
            filepath = os.path.join(IMAGE_DIR, filename)
            if os.path.isfile(filepath):
                # The `arcname` is how the file is named in the ZIP
                zipf.write(filepath, arcname=filename)

    # Important: move to the beginning of the BytesIO buffer so `send_file` can read it
    zip_buffer.seek(0)

    # Send file to user
    return send_file(
        zip_buffer,
        download_name='selected_images.zip',  # name of the zip download
        as_attachment=True
    )
@app.route("/logs", methods=["GET"])
def get_logs():
    try:
        with open(LOG_FILE_PATH, "r") as log_file:
            logs = log_file.readlines()
        return jsonify({"logs": logs}), 200
    except FileNotFoundError:
        return jsonify({"error": "Log file not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stream_logs")
def stream_logs():
    def generate_logs():
        with open(LOG_FILE_PATH, "r") as log_file:
            # Read all existing content first
            log_file.seek(0)  # Go to the beginning of the file
            for line in log_file:
                yield f"data: {line}\n\n"

            # Continue streaming new content as it is added
            log_file.seek(0, os.SEEK_END)  # Move to the end for live updates
            while True:
                line = log_file.readline()
                if line:
                    yield f"data: {line}\n\n"
                time.sleep(1)

    return Response(generate_logs(), content_type="text/event-stream")

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    try:
        with open(LOG_FILE_PATH, 'w') as log_file:
            log_file.truncate(0)  # Clear the file
        return jsonify({"message": "Log file cleared successfully."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')
