# region imports
import itertools
import json
import logging
import math
import os
import os as _os
import queue
import random as rand
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import NamedTuple

import cv2
import numpy as np
import psutil
from pillow_heif import register_heif_opener

from FrameServer.EffectHandler import EffectHandler
from FrameServer.image_handler import Image_Utils
from FrameServer.overlay import OverlayRenderer
from Utilities.brightness import get_brightness_percent
from Utilities.config_events import on_settings_changed
from Utilities.config_store import load_settings as _load_settings
from Utilities.image_utils import compute_image_hash as _compute_image_hash
from Utilities.media_types import SUPPORTED_MEDIA_EXTENSIONS
from Utilities.observer import ImagesObserver
from Utilities.Weather.weather_adapter import build_weather_client

# endregion imports


class iFrame(ABC):
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def send_log_message(self, msg, logger: logging):
        pass

    @abstractmethod
    def get_live_frame(self):
        pass

    @abstractmethod
    def get_is_running(self):
        pass

    @abstractmethod
    def update_images_list(self):
        pass

    @abstractmethod
    def set_frame(self):
        pass

    @abstractmethod
    def update_frame_to_stream(self):
        pass

    @abstractmethod
    def set_date_time(self):
        pass

    @abstractmethod
    def set_weather(self):
        pass


logger = logging.getLogger(__name__)

SETTINGS_PATH = ""


class AnimationStatus(Enum):
    ANIMATION_FINISHED = 1
    ANIMATION_ERROR = 2


class RenderConfig(NamedTuple):
    """Immutable snapshot of settings fields read on every frame.

    Built once per settings-change event; read lock-free in _send_frame
    and run_photoframe. All mutable dict values (margins) are converted
    to plain tuples or primitives so no per-frame allocation is needed.
    """

    # pre-computed per settings change; avoids ~10 dict lookups at 30fps
    animation_fps: int
    transition_fps: int
    show_weather: bool
    show_overlay: bool
    stats_show: bool
    contrast_text: bool
    datetime_corner: str
    weather_corner: str
    stats_corner: str
    stats_color: str
    stats_margin_x: int
    stats_margin_y: int
    # margins stored as a plain dict snapshot — immutable after construction
    margins: dict
    anim_duration: float
    delay_between: float


def _build_render_config(settings: dict) -> RenderConfig:
    """Extract render-critical fields from the settings dict into a RenderConfig.

    Called only on settings change (off the frame path), never per frame.
    """
    ui_cfg = settings.get("ui", {}) or {}
    stats_cfg = settings.get("stats", {}) or {}
    stream_cfg = settings.get("stream", {}) or {}
    playback_cfg = settings.get("playback", {}) or {}

    raw_margins = ui_cfg.get("margins", {}) or {}
    # Build a new dict that is safe to read without .copy() in the frame path
    margins_snapshot = dict(raw_margins)
    margins_snapshot.setdefault("spacing_between", ui_cfg.get("spacing_between", 50))

    return RenderConfig(
        animation_fps=int(playback_cfg.get("animation_fps") or 30),
        transition_fps=int(playback_cfg.get("transition_fps") or 30),
        show_weather=bool(ui_cfg.get("show_weather", True)),
        show_overlay=bool(stream_cfg.get("show_overlay", False)),
        stats_show=bool(stats_cfg.get("show", False)),
        contrast_text=bool(ui_cfg.get("contrast_text", False)),
        datetime_corner=str(ui_cfg.get("datetime_corner", "bottom-left")),
        weather_corner=str(ui_cfg.get("weather_corner", "bottom-right")),
        stats_corner=str(stats_cfg.get("corner", "top-left")),
        stats_color=str(stats_cfg.get("font_color", "white")),
        stats_margin_x=int(stats_cfg.get("margin_x", 20)),
        stats_margin_y=int(stats_cfg.get("margin_y", 20)),
        margins=margins_snapshot,
        anim_duration=float(playback_cfg.get("animation_duration") or 10),
        delay_between=float(playback_cfg.get("delay_between_images") or 30),
    )


class PhotoFrameServer(iFrame):
    """
    Server owns:
      - Sizing (letterbox)
      - Date/time + weather overlay (every frame)
      - 30 fps compositor that continues between transitions
    Client displays frames only.
    """

    def __init__(
        self,
        width=1920,
        height=1080,
        iframe: iFrame = None,
        images_dir=None,
        settings_path="settings.json",
    ):
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

        self._settings: dict = _load_settings()
        # Single lock protecting self._settings; _settings_reload_lock removed
        # (H2: two locks guarding the same field caused torn-read risk).
        self._settings_lock = threading.Lock()
        # Lock-free render config: written off-path on settings change, read
        # lock-free in _send_frame — immutable NamedTuple swap is atomic on CPython.
        self._render_cfg: RenderConfig = _build_render_config(self._settings)
        # Frame buffer lock: protects _raw_frame_to_stream / frame_to_stream /
        # _stats_frame_to_stream against concurrent reads in get_stream_frame (M6).
        self._frame_lock = threading.Lock()

        if not self.set_images_dir(images_dir=images_dir):
            logging.error("Failed to set images directory. Exiting.")
            raise FileNotFoundError(
                "Images directory not found and could not be created."
            )

        self.screen_width = width
        self.screen_height = height

        # --- FPS from 'playback' ---
        playback = self._settings.get("playback", {})
        self._target_fps = int(playback.get("animation_fps") or 30)
        self._transition_fps = int(playback.get("transition_fps") or 30)
        self._transition_frame_interval = 1.0 / max(1.0, float(self._transition_fps))

        self.current_image_idx = 0
        self.current_effect_idx = 0
        self.current_image = None
        self.next_image = None
        self.frame_to_stream = None
        self._raw_frame_to_stream = None
        self.is_running = True

        self.EffectHandler = EffectHandler()
        self.image_handler = Image_Utils(settings=self._settings)
        self.effects = self.EffectHandler.get_effects()
        self.update_images_list()

        # --- Overlay renderer (bakes date/time/weather into every frame) ---
        ui_cfg = self._settings.get("ui", {}) or {}
        font_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ui_cfg.get("font_name", "arial.ttf"),
        )
        if not os.path.isfile(font_path):
            font_path = "arial.ttf"
        try:
            self._overlay = OverlayRenderer(
                font_path=font_path,
                time_font_size=int(ui_cfg.get("time_font_size", 80)),
                date_font_size=int(ui_cfg.get("date_font_size", 60)),
                stats_font_size=int(
                    (self._settings.get("stats", {}) or {}).get("font_size", 20)
                ),
                desired_size=(self.screen_width, self.screen_height),
            )
        except Exception:
            logging.exception("Failed to create OverlayRenderer; overlays disabled")
            self._overlay = None
        self._weather_data = {}
        self._weather_lock = threading.Lock()

        # Weather client and loop (all modes)
        self._weather_stop = threading.Event()
        self.weather_client = build_weather_client(self, self._settings)
        self._weather_thread = None
        self._start_local_weather_loop()

        # DateTime thread for GUI mode only (overlay is baked in _send_frame for all modes)
        if self._gui_frame:
            self._date_time_thread = threading.Thread(
                target=self.start_date_time_loop,
                name="DateTimeThread",
                daemon=True,
            )
            self._date_time_thread.start()
        else:
            self._date_time_thread = None

        # Filesystem observer
        self._observer_started = False
        self._observer_debounce_ts = 0.0
        self._observer_min_interval = 1.0
        self.Observer = ImagesObserver(frame=self, images_dir=self.IMAGE_DIR)
        # If your ImagesObserver supports a callback, register it:
        if hasattr(self.Observer, "on_change"):
            # type: ignore[attr-defined]
            self.Observer.on_change = self._on_images_dir_changed
        if not self._observer_started:
            self.Observer.start_observer()
            self._observer_started = True

        # Register HEIF/HEIC plugin for Pillow once per server instance
        try:
            register_heif_opener()
            logging.info("HEIF/HEIC plugin registered successfully")
        except Exception as e:
            logging.warning("Could not register HEIF/HEIC plugin: %s", e)

        # Compatibility shim so app.py can still pass srv.settings_handler to Backend()
        # (removed in Task 6)
        self.settings_handler = self._settings

        on_settings_changed(self._on_settings_changed)

        # Stats overlay cache
        self._stats_last_refresh: float = 0.0
        self._stats_text: str = ""
        self._stats_frame_to_stream = None

        # Background metadata worker (H3): SHA-256 + JSON I/O moved off the
        # transition path; transitions enqueue work here and proceed immediately.
        self._metadata_queue: queue.Queue = queue.Queue()
        self._metadata_worker = threading.Thread(
            target=self._metadata_worker_loop,
            name="MetadataWorker",
            daemon=True,
        )
        self._metadata_worker.start()

    def _blank_frame(self):
        # neutral gray, screen-sized
        return np.full((self.screen_height, self.screen_width, 3), 32, dtype=np.uint8)

    def _reload_runtime_settings(self, reload_from_disk: bool = True) -> None:
        # Consolidated to _settings_lock — _settings_reload_lock removed (H2).
        with self._settings_lock:
            if reload_from_disk:
                self._settings = _load_settings()
            playback = self._settings.get("playback", {}) or {}
            self._target_fps = int(playback.get("animation_fps") or 30)
            self._transition_fps = int(playback.get("transition_fps") or 30)
            self._transition_frame_interval = 1.0 / max(
                1.0, float(self._transition_fps)
            )
            # Rebuild render config snapshot under the same lock so it is
            # always consistent with self._settings after this call.
            self._render_cfg = _build_render_config(self._settings)

    def _on_settings_changed(self, new_data: dict) -> None:
        # Build snapshot before acquiring lock to keep critical section short.
        new_render_cfg = _build_render_config(new_data)
        with self._settings_lock:
            self._settings = new_data
            # Atomic NamedTuple replacement; _send_frame reads this lock-free
            # because CPython attribute assignment is atomic for simple objects.
            self._render_cfg = new_render_cfg
        # Keep the legacy alias in sync so run_photoframe() picks up new values
        self.settings_handler = new_data

        # Sync scalar fps attrs from the new render config snapshot.
        # pre-computed per settings change; avoids playback dict lookups per frame
        self._target_fps = new_render_cfg.animation_fps
        self._transition_fps = new_render_cfg.transition_fps
        self._transition_frame_interval = 1.0 / max(1.0, float(self._transition_fps))

        # Rebuild overlay so font size / panel changes take effect immediately
        ui_cfg = new_data.get("ui", {}) or {}
        font_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(__file__)),
            ui_cfg.get("font_name", "arial.ttf"),
        )
        if not _os.path.isfile(font_path):
            font_path = "arial.ttf"
        try:
            self._overlay = OverlayRenderer(
                font_path=font_path,
                time_font_size=int(ui_cfg.get("time_font_size", 80)),
                date_font_size=int(ui_cfg.get("date_font_size", 60)),
                stats_font_size=int(
                    (new_data.get("stats", {}) or {}).get("font_size", 20)
                ),
                desired_size=(self.screen_width, self.screen_height),
            )
        except Exception:
            pass

        # Update image handler so effects (opacity, blur, etc.) hot-reload
        try:
            self.image_handler.settings = new_data
        except Exception:
            pass

        # Rebuild weather client so location/unit changes take effect
        try:
            self.weather_client = build_weather_client(self, new_data)
        except Exception:
            pass

        self.logger.info("[PhotoFrameServer] Settings hot-reloaded")

    def apply_settings_now(self) -> bool:
        try:
            self._reload_runtime_settings(reload_from_disk=True)
            return True
        except Exception:
            logging.exception("Immediate settings apply failed")
            return False

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
            # thread-safe (invokeMethod with Q_ARG or signals)
            self._gui_frame.set_date_time(dt)
            time.sleep(1)

    def _start_local_weather_loop(self) -> None:
        poll_sec = int(
            self._settings.get("weather_poll_seconds", 900)
        )  # default 15 min

        def _weather_loop():
            while not self._weather_stop.is_set():
                try:
                    self.weather_client.fetch()
                    data = self.weather_client.data() or {}
                    with self._weather_lock:
                        self._weather_data = data
                    # Also push to GUI if it exists
                    if self._gui_frame and hasattr(self._gui_frame, "set_weather"):
                        self._gui_frame.set_weather(data)
                except Exception:
                    logging.exception("weather loop error (server)")
                self._weather_stop.wait(poll_sec)

        self._weather_thread = threading.Thread(
            target=_weather_loop, name="WeatherThread", daemon=True
        )
        self._weather_thread.start()

    def _stop_weather_loop(self) -> None:
        try:
            self._weather_stop.set()
        except Exception:
            pass

    def _send_frame(self, frame_bgr: np.ndarray) -> None:
        """High-performance frame delivery for Raspberry Pi."""
        if frame_bgr is None:
            return

        # 1. Fast dimension check.
        # We assume the EffectHandler already provided a screen-sized frame.
        h, w = frame_bgr.shape[:2]
        if w != self.screen_width or h != self.screen_height:
            # Use fast cv2.resize only if the compositor failed to provide correct size
            frame_bgr = cv2.resize(
                frame_bgr,
                (self.screen_width, self.screen_height),
                interpolation=cv2.INTER_LINEAR,
            )

        # 2. Bake Overlay (Date/Time/Weather)
        # Save raw frame before overlay so stream can serve clean frames.
        # _render_cfg read is lock-free: NamedTuple attribute access is atomic
        # on CPython; writes only happen off the frame path in settings events.
        rcfg = (
            self._render_cfg
        )  # single attribute read; pre-computed per settings change

        # Store raw frame before overlay (lock-protected for get_stream_frame thread safety).
        with self._frame_lock:
            self._raw_frame_to_stream = frame_bgr

        if self._overlay:
            try:
                # All fields pre-computed per settings change; avoids ~6 dict lookups at 30fps
                with self._weather_lock:
                    weather = self._weather_data if rcfg.show_weather else {}

                frame_bgr = self._overlay.render_datetime_and_weather(
                    frame_bgr,
                    rcfg.margins,  # pre-computed snapshot; no per-frame .copy() needed
                    weather,
                    datetime_corner=rcfg.datetime_corner,
                    weather_corner=rcfg.weather_corner,
                    font_color=(255, 255, 255),
                    contrast_text=rcfg.contrast_text,
                )
            except Exception:
                # Fallback to raw frame if overlay fails to prevent a hard crash/freeze
                pass

        # 2b. Stats overlay (CPU/RAM/Temp/Disk/Brightness)
        # rcfg.stats_show pre-computed; avoids nested dict lookup at 30fps
        if self._overlay and rcfg.stats_show:
            try:
                now_ts = time.time()
                if now_ts - self._stats_last_refresh >= 5.0:
                    cpu = round(psutil.cpu_percent())
                    ram = round(psutil.virtual_memory().percent)
                    try:
                        temps = psutil.sensors_temperatures()
                        temp_val = None
                        if temps:
                            for key in (
                                "coretemp",
                                "cpu_thermal",
                                "cpu-thermal",
                                "k10temp",
                                "acpitz",
                            ):
                                if key in temps and temps[key]:
                                    temp_val = round(temps[key][0].current)
                                    break
                        temp_str = f"{temp_val}°C" if temp_val is not None else "N/A"
                    except Exception:
                        temp_str = "N/A"
                    try:
                        disk_free = psutil.disk_usage("/").free / (1024**3)
                        disk_str = f"{disk_free:.1f}GB"
                    except Exception:
                        disk_str = "N/A"
                    try:
                        bright = get_brightness_percent()
                        bright_str = f"{bright}%" if bright is not None else "N/A"
                    except Exception:
                        bright_str = "N/A"
                    self._stats_text = (
                        f"CPU {cpu}%  Temp {temp_str}\n"
                        f"RAM {ram}%  Disk {disk_str}\n"
                        f"Bright {bright_str}"
                    )
                    self._stats_last_refresh = now_ts
                # All stats fields pre-computed per settings change; avoids 4 dict lookups at 30fps
                frame_bgr = self._overlay.render_stats(
                    frame_bgr,
                    self._stats_text,
                    rcfg.stats_color,
                    corner=rcfg.stats_corner,
                    margin_x=rcfg.stats_margin_x,
                    margin_y=rcfg.stats_margin_y,
                )
            except Exception:
                pass

        # 2c. Save stats-included frame for stream (set unconditionally so stream
        #     always has the most recent frame at this point, with or without stats).
        # Lock protects concurrent reads in get_stream_frame (M6).
        with self._frame_lock:
            self._stats_frame_to_stream = frame_bgr
            # 3. Update internal buffers
            self.frame_to_stream = frame_bgr

        # 4. Dispatch to Pygame GUI (Main Thread will pick this up)
        if self._gui_frame and hasattr(self._gui_frame, "set_frame"):
            try:
                self._gui_frame.set_frame(frame_bgr)
            except Exception:
                logging.error("Failed to push frame to Pygame GUI")

        # 5. Signal the Backend MJPEG stream
        try:
            if hasattr(self, "m_api") and self.m_api:
                self.m_api._new_frame_ev.set()
        except Exception:
            pass

    # ------------- Stream API -------------
    def update_frame(self, generator):
        """
        Pull frames from the transition generator and push each one to the GUI.
        """
        last_frame = None

        try:
            # Prefer perf_counter() (monotonic, high-res) for pacing
            interval = float(
                getattr(
                    self, "_transition_frame_interval", self._transition_frame_interval
                )
            )
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
        return _compute_image_hash(image_path)

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

    def get_stream_frame(self):
        """Return the frame for the web stream — raw (no overlay) by default.

        Lock is held only for the buffer reference read, not during JPEG
        encoding (which happens in the capture loop after this returns).
        pre-computed render config avoids nested dict lookups on every poll (M6).
        """
        # rcfg read is lock-free (immutable NamedTuple, atomic attribute swap)
        rcfg = self._render_cfg
        with self._frame_lock:
            if not rcfg.show_overlay:
                if rcfg.stats_show:
                    stats_frame = self._stats_frame_to_stream
                    if isinstance(stats_frame, np.ndarray) and stats_frame.size:
                        return stats_frame
                raw = self._raw_frame_to_stream
                if isinstance(raw, np.ndarray) and raw.size:
                    return raw
            frame = self.frame_to_stream
        if isinstance(frame, np.ndarray) and frame.size:
            return frame
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
        image_paths = []
        for root, _dirs, files in os.walk(self.IMAGE_DIR):
            for file in files:
                if file.lower().endswith(SUPPORTED_MEDIA_EXTENSIONS):
                    image_paths.append(os.path.join(root, file))
        return image_paths

    def get_random_image(self):
        if len(self.shuffled_images) == 0:
            self.shuffled_images = list(self.images)
            rand.shuffle(self.shuffled_images)
        if len(self.shuffled_images) == 0:
            return None
        self.current_image_idx = (self.current_image_idx + 1) % len(
            self.shuffled_images
        )
        return self.shuffled_images[self.current_image_idx]

    def set_images_dir(self, images_dir=None):
        base_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        old_dir = getattr(self, "IMAGE_DIR", None)

        if images_dir is not None:
            if os.path.isabs(images_dir):
                self.IMAGE_DIR = images_dir
            else:
                self.IMAGE_DIR = os.path.join(base_root, images_dir)
        else:
            # --- Read from canonical 'system.image_dir' ---
            sys_cfg = self._settings.get("system", {})
            cfg = sys_cfg.get("image_dir") or "Images"

            if os.path.isabs(cfg):
                self.IMAGE_DIR = cfg
            else:
                self.IMAGE_DIR = os.path.join(base_root, cfg)

        if not os.path.exists(self.IMAGE_DIR):
            os.makedirs(self.IMAGE_DIR, exist_ok=True)
            logging.warning(
                "'%s' directory not found. Created a new one.", self.IMAGE_DIR
            )

        logging.info("Using IMAGE_DIR = %s", self.IMAGE_DIR)

        # Restart observer on new directory so watchdog tracks the right path.
        # If the directory is unchanged, still reload; remote streaming caches
        # can mutate the active directory without a reliable watchdog event.
        if getattr(self, "_observer_started", False) and self.IMAGE_DIR != old_dir:
            try:
                self.Observer.stop_observer()
            except Exception:
                pass
            self.Observer = ImagesObserver(frame=self, images_dir=self.IMAGE_DIR)
            if hasattr(self.Observer, "on_change"):
                self.Observer.on_change = self._on_images_dir_changed
            self._observer_started = False
            self.Observer.start_observer()
            self._observer_started = True
            self.update_images_list()
        elif self.IMAGE_DIR == old_dir:
            self.update_images_list()

        return True

    def update_images_list(self):
        self.images = self.get_images_from_directory()
        self.shuffled_images = self.image_handler.shuffle_images(self.images)

    # ------------- Video / Image Loaders -------------

    def _is_video(self, path: str) -> bool:
        if not path:
            return False
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

    def _video_generator(self, video_path, total_duration):
        """
        Yields frames from the video.
        - skip_background=True is used to reduce CPU load.
        - Loops based on total_duration (animation_duration + delay_between_images).
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logging.error(f"Could not open video: {video_path}")
            return

        # Video Metrics
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration = total_frames / fps

        # --- Rule: Delete if > 30 seconds (unchanged) ---
        if video_duration > 30.0:
            cap.release()
            logging.warning(
                f"Video {os.path.basename(video_path)} is too long ({video_duration:.2f}s). Deleting."
            )
            try:
                os.remove(video_path)
                self.update_images_list()
            except Exception as e:
                logging.error(f"Failed to delete long video: {e}")
            return

        # --- Calculate Loops for TOTAL duration ---
        # We ensure the video plays for at least the total time required
        if video_duration >= total_duration:
            loop_count = 1
        else:
            loop_count = math.ceil(total_duration / video_duration)
            loop_count = max(loop_count, 1)

        logging.info(
            f"Playing Video: {os.path.basename(video_path)} | VidLen: {video_duration:.1f}s | Target: {total_duration}s | Loops: {loop_count}"
        )

        frame_interval = 1.0 / fps

        for i in range(int(loop_count)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            loop_start_time = time.perf_counter()

            while True:
                now = time.perf_counter()
                elapsed_since_start = now - loop_start_time

                target_frame_index = int(elapsed_since_start * fps)
                current_frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

                if target_frame_index > current_frame_index:
                    frames_to_skip = target_frame_index - current_frame_index
                    if frames_to_skip > 0:
                        for _ in range(frames_to_skip):
                            cap.grab()

                ret, frame = cap.read()
                if not ret:
                    break

                # OPTIMIZATION: Pass skip_background=True here
                resized_frame = self.image_handler.resize_image_with_background(
                    frame, self.screen_width, self.screen_height, skip_background=True
                )
                yield resized_frame

                after_process = time.perf_counter()
                next_frame_time = loop_start_time + (
                    (target_frame_index + 1) * frame_interval
                )
                sleep_time = next_frame_time - after_process

                if sleep_time > 0:
                    time.sleep(sleep_time)

            # Optional: 1.5s Pause between loops (matches your previous style)
            if i < (loop_count - 1):
                if "resized_frame" in locals():
                    pause_start = time.perf_counter()
                    while (time.perf_counter() - pause_start) < 1.5:
                        yield resized_frame
                        time.sleep(0.05)

        cap.release()

    def _load_image_safe(self, path: str):
        if self._is_video(path):
            return self._get_first_video_frame(path)

        if not path:
            logging.warning("PhotoFrameServer._load_image_safe: empty image path")
            return None
        if not os.path.isfile(path):
            logging.warning(
                "PhotoFrameServer._load_image_safe: missing image file %r", path
            )
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
                    logging.warning(
                        "PhotoFrameServer: Pillow HEIC decode failed for %r: %s",
                        path,
                        e,
                    )

                try:
                    import pyheif

                    heif = pyheif.read(path)
                    pil_img = Image.frombytes(
                        heif.mode, heif.size, heif.data, "raw", heif.mode, heif.stride
                    )
                    pil_img = pil_img.convert("RGB")
                    arr = np.array(pil_img)
                    arr = arr[:, :, ::-1].copy()
                    return arr
                except Exception as e:
                    logging.warning(
                        "PhotoFrameServer: HEIC decode failed for %r via pyheif: %s",
                        path,
                        e,
                    )
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

    def start_image_transition(
        self, image1_path=None, image2_path=None, duration=5, hold_time=0
    ):
        if self.current_image is None:
            first_path = image1_path or self.get_random_image()
            img1 = self._load_image_safe(first_path)
            if img1 is None:
                self.current_image = self._blank_frame()
                self._send_frame(self.current_image)
                return False  # Not a video

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
            logging.error(
                "start_image_transition: failed to load next media. Skipping."
            )
            self._send_frame(self.current_image)
            return False

        # H3: SHA-256 + JSON I/O moved off the transition path.
        # Enqueue path for background worker; transition proceeds immediately.
        self._metadata_queue.put_nowait(image2_path)

        self.next_image = self.image_handler.resize_image_with_background(
            img2, self.screen_width, self.screen_height
        )

        effect_function = self.effects[self.EffectHandler.get_random_effect()]
        transition_gen = effect_function(
            self.current_image, self.next_image, duration, fps=self._target_fps
        )

        final_generator = transition_gen

        if is_video_transition:
            # Pass (duration + hold_time) so the video loops for the full experience
            # This covers the transition AND the delay
            video_gen = self._video_generator(image2_path, duration + hold_time)
            final_generator = itertools.chain(transition_gen, video_gen)

        self.status = self.update_frame(final_generator)

        if self.status == AnimationStatus.ANIMATION_FINISHED:
            self.current_image = self.next_image

        return is_video_transition

    def set_frame(self, frame):
        pass

    # ------------- Main loops -------------
    def run_photoframe(self):
        self.shuffled_images = self.image_handler.shuffle_images(self.images)
        img_path = self.get_random_image()

        # Initial image load
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
            # pre-computed per settings change; avoids playback dict lookups per slide
            rcfg = self._render_cfg
            anim_duration = rcfg.anim_duration
            delay = rcfg.delay_between

            if anim_duration > 0:
                is_video = self.start_image_transition(
                    duration=anim_duration, hold_time=delay
                )

                if not is_video:
                    hold_until = time.time() + delay
                    next_tick = time.time()
                    while time.time() < hold_until and self.is_running:
                        self._send_frame(self.current_image)

                        # PRECISE TIMING: Calculate next exact second
                        next_tick += 1.0
                        sleep_time = next_tick - time.time()
                        if sleep_time > 0:
                            time.sleep(sleep_time)
            else:
                self._send_frame(self.current_image)
                time.sleep(1.0)

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
        _join(getattr(self, "_metadata_worker", None), "MetadataWorker")

        try:
            if self._gui_frame and hasattr(self._gui_frame, "stop"):
                self._gui_frame.stop()
        except Exception:
            logging.exception("GUI stop failed")

        logging.info("PhotoFrameServer.stop_services: done.")

    # ------------- Metadata background worker (H3) -------------

    def _metadata_worker_loop(self) -> None:
        """Drain _metadata_queue and call update_image_metadata off the frame path.

        SHA-256 hashing and JSON I/O are expensive; moving them here lets
        start_image_transition return immediately and keeps the compositor loop
        unblocked. Worker runs as a daemon thread so it exits with the process.

        NOTE: WebAPI uses SQLite (WebAPI/database.py) for the same metadata;
        this JSON store (_load/_save_metadata_db) is a divergent second store.
        A future pass should migrate update_image_metadata to SQLite and
        remove the JSON file path entirely.
        """
        while True:
            try:
                image_path = self._metadata_queue.get(timeout=1.0)
            except queue.Empty:
                if not self.is_running:
                    break
                continue
            try:
                self.update_image_metadata(image_path)
            except Exception:
                logging.exception(
                    "MetadataWorker: update_image_metadata failed for %r", image_path
                )
            finally:
                self._metadata_queue.task_done()

    # ------------- Metadata I/O (server-owned) -------------

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
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except Exception:
            return None

    def _extract_exif_datetime(self, path: str) -> str:
        try:
            from PIL import ExifTags, Image

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
                    return dt.replace(tzinfo=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
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
