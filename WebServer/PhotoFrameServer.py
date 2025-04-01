#region imports
import logging
import json
import threading
import time
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import requests
import cv2
import random as rand
import os
from enum import Enum
import numpy as np
from abc import ABC, abstractmethod
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import psutil 
import hashlib
import datetime
from ManagerBackend import ManagerBackend
from Handlers.image_handler import Image_Utils
from Handlers.mjpeg_server import mjpeg_server
from Handlers.weather_handler import weather_handler
from Handlers.observer import ImagesObserver
from iFrame import iFrame
# region Importing Effects
from Effects.CheckerboardEffect import CheckerboardEffect
from Effects.AlphaDissolveEffect import AlphaDissolveEffect
from Effects.PixelDissolveEffect import PixelDissolveEffect
from Effects.BlindsEffect import BlindsEffect
from Effects.ScrollEffect import ScrollEffect
from Effects.WipeEffect import WipeEffect
from Effects.ZoomOutEffect import ZoomOutEffect
from Effects.ZoomInEffect import ZoomInEffect
from Effects.IrisOpenEffect import IrisOpenEffect
from Effects.IrisCloseEffect import IrisCloseEffect
from Effects.BarnDoorOpenEffect import BarnDoorOpenEffect
from Effects.BarnDoorCloseEffect import BarnDoorCloseEffect
from Effects.ShrinkEffect import ShrinkEffect
from Effects.StretchEffect import StretchEffect
from Effects.PlainEffect import PlainEffect
# endregion Importing Effects

from Utilities.NotificationManager import NotificationManager
#endregion imports

# region Logging Setup
log_file_path = os.path.join(os.path.dirname(__file__), "PhotoFrame.log")
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO) 
console_formatter = logging.Formatter("%(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)
logging.getLogger().addHandler(console_handler)
logging.info("PhotoFrame application starting...")
# endregion Logging Setup


class AnimationStatus(Enum):
    ANIMATION_FINISHED = 1
    ANIMATION_ERROR = 2

class PhotoFrame(iFrame):
    def __init__(self):
        logging.debug("Initializing PhotoFrame...")
        try:
            with open("settings.json", 'r') as file:
                self.settings = json.load(file)
            logging.info("Loaded settings from settings.json.")
        except FileNotFoundError:
            logging.error("settings.json not found. Exiting.")
            raise

        self.images_dir_full_path = self.settings["images_dir_full_path"]
        if not os.path.exists(self.images_dir_full_path):
            os.mkdir(self.images_dir_full_path)
            logging.warning("'Images' directory not found. Created a new one.")
            return
        
        self.logger = logging.getLogger(__name__)

        self.effects = self.set_effects()
        self.images = self.get_images_from_directory()
        self.shuffled_images = list(self.images)
        self.shuffled_effects = list(self.effects.keys())
        self.current_image_idx = -1
        self.current_effect_idx = -1
        self.root = None
        self.frame = None
        self.label = None
        self.screen_width = None
        self.screen_height = None
        self.current_image = None
        self.next_image = None

        self.wait_time = self.settings["delay_between_images"]
        self.is_running = True
        
        self.image_handler = Image_Utils(settings = self.settings)
        self.mjpeg_server = mjpeg_server(frame = self)
        self.Observer = ImagesObserver(frame = self) 
        self.weather_handler = weather_handler(frame = self, settings = self.settings)
 
        self.manager_backend = ManagerBackend() 
        self.manager_backend.start()

        #self.weather_handler.fetch_weather_data()
        self.weather_handler.initialize_weather_updates()
        self.Observer.start_observer()
        
        self.notification_manager = None
        
        self.triple_tap_count = 0  # Counter for triple tap detection
        self.last_tap_time = 0
       
        # Cached system stats and update time
        self.cached_stats = ""
        self.last_stats_update = 0

        # Start background thread to update stats every second
        #self.stats_thread = threading.Thread(target=self.update_stats_loop, daemon=True)
        #self.stats_thread.start()
        

# region guestbook
    def update_image_metadata(self, image_path):
        image_hash = self.compute_image_hash(image_path)
        db_file = "image_db.json"
        try:
            if os.path.exists(db_file):
                with open(db_file, "r") as f:
                    data = json.load(f)
            else:
                data = {}

            # If the image already exists, do not update date_added.
            if image_hash in data:
                metadata = data[image_hash]
            else:
                metadata = {
                    "hash": image_hash,
                    "uploader": "unknown",
                    "date_added": datetime.datetime.now().isoformat(),
                    "caption": ""
                }

            # Save updated data back to DB
            data[image_hash] = metadata
            with open(db_file, "w") as f:
                json.dump(data, f, indent=4)

        except Exception as e:
            self.logger.error(f"Error updating image DB: {e}")

        # Broadcast the final metadata to ManagerBackend
        if hasattr(self, "manager_backend"):
            self.manager_backend.update_metadata(metadata)
        
# endregion guestbook

# region Utils
    def compute_image_hash(self, image_path):
        hash_md5 = hashlib.md5()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
        def update_stats_loop(self):
            """Runs in a separate thread to update system stats every second."""
            while self.is_running:
                self.cached_stats = self.get_system_stats()
                time.sleep(1)

        
    def send_log_message(self, msg, logger: logging):
        logger(msg)
        
    def on_touch_event(self, event):
        """Handler for touchscreen events. Does nothing."""
        logging.info(f"Touch event detected: {event}. Ignored.")
        if event.type == "swipe" and event.direction == "right":
            self.notification_manager.remove_all_notifications()
        
    def set_effects(self):
        return {
            0: AlphaDissolveEffect,
            1: PixelDissolveEffect,
            2: CheckerboardEffect,
            3: BlindsEffect,
            4: ScrollEffect,
            5: WipeEffect,
            6: ZoomOutEffect,
            7: ZoomInEffect,
            8: IrisOpenEffect,
            9: IrisCloseEffect,
            10: BarnDoorOpenEffect,
            11: BarnDoorCloseEffect,
            12: ShrinkEffect,
            13: StretchEffect,
            # 14: PlainEffect
        }

    def get_images_from_directory(self):
        """Gets all image files (as paths) from a given directory.

        Args:
            directory_path: The path to the directory to search for images.

        Returns:
            A list of paths to image files found in the directory.
        """
        image_extensions = [".jpg", ".jpeg", ".png",
                            ".gif"]  # Add more extensions if needed
        image_paths = []

        for root, dirs, files in os.walk(self.images_dir_full_path):
            for file in files:
                if file.lower().endswith(tuple(image_extensions)):
                    image_path = os.path.join(root, file)
                    image_paths.append(image_path)

        return image_paths

    def get_random_image(self):
        '''Returns a different image path each time.'''
        if len(self.shuffled_images) == 0:
            self.shuffled_images = list(self.images)
            rand.shuffle(self.shuffled_images)
        self.current_image_idx = (self.current_image_idx + 1) % len(self.shuffled_images)
        return self.shuffled_images[self.current_image_idx]

    def get_random_effect(self):
        '''Returns a different effect each time.'''
        if len(self.shuffled_effects) == 0:
            self.shuffled_effects = list(self.effects.keys())
            rand.shuffle(self.shuffled_effects)
        self.current_effect_idx = (
            self.current_effect_idx + 1) % len(self.shuffled_effects)
        return self.shuffled_effects[self.current_effect_idx]
# endregion Utils

# region DateTime
    def add_time_date_to_frame(self, frame):
        """
        Adds the current time, date, and weather to the frame using the settings from the JSON file.

        Args:
            frame: The image frame to modify.

        Returns:
            The modified frame with time, date, and weather added.
        """
        # Get current time and date
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%d/%m/%y")

        # Load font settings
        font_path = self.settings['font_name']
        time_font_size = self.settings['time_font_size']
        date_font_size = self.settings['date_font_size']
        margin_left = self.settings['margin_left']
        margin_bottom = self.settings['margin_bottom']
        spacing_between = self.settings['spacing_between']

        # Load the fonts
        time_font = ImageFont.truetype(font_path, time_font_size)
        date_font = ImageFont.truetype(font_path, date_font_size)

        # Convert frame to PIL Image
        pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)

        # Calculate text sizes
        time_bbox = draw.textbbox((0, 0), current_time, font=time_font)
        date_bbox = draw.textbbox((0, 0), current_date, font=date_font)

        time_text_size = (time_bbox[2] - time_bbox[0], time_bbox[3] - time_bbox[1])
        date_text_size = (date_bbox[2] - date_bbox[0], date_bbox[3] - date_bbox[1])

        # Calculate positions based on settings
        x_date = margin_left
        x_time = x_date + (date_text_size[0] - time_text_size[0]) // 2
        y_date = self.screen_height - margin_bottom
        y_time = y_date - date_text_size[1] - spacing_between

        # Set font color
        font_color = (255, 255, 255)  # White color

        # Draw the time and date on the image
        draw.text((x_time, y_time), current_time, font=time_font, fill=font_color)
        draw.text((x_date, y_date), current_date, font=date_font, fill=font_color)

        # Add weather to the frame
        frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        return self.add_weather_to_frame(frame)
   
    def add_text_to_frame(self, frame):
        frame = self.add_time_date_to_frame(frame)
        frame = self.add_weather_to_frame(frame)
        frame = self.add_stats_to_frame(frame)
        
        return frame
    
    
    def display_image_with_time(self, image, duration):
        """
        Displays the image and updates the time and date labels during the specified duration.

        Args:
            image: The image to display.
            duration: The duration to display the image in seconds.
        """
        #logging.info("Starting to display image with time and weather.")
        start_time = time.time()

        while time.time() - start_time < duration and self.is_running:
            try:
                # Copy the image to avoid modifying the original
                frame = image.copy()
                self.mjpeg_server.update_live_frame(frame)
                # Add time, date, and weather to the frame
                frame = self.add_text_to_frame(frame)
                # Convert OpenCV image to PIL ImageTk format
                # frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # image_pil = Image.fromarray(frame_rgb)
                # image_tk = ImageTk.PhotoImage(image_pil)

                # # Update the label with the new image
                # self.label.config(image=image_tk)
                # self.label.image = image_tk

                # Log successful frame update
                #logging.debug("Updated frame displayed.")

                # Update the GUI
                # self.root.update_idletasks()
                # self.root.update()

            except Exception as e:
                logging.error(f"Error during image display: {e}", exc_info=True)

            # Sleep for a short time to update every second
            time.sleep(1)

        #logging.info("Completed displaying image with time and weather.")

    def add_weather_to_frame(self, frame):
        """
        Adds weather information (temperature, description, icon) to the bottom-right of the frame.

        Args:
            frame: The image frame to modify.

        Returns:
            The modified frame with weather information added.
        """
        if not self.weather_handler.get_weather_data() or not self.weather_handler.get_weather_icon():
            return frame

        try:
            # Load font settings
            font_path = self.settings['font_name']
            time_font_size = self.settings['time_font_size']  # Same as time font
            date_font_size = self.settings['date_font_size']  # Same as date font
            margin_bottom = self.settings['margin_bottom']
            margin_right = self.settings['margin_right']
            spacing_between = self.settings['spacing_between']
            font_color = (255, 255, 255)  # White color

            # Load fonts
            temperature_font = ImageFont.truetype(font_path, time_font_size)
            description_font = ImageFont.truetype(font_path, date_font_size)

            # Prepare weather texts
            temperature_text = f"{self.weather_handler.get_weather_data()['temp']}°{self.weather_handler.get_weather_data()['unit']}"
            description_text = self.weather_handler.get_weather_data()['description']

            # Convert frame to PIL Image
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_image)

            # Calculate text sizes
            temp_bbox = draw.textbbox((0, 0), temperature_text, font=temperature_font)
            desc_bbox = draw.textbbox((0, 0), description_text, font=description_font)

            temp_text_width = temp_bbox[2] - temp_bbox[0]
            temp_text_height = temp_bbox[3] - temp_bbox[1]
            desc_text_width = desc_bbox[2] - desc_bbox[0]
            desc_text_height = desc_bbox[3] - desc_bbox[1]

            # Icon size and position
            icon_size = 100
            x_icon = self.screen_width - margin_right - icon_size
            y_icon = self.screen_height - margin_bottom - icon_size

            # Calculate positions for temperature and description
            x_temp = x_icon - spacing_between - temp_text_width
            y_temp = y_icon + (icon_size - temp_text_height) // 2  # Center temperature vertically with icon

            x_desc = x_temp
            y_desc = y_temp + temp_text_height + 10  # Below the temperature text

            # Draw weather icon
            weather_icon_resized = self.weather_handler.get_weather_icon().resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            pil_image.paste(weather_icon_resized, (x_icon, y_icon), weather_icon_resized)

            # Draw temperature and description
            draw.text((x_temp, y_temp), temperature_text, font=temperature_font, fill=font_color)
            draw.text((x_desc, y_desc), description_text, font=description_font, fill=font_color)

            # Convert back to OpenCV format
            return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        except Exception as e:
            self.logger.error(f"Error during weather rendering: {e}", exc_info=True)
            return frame

# endregion DateTime

# region Events
    def on_closing(self):
        """Handler for window close event."""
        logging.info("Closing application...")
        self.stop_event.set()  # Stop the weather thread
        self.is_running = False
        self.stop_observer()
        self.root.destroy()
# endregion Events

#region stats
    def handle_triple_tap(self, event):
        """Handles triple tap to toggle stats display."""
        current_time = time.time()
        if current_time - self.last_tap_time < 1.5:  # Time window for triple-tap
            self.triple_tap_count += 1
        else:
            self.triple_tap_count = 1  # Reset if too much time has passed

        self.last_tap_time = current_time

        if self.triple_tap_count == 3:  # Toggle stats on third tap
            self.settings["stats"]["show"] = not self.settings["stats"]["show"]
            self.triple_tap_count = 0  # Reset counter
            logging.info(f"Stats display toggled to {self.settings['stats']['show']}")

            # Save the updated settings
            with open("settings.json", "w") as file:
                json.dump(self.settings, file, indent=4)

    def get_system_stats(self):
        """Retrieves system stats (CPU usage, RAM usage, CPU temperature)."""
        cpu_usage = psutil.cpu_percent()

        # Get RAM usage
        ram = psutil.virtual_memory()
        ram_used = ram.used // (1024 * 1024)  # Convert to MB
        ram_total = ram.total // (1024 * 1024)  # Convert to MB
        ram_percent = ram.percent  # Get RAM usage percentage

        # Get CPU temperature correctly
        try:
            cpu_temps = psutil.sensors_temperatures().get("cpu_thermal", [])
            cpu_temp = round(cpu_temps[0].current, 1) if cpu_temps else "N/A"
        except (IndexError, AttributeError):
            cpu_temp = "N/A"

        return f"CPU: {cpu_usage}%\nRAM: {ram_percent}% ({ram_used}/{ram_total}MB)\nCPU Temp: {cpu_temp}°C"

    def add_stats_to_frame(self, frame):
        """Adds cached system stats to the image if enabled."""
        if not self.settings["stats"]["show"]:
            return frame  # Skip if stats are disabled

        font_path = self.settings['font_name']
        font_size = self.settings['stats']['font_size']
        font_color = self.settings['stats']['font_color']

        color_map = {
            "yellow": (255, 255, 0),
            "white": (255, 255, 255),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255)
        }
        font_color = color_map.get(font_color.lower(), (255, 255, 0))

        stats_font = ImageFont.truetype(font_path, font_size)

        # Use cached stats (updated once per second)
        stats_text = self.cached_stats

        pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)

        draw.text((10, 10), stats_text, font=stats_font, fill=font_color)

        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


#endregion stats


# region Main
    def update_frame(self, generator):
        """
        Update the frame in the Tkinter window by fetching the next frame from the generator.

        Args:
        generator: The generator yielding transition frames.
        """
        if generator is None:
            return
        try:
            # Iterate over frames from the generator
            for frame in generator:
                self.mjpeg_server.update_live_frame(frame)  # Update live frame for streaming
                # Add time and date to the frame
                frame = self.add_text_to_frame(frame)

                # Convert OpenCV image to PIL ImageTk format
                #frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                #image = Image.fromarray(frame_rgb)
                #image_tk = ImageTk.PhotoImage(image)

                # Update the label with the new image
                # self.label.config(image=image_tk)
                # self.label.image = image_tk
                # Update the live frame during the transition
                
                # Update the GUI
                # self.root.update_idletasks()
                # self.root.update()
            return AnimationStatus.ANIMATION_FINISHED
        except Exception as e:
            print(f"Error during frame update: {e}")
            return AnimationStatus.ANIMATION_ERROR

    def start_image_transition(self, image1_path=None, image2_path=None, duration=5):
        """
        Start the image transition inside a Tkinter frame.
        """
        if self.current_image is None:
            self.current_image = cv2.imread(self.get_random_image())
            self.current_image = self.image_handler.resize_image_with_background(
                self.current_image, self.screen_width, self.screen_height)

        if image2_path is None:
            image2_path = self.get_random_image()

        self.update_image_metadata(image2_path)

        self.next_image = cv2.imread(image2_path)
        self.next_image = self.image_handler.resize_image_with_background(
            self.next_image, self.screen_width, self.screen_height)

        effect_function = self.effects[self.get_random_effect()]
        gen = effect_function(self.current_image, self.next_image, duration)
        self.status = self.update_frame(gen)
        self.mjpeg_server.update_live_frame(frame)  # Update live frame for streaming

        if self.status == AnimationStatus.ANIMATION_FINISHED:
            self.current_image = self.next_image
            # Update the current image to image2 after the transition completes
            return AnimationStatus.ANIMATION_FINISHED

    def run_photoframe(self):
        while self.is_running:
            # Start the transition with a random image pair
            self.start_image_transition(duration=self.settings["animation_duration"])
            # Display the current image with time and date during the wait time
            self.display_image_with_time(
                self.current_image, self.wait_time)
            time.sleep(1)

    def set_window_properties(self):
        # Create the Tkinter root window and frame
        self.root = tk.Tk()
        self.root.title("Digital Photo Frame V2.0")

        # Make the window full-screen and borderless
        self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
        self.root.attributes("-fullscreen", True)
        self.root.wm_attributes("-topmost", True)  # Ensure it's always on top
        self.root.configure(bg='black')

        # Hide the mouse cursor
        self.root.config(cursor="none")
        self.root.option_add('*Cursor', 'none')

        # Get screen dimensions
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        # Create a full-screen frame
        self.frame = tk.Frame(
            self.root, width=self.screen_width, height=self.screen_height, bg='black')
        self.frame.pack(fill="both", expand=True)

        self.notification_manager = NotificationManager(self.root)
        
        self.root.bind("<Button-1>", self.handle_triple_tap)  # Bind tap event to toggle stats display  
        
        # Bind the close event (Alt+F4)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Bind Ctrl+C to terminate the application
        self.root.bind_all('<Control-c>', lambda e: self.on_closing())
        
        

    def shuffle_images(self):
        self.shuffled_images = list(self.images)
        rand.shuffle(self.shuffled_images)
        self.shuffled_effects = list(self.effects.keys())
        rand.shuffle(self.shuffled_effects)

    def main(self):
        logging.info("Starting main application...")
        self.shuffle_images()
        self.set_window_properties()

        # Start the MJPEG server
        self.mjpeg_server.start_mjpeg_server(settings = self.settings["mjpeg_server"])

        # Start the transition thread
        logging.info("Starting transition thread...")
        transition_thread = threading.Thread(target=self.run_photoframe)
        transition_thread.start()

        # try:
        #     # Start the Tkinter main loop
        #     #logging.info("Entering Tkinter main loop.")
        #     #self.root.mainloop()
        # except KeyboardInterrupt:
        #     logging.warning("Keyboard interrupt received. Exiting application...")
        #     self.on_closing()

# endregion Main


if __name__ == "__main__":
    try:
        frame = PhotoFrame()
        frame.main()
    except Exception as e:
        logging.critical(f"Unhandled exception occurred: {e}")
        raise