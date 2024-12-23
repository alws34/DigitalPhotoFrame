import time
from flask import Flask, Response, jsonify, request, redirect, url_for, send_from_directory, render_template_string, flash, session
import os
import json
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for session management and flash messages

# Directory where images are stored
IMAGE_DIR = 'Images'

# Allowed image extensions
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}

# Color for selected image highlight
SELECTED_COLOR = '#ffcccc'  # Light red, adjust as needed

# Path to the JSON file for storing user data
USER_DATA_FILE = 'users.json'

SETTINGS_FILE = 'settings.json'
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

    return render_template_string('''
    <!doctype html>
    <html>
    <head><title>Signup</title></head>
    <body style="background-color: #1e1e1e; color: #ffffff;">
    <h1>Signup</h1>
    <form method="post">
        <label for="email">Email:</label><br>
        <input type="email" id="email" name="email" required style="color:#000;"><br><br>
        <label for="username">Username:</label><br>
        <input type="text" id="username" name="username" required style="color:#000;"><br><br>
        <label for="password">Password:</label><br>
        <input type="password" id="password" name="password" required style="color:#000;"><br><br>
        <input type="submit" value="Signup" style="background-color:#333;color:white;">
    </form>
    <p>Already have an account? <a href="{{ url_for('login') }}" style="color:#00ffcc;">Login here</a>.</p>
    </body>
    </html>
    ''')

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

    return render_template_string('''
    <!doctype html>
    <html>
    <head><title>Login</title></head>
    <body style="background-color: #1e1e1e; color: #ffffff;">
    <h1>Login</h1>
    <form method="post">
        <label for="email_or_username">Email or Username:</label><br>
        <input type="text" id="email_or_username" name="email_or_username" required style="color:#000;"><br><br>
        <label for="password">Password:</label><br>
        <input type="password" id="password" name="password" required style="color:#000;"><br><br>
        <input type="submit" value="Login" style="background-color:#333;color:white;">
    </form>
    <p>Don't have an account? <a href="{{ url_for('signup') }}" style="color:#00ffcc;">Sign up here</a>.</p>
    </body>
    </html>
    ''')

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

    return render_template_string('''
    <!doctype html>
    <html>
    <head>
        <title>Image Gallery</title>
        <style>
            body {
                background-color: #2e2e2e;
                color: #ffffff;
                font-family: Arial, sans-serif;
            }
            .top-right-table {
                position: absolute;
                top: 10px;
                right: 10px;
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 10px;
                padding: 10px;
                display: table;
            }
            .top-right-table button {
                background-color: #333;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 15px;
                margin: 5px;
                cursor: pointer;
            }
            .top-right-table button:hover {
                background-color: #444;
            }
            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.9);
                overflow: auto;
                padding-top: 60px;
            }
            .modal-content {
                background-color: #2e2e2e;
                margin: auto;
                padding: 20px;
                border: 1px solid #888;
                width: 70%;
                color: white;
                border-radius: 10px;
            }
            .close {
                color: #aaa;
                float: right;
                font-size: 28px;
                font-weight: bold;
            }
            .close:hover, .close:focus {
                color: white;
                text-decoration: none;
                cursor: pointer;
            }
            .log-content {
                max-height: 300px;
                overflow-y: auto;
                white-space: pre-wrap;
                font-family: monospace;
                background-color: #1e1e1e;
                padding: 10px;
                border-radius: 5px;
                border: 1px solid #555;
            }
        </style>
    </head>
    <body>
        <h1>Image Gallery</h1>
        <div class="top-right-table">
            <button onclick="logout()">Sign Out</button>
            <button onclick="openLogsModal()">Logs</button>
            <button onclick="openSettingsModal()">Edit Settings</button>
            <span style="padding: 10px; color: white;">Images Count: {{ image_count }}</span>
        </div>

        <!-- Logs Modal -->
        <div id="logsModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="closeLogsModal()">&times;</span>
                <h2>Live Logs</h2>
                <div id="logStream" class="log-content"></div>
                <div style="text-align: center; margin-top: 20px;">
                    <button onclick="clearLogs()" style="background-color: #00ffcc; color: black; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer;">Clear Logs</button>
                </div>
            </div>
        </div>

        <!-- Settings Modal -->
        <div id="settingsModal" class="modal">
            <div class="modal-content" style="max-width: 600px;">
                <span class="close" onclick="closeSettingsModal()" style="font-size: 28px; font-weight: bold; cursor: pointer; color: white;">&times;</span>
                <h2 style="text-align: center; color: white;">Edit Settings</h2>
                <form method="POST" action="{{ url_for('save_settings_route') }}" style="display: flex; flex-direction: column; gap: 20px; padding: 20px;">
                    {% for key, value in settings.items() %}
                        <div style="display: flex; flex-direction: column; gap: 10px;">
                            {% if value is mapping %}
                                <!-- Section Header for Nested JSON -->
                                <h3 style="color: #00ffcc; margin-bottom: 5px;">{{ key.replace('_', ' ') }}</h3>
                                {% for subkey, subvalue in value.items() %}
                                    <label for="{{ key }}_{{ subkey }}" style="color: white;">{{ subkey.replace('_', ' ') }}</label>
                                    {% if subvalue in [true, false] or subvalue|string|lower in ['on', 'off', 'true', 'false'] %}
                                        <input type="checkbox" id="{{ key }}_{{ subkey }}" name="{{ key }}[{{ subkey }}]" {% if subvalue in [true, 'true', 'on'] %}checked{% endif %}>
                                    {% else %}
                                        <input type="text" id="{{ key }}_{{ subkey }}" name="{{ key }}[{{ subkey }}]" value="{{ subvalue }}" style="width: 100%; padding: 10px; border-radius: 5px; border: 1px solid #555; background-color: #1e1e1e; color: white;">
                                    {% endif %}
                                {% endfor %}
                            {% else %}
                                <label for="{{ key }}" style="color: white;">{{ key.replace('_', ' ') }}</label>
                                {% if value in [true, false] or value|string|lower in ['on', 'off', 'true', 'false'] %}
                                    <input type="checkbox" id="{{ key }}" name="{{ key }}" {% if value in [true, 'true', 'on'] %}checked{% endif %}>
                                {% else %}
                                    <input type="text" id="{{ key }}" name="{{ key }}" value="{{ value }}" style="width: 100%; padding: 10px; border-radius: 5px; border: 1px solid #555; background-color: #1e1e1e; color: white;">
                                {% endif %}
                            {% endif %}
                        </div>
                    {% endfor %}
                    <div style="text-align: center; margin-top: 20px;">
                        <button type="submit" style="background-color: #00ffcc; color: black; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer;">Save</button>
                        <button type="button" onclick="closeSettingsModal()" style="background-color: #333; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer;">Cancel</button>
                    </div>
                </form>
            </div>
        </div>


        <!-- Main Content -->
       <div>
            <form method="post" action="/upload" enctype="multipart/form-data">
                <input type="file" name="file[]" multiple>
                <input type="submit" value="Upload" style="background-color:#333;color:white;">
            </form>
            <form method="post">
                <button type="submit" formaction="/delete_selected" style="margin-right: 10px;background-color:#333;color:white;">Delete Selected</button>
                <button type="submit" formaction="/download_selected" style="margin-right: 10px;background-color:#333;color:white;">Download Selected</button>
                <div style="display: flex; flex-wrap: wrap; gap: 20px; justify-content: center;">
                    {% for image in images %}
                        <div style="border: 1px solid #444; border-radius: 10px; padding: 10px; text-align: center; background-color: rgba(0, 0, 0, 0.7);">
                            <img src="{{ url_for('serve_image', filename=image) }}" 
                                alt="{{ image }}" 
                                style="width: 200px; height: 200px; object-fit: cover; border-radius: 10px; margin-bottom: 10px; transition: transform 0.3s;" 
                                onmouseover="this.style.transform='scale(1.1)'" 
                                onmouseout="this.style.transform='scale(1)'" 
                                onclick="openImageModal('{{ url_for('serve_image', filename=image) }}')">
                            <br>
                            <input type="checkbox" name="selected_files" value="{{ image }}" style="margin-bottom: 10px;"> Select
                            <br>
                            <button type="button" style="background-color:#333;color:white;" onclick="confirmDelete('{{ image }}')">Delete</button>
                            <a href="{{ url_for('download_image', filename=image) }}">
                                <button type="button" style="background-color:#333;color:white;">Download</button>
                            </a>
                        </div>
                    {% endfor %}
                </div>
            </form>
        </div>

        <!-- Image Modal -->
        <div id="imageModal" style="display:none; position:fixed; z-index:1000; left:0; top:0; width:100%; height:100%; background-color:rgba(0,0,0,0.9);">
            <span style="position:absolute; top:20px; right:35px; color:#f1f1f1; font-size:40px; font-weight:bold; cursor:pointer;" onclick="closeImageModal()">&times;</span>
            <img id="modalImage" style="margin:auto; display:block; width:80%; max-width:700px;">
        </div>

        <script>
            function openImageModal(imageSrc) {
                const modal = document.getElementById('imageModal');
                const modalImg = document.getElementById('modalImage');
                modal.style.display = "block";
                modalImg.src = imageSrc;
            }

            function closeImageModal() {
                const modal = document.getElementById('imageModal');
                modal.style.display = "none";
            }
        </script>

        <script>
            function logout() {
                window.location.href = "{{ url_for('logout') }}";
            }

            function openSettingsModal() {
                document.getElementById('settingsModal').style.display = 'block';
            }

            function closeSettingsModal() {
                document.getElementById('settingsModal').style.display = 'none';
            }

            function openLogsModal() {
                document.getElementById('logsModal').style.display = 'block';
                const logStream = document.getElementById('logStream');
                logStream.innerHTML = ''; // Clear previous logs
                const eventSource = new EventSource("{{ url_for('stream_logs') }}");
                eventSource.onmessage = function (event) {
                    logStream.innerHTML += event.data + '<br>';
                    logStream.scrollTop = logStream.scrollHeight; // Auto-scroll to the bottom
                };
                eventSource.onerror = function () {
                    eventSource.close();
                };
            }

            function closeLogsModal() {
                document.getElementById('logsModal').style.display = 'none';
            }
        </script>
        <script>
            function clearLogs() {
                fetch('/clear_logs', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                })
                .then(response => {
                    if (response.ok) {
                        document.getElementById('logStream').innerHTML = ''; // Clear logs in the modal
                        alert('Log file cleared successfully.');
                    } else {
                        alert('Failed to clear logs.');
                    }
                })
                .catch(error => {
                    console.error('Error clearing logs:', error);
                    alert('An error occurred while clearing logs.');
                });
            }
        </script>
    </body>
    </html>
    ''', images=images, image_count=image_count, settings=settings)


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
    # For simplicity, we'll just download the first selected file. You might want to handle multiple file downloads differently.
    if selected_files:
        return send_from_directory(IMAGE_DIR, selected_files[0], as_attachment=True)
    flash('No files selected for download.')
    return redirect(url_for('index'))

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
