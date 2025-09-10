# 📸 Digital Photo Frame

A modern, high-performance photo-frame engine with a web UI. Runs on Raspberry Pi or any Linux/Windows machine. Plays animated slideshows, overlays time/date and weather, and exposes a browser-based management UI.

## 🚀 Quick Start

```bash
git clone <your-repo-url> DigitalPhotoFrame
cd DigitalPhotoFrame
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
mkdir -p Images
python app.py --headless --settings photoframe_settings.json
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

## 🛠️ Installation

### 📦 Raspberry Pi (systemd service)

```bash
cd /home/pi/Desktop/DigitalPhotoFrame
chmod +x install_photoframe_service.sh
./install_photoframe_service.sh
```

Service management:

```bash
sudo systemctl status PhotoFrame_Desktop_App
sudo systemctl restart PhotoFrame_Desktop_App
sudo systemctl stop PhotoFrame_Desktop_App
```

### 🖥️ Manual install

```bash
git clone <your-repo-url> DigitalPhotoFrame
cd DigitalPhotoFrame
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
mkdir -p Images
python app.py
```

## ⚙️ Configuration

Example `settings.json`:

```json
"backend_configs": {
  "host": "0.0.0.0",
  "server_port": 5002,
  "stream_width": 1920,
  "stream_height": 1080,
  "stream_fps": 30,
  "idle_fps": 5,
  "supersecretkey": "YOUR_SUPERSECRET_KEY"
}
```

- `stream_fps`: fps during transitions
- `idle_fps`: fps when idle

## 🐛 Troubleshooting

- 🔁 **Every other frame shows “waiting for frame”** → increase `idle_fps`
- 🛑 **Stream freezes but GUI works** → check `srv.m_api = backend` wiring in `app.py`
- 🌐 **Client disconnects** → disable proxy buffering in nginx:

```nginx
location /stream {
    proxy_pass http://127.0.0.1:5002/stream;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
}
```

## 📂 Project layout

```
FrameServer/
├── PhotoFrameServer.py
├── EffectHandler.py
├── WebAPI/API.py
├── Effects/
├── static/
├── templates/
└── Images/
```

## 📜 License

Licensed under the terms in `LICENSE` (non-commercial use).

## 🙏 Acknowledgements

- OpenCV for image processing
- Pillow for font rendering
- AccuWeather / Open-Meteo for weather
- PySide6/Tkinter for GUI
