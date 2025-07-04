# Digital Photo Frame

A modern, customizable photo-frame engine and web-interface for Raspberry Pi or any Linux/Windows machine. Displays animated slideshows, overlays weather and system stats, and provides a browser-based management UI.

## Overview

This project consists of two main components:

- **PhotoFrame engine** (`PhotoFrameServer.py`)  
  - Loads images from a directory  
  - Applies 13 different transition effects via OpenCV  
  - Streams a full-screen MJPEG slideshow at `/stream`  
  - Optionally overlays live weather (AccuWeather) and system stats (CPU, RAM, temp)  
- **Flask backend & web UI** (`API.py` + `templates/`, `static/`)  
  - Secure login/signup  
  - Upload images with caption & uploader metadata  
  - Edit metadata, delete or download single/multiple images  
  - Live logs viewer & clear logs  
  - Server-Sent Events for real-time metadata updates  

## Features

- Animated image transitions (alpha, pixel, checkerboard, blinds, scroll, wipe, zoom, iris, barn-door, shrink, stretch, plain)  
- Translucent or solid background support  
- Configurable animation duration, delay, FPS  
- Weather overlay with caching fallback  
- System stats overlay (CPU %, RAM %, temperature)  
- Full-screen MJPEG stream endpoint (`/stream`)  
- Web UI for remote management:  
  - Browse, select, delete, download multiple images  
  - Upload via drag-and-drop or file picker  
  - Edit caption, uploader, date added  
  - Live logs (via `/stream_logs`)  
- Configurable entirely via `settings.json`  

## Prerequisites

- Python 3.7 or higher  
- Git, pip  

## Installation

1. **Clone the repo**  
   ```bash
   git clone https://your-repo-url.git
   cd DigitalPhotoFrame
   ```

2. **Create and activate a virtual environment**  
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**  
   ```bash
   pip install -r Requirments.txt
   ```

4. **Configure**  
   - Copy `settings.json` and update keys:  
     - `backend_configs.supersecretkey` – session encryption key  
     - `weather_api_key` and `location_key` – for AccuWeather  
   - Ensure `arial.ttf` (or your chosen font) is available in the working directory or system fonts.

5. **Prepare image directory**  
   ```bash
   mkdir -p Images
   ```

## Running

### Native

```bash
python3 PhotoFrameServer.py
```

- Slideshow & backend both start in one process.  
- Visit `http://<host>:<port>/stream` to view the slideshow.  
- Visit `http://<host>:<port>/` to log in and manage images.

### Docker

```bash
docker compose up -d --build
```

- Exposes the same endpoints on the configured port.  

## Configuration (`settings.json`)

```json
{
  "backend_configs": {
    "host": "0.0.0.0",
    "server_port": 5001,
    "stream_width": 1920,
    "stream_height": 1080,
    "stream_fps": 30,
    "supersecretkey": "<your-secret-key>"
  },
  "image_quality_encoding": 100,
  "weather_api_key": "<your-accuweather-key>",
  "location_key": "<your-location-key>",
  "animation_duration": 10,
  "delay_between_images": 10,
  "animation_fps": 30,
  "allow_translucent_background": true,
  "image_dir": "Images",
  "font_name": "arial.ttf",
  "time_font_size": 80,
  "date_font_size": 50,
  "margin_left": 50,
  "margin_bottom": 80,
  "margin_right": 50,
  "spacing_between": 50,
  "stats": {
    "show": true,
    "font_size": 20,
    "font_color": "yellow"
  }
}
```

- **backend_configs**: Flask host, port, MJPEG dimensions, secret key  
- **image_quality_encoding**: JPEG quality for streamed frames (0–100)  
- **weather_api_key/location_key**: for live weather overlay  
- **animation_duration** & **delay_between_images**: slideshow timing  
- **animation_fps**: transition smoothness  
- **allow_translucent_background**: enable blurred background behind images  
- **font_***, **margin_***, **spacing_between**: on-screen text layout  
- **stats**: toggle system stats overlay  

## Project Structure

```
.
├── PhotoFrameServer.py        # Main engine and entry point
├── API.py                     # Flask backend and routes
├── Settings.py                # Thread-safe settings loader
├── image_handler.py           # Resize and background utilities
├── EffectHandler.py           # Transition effect selection
├── iFrame.py                  # Abstract base for frame interface
├── Requirments.txt            # Python dependencies
├── settings.json              # Configuration file
├── templates/                 # Jinja2 templates (index, login, signup)
├── static/
│   ├── styles.css             # UI styles
│   └── scripts.js             # UI logic
└── Images/                    # Drop your image files here
```

## Notes

- Rename `Requirments.txt` to `requirements.txt` if needed.  
- Supported image formats: PNG, JPEG, GIF, BMP, TIFF, WEBP, HEIC/HEIF (requires `pyheif`).  
- To create the first user, visit `http://<host>:<port>/signup`.  
- Logs are written to `PhotoFrame.log` and viewable in the UI.

---

Q1: Would you like example systemd service files for running the engine and web UI on boot?  
Q2: Do you need a sample Docker Compose file tailored to this project?  
Q3: Should I add instructions for embedding the MJPEG stream inside a Tkinter or PyQT desktop window?
