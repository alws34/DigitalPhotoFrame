#region imports
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
import threading
import time
from cv2 import imread
import random as rand
from enum import Enum
import hashlib
import psutil

from WebServer.Settings import SettingsHandler
from WebServer.API import Backend
from WebServer.utilities.image_handler import Image_Utils
from Utilities.observer import ImagesObserver
from iFrame import iFrame
from EffectHandler import EffectHandler


#from Utilities.NotificationManager import NotificationManager
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

SETTINGS_PATH = "settings.json"
class AnimationStatus(Enum):
    ANIMATION_FINISHED = 1
    ANIMATION_ERROR = 2


class PhotoFrameServer(iFrame):
    def __init__(self, width=1920, height=1080, iframe: iFrame = None, images_dir = None):
        self.set_logger(logging)
        self.settings = SettingsHandler(SETTINGS_PATH, logging)
        if not self.set_images_dir(images_dir=images_dir):
            logging.error("Failed to set images directory. Exiting.")
            raise FileNotFoundError("Images directory not found and could not be created.")

        self.EffectHandler = EffectHandler()
        self.image_handler = Image_Utils(settings=self.settings)
        self.effects = self.EffectHandler.get_effects()
        self._gui_frame = iframe
        self.update_images_list()
        self.current_image_idx = -1
        self.current_effect_idx = -1
        self.screen_width = width
        self.screen_height = height
        self.current_image = None
        self.next_image = None
        self.frame_to_stream = None
        self.is_running = True

        # start filesystem observer
        self.Observer = ImagesObserver(frame=self, images_dir= self.IMAGE_DIR)
        self.Observer.start_observer()

    def start_monitor_thread(self, pid, interval=1.0):
        t = threading.Thread(
        target=self.monitor_cpu_usage,
        args=(pid, interval),
        daemon=True
        )
        t.start()
        return t

    def monitor_cpu_usage(self,pid, interval=1.0):
        """
        Monitors the CPU usage of the process with the given PID.
        Prints a line every `interval` seconds until the process exits.
        """
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            logging.error(f"No process found with PID={pid}")
            return

        # Prime the internal cpu_percent counter
        proc.cpu_percent(interval=None)

        while True:
            try:
                cpu = proc.cpu_percent(interval=None)
                print(f"PID={pid} CPU: {cpu:5.1f}%")
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                logging.info(f"Process PID={pid} has exited.")
                break
            time.sleep(interval)


    def set_logger(self, logger):
        try:
            self.logger = logging.getLogger(__name__)
            logging.info("Loaded settings from settings.json.")
        except FileNotFoundError:
            logging.error("settings.json not found. Exiting.")
            raise
    
    def set_images_dir(self,  images_dir = None):
        if images_dir != None:
            self.IMAGE_DIR = images_dir
            if not os.path.exists(self.IMAGE_DIR):
                os.makedirs(self.IMAGE_DIR, exist_ok=True)
                logging.warning(f"'{self.IMAGE_DIR}' directory not found. Created a new one.")
            return True
        
        images_dir = self.settings.get("images_dir") or "Images"

        self.IMAGE_DIR = os.path.abspath(
            os.path.join(os.path.dirname(__file__), images_dir)
        )

        if not os.path.exists(self.IMAGE_DIR):
            os.makedirs(self.IMAGE_DIR, exist_ok=True)
            logging.warning(f"'{self.IMAGE_DIR}' directory not found. Created a new one.")
            # you probably want to continue running even if you just created it
        return True

    def update_images_list(self):
        self.images = self.get_images_from_directory()
        self.shuffled_images = self.image_handler.shuffle_images(self.images)
        
# region guestbook
    def update_image_metadata(self, image_path):
        if hasattr(self, "m_api"):
            self.m_api.update_image_metadata(image_path)
            metadata_db = self.m_api.load_metadata_db()
            file_hash = self.m_api.compute_image_hash(image_path)
            if file_hash in metadata_db:
                self.m_api.update_current_metadata(metadata_db[file_hash]) 
             
# endregion guestbook

#region Stream
    def update_frame_to_stream(self, frame):
        self.frame_to_stream = frame
        if hasattr(self, 'm_api'):
            self.m_api._new_frame_ev.set()
        if self._gui_frame:
            self._gui_frame.update_frame_to_stream(frame)    
            
    def get_live_frame(self):
        return self.frame_to_stream

#endregion Stream

# region Utils
    def compute_image_hash(self, image_path):
        hash_obj = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    def get_is_running(self):
        return self.is_running
    
    def send_log_message(self, msg, logger: logging):
        logger(msg)

    def get_images_from_directory(self):
        image_extensions = [".jpg", ".jpeg", ".png",
                            ".gif"]  # Add more extensions if needed
        image_paths = []

        for root, dirs, files in os.walk(self.IMAGE_DIR):
            for file in files:
                if file.lower().endswith(tuple(image_extensions)):
                    image_path = os.path.join(root, file)
                    image_paths.append(image_path)

        return image_paths

    def get_random_image(self):
        if len(self.shuffled_images) == 0:
            self.shuffled_images = list(self.images)
            rand.shuffle(self.shuffled_images)
        if len(self.shuffled_images) == 0:
            return None
        self.current_image_idx = (self.current_image_idx + 1) % len(self.shuffled_images)
        return self.shuffled_images[self.current_image_idx]


# endregion Utils



# region Main
    def update_frame(self, generator):
            """
            Consume an effect-generator at a fixed FPS so CPU gets idle time.
            """
            target_fps = self.settings.get("animation_fps", 30)
            interval = 1.0 / float(target_fps)

            try:
                for frame in generator:
                    self.update_frame_to_stream(frame)
                    time.sleep(interval)  
                return AnimationStatus.ANIMATION_FINISHED
            except Exception as e:
                print(f"Error during frame update: {e}")
                return AnimationStatus.ANIMATION_ERROR
           
    def start_image_transition(self, image1_path=None, image2_path=None, duration=5):
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

        effect_function = self.effects[self.EffectHandler.get_random_effect()]
        gen = effect_function(self.current_image, self.next_image, duration)
        self.status = self.update_frame(gen)

        if self.status == AnimationStatus.ANIMATION_FINISHED:
            self.current_image = self.next_image
            return AnimationStatus.ANIMATION_FINISHED

    def run_photoframe(self):
        self.shuffled_images = self.image_handler.shuffle_images(self.images)
        self.current_image = imread(self.get_random_image())
        self.current_image = self.image_handler.resize_image_with_background(
            self.current_image, self.screen_width, self.screen_height
        )
        self.update_frame_to_stream(self.current_image)
        
        while self.is_running:
            if self.settings["animation_duration"] > 0:
                self.start_image_transition(duration=self.settings["animation_duration"])
                time.sleep(self.settings["delay_between_images"])
            else:
                time.sleep(0.1) 

    def main(self):
        threading.Thread(target=self.run_photoframe, daemon=True).start()
        threading.Thread(target=self._start_api, daemon=True).start()

        my_pid = os.getpid()
        #self.start_monitor_thread(my_pid, interval=1.0)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutting down.")
            self.is_running = False

    def _start_api(self):
        self.m_api = Backend(frame=self, settings=self.settings, image_dir=self.IMAGE_DIR)
        self.m_api.start()

if __name__ == "__main__":
    
    frame = PhotoFrameServer()
    frame.main()