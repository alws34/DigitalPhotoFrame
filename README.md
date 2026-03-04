# 📸 Digital Photo Frame

![Build Status](https://github.com/alon/DigitalPhotoFrame/actions/workflows/tests.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

A modern, high-performance photo-frame engine with a web UI. Runs on Raspberry Pi or any Linux/Windows machine. Plays animated slideshows, overlays time/date and weather, and exposes a browser-based management UI.

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- `git`

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/alon/DigitalPhotoFrame.git
    cd DigitalPhotoFrame
    ```

2.  **Create a virtual environment:**

    ```bash
    python3 -m venv env
    source env/bin/activate  # On Windows: env\Scripts\activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install -e .
    ```

4.  **Configuration:**
    Copy the example settings file and customize it:

    ```bash
    cp photoframe_settings.example.json photoframe_settings.json
    # Edit photoframe_settings.json with your preferred text editor
    ```

5.  **Run:**

    ```bash
    mkdir -p Images
    # Run the application
    python app.py
    ```

    Open 👉 `http://<host>:<port>/stream` in your browser.

## ✨ Highlights

- 🎞️ Smooth 30 FPS compositor that keeps clock/weather live between transitions
- 🌐 Live MJPEG stream served by Flask backend (`/stream`) — always in sync with GUI frame
- 🖼️ Idle streaming: pushes last good frame at configurable `idle_fps` (no “waiting for frame” flicker)
- 🖌️ Efficient overlay pipeline: cached RGBA overlay alpha-blended over BGR frames
- ⚙️ Dynamic Settings editor tab: auto-builds UI from `settings.json`
- 🗂️ Filesystem watcher that picks up newly added photos automatically
- 📡 Optional MQTT heartbeat and Home Assistant discovery
- 💻 Works headless or with a local Qt/Tkinter preview window

## 🏗️ Architecture

### Core components

- **PhotoFrameServer.py** → loads images, runs transitions, owns `frame_to_stream`
- **WebAPI/API.py** → Flask backend, streams MJPEG at `stream_fps` / `idle_fps`
- **app.py** → entry point, wires PhotoFrameServer to Backend, GUI or headless

### Stream behavior

- Transitions: fresh frames at `animation_fps`
- Idle: last frame re-published at `idle_fps` (default 5)
- Heartbeat JPEG only if producer stops

## 🎨 Transition effects

Generators that yield `np.uint8 (H,W,3)` frames. Includes:

- AlphaDissolve, PixelDissolve, Checkerboard, Blinds, Scroll, Wipe
- ZoomIn, ZoomOut, IrisOpen, IrisClose, BarnDoorOpen, BarnDoorClose
- Shrink, Stretch, Linear, Plain
- SoftWipe, Ripple

## ⚡ Performance notes

- Overlay re-rendered at most once per second or on weather change
- Alpha blend in one vectorized pass
- Idle streaming keeps clients alive with `idle_fps`
- OpenCV optimizations enabled

Tuning:

- Lower `backend_configs.stream_fps` or `animation_fps`
- Reduce `image_quality_encoding`
- Use 1280x720 on low-power devices
- Adjust `idle_fps`

## 🛠️ Deployment (Raspberry Pi)

See [install_photoframe_service.sh](install_photoframe_service.sh) for systemd service installation.

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgements

- OpenCV for image processing
- Pillow for font rendering
- AccuWeather / Open-Meteo for weather
- PySide6/Tkinter for GUI
