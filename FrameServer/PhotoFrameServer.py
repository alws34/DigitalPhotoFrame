# region imports
import hashlib
import os
import sys
import itertools
import math

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
import pyheif
from PIL import Image
from pillow_heif import register_heif_opener

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

        # Instance logger (inherits global configuration)
        self.logger = logging.getLogger(__name__)

        try:
            cv2.setUseOptimized(True)
            cv2.setNumThreads(max(1, (os.cpu_count() or 4) - 1))
        except Exception as e:
            self.logger.exception("Failed to set OpenCV optimizations: %s", e)

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

            self._weather_stop = threading.Event()
            self.weather_client = build_weather_client(self, self.settings_handler)

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

        # Register HEIF/HEIC plugin for Pillow once per server instance
        try:
            register_heif_opener()
            logging.info("HEIF/HEIC plugin registered successfully")
        except Exception as e:
            logging.warning("Could not register HEIF/HEIC plugin: %s", e)

    def _blank_frame(self):
        # neutral gray, screen-sized
        return np.full((self.screen_height, self.screen_width, 3), 32, dtype=np.uint8)

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
        poll_sec = int(self.settings_handler.get("weather_poll_seconds", 900))  # default 15 min

        def _weather_loop():
            while not self._weather_stop.is_set():
                try:
                    self.weather_client.fetch()
                    self._gui_frame.set_weather(self.weather_client.data() or {})
                except Exception:
                    logging.exception("weather loop error (server)")
                self._weather_stop.wait(poll_sec)

        self._weather_thread = threading.Thread(target=_weather_loop, name="WeatherThread", daemon=True)
        self._weather_thread.start()

    def _stop_weather_loop(self) -> None:
        try:
            self._weather_stop.set()
        except Exception:
            pass

    def _send_frame(self, frame_bgr: np.ndarray) -> None:
        if frame_bgr is None:
            logging.warning("PhotoFrameServer._send_frame: got None frame")
            return

        arr = np.asarray(frame_bgr)
        if not isinstance(arr, np.ndarray):
            logging.error("PhotoFrameServer._send_frame: non-ndarray frame: %r", type(frame_bgr))
            return

        if arr.dtype == object:
            logging.error(
                "PhotoFrameServer._send_frame: bad dtype=object from effect, shape=%s, dropping frame",
                arr.shape,
            )
            return

        if arr.ndim not in (2, 3):
            logging.error(
                "PhotoFrameServer._send_frame: unexpected ndim=%d, shape=%s",
                arr.ndim,
                arr.shape,
            )
            return

        # Normalize gray / BGRA
        if arr.ndim == 2:
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        elif arr.ndim == 3 and arr.shape[2] == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)

        if arr.dtype != np.uint8:
            try:
                arr = arr.astype(np.uint8)
            except Exception as e:
                logging.exception(
                    "PhotoFrameServer._send_frame: cannot cast dtype %s to uint8: %s", arr.dtype, e
                )
                return

        h, w = arr.shape[:2]
        if w != self.screen_width or h != self.screen_height:
            arr = self.image_handler.resize_image_with_background(
                arr, self.screen_width, self.screen_height
            )

        # Make the current frame available to the backend streamer
        self.frame_to_stream = arr

        # Push to GUI
        if self._gui_frame and hasattr(self._gui_frame, "set_frame"):
            try:
                self._gui_frame.set_frame(arr)
            except Exception:
                logging.exception("Failed to publish frame to GUI")

        # Signal backend streamer that a fresh frame exists
        try:
            if hasattr(self, "m_api") and self.m_api:
                self.m_api._new_frame_ev.set()
        except Exception:
            logging.exception("Failed to signal API new frame")

    # ------------- Stream API -------------
    def update_frame(self, generator):
        """
        Pull frames from the transition generator and push each one to the GUI.
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
                    end = next_deadline
                    while True:
                        now = time.perf_counter()
                        remaining = end - now
                        if remaining <= 0:
                            break
                        time.sleep(min(remaining, 0.005))

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
        if isinstance(self.frame_to_stream, np.ndarray) and self.frame_to_stream.size:
            return self.frame_to_stream
        return self._blank_frame()

    def update_frame_to_stream(self, frame_bgr: np.ndarray) -> None:
        pass

    def send_log_message(self, msg, logger=None):
        try:
            lg = getattr(self, "logger", None) or logging.getLogger(__name__)
            if callable(logger):
                logger(msg)
            elif isinstance(logger, int):
                lg.log(logger, msg)
            else:
                lg.info(msg)
        except Exception:
            try:
                (lg or logging).info(msg)
            except Exception:
                print(f"[PhotoFrame LOG] {msg}")

    def get_images_from_directory(self):
        image_extensions = [
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif",
            ".mov", ".mp4"
        ]
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
        base_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        if images_dir is not None:
            if os.path.isabs(images_dir):
                self.IMAGE_DIR = images_dir
            else:
                self.IMAGE_DIR = os.path.join(base_root, images_dir)
        else:
            cfg = self.settings_handler.get("images_dir") or "Images"
            if os.path.isabs(cfg):
                self.IMAGE_DIR = cfg
            else:
                self.IMAGE_DIR = os.path.join(base_root, cfg)

        if not os.path.exists(self.IMAGE_DIR):
            os.makedirs(self.IMAGE_DIR, exist_ok=True)
            logging.warning("'%s' directory not found. Created a new one.", self.IMAGE_DIR)

        logging.info("Using IMAGE_DIR = %s", self.IMAGE_DIR)
        return True

    def update_images_list(self):
        self.images = self.get_images_from_directory()
        self.shuffled_images = self.image_handler.shuffle_images(self.images)

    # ------------- Video / Image Loaders -------------

    def _is_video(self, path: str) -> bool:
        if not path: return False
        return path.lower().endswith((".mov", ".mp4"))

    def _get_first_video_frame(self, path: str):
        """Opens a video and returns the first frame as a numpy array."""
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                return None
            ret, frame = cap.read()
            cap.release()
            if ret:
                return frame
            return None
        except Exception as e:
            logging.error(f"Failed to extract first frame from video {path}: {e}")
            return None

    def _video_generator(self, video_path, configured_transition_time):
        """
        Yields frames from the video with Frame Skipping to prevent lag.
        - If processing is slow, it drops video frames to keep sync.
        - Deletes videos > 30s.
        - Dynamic looping + 1.5s pause.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logging.error(f"Could not open video: {video_path}")
            return

        # Video Metrics
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration = total_frames / fps

        # --- Rule: Delete if > 30 seconds ---
        if video_duration > 30.0:
            cap.release()
            logging.warning(f"Video {os.path.basename(video_path)} is too long ({video_duration:.2f}s). Deleting.")
            try:
                os.remove(video_path)
                self.update_images_list()
            except Exception as e:
                logging.error(f"Failed to delete long video: {e}")
            return

        # --- Calculate Loops ---
        if video_duration >= configured_transition_time:
            loop_count = 1
            remainder = video_duration % configured_transition_time
            if remainder > 0 and remainder < 5:
                loop_count = 2
        else:
            loop_count = math.ceil(configured_transition_time / video_duration)
            loop_count = max(loop_count, 3) 

        total_play_duration = (video_duration * loop_count) + (1.5 * (loop_count - 1))
        
        logging.info(f"Playing {os.path.basename(video_path)} ({video_duration:.1f}s). Loops: {loop_count}. Sync FPS: {fps}")

        # Pre-calculation for aspect ratio to avoid re-calc every frame if possible
        # (This simple check relies on the image_handler logic, keeping it standard for now)

        frame_interval = 1.0 / fps

        for i in range(int(loop_count)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            
            # Reset timing for this loop iteration
            loop_start_time = time.perf_counter()
            
            while True:
                # 1. Sync Check: How much time has passed in this loop?
                now = time.perf_counter()
                elapsed_since_start = now - loop_start_time
                
                # 2. Which frame *should* we be on?
                target_frame_index = int(elapsed_since_start * fps)
                current_frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                
                # 3. Frame Skipping Logic
                if target_frame_index > current_frame_index:
                    frames_to_skip = target_frame_index - current_frame_index
                    if frames_to_skip > 0:
                        # If we are way behind (e.g. > 5 frames), grab() without decoding to catch up fast
                        # logging.debug(f"Lag detected. Skipping {frames_to_skip} frames.")
                        for _ in range(frames_to_skip):
                            cap.grab() 

                # 4. Read and Process
                ret, frame = cap.read()
                if not ret:
                    break # End of video file
                
                resized_frame = self.image_handler.resize_image_with_background(
                    frame, self.screen_width, self.screen_height
                )
                yield resized_frame

                # 5. Precise Sleep
                # processing time = time.perf_counter() - now
                # We only sleep if we are actually AHEAD of schedule (rare if resizing is slow)
                after_process = time.perf_counter()
                next_frame_time = loop_start_time + ((target_frame_index + 1) * frame_interval)
                sleep_time = next_frame_time - after_process
                
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # --- Pause between loops ---
            if i < (loop_count - 1):
                # Show the last frame static for 1.5 seconds
                # We assume 'resized_frame' is holding the last valid frame
                if 'resized_frame' in locals():
                    pause_start = time.perf_counter()
                    while (time.perf_counter() - pause_start) < 1.5:
                        yield resized_frame
                        time.sleep(0.05) # Sleep briefly to not hammer CPU during pause

        cap.release()
        
    def _load_image_safe(self, path: str):
        if self._is_video(path):
            return self._get_first_video_frame(path)

        if not path:
            logging.warning("PhotoFrameServer._load_image_safe: empty image path")
            return None
        if not os.path.isfile(path):
            logging.warning("PhotoFrameServer._load_image_safe: missing image file %r", path)
            return None

        ext = os.path.splitext(path)[1].lower()

        # HEIC/HEIF path
        if ext in (".heic", ".heif"):
            try:
                try:
                    from PIL import Image, ImageOps
                    pil_img = Image.open(path)
                    try:
                        pil_img = ImageOps.exif_transpose(pil_img)
                    except Exception:
                        pass
                    pil_img = pil_img.convert("RGB")
                    arr = np.array(pil_img)
                    arr = arr[:, :, ::-1].copy()
                    return arr
                except Exception as e:
                    logging.warning("PhotoFrameServer: Pillow HEIC decode failed for %r: %s", path, e)

                try:
                    heif = pyheif.read(path)
                    pil_img = Image.frombytes(heif.mode, heif.size, heif.data, "raw", heif.mode, heif.stride)
                    pil_img = pil_img.convert("RGB")
                    arr = np.array(pil_img)
                    arr = arr[:, :, ::-1].copy()
                    return arr
                except Exception as e:
                    logging.warning("PhotoFrameServer: HEIC decode failed for %r via pyheif: %s", path, e)
                    return None
            except Exception:
                logging.exception("PhotoFrameServer: HEIC decode crashed for %r", path)
                return None

        img = cv2.imread(path)
        if img is None:
            logging.warning("PhotoFrameServer: cv2.imread failed for %r", path)
            return None

        return img

    # ------------- Main Transition Logic -------------

    def start_image_transition(self, image1_path=None, image2_path=None, duration=5):
        # Initialize current_image if needed
        if self.current_image is None:
            first_path = image1_path or self.get_random_image()
            img1 = self._load_image_safe(first_path)

            if img1 is None:
                logging.error("start_image_transition: no valid first image. Using blank.")
                self.current_image = self._blank_frame()
                self._send_frame(self.current_image)
                return AnimationStatus.ANIMATION_FINISHED

            self.current_image = self.image_handler.resize_image_with_background(
                img1, self.screen_width, self.screen_height
            )

        if image2_path is None:
            image2_path = self.get_random_image()

        is_video_transition = self._is_video(image2_path)

        if is_video_transition:
            img2 = self._get_first_video_frame(image2_path)
        else:
            img2 = self._load_image_safe(image2_path)

        if img2 is None:
            logging.error("start_image_transition: failed to load next media. Skipping.")
            self._send_frame(self.current_image)
            return AnimationStatus.ANIMATION_FINISHED

        try:
            self.update_image_metadata(image2_path)
        except Exception:
            logging.exception("start_image_transition: update_image_metadata failed")

        self.next_image = self.image_handler.resize_image_with_background(
            img2, self.screen_width, self.screen_height
        )

        # Standard transition effect
        effect_function = self.effects[self.EffectHandler.get_random_effect()]
        transition_gen = effect_function(self.current_image, self.next_image, duration, fps=self._target_fps)

        final_generator = transition_gen

        if is_video_transition:
            # Chain: Transition -> Video Playback (with frame skipping)
            video_gen = self._video_generator(image2_path, duration)
            final_generator = itertools.chain(transition_gen, video_gen)

        self.status = self.update_frame(final_generator)

        # Update state for next cycle
        if self.status == AnimationStatus.ANIMATION_FINISHED:
            if self.frame_to_stream is not None:
                self.current_image = self.frame_to_stream
            else:
                self.current_image = self.next_image

        return self.status
    def set_frame(self, frame):
        pass

    # ------------- Main loops -------------
    def run_photoframe(self):
        self.shuffled_images = self.image_handler.shuffle_images(self.images)

        img_path = self.get_random_image()
        if img_path:
            img = self._load_image_safe(img_path)
            if img is not None:
                self.current_image = self.image_handler.resize_image_with_background(
                    img, self.screen_width, self.screen_height
                )
            else:
                self.current_image = self._blank_frame()
        else:
            self.current_image = self._blank_frame()

        self._send_frame(self.current_image)

        while self.is_running:
            if self.settings_handler["animation_duration"] > 0:
                self.start_image_transition(duration=self.settings_handler["animation_duration"])
                time.sleep(self.settings_handler["delay_between_images"])
            else:
                time.sleep(0.1)

    def main(self):
        threading.Thread(target=self.run_photoframe, daemon=True).start()
        # threading.Thread(target=self._start_api, daemon=True).start()

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
                settings=self.settings_handler,
                image_dir=self.IMAGE_DIR,
                settings_path=self.settings_handler_path
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
                try:
                    dt = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
                    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    continue
            return None
        except Exception:
            return None

    def update_image_metadata(self, image_path: str) -> None:
        try:
            if not image_path or not os.path.isfile(image_path):
                return

            db = self._load_metadata_db()
            file_hash = self.compute_image_hash(image_path)
            entry = db.get(file_hash, {})

            try:
                st = os.stat(image_path)
                fsize = int(st.st_size)
            except Exception:
                fsize = None

            width = entry.get("width")
            height = entry.get("height")
            if width is None or height is None:
                try:
                    if self._is_video(image_path):
                        cap = cv2.VideoCapture(image_path)
                        if cap.isOpened():
                            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            cap.release()
                    else:
                        img = cv2.imread(image_path)
                        if img is not None:
                            height, width = int(img.shape[0]), int(img.shape[1])
                except Exception:
                    pass

            date_taken = entry.get("date_taken")
            if not date_taken and not self._is_video(image_path):
                date_taken = self._extract_exif_datetime(image_path)

            now_iso = self._utcnow_iso()
            date_added = entry.get("date_added") or now_iso
            date_modified = self._file_mtime_iso(image_path)

            filename = os.path.basename(image_path)
            try:
                rel_path = os.path.relpath(image_path, self.IMAGE_DIR)
            except Exception:
                rel_path = image_path

            views = int(entry.get("views") or 0) + 1
            caption = entry.get("caption") or "N/A"
            uploader = entry.get("uploader")

            updated = {
                "hash": file_hash,
                "filename": filename,
                "relative_path": rel_path,
                "absolute_path": image_path,
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

            try:
                self.current_metadata = updated
            except Exception:
                pass

        except Exception:
            logging.exception("update_image_metadata failed")


if __name__ == "__main__":
    frame = PhotoFrameServer()
    frame.main()