
# 📷 Digital Photo Frame

A modern, customizable **photo frame application** with touchscreen support and web interface support. Built with Python, it displays beautiful image transitions, shows real-time weather, and allows remote management via a browser.

---

## 🧠 Overview

This project includes:

- A **Tkinter-based Desktop App** designed for Raspberry Pi (SPI touch screen support).
- A **Flask-based Backend** for image management and live streaming.
- Optional **weather overlay**, **stats display**, and **touch gestures**.
- Two deployment options: **Docker** and **Native (systemd + venv)**.


---

## ⚙️ Settings Files

### `settings.json` (used by backend and main slideshow)

```json
{
  "images_dir_full_path": "./Images",
  "animation_duration": 10,
  "delay_between_images": 30,
  "allow_translucent_background": true,
  "weather_api_key": "",
  "location_key": "",
  "backend_configs": {
    "server_port": 5001,
    "host": "0.0.0.0"
  }
}
```

### `photoframe_settings.json` (used by desktop app)

```json
{
  "font_name": "arial.ttf",
  "time_font_size": 80,
  "date_font_size": 50,
  "margin_left": 80,
  "margin_bottom": 80,
  "margin_right": 50,
  "spacing_between": 50,
  "weather_api_key": "",
  "location_key": "",
  "backend_configs": {
    "server_port": 5001,
    "host": "0.0.0.0"
  },
  "stats": {
    "show": true,
    "font_size": 20,
    "font_color": "yellow"
  }
}
```

---

## ✨ Capabilities

- 🖼️ **Slideshow with animated transitions**
- 🌦️ **Weather overlay** via AccuWeather API (optional)
- 🧠 **System stats**: CPU, RAM, temperature
- 👆 **Triple tap gesture** to toggle stats on screen
- 🌐 **Web-based UI** to upload, edit, delete images
- 🧾 **Live streaming** over LAN (`/live_feed`)

---

## 🚀 Installation Instructions

### Option 1: Docker (Backend + Desktop)

#### 🔧 Backend

1. Build & Run:

```bash
docker compose up -d --build
```

This runs the Flask backend at `http://<device>:5001`.

#### 🖥️ Desktop App (Tested with Raspberry Pi)
```bash
cd /home/pi/DigitalPhotoFrame/DesktopApp
chmod +x install_photoframe_service.sh
sudo ./install_photoframe_service.sh

sudo systemctl status PhotoFrame_Desktop_App #if needed
sudo systemctl restart PhotoFrame_Desktop_App #if needed
```


#### 📦 Backend

```bash
cd /home/pi/DigitalPhotoFrame
docker-compose down --remove-orphans
docker-compose build --no-cache
docker-compose up -d
docker logs -f photoframe_web 
```

---

## 📝 Notes

- Use `.json` files to customize layout, weather, and font sizes.
- Install `pyheif` if you want to support HEIC image uploads.
- Make sure your `arial.ttf` is available or change the font name.

---

Enjoy your smart photo frame!
