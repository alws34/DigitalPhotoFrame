from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, flash
import os
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flash messages

# Directory where images are stored
IMAGE_DIR = 'Images'

# Allowed image extensions
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}

# Color for selected image highlight
SELECTED_COLOR = '#ffcccc'  # Light red, adjust as needed

def allowed_file(filename):
    return '.' in filename and Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def get_images_from_directory(directory: str):
    images = [entry.name for entry in Path(directory).iterdir() if entry.is_file() and allowed_file(entry.name)]
    return images

@app.route('/')
def index():
    images = get_images_from_directory(IMAGE_DIR)
    image_count = len(images)
    return render_template_string('''
    <!doctype html>
    <title>Image Gallery</title>
    <h1 style="display: inline-block;">Image Gallery</h1>
    <span style="float: right; font-size: 18px;">Images Count: {{ image_count }}</span>
    <form method="post" action="/upload" enctype="multipart/form-data" style="margin-bottom: 20px; clear: both;">
        <input type="file" name="file[]" multiple>
        <input type="submit" value="Upload">
    </form>
    <form id="multiActionForm" method="post">
        <button type="submit" formaction="/delete_selected" formmethod="post" style="margin-right: 10px;">Delete Selected</button>
        <button type="submit" formaction="/download_selected" formmethod="post" style="margin-right: 10px;">Download Selected</button>
        <div>
        {% for image in images %}
            <div style="display:inline-block; margin:10px; text-align:center; padding: 10px; border: 2px solid transparent;" id="div_{{ image }}">
                <img src="{{ url_for('serve_image', filename=image) }}" alt="{{ image }}" loading="lazy" style="max-width:200px; transition: transform 0.2s; cursor:pointer;" onclick="openModal('{{ url_for('serve_image', filename=image) }}')" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'" />                <br>
                <input type="checkbox" name="selected_files" value="{{ image }}" onclick="toggleSelection(this, '{{ image }}')"> Select
                <br>
                <button type="button" onclick="confirmDelete('{{ image }}')">Delete</button>
                <a href="{{ url_for('download_image', filename=image) }}">
                    <button type="button">Download</button>
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
    ''', images=images, image_count=image_count, SELECTED_COLOR=SELECTED_COLOR)

@app.route('/images/<filename>')
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'file[]' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))

    files = request.files.getlist('file[]')
    for file in files:
        if file and allowed_file(file.filename):
            file.save(os.path.join(IMAGE_DIR, file.filename))
    return redirect(url_for('index'))

@app.route('/delete/<filename>', methods=['POST'])
def delete_image(filename):
    try:
        os.remove(os.path.join(IMAGE_DIR, filename))
    except FileNotFoundError:
        flash(f'File {filename} not found.')
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_image(filename):
    return send_from_directory(IMAGE_DIR, filename, as_attachment=True)

@app.route('/delete_selected', methods=['POST'])
def delete_selected():
    selected_files = request.form.getlist('selected_files')
    for filename in selected_files:
        try:
            os.remove(os.path.join(IMAGE_DIR, filename))
        except FileNotFoundError:
            flash(f'File {filename} not found.')
    return redirect(url_for('index'))

@app.route('/download_selected', methods=['POST'])
def download_selected():
    selected_files = request.form.getlist('selected_files')
    for filename in selected_files:
        return send_from_directory(IMAGE_DIR, filename, as_attachment=True)

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)