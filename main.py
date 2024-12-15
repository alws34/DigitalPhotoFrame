from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, flash, session
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
    return render_template_string('''
    <!doctype html>
    <html>
    <head><title>Image Gallery</title></head>
    <body style="background-color: #2e2e2e; color: #ffffff;">
    <h1 style="display: inline-block;">Image Gallery</h1>
    <span style="float: right; font-size: 18px;">Images Count: {{ image_count }}</span>
    <span style="float: right; font-size: 18px; margin-right: 20px;">
        <a href="{{ url_for('logout') }}" style="text-decoration:none; color:black;">
            <button type="button" style="background-color:#333;color:white;">Sign Out</button>
        </a>
    </span>
    <form method="post" action="/upload" enctype="multipart/form-data" style="margin-bottom: 20px; clear: both;">
        <input type="file" name="file[]" multiple>
        <input type="submit" value="Upload" style="background-color:#333;color:white;">
    </form>
    <form id="multiActionForm" method="post">
        <button type="submit" formaction="/delete_selected" formmethod="post" style="margin-right: 10px;background-color:#333;color:white;">Delete Selected</button>
        <button type="submit" formaction="/download_selected" formmethod="post" style="margin-right: 10px;background-color:#333;color:white;">Download Selected</button>
        <div>
        {% for image in images %}
            <div style="display:inline-block; margin:10px; text-align:center; padding: 10px; border: 2px solid transparent; width: 300px; height: 350px;" id="div_{{ image }}">
                <img src="{{ url_for('serve_image', filename=image) }}" alt="{{ image }}" loading="lazy" style="width:300px; height:300px; transition: transform 0.2s; cursor:pointer;" onclick="openModal('{{ url_for('serve_image', filename=image) }}')" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'" />
                <br>
                <input type="checkbox" name="selected_files" value="{{ image }}" onclick="toggleSelection(this, '{{ image }}')"> Select
                <br>
                <button type="button" style="background-color:#333;color:white;" onclick="confirmDelete('{{ image }}')">Delete</button>
                <a href="{{ url_for('download_image', filename=image) }}">
                    <button type="button" style="background-color:#333;color:white;">Download</button>
                </a>
            </div>
        {% endfor %}
        </div>
    </form>

    <!-- Modal structure -->
    <div id="imageModal" style="display:none; position:fixed; z-index:1000; left:0; top:0; width:100%; height:100%; background-color:rgba(0,0,0,0.9);">
        <span style="position:absolute; top:20px; right:35px; color:#f1f1f1; font-size:40px; font-weight:bold; cursor:pointer;" onclick="closeModal()">&times;</span>
        <img id="modalImage" style="margin:auto; display:block; width:80%; max-width:700px;">
    </div>

    <script>
        function toggleSelection(checkbox, imageName) {
            var div = document.getElementById('div_' + imageName);
            if (checkbox.checked) {
                div.style.backgroundColor = '{{ SELECTED_COLOR }}';
            } else {
                div.style.backgroundColor = '';
            }
        }

        function confirmDelete(imageName) {
            if (confirm('Are you sure you want to delete this image?')) {
                fetch('/delete/' + imageName, {
                    method: 'POST'
                }).then(response => {
                    if (response.ok) {
                        window.location.reload();
                    } else {
                        alert('Failed to delete the image.');
                    }
                });
            }
        }

        function openModal(imageSrc) {
            var modal = document.getElementById('imageModal');
            var modalImg = document.getElementById('modalImage');
            modal.style.display = "block";
            modalImg.src = imageSrc;
        }

        function closeModal() {
            var modal = document.getElementById('imageModal');
            modal.style.display = "none";
        }
    </script>
    </body>
    </html>
    ''', images=images, image_count=image_count, SELECTED_COLOR=SELECTED_COLOR)

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
