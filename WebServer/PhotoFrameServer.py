#region imports
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
import json
import threading
import time
from PIL import Image, ImageDraw, ImageFont
from cv2 import COLOR_RGB2BGR, COLOR_BGR2RGB, cvtColor, imread
import random as rand
from enum import Enum
from numpy import array as np_array
import psutil 
import hashlib


from WebServer.Settings import SettingsHandler
from WebServer.API import Backend
from Handlers.image_handler import Image_Utils
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
            # with open("settings.json", 'r') as file:
            #     self.settings = json.load(file)
            self.settings = SettingsHandler("settings.json", logging)
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
        self.screen_width = 1920
        self.screen_height = 1080
        self.current_image = None
        self.next_image = None
        self.frame_to_stream = None
        self.is_running = True
        
        self.image_handler = Image_Utils(settings = self.settings)
        self.Observer = ImagesObserver(frame = self) 
        self.weather_handler = weather_handler(frame = self, settings = self.settings)
 
        self.m_api = Backend(frame = self, settings=self.settings["backend_configs"]) 
        self.m_api.start()

        #self.weather_handler.fetch_weather_data()
        self.weather_handler.initialize_weather_updates()
        self.Observer.start_observer()
        
        self.notification_manager = None
        
        self.triple_tap_count = 0  # Counter for triple tap detection
        self.last_tap_time = 0
       
        # Cached system stats and update time
        self.cached_stats = ""
        self.last_stats_update = 0        

    def update_images_list(self):
        self.images = self.get_images_from_directory()
        self.shuffle_images()
        
# region guestbook
    def update_image_metadata(self, image_path):
        # Use Backend's absolute metadata file and store_image_metadata method.
        if hasattr(self, "m_api"):
            # This will create metadata only if it doesn't already exist.
            self.m_api.update_image_metadata(image_path)
            # Load the updated metadata and update the current metadata for polling.
            metadata_db = self.m_api.load_metadata_db()
            file_hash = self.m_api.compute_image_hash(image_path)
            if file_hash in metadata_db:
                self.m_api.update_current_metadata(metadata_db[file_hash]) 

                
# endregion guestbook

#region Stream
    def update_frame_to_stream(self, frame):
        self.frame_to_stream = frame

    def get_live_frame(self):
        return self.frame_to_stream
    
    def get_metadata(self):
        """Returns metadata for the current image."""
        return self.m_api.current_metadata if hasattr(self.m_api, "current_metadata") else {}
#endregion Stream

# region Utils
    def compute_image_hash(self, image_path):
        hash_obj = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    def update_stats_loop(self):
        """Runs in a separate thread to update system stats every second."""
        while self.is_running:
            self.cached_stats = self.get_system_stats()
            time.sleep(1)

    def get_is_running(self):
        return self.is_running
    
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
        if len(self.shuffled_images) == 0:
            return None
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

# region Events
    def on_closing(self):
        """Handler for window close event."""
        logging.info("Closing application...")
        self.stop_event.set() 
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

        pil_image = Image.fromarray(cvtColor(frame, COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)

        draw.text((10, 10), stats_text, font=stats_font, fill=font_color)

        return cvtColor(np_array(pil_image), COLOR_RGB2BGR)


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
            for frame in generator:
                self.update_frame_to_stream(frame)
            return AnimationStatus.ANIMATION_FINISHED
        except Exception as e:
            print(f"Error during frame update: {e}")
            return AnimationStatus.ANIMATION_ERROR

    def start_image_transition(self, image1_path=None, image2_path=None, duration=5):
        """
        Start the image transition inside a Tkinter frame.
        """
        if self.current_image is None:
            self.current_image = imread(self.get_random_image())
            if self.current_image is None:
                return AnimationStatus.ANIMATION_FINISHED
            self.current_image = self.image_handler.resize_image_with_background(
                self.current_image, self.screen_width, self.screen_height)

        if image2_path is None:
            image2_path = self.get_random_image()

        self.update_image_metadata(image2_path)

        self.next_image = imread(image2_path)
        self.next_image = self.image_handler.resize_image_with_background(
            self.next_image, self.screen_width, self.screen_height)

        effect_function = self.effects[self.get_random_effect()]
        gen = effect_function(self.current_image, self.next_image, duration)
        self.status = self.update_frame(gen)

        if self.status == AnimationStatus.ANIMATION_FINISHED:
            self.current_image = self.next_image
            # Update the current image to image2 after the transition completes
            return AnimationStatus.ANIMATION_FINISHED

    def run_photoframe(self):
        while self.is_running:
            # Start the transition with a random image pair
            self.start_image_transition(duration=self.settings["animation_duration"])
            time.sleep(self.settings["delay_between_images"])     

    def shuffle_images(self):
        self.shuffled_images = list(self.images)
        rand.shuffle(self.shuffled_images)
        self.shuffled_effects = list(self.effects.keys())
        rand.shuffle(self.shuffled_effects)

    def main(self):
        logging.info("Starting PhotoFrame Main Loop.")
        self.shuffle_images()
        #self.set_window_properties()

        # Start the transition thread
        logging.info("Starting transition thread.")
        transition_thread = threading.Thread(target=self.run_photoframe)
        transition_thread.start()
# endregion Main


if __name__ == "__main__":
    try:
        frame = PhotoFrame()
        frame.main()
    except Exception as e:
        logging.critical(f"Unhandled exception occurred: {e}")
        raise