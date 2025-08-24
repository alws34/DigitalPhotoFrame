# region imports
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
import queue
import cv2
import numpy as np
import json
from datetime import datetime, timezone

from Settings import SettingsHandler
from WebAPI.API import Backend
from image_handler import Image_Utils
from Utilities.observer import ImagesObserver
from Utilities.Weather.weather_adapter import build_weather_client
from overlay import OverlayRenderer
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
        self.set_logger(logging)
        global SETTINGS_PATH
        SETTINGS_PATH = settings_path
        self.settings_path = os.path.abspath(settings_path)
        self.settings = SettingsHandler(SETTINGS_PATH, logging)
        
        if not self.set_images_dir(images_dir=images_dir):
            logging.error("Failed to set images directory. Exiting.")
            raise FileNotFoundError("Images directory not found and could not be created.")

        self.screen_width = width
        self.screen_height = height

        # Effects and image utils
        self.EffectHandler = EffectHandler()
        self.image_handler = Image_Utils(settings=self.settings)
        self.effects = self.EffectHandler.get_effects()

        # iFrame peer (GUI)
        self._gui_frame = iframe

        # Images cache
        self.update_images_list()
        self.current_image_idx = -1
        self.current_effect_idx = -1
        self.current_image = None
        self.next_image = None
        self.frame_to_stream = None
        self.is_running = True

        # Timing
        self._target_fps = 30
        self._frame_interval = 1.0 / float(self._target_fps)
        self._in_transition = False

        # Weather + overlay configuration (server side)
        self._init_overlay_pipeline()

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

        # Start compositor thread to keep time/weather updating between transitions
        self._compositor_stop = threading.Event()
        self._compositor_thread = threading.Thread(target=self._compositor_loop, name="Compositor30FPS", daemon=True)
        self._compositor_thread.start()

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
        
    # ------------- Overlay pipeline (server side) -------------
    def _init_overlay_pipeline(self) -> None:
        font_name = self.settings.get("font_name") or "DejaVuSans.ttf"
        candidate_dirs = [
            os.path.abspath(os.path.dirname(__file__)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        ]
        font_path = None
        for d in candidate_dirs:
            fp = os.path.join(d, font_name)
            if os.path.isfile(fp):
                font_path = fp
                break
        if font_path is None:
            font_path = font_name

        # Panels config
        enable_panels = bool(self.settings.get("allow_translucent_background", False))
        panels_cfg = self.settings.get("overlay_panels", {}) or {}
        panel_alpha = int(panels_cfg.get("alpha", 128))
        panel_padding = int(panels_cfg.get("padding", 12))
        panel_radius = int(panels_cfg.get("radius", 10))
        # Optional: keep your full-width contrast band together with panels
        self._keep_band_with_panels = bool(panels_cfg.get("keep_band_with_panels", False))

        self.overlay = OverlayRenderer(
            font_path=font_path,
            time_font_size=int(self.settings.get("time_font_size", 48)),
            date_font_size=int(self.settings.get("date_font_size", 28)),
            stats_font_size=int(self.settings.get("stats", {}).get("font_size", 20)),
            desired_size=(self.screen_width, self.screen_height),
            enable_panels=enable_panels,
            panel_alpha=panel_alpha,
            panel_padding=panel_padding,
            panel_radius=panel_radius,
        )

        self._overlay_margins = {
            "left": int(self.settings.get("margin_left", 50)),
            "bottom": int(self.settings.get("margin_bottom", 50)),
            "right": int(self.settings.get("margin_right", 50)),
            "spacing": int(self.settings.get("spacing_between", 10)),
        }

        # Weather client
        self.weather_client = build_weather_client(self, self.settings)
        try:
            self.weather_client.fetch()
            logging.info("Initial weather fetched: %s", str(self.weather_client.data())[:200])
        except Exception:
            logging.exception("Initial weather fetch failed")

        # Start periodic updates: prefer client's own scheduler if available
        self._weather_stop = threading.Event()
        if hasattr(self.weather_client, "initialize_weather_updates"):
            try:
                self.weather_client.initialize_weather_updates()
                self._weather_thread = None  # managed by the client
                logging.info("Weather updates initialized by provider.")
            except Exception:
                logging.exception("Failed to initialize provider-managed weather updates; falling back to local loop.")
                self._start_local_weather_loop()
        else:
            self._start_local_weather_loop()

        def _weather_loop(self) -> None:
            while not getattr(self, "_weather_stop", threading.Event()).is_set():
                try:
                    self.weather_client.fetch()
                except Exception:
                    logging.exception("weather loop error (server)")
                time.sleep(600)
    
    def _start_local_weather_loop(self) -> None:
        def _weather_loop():
            while not self._weather_stop.is_set():
                try:
                    self.weather_client.fetch()
                except Exception:
                    logging.exception("weather loop error (server)")
                # wait with interruptibility
                self._weather_stop.wait(600.0)
        self._weather_thread = threading.Thread(target=_weather_loop, name="WeatherLoop", daemon=True)
        self._weather_thread.start()

    def _stop_weather_loop(self) -> None:
        try:
            self._weather_stop.set()
        except Exception:
            pass

    # ------------- 30 fps compositor loop -------------
    def _compositor_loop(self) -> None:
        """
        Runs continuously at 30 fps when not in a transition, to keep the clock and weather
        updating on screen even when the base image is static.
        """
        last_push = 0.0
        while not self._compositor_stop.is_set() and self.is_running:
            start = time.time()
            try:
                if not self._in_transition and self.current_image is not None:
                    # Compose from the current base image every frame
                    composed = self._compose_final_frame(self.current_image)
                    self._push_composed_to_outputs(composed)
                    last_push = start
            except Exception:
                logging.exception("compositor loop error")
            # Sleep to maintain ~30 fps
            elapsed = time.time() - start
            sleep_time = max(0.0, self._frame_interval - elapsed)
            time.sleep(sleep_time)

    # ------------- Composition helpers -------------
    def _draw_contrast_band(self, frame_bgr: np.ndarray) -> None:
        """
        Draw a translucent black band behind the overlay area to guarantee readability.
        In-place modification. Keeps image detail visible but improves contrast.
        """
        h, w = frame_bgr.shape[:2]
        # Band height proportional to time+date font sizes
        band_h = max(60, int((self.overlay.time_font_size + self.overlay.date_font_size) * 1.2))

        # Bottom-aligned band, leave margin_bottom
        mb = max(0, int(self._overlay_margins.get("bottom", 50)))
        y2 = h - mb
        y1 = max(0, y2 - band_h)
        x1 = 0
        x2 = w

        roi = frame_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return
        # Blend roi with black at alpha 0.35
        overlay = np.zeros_like(roi, dtype=roi.dtype)
        cv2.addWeighted(roi, 0.65, overlay, 0.35, 0.0, dst=roi)

    def _compose_final_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        composed = self.overlay.resize_and_letterbox(frame_bgr, self.screen_width, self.screen_height)

        try:
            # Only draw the old band if panels are disabled, or if explicitly requested
            if (not self.overlay.enable_panels) or getattr(self, "_keep_band_with_panels", False):
                self._draw_contrast_band(composed)
        except Exception:
            pass

        try:
            weather = self.weather_client.data() or {}
            composed = self.overlay.render_datetime_and_weather(
                frame_bgr=composed,
                margins=self._overlay_margins,
                weather=weather,
                font_color=(255, 255, 255),
            )
        except Exception:
            logging.exception("overlay.render_datetime_and_weather failed")

        return composed

    def _push_composed_to_outputs(self, composed: np.ndarray) -> None:
        self.frame_to_stream = composed
        if hasattr(self, 'm_api'):
            try:
                self.m_api._new_frame_ev.set()
            except Exception:
                pass
        if self._gui_frame and hasattr(self._gui_frame, "publish_frame_from_backend"):
            try:
                self._gui_frame.publish_frame_from_backend(composed)
            except Exception:
                pass

    # ------------- Stream API -------------
    def update_frame_to_stream(self, frame):
        """
        Compose final frame here (server), then push to stream and GUI.
        Used by transition driver and also by initial display.
        """
        try:
            if frame is None:
                return
            composed = self._compose_final_frame(frame)
            self._push_composed_to_outputs(composed)
        except Exception:
            logging.exception("update_frame_to_stream failed")

    def get_live_frame(self):
        return self.frame_to_stream

    # ------------- Utils -------------
    def compute_image_hash(self, image_path):
        hash_obj = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    def get_is_running(self):
        return self.is_running

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

    def set_logger(self, logger):
        try:
            self.logger = logging.getLogger(__name__)
            logging.info("Loaded settings from settings.json.")
        except FileNotFoundError:
            logging.error("settings.json not found. Exiting.")
            raise

    def set_images_dir(self, images_dir=None):
        if images_dir is not None:
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
        return True

    def update_images_list(self):
        self.images = self.get_images_from_directory()
        self.shuffled_images = self.image_handler.shuffle_images(self.images)

    # ------------- Transition driver -------------
    def update_frame(self, generator):
        """
        Drive a transition generator. Server composes and publishes frames at ~30 fps.
        The compositor loop is paused by _in_transition flag while this runs.
        """
        self._in_transition = True
        try:
            frame_interval = self._frame_interval
            last = time.time()
            for frame in generator:
                now = time.time()
                # Compose and push
                self.update_frame_to_stream(frame)
                # Pace to 30 fps
                elapsed = now - last
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
                last = time.time()
            return AnimationStatus.ANIMATION_FINISHED
        except Exception as e:
            logging.exception(f"Error during frame update: {e}")
            return AnimationStatus.ANIMATION_ERROR
        finally:
            self._in_transition = False

    def start_image_transition(self, image1_path=None, image2_path=None, duration=5):
        if self.current_image is None:
            self.current_image = imread(self.get_random_image())
            if self.current_image is None:
                return AnimationStatus.ANIMATION_FINISHED
            self.current_image = self.image_handler.resize_image_with_background(
                self.current_image, self.screen_width, self.screen_height
            )

        if image2_path is None:
            image2_path = self.get_random_image()

        self.update_image_metadata(image2_path)

        self.next_image = imread(image2_path)
        self.next_image = self.image_handler.resize_image_with_background(
            self.next_image, self.screen_width, self.screen_height
        )

        effect_function = self.effects[self.EffectHandler.get_random_effect()]
        gen = effect_function(self.current_image, self.next_image, duration)
        self.status = self.update_frame(gen)

        if self.status == AnimationStatus.ANIMATION_FINISHED:
            self.current_image = self.next_image
            return AnimationStatus.ANIMATION_FINISHED

    def publish_frame_from_backend(self, frame):
        # No-op in server. Client implements publish to GUI.
        pass

    # ------------- Main loops -------------
    def run_photoframe(self):
        self.shuffled_images = self.image_handler.shuffle_images(self.images)
        self.current_image = imread(self.get_random_image())
        if self.current_image is not None:
            self.current_image = self.image_handler.resize_image_with_background(
                self.current_image, self.screen_width, self.screen_height
            )
            # Initial compose+push
            self.update_frame_to_stream(self.current_image)

        while self.is_running:
            if self.settings["animation_duration"] > 0:
                # Kick a transition; compositor loop will pause while transition runs
                self.start_image_transition(duration=self.settings["animation_duration"])
                time.sleep(self.settings["delay_between_images"])
            else:
                # Idle mode: compositor loop already pushes 30 fps with time/weather
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
            self.is_running = False
            self._compositor_stop.set()
            self._stop_weather_loop() 

    def _start_api(self):
        try:
            self.m_api = Backend(
                frame=self,
                settings=self.settings,          # existing settings dict/object
                image_dir=self.IMAGE_DIR,
                settings_path=self.settings_path  # <-- pass absolute path
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
                    img = cv2.imread(image_path)
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
