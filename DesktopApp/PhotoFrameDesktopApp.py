import json
import logging
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import sys
import os


sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Handlers.weather_handler import weather_handler
from iFrame import iFrame
import threading
import psutil
import requests
import cv2
import numpy as np
import time


class MJPEGStreamClient:
    def __init__(self, url):
        self.url = url
        self.stream = None

    def get_frames(self):
        try:
            stream = requests.get(self.url, stream=True, timeout=5)
            if stream.status_code != 200:
                print(f"[MJPEGStreamClient] HTTP {stream.status_code}, no stream.")
                yield None
                return

            content_type = stream.headers.get("Content-Type", "")
            if "boundary=" in content_type:
                self.boundary = content_type.split("boundary=")[1]
            else:
                self.boundary = "--frame"

            buffer = b""
            for chunk in stream.iter_content(chunk_size=1024):
                buffer += chunk
                while True:
                    start = buffer.find(b'\xff\xd8')  # JPEG start
                    end = buffer.find(b'\xff\xd9')    # JPEG end
                    if start != -1 and end != -1 and end > start:
                        jpg = buffer[start:end + 2]
                        buffer = buffer[end + 2:]
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            yield frame
                    else:
                        break
        except requests.exceptions.RequestException as e:
            yield None             
                  

class PhotoFrame(tk.Frame, iFrame):
    """
    A tkinter frame that fetches frames from an MJPEG server, resizes them,
    and displays the live video stream.
    
    The image handling (fetching and resizing) is decoupled from the frame display.
    """
    def __init__(self, parent, stream_url, desired_width, desired_height, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.stream_url = stream_url
        self.desired_width = desired_width
        self.desired_height = desired_height
        self.triple_tap_count = 0
        self.last_tap_time = 0
        self.show_stats = settings.get("stats", {}).get("show", False)
        self.cached_stats = self.get_system_stats()
        
        if isinstance(self.parent, tk.Tk):
            self.parent.title("Digital Photo Frame V2.0")
            self.parent.geometry(f"{self.parent.winfo_screenwidth()}x{self.parent.winfo_screenheight()}+0+0")
            self.parent.attributes("-fullscreen", True)
            self.parent.wm_attributes("-topmost", True)
            self.parent.configure(bg='black')
            self.parent.config(cursor="none")
            self.parent.option_add('*Cursor', 'none')
            self.parent.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.parent.bind_all('<Control-c>', lambda e: self.on_closing())
            self.parent.bind("<Button-1>", self.handle_triple_tap)
        self.time_font = ImageFont.truetype(settings['font_name'], settings['time_font_size'])
        self.date_font = ImageFont.truetype(settings['font_name'], settings['date_font_size'])
        self.font_temp = self.time_font  # reuse
        self.font_desc = self.date_font  # reuse
        stats_font_path = settings['font_name']
        stats_font_size = settings.get("stats", {}).get("font_size", 20)
        self.stats_font = ImageFont.truetype(stats_font_path, stats_font_size)

        self.label = tk.Label(self, bg='black')
        self.label.pack(fill="both", expand=True)
        
        self.stream_client = MJPEGStreamClient(self.stream_url)
        self.current_frame = None
        self.stop_event = threading.Event()
        
        self.fetch_thread = threading.Thread(target=self.frame_fetch_loop, daemon=True)
        self.fetch_thread.start()

        self.weather_client = weather_handler(frame = self, settings= settings)
        self.weather_thread = threading.Thread(target=self.weather_loop, daemon=True)
        self.weather_thread.start()
        self.stats_thread = threading.Thread(target=self.update_stats_loop, daemon=True)
        self.stats_thread.start()
        
        self.update_display()

    def send_log_message(self, msg, logger: logging):
        print(msg)
    
    def handle_triple_tap(self, event):
        now = time.time()
        if now - self.last_tap_time < 1.5:
            self.triple_tap_count += 1
        else:
            self.triple_tap_count = 1  # Restart counting

        self.last_tap_time = now

        if self.triple_tap_count == 3:
            self.show_stats = not self.show_stats
            print(f"Stats display toggled to {self.show_stats}")
            self.triple_tap_count = 0

    def weather_loop(self):
        while not self.stop_event.is_set():
            self.weather_client.fetch_weather_data()
            time.sleep(600)  # Every 10 minutes

    def add_stats_to_frame(self, frame):
        font_path = settings['font_name']
        font_size = settings['stats']['font_size']
        font_color = settings['stats']['font_color']

        color_map = {
            "yellow": (255, 255, 0),
            "white": (255, 255, 255),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255)
        }
        font_color = color_map.get(font_color.lower(), (255, 255, 0))

        pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)
        draw.text((10, 10), self.cached_stats, font=self.stats_font, fill=font_color)

        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    def on_closing(self):
        """Handler for window close event."""
        self.stop_event.set()
        self.parent.destroy()

    def resize_image(self, cv_img):
        """
        Resizes the given OpenCV image to fit within the desired dimensions while
        preserving its aspect ratio. It also centers the resized image on a black background.
        """
        h, w, _ = cv_img.shape
        aspect_ratio = w / h
        desired_aspect = self.desired_width / self.desired_height

        if aspect_ratio > desired_aspect:
            new_w = self.desired_width
            new_h = int(self.desired_width / aspect_ratio)
        else:
            new_h = self.desired_height
            new_w = int(self.desired_height * aspect_ratio)
        
        resized_img = cv2.resize(cv_img, (new_w, new_h))
        
        # Create a black background and center the resized image on it
        background = np.zeros((self.desired_height, self.desired_width, 3), dtype=np.uint8)
        x_offset = (self.desired_width - new_w) // 2
        y_offset = (self.desired_height - new_h) // 2
        background[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized_img
        
        return background
    
    def get_fallback_frame(self, text="Waiting for stream..."):
        """
        Returns a black image with centered white text.
        """
        # Create black background
        img = Image.new('RGB', (self.desired_width, self.desired_height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        font = self.date_font  # Use your existing font
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (self.desired_width - text_width) // 2
        y = (self.desired_height - text_height) // 2

        draw.text((x, y), text, font=font, fill=(255, 255, 255))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


    def frame_fetch_loop(self):
        """
        Continuously fetch frames from the MJPEG client, resize them,
        and update the current_frame variable.
        """
        for frame in self.stream_client.get_frames():
            if self.stop_event.is_set():
                break
            if frame is None:
                self.current_frame = self.get_fallback_frame("Waiting for stream...")
                time.sleep(5)
                break
            resized_frame = self.resize_image(frame)
            self.current_frame = resized_frame
            # Sleep briefly to allow a consistent fetch rate (~30 FPS)
            time.sleep(1/30)

    def update_display(self):
        """
        Periodically updates the tkinter label with the latest frame.
        This method is scheduled using after() to ensure updates occur in the GUI thread.
        """
        if self.current_frame is not None:
            # Convert the BGR image to RGB
            overlay_frame = self.add_overlay_text(self.current_frame.copy())
            cv_img_rgb = cv2.cvtColor(overlay_frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(cv_img_rgb)
            image_tk = ImageTk.PhotoImage(pil_image)
            self.label.config(image=image_tk)
            self.label.image = image_tk  # Keep a reference to avoid garbage collection
        # Schedule the next update (about every 33 ms for ~30 FPS)
        self.after(33, self.update_display)

    def stop(self):
        """Stops the background frame fetching thread."""
        self.stop_event.set()

    def add_overlay_text(self, frame):
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%d/%m/%y")

        font_path = settings['font_name']
        time_font_size = settings['time_font_size']
        date_font_size = settings['date_font_size']
        margin_left = settings['margin_left']
        margin_bottom = settings['margin_bottom']
        spacing = settings['spacing_between']
        margin_right = settings.get('margin_right', 50)
        font_color = (255, 255, 255)

        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        # Draw time and date
        time_bbox = draw.textbbox((0, 0), current_time, font=self.time_font)
        date_bbox = draw.textbbox((0, 0), current_date, font=self.date_font)

        x_date = margin_left
        x_time = x_date + (date_bbox[2] - date_bbox[0] - (time_bbox[2] - time_bbox[0])) // 2
        y_date = self.desired_height - margin_bottom
        y_time = y_date - (date_bbox[3] - date_bbox[1]) - spacing

        draw.text((x_time, y_time), current_time, font=self.time_font, fill=font_color)
        draw.text((x_date, y_date), current_date, font=self.date_font, fill=font_color)

        # Draw weather if available
        weather = self.weather_client.get_weather_data()
        icon = self.weather_client.get_weather_icon()

        if weather and icon:
            temp_text = f"{weather['temp']}°{weather['unit']}"
            desc_text = weather['description']

            temp_bbox = draw.textbbox((0, 0), temp_text, font=self.time_font)
            desc_bbox = draw.textbbox((0, 0), desc_text, font=self.font_desc)

            icon_size = 100
            x_icon = self.desired_width - margin_right - icon_size
            y_icon = self.desired_height - margin_bottom - icon_size

            x_temp = x_icon - spacing - (temp_bbox[2] - temp_bbox[0])
            y_temp = y_icon + (icon_size - (temp_bbox[3] - temp_bbox[1])) // 2

            x_desc = x_temp
            y_desc = y_temp + (temp_bbox[3] - temp_bbox[1]) + 10

            icon_resized = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            pil_img.paste(icon_resized, (x_icon, y_icon), icon_resized)
            draw.text((x_temp, y_temp), temp_text, font=self.date_font , fill=font_color)
            draw.text((x_desc, y_desc), desc_text, font=self.date_font, fill=font_color)

        # Move this out of the if block so it's always executed
        frame_with_text = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        if self.show_stats:
            try:
                frame_with_text = self.add_stats_to_frame(frame_with_text)
            except Exception as e:
                print("Error adding stats to frame:", e)

        return frame_with_text

    def get_system_stats(self):
        #cpu = cv2.getCPUTickCount()
        cpu_usage = int(psutil.cpu_percent(interval=1))

        ram = psutil.virtual_memory()
        ram_used = ram.used // (1024 * 1024)
        ram_total = ram.total // (1024 * 1024)
        ram_percent = ram.percent

        try:
            cpu_temps = psutil.sensors_temperatures().get("cpu_thermal", [])
            cpu_temp = round(cpu_temps[0].current, 1) if cpu_temps else "N/A"
        except Exception:
            cpu_temp = "N/A"

        return f"CPU: {cpu_usage}%\nRAM: {ram_percent}% ({ram_used}/{ram_total}MB)\nCPU Temp: {cpu_temp}°C"

    def update_stats_loop(self):
        while not self.stop_event.is_set():
            self.cached_stats = self.get_system_stats()
            time.sleep(5)


if __name__ == "__main__":
    with open(os.getcwd() + "/photoframe_settings.json", "r") as f:
        settings = json.load(f)

    backend_host = settings.get("backend_configs", {}).get("host", "localhost")
    if backend_host == "0.0.0.0":
        backend_host = "127.0.0.1"    
    backend_port = settings.get("backend_configs", {}).get("server_port", 5001)
    print(backend_host)
    print(backend_port)
    STREAM_URL = f"http://{backend_host}:{backend_port}/video_feed"

    os.environ["DISPLAY"] = ":0"
    root = tk.Tk()
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    mjpeg_frame = PhotoFrame(root, stream_url=STREAM_URL, desired_width=screen_width, desired_height=screen_height)
    mjpeg_frame.pack(fill="both", expand=True)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        mjpeg_frame.stop()
        root.destroy()
