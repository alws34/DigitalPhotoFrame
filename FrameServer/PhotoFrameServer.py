# region imports
import hashlib
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
import threading
import time
import random as rand
from enum import Enum
import cv2
import numpy as np
import json
from datetime import datetime, timezone

from Settings import SettingsHandler
from WebAPI.API import Backend
from image_handler import Image_Utils
from Utilities.observer import ImagesObserver
from Utilities.Weather.weather_adapter import build_weather_client
from iFrame import iFrame
from EffectHandler import EffectHandler

# endregion imports

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
logging.info("PhotoFrame server starting...")
# endregion Logging Setup

SETTINGS_PATH = ""


class AnimationStatus(Enum):
    ANIMATION_FINISHED = 1
    ANIMATION_ERROR = 2


class PhotoFrameServer(iFrame):
    """
    Server owns:
      - Sizing (letterbox)
      - Date/time + weather overlay (every frame)
      - 30 fps compositor that continues between transitions
    Client displays frames only.
    """
    def __init__(self, width=1920, height=1080, iframe: iFrame = None, images_dir=None, settings_path="settings.json"):
        global SETTINGS_PATH
        SETTINGS_PATH = settings_path
        self._gui_frame = iframe
        
        try:
            cv2.setUseOptimized(True)
            cv2.setNumThreads(max(1, (os.cpu_count() or 4) - 2))
        except Exception as e:
            self.logger.exception(f"Failed to set OpenCV optimizations: {e}")
        
        self.settings_handler_path = os.path.abspath(settings_path)
        self.settings_handler = SettingsHandler(SETTINGS_PATH, logging)

        if not self.set_images_dir(images_dir=images_dir):
            logging.error("Failed to set images directory. Exiting.")
            raise FileNotFoundError("Images directory not found and could not be created.")

        self.screen_width = width
        self.screen_height = height

        self._target_fps = int(self.settings_handler.get("animation_fps", 30))
        self._transition_fps = int(self.settings_handler.get("transition_fps", 30))
        self._transition_frame_interval = 1.0 / max(1.0, float(self._transition_fps))
 
        self.current_image_idx = 0
        self.current_effect_idx = 0
        self.current_image = None
        self.next_image = None
        self.frame_to_stream = None
        self.is_running = True

        
        self.EffectHandler = EffectHandler()
        self.image_handler = Image_Utils(settings=self.settings_handler)
        self.effects = self.EffectHandler.get_effects()
        self.update_images_list()    
        
        if self._gui_frame:
            # Keep a handle to the thread so we can join on shutdown
            self._date_time_thread = threading.Thread(
                target=self.start_date_time_loop,
                name="DateTimeThread",
                daemon=True,
            )
            self._date_time_thread.start()

            # Weather client and loop
            self._weather_stop = threading.Event()
            self.weather_client = build_weather_client(self, self.settings_handler)

            # Some handlers may expose initialize_weather_updates(); call if present.
            init = getattr(self.weather_client, "initialize_weather_updates", None)
            if callable(init):
                try:
                    init()
                except Exception:
                    logging.exception("weather_client.initialize_weather_updates failed")

            self._weather_thread = None
            self._start_local_weather_loop()
        else:
            self._date_time_thread = None

        # Filesystem observer
        self._observer_started = False
        self._observer_debounce_ts = 0.0
        self._observer_min_interval = 1.0
        self.Observer = ImagesObserver(frame=self, images_dir=self.IMAGE_DIR)
        # If your ImagesObserver supports a callback, register it:
        if hasattr(self.Observer, "on_change"):
            self.Observer.on_change = self._on_images_dir_changed  # type: ignore[attr-defined]
        if not self._observer_started:
            self.Observer.start_observer()
            self._observer_started = True

   

    def _on_images_dir_changed(self):
        now = time.time()
        if now - self._observer_debounce_ts < self._observer_min_interval:
            return
        self._observer_debounce_ts = now
        try:
            self.update_images_list()
            # Keep shuffle stable if empty; otherwise reshuffle for new content
            if len(self.images) > 0:
                self.shuffled_images = self.image_handler.shuffle_images(self.images)
            logging.info("Images directory changed. Found %d images.", len(self.images))
        except Exception:
            logging.exception("Failed to update images list after directory change")
        
        
    def start_date_time_loop(self):
        # runs in a worker thread, not the GUI thread
        while self.is_running:
            now = time.localtime()
            dt = f"{now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"
            self._gui_frame.set_date_time(dt)  # thread-safe (invokeMethod with Q_ARG or signals)
            time.sleep(1)

    def _start_local_weather_loop(self) -> None:
        def _weather_loop():
            while not self._weather_stop.is_set():
                try:
                    self.weather_client.fetch()
                    self._gui_frame.set_weather(self.weather_client.data() or {})
                except Exception:
                    logging.exception("weather loop error (server)")
                # wait with interruptibility
                self._weather_stop.wait(600.0)
        self._weather_thread = threading.Thread(target=_weather_loop, name="WeatherThread", daemon=True)
        self._weather_thread.start()

    def _stop_weather_loop(self) -> None:
        try:
            self._weather_stop.set()
        except Exception:
            pass

    def _send_frame(self, frame_bgr: np.ndarray) -> None:
        """
        Ensure frame is screen-sized, then push directly to GUI and API.
        No server-side overlays or blending.
        """
        if frame_bgr is None:
            return

        # Resize/letterbox only if needed
        h, w = frame_bgr.shape[:2]
        if w != self.screen_width or h != self.screen_height:
            frame_bgr = self.image_handler.resize_image_with_background(
                frame_bgr, self.screen_width, self.screen_height
            )

        # For API (if any consumers still pull latest)
        self.frame_to_stream = frame_bgr

        # GUI push
        if self._gui_frame and hasattr(self._gui_frame, "set_frame"):
            try:
                self._gui_frame.set_frame(frame_bgr)
            except Exception:
                logging.exception("Failed to publish frame to GUI")

        # API notify (optional)
        if hasattr(self, "m_api"):
            try:
                self.m_api._new_frame_ev.set()
            except Exception:
                logging.exception("Failed to signal API new frame")

    # ------------- Stream API -------------
    def update_frame(self, generator):
        """
        Pull frames from the transition generator and push each one to the GUI.
        Uses a monotonic running deadline to avoid drift. After the generator
        completes, explicitly pushes the last frame again to guarantee it lands.
        """
        last_frame = None

        try:
            # Prefer perf_counter() (monotonic, high-res) for pacing
            interval = float(getattr(self, "_transition_frame_interval", self._transition_frame_interval))
            now = time.perf_counter()
            next_deadline = now  # send first frame immediately

            for frame in generator:
                last_frame = frame

                # Send immediately on arrival
                self._send_frame(frame)

                # Compute next deadline and sleep just enough
                next_deadline += interval
                now = time.perf_counter()
                sleep_for = next_deadline - now
                if sleep_for > 0:
                    # Sleep in small chunks to be responsive on wake-ups
                    # (keeps jitter lower on some platforms)
                    end = next_deadline
                    while True:
                        now = time.perf_counter()
                        remaining = end - now
                        if remaining <= 0:
                            break
                        time.sleep(min(remaining, 0.005))

            # The generator ended. Some effects do not yield the exact final image.
            # Push the last frame one more time to guarantee the final state landed.
            if last_frame is not None:
                self._send_frame(last_frame)

            return AnimationStatus.ANIMATION_FINISHED

        except Exception as e:
            logging.exception(f"Error during frame update: {e}")
            return AnimationStatus.ANIMATION_ERROR



    # ------------- Utils -------------
    def compute_image_hash(self, image_path):
        hash_obj = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    def get_is_running(self):
        return self.is_running

    def set_date_time(self):
        pass
    
    def set_weather(self):
        pass

    def get_live_frame(self):
        return self.frame_to_stream
    
    def update_frame_to_stream(self, frame_bgr: np.ndarray) -> None:
        pass

    def send_log_message(self, msg, logger: logging):
        try:
        # Prefer an instance logger if you set one in set_logger()
            lg = getattr(self, "logger", None)
            if callable(logger):
                # A callable like logging.info / self.logger.info
                logger(msg)
            else:
                # Assume a numeric level constant (int)
                level = int(logger)
                if lg is not None:
                    lg.log(level, msg)
                else:
                    logging.log(level, msg)
        except Exception:
            # Ultimate fallback to keep logs flowing even if something is off
            try:
                (lg or logging).info(msg)
            except Exception:
                print(f"[PhotoFrame LOG] {msg}")

    def get_images_from_directory(self):
        image_extensions = [".jpg", ".jpeg", ".png", ".gif"]
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

    def set_images_dir(self, images_dir=None):
        if images_dir is not None:
            self.IMAGE_DIR = images_dir
            if not os.path.exists(self.IMAGE_DIR):
                os.makedirs(self.IMAGE_DIR, exist_ok=True)
                logging.warning(f"'{self.IMAGE_DIR}' directory not found. Created a new one.")
            return True

        images_dir = self.settings_handler.get("images_dir") or "Images"
        self.IMAGE_DIR = os.path.abspath(
            os.path.join(os.path.dirname(__file__), images_dir)
        )
        if not os.path.exists(self.IMAGE_DIR):
            os.makedirs(self.IMAGE_DIR, exist_ok=True)
            logging.warning(f"'{self.IMAGE_DIR}' directory not found. Created a new one.")
        return True

    def update_images_list(self):
        self.images = self.get_images_from_directory()
        self.shuffled_images = self.image_handler.shuffle_images(self.images)

    # ------------- Transition driver -------------

    def start_image_transition(self, image1_path=None, image2_path=None, duration=5):
        if self.current_image is None:
            self.current_image = cv2.imread(self.get_random_image())
            if self.current_image is None:
                return AnimationStatus.ANIMATION_FINISHED
            self.current_image = self.image_handler.resize_image_with_background(
                self.current_image, self.screen_width, self.screen_height
            )

        if image2_path is None:
            image2_path = self.get_random_image()

        self.update_image_metadata(image2_path)

        self.next_image = cv2.imread(image2_path)
        self.next_image = self.image_handler.resize_image_with_background(
            self.next_image, self.screen_width, self.screen_height
        )

        effect_function = self.effects[self.EffectHandler.get_random_effect()]
        gen = effect_function(self.current_image, self.next_image, duration, fps=self._target_fps)
        self.status = self.update_frame(gen)

        if self.status == AnimationStatus.ANIMATION_FINISHED and self.next_image is not None:
            try:
                self._send_frame(self.next_image)
            except Exception:
                logging.exception("final next_image push failed")

        if self.status == AnimationStatus.ANIMATION_FINISHED:
            self.current_image = self.next_image
            return AnimationStatus.ANIMATION_FINISHED

    def set_frame(self, frame):
        # No-op in server. Client implements publish to GUI.
        pass

    # ------------- Main loops -------------
    def run_photoframe(self):
        self.shuffled_images = self.image_handler.shuffle_images(self.images)
        self.current_image = cv2.imread(self.get_random_image())
        if self.current_image is not None:
            self.current_image = self.image_handler.resize_image_with_background(
                self.current_image, self.screen_width, self.screen_height
            )
            self._send_frame(self.current_image)

        while self.is_running:
            if self.settings_handler["animation_duration"] > 0:
                self.start_image_transition(duration=self.settings_handler["animation_duration"])
                time.sleep(self.settings_handler["delay_between_images"])
            else:
                # No compositor; nothing to do here other than keep process responsive
                time.sleep(0.1)

    def main(self):
        threading.Thread(target=self.run_photoframe, daemon=True).start()
        threading.Thread(target=self._start_api, daemon=True).start()

        my_pid = os.getpid()
        # self.start_monitor_thread(my_pid, interval=1.0)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutting down.")
            self.stop_services()

    def stop_services(self) -> None:
        def _join(th, name: str, timeout: float = 2.0) -> None:
            if th is None:
                return
            try:
                if th.is_alive():
                    th.join(timeout=timeout)
                    if th.is_alive():
                        logging.warning("Thread %s did not stop within %.1fs.", name, timeout)
            except Exception:
                logging.exception("Failed joining thread %s", name)

        logging.info("PhotoFrameServer.stop_services: stopping...")

        self.is_running = False

        try:
            if hasattr(self, "_weather_stop") and self._weather_stop:
                self._weather_stop.set()
        except Exception:
            pass

        try:
            if hasattr(self, "Observer") and self.Observer:
                stop_fn = getattr(self.Observer, "stop_observer", None)
                if callable(stop_fn):
                    stop_fn()
                else:
                    close_fn = getattr(self.Observer, "close", None)
                    if callable(close_fn):
                        close_fn()
        except Exception:
            logging.exception("Failed to stop ImagesObserver")

        try:
            if hasattr(self, "m_api") and self.m_api:
                for meth in ("stop", "shutdown", "close"):
                    fn = getattr(self.m_api, meth, None)
                    if callable(fn):
                        try:
                            fn()
                        except Exception:
                            logging.exception("Backend.%s() failed", meth)
        except Exception:
            logging.exception("Failed to stop Backend API")

        _join(getattr(self, "_date_time_thread", None), "DateTimeThread")
        _join(getattr(self, "_weather_thread", None), "WeatherThread")

        try:
            if self._gui_frame and hasattr(self._gui_frame, "stop"):
                self._gui_frame.stop()
        except Exception:
            logging.exception("GUI stop failed")

        logging.info("PhotoFrameServer.stop_services: done.")

    
    def _start_api(self):
        try:
            self.m_api = Backend(
                frame=self,
                settings=self.settings_handler,          # existing settings dict/object
                image_dir=self.IMAGE_DIR,
                settings_path=self.settings_handler_path  # <-- pass absolute path
            )
            self.m_api.start()
        except Exception:
            logging.exception("Failed to start Backend API")


    # ------------- Metadata (server-owned) -------------

    def _metadata_db_path(self) -> str:
        return os.path.join("metadata.json")

    def _load_metadata_db(self) -> dict:
        p = self._metadata_db_path()
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception:
            logging.exception("Failed to load metadata.json")
            return {}

    def _save_metadata_db(self, db: dict) -> None:
        """
        Atomic write to avoid corruption on power loss.
        """
        p = self._metadata_db_path()
        tmp = p
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=True, indent=2, sort_keys=True)
            os.replace(tmp, p)
        except Exception:
            logging.exception("Failed to save metadata.json")


    def _utcnow_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _file_mtime_iso(self, path: str) -> str:
        try:
            ts = os.path.getmtime(path)
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None

    def _extract_exif_datetime(self, path: str) -> str:
        """
        Try to read a capture date from EXIF. Returns ISO8601 Z or None.
        """
        try:
            from PIL import Image, ExifTags
            img = Image.open(path)
            exif = img.getexif()
            if not exif:
                return None
            key_map = {ExifTags.TAGS.get(k, str(k)): k for k in exif.keys()}
            for tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                k = key_map.get(tag_name)
                if k is None:
                    continue
                raw = exif.get(k)
                if not raw:
                    continue
                # EXIF format "YYYY:MM:DD HH:MM:SS"
                try:
                    dt = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
                    # Treat as naive local time is ambiguous; use UTC to be consistent
                    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    continue
            return None
        except Exception:
            return None

    def update_image_metadata(self, image_path: str) -> None:
        """
        Ensure an entry exists for image_path and update runtime fields:
          - views (increment)
          - last_displayed (now)
          - dimensions (w,h) if missing
          - filesize, file timestamps
          - EXIF date_taken if available
        Keyed by SHA256 of file contents to stay stable if the path moves.
        """
        try:
            if not image_path or not os.path.isfile(image_path):
                return

            # Load DB
            db = self._load_metadata_db()

            # Compute key
            file_hash = self.compute_image_hash(image_path)

            # Derive or read current entry
            entry = db.get(file_hash, {})

            # File stats
            try:
                st = os.stat(image_path)
                fsize = int(st.st_size)
            except Exception:
                fsize = None

            # Dimensions (use existing if already stored)
            width = entry.get("width")
            height = entry.get("height")
            if width is None or height is None:
                try:
                    img = cv2.cv2.imread(image_path)
                    if img is not None:
                        height, width = int(img.shape[0]), int(img.shape[1])
                except Exception:
                    pass

            # EXIF date (do not overwrite if already present)
            date_taken = entry.get("date_taken")
            if not date_taken:
                date_taken = self._extract_exif_datetime(image_path)

            # Dates
            now_iso = self._utcnow_iso()
            date_added = entry.get("date_added") or now_iso
            date_modified = self._file_mtime_iso(image_path)

            # Identity fields
            filename = os.path.basename(image_path)
            # Prefer a path relative to IMAGE_DIR to keep portability
            try:
                rel_path = os.path.relpath(image_path, self.IMAGE_DIR)
            except Exception:
                rel_path = image_path

            # Counters
            views = int(entry.get("views") or 0) + 1

            # Keep existing caption/uploader if present, otherwise defaults
            caption = entry.get("caption") or "N/A"
            uploader = entry.get("uploader")  # may be None

            # Assemble updated entry
            updated = {
                "hash": file_hash,
                "filename": filename,
                "relative_path": rel_path,
                "absolute_path": image_path,  # helpful for tools; keep both
                "filesize": fsize,
                "width": width,
                "height": height,
                "date_taken": date_taken,
                "date_added": date_added,
                "date_modified": date_modified,
                "last_displayed": now_iso,
                "views": views,
                "caption": caption,
                "uploader": uploader,
            }

            db[file_hash] = updated
            self._save_metadata_db(db)

            # Expose current metadata to other components if useful
            try:
                self.current_metadata = updated
            except Exception:
                pass

        except Exception:
            logging.exception("update_image_metadata failed")

if __name__ == "__main__":
    frame = PhotoFrameServer()
    frame.main()
