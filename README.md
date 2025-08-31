# Digital Photo Frame

A modern, high-performance photo-frame engine with a web UI. Runs on Raspberry Pi or any Linux/Windows machine. Plays animated slideshows, overlays time/date and weather, and exposes a browser-based management UI.

## Highlights

- Smooth 30 FPS compositor that keeps clock/weather live between transitions
- Efficient overlay pipeline: cached RGBA overlay alpha-blended over BGR frames
- Zero background behind text by default (no panel), optional translucent panels
- Dynamic Settings editor tab: auto-builds UI from `settings.json` (free fields in one page; nested objects as tabs; Save/Revert)
- Robust, vectorized OpenCV effects implemented as Python generators
- Filesystem watcher that picks up newly added photos automatically
- Optional MQTT heartbeat and Home Assistant discovery
- Works headless or with a local Tkinter preview window

## Architecture

### Core process
- **PhotoFrameServer.py**
  - Loads and shuffles images from `Images/`
  - Drives transition generators at a paced 30 FPS
  - Continuous compositor thread that renders time/date/weather even when not transitioning
  - Alpha-blends a cached overlay (time/date/weather) over the current base image
  - Exposes a backend API (WebAPI/Backend) for the browser UI

### Overlay pipeline
- `OverlayRenderer.render_overlay_rgba()` builds an RGBA overlay only when needed (once per second or when weather changes).
- `_blend_rgba_over_bgr()` composites the cached overlay onto the current frame with a single vectorized pass.
- No background panel is drawn unless `allow_translucent_background` or `overlay_panels` is enabled.

### Dynamic settings UI
- The Settings dialog now has a **Config** tab that renders from `settings.json`:
  - All top-level non-dict keys appear together under "General".
  - Each top-level dict gets its own tab (and sub-tabs for nested dicts).
  - Type-aware editors: bool -> checkbox, number -> entry, string -> entry, list/dict -> JSON text.
  - Save and Revert buttons at the bottom. The dialog stays always-on-top.

## Transition effects

All effects are implemented as **generators** that yield `np.uint8 (H,W,3)` BGR frames. Images are resized beforehand to match output resolution.

Included (vectorized, broadcast-safe):
- AlphaDissolve
- PixelDissolve
- Checkerboard
- Blinds
- Scroll
- Wipe
- ZoomIn
- ZoomOut
- IrisOpen
- IrisClose
- BarnDoorOpen
- BarnDoorClose
- Shrink
- Stretch
- Linear
- Plain (no transition)
- SoftWipe (cosine eased directional wipe; up/down/left/right, can be randomized)
- Ripple (centered radial water ripple with robust `cv2.remap` maps in `float32`, supports multiple rings)

> Note: EffectHandler selects effects in a rotating random order. You can disable or pin a subset by editing `EffectHandler.effects`.

### Writing a new effect

```python
import numpy as np

def MyEffect(img1, img2, duration, fps=30):
    # img1, img2 are np.uint8 BGR with identical shape
    h, w = img1.shape[:2]
    steps = max(1, int(duration * fps))
    for i in range(steps):
        t = i / float(steps - 1) if steps > 1 else 1.0
        # build a mask with shape (H,W,1) for broadcasting
        mask = (t > 0.5).astype(np.uint8)[None, None, None]
        mask = np.ones((h, w, 1), dtype=np.uint8) * mask  # example only
        # composite
        yield np.where(mask > 0, img2, img1)
```

Rules of thumb:
- Never allocate inside the inner loop if you can pre-allocate outside.
- Use broadcast-friendly masks of shape `(H,W,1)`.
- Keep all arrays `np.uint8` unless a specific operation needs `float32`.
- For `cv2.remap`, both `map_x` and `map_y` must be `float32` and same shape `(H,W)`.

## Performance notes

- Frame pacing at 30 FPS with `self._frame_interval`
- Overlay re-rendered at most once per second or on weather change
- Alpha blend done in one vectorized pass
- Transition generators expected to yield frames quickly; most compute is vectorized
- Optional full-width contrast band is disabled by default; use `overlay_panels` instead if needed
- OpenCV compiled with NEON/AVX helps a lot on ARM/x86

Tuning:
- Lower `backend_configs.stream_fps` or `animation_fps`
- Reduce `image_quality_encoding` (JPEG quality)
- Disable weather if the device is network constrained
- Use 1280x720 output on low-power devices

## Installation

### Quick install on Raspberry Pi (systemd service)

The repo includes `install_photoframe_service.sh`, which:
- Installs NetworkManager + polkit rules for passwordless Wi-Fi control by user `pi`
- Creates a Python venv and installs `requirements.txt`
- Sets up a systemd service named `PhotoFrame_Desktop_App`
- Generates Desktop helper scripts to start/stop/restart the service

Run it on the Pi:

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

If you prefer manual setup, see the steps below.

### Manual install

Prerequisites:
- Python 3.9+ recommended
- pip, venv, git
- On Raspberry Pi: `sudo apt-get install python3-tk libjpeg-dev libopenjp2-7 libheif1 libheif-dev`

Steps:

```bash
git clone <your-repo-url> DigitalPhotoFrame
cd DigitalPhotoFrame

python3 -m venv env
source env/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

mkdir -p Images
```

Start the app:

```bash
python PhotoFrameServer.py
```

- Slideshow will run and the backend API will start.
- Browse to `http://<host>:<port>/` for the web UI (port comes from `backend_configs.server_port`).

## Configuration

All configuration lives in `settings.json`. The dynamic Config tab in the UI renders it for you. Below is a representative example:

```json
{
  "font_name": "arial.ttf",
  "service_name": "PhotoFrame_Desktop_App",
  "time_font_size": 120,
  "date_font_size": 80,
  "margin_left": 80,
  "margin_bottom": 30,
  "margin_right": 50,
  "spacing_between": 50,
  "image_quality_encoding": 100,
  "animation_duration": 10,
  "delay_between_images": 10,
  "animation_fps": 30,
  "allow_translucent_background": false,
  "image_dir": "Images",

  "accuweather_api_key": "YOUR_ACCUWEATHER_API_KEY",
  "accuweather_location_key": "YOUR_LOCATION_KEY",

  "open_meteo": {
    "latitude": "32.0853",
    "longitude": "34.7818",
    "units": "metric",
    "timezone": "auto",
    "temperature_unit": "celsius",
    "windspeed_unit": "kmh",
    "wind_speed_unit": "kmh",
    "precipitation_unit": "mm",
    "timeformat": "iso8601",
    "cache_ttl_minutes": 60
  },

  "backend_configs": {
    "host": "0.0.0.0",
    "server_port": 5002,
    "stream_width": 1920,
    "stream_height": 1080,
    "stream_fps": 30,
    "supersecretkey": "YOUR_SUPERSECRET_KEY"
  },

  "stats": {
    "show": true,
    "font_size": 20,
    "font_color": "yellow"
  },

  "about": {
    "text": "Digital Photo Frame by alws34...",
    "image_path": ""
  },

  "screen": {
    "orientation": 270,
    "brightness": 100,
    "schedule_enabled": true,
    "off_hour": 0,
    "on_hour": 8,
    "schedules": "[{'enabled': true, 'off_hour': 0, 'on_hour': 8, 'days': [0,1,2,3,4,5,6]}]"
  },

  "mqtt": {
    "enabled": true,
    "host": "",
    "port": 1883,
    "username": "",
    "password": "",
    "tls": false,
    "client_id": "photoframe-livingroom",
    "base_topic": "photoframe",
    "discovery": true,
    "discovery_prefix": "homeassistant",
    "interval_seconds": 1,
    "retain_config": true
  },

  "autoupdate": {
    "enabled": true,
    "hour": 4,
    "minute": 0,
    "repo_path": "",
    "remote": "origin",
    "branch": "None",
    "shallow_ok": true
  },

  "overlay_panels": {
    "alpha": 128,
    "padding": 12,
    "radius": 10,
    "keep_band_with_panels": false
  }
}
```

Notes:
- The `screen.schedules` field is accepted as a JSON string for backward compatibility; the UI normalizes it.
- When `allow_translucent_background` is false, text is drawn directly with no background.
- If you enable panels via `allow_translucent_background` or `overlay_panels`, rounded rectangles are drawn behind text.

## Troubleshooting

### Broadcasting errors
```
ValueError: operands could not be broadcast together with shapes ...
```
Cause: using a 2D mask with `(H,W)` against 3-channel images.  
Fix: expand to `(H,W,1)` and rely on broadcasting.

```python
mask = mask.astype(bool)
mask3 = mask[..., None]  # shape (H,W,1)
frame = np.where(mask3, img2, img1)
```

### remap assertion
```
cv2.error: ... error: (-215:Assertion failed) ((map1.type() == CV_32FC2 ... ) in function 'remap'
```
Cause: `map_x`, `map_y` not `float32` or mismatched shapes.  
Fix: build both as `np.float32` of shape `(H,W)`.

```python
map_x = (grid_x + dx).astype(np.float32)
map_y = (grid_y + dy).astype(np.float32)
warped = cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
```

### Performance still stutters
- Ensure output resolution is attainable on your device (try 1280x720).
- Use release build of OpenCV with NEON/AVX.
- Reduce `animation_fps` and `backend_configs.stream_fps`.
- Avoid heavy Python loops in effects; prefer NumPy ops.

## Project layout (selected)

```
FrameServer/
├── PhotoFrameServer.py
├── EffectHandler.py
├── overlay.py
├── image_handler.py
├── WebAPI/
│   └── API.py
├── Effects/
│   ├── AlphaDissolveEffect.py
│   ├── BarnDoorCloseEffect.py
│   ├── BarnDoorOpenEffect.py
│   ├── BlindsEffect.py
│   ├── CheckerboardEffect.py
│   ├── IrisCloseEffect.py
│   ├── IrisOpenEffect.py
│   ├── LinearEffect.py
│   ├── PixelDissolveEffect.py
│   ├── PlainEffect.py
│   ├── ScrollEffect.py
│   ├── ShrinkEffect.py
│   ├── SoftWipeEffect.py
│   ├── StretchEffect.py
│   ├── WipeEffect.py
│   ├── ZoomInEffect.py
│   ├── ZoomOutEffect.py
│   └── RippleEffect.py
├── templates/
├── static/
├── install_photoframe_service.sh
└── Images/
```

## License

This project is licensed under the terms in `LICENSE` (non-commercial use; see file).

## Acknowledgements

- OpenCV for image processing
- Pillow for font rendering
- AccuWeather / Open-Meteo for weather data
- Tkinter for local preview and settings UI

---

If you want badges, screenshots, or short GIFs of transitions in the README, add them to `static/` and I can wire them in.
