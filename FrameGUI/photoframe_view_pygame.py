"""
Lightweight fullscreen display using pygame (SDL2).

Receives composited BGR frames (with overlays baked in) from PhotoFrameServer
and blits them directly to the screen. No encoding, no HTTP, no polling.

Requires: pygame
Display: works with Wayland, X11, DRM/KMS via SDL2 backends.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time as _time
from typing import Optional

import cv2
import numpy as np

try:
    import pygame
except ImportError:
    pygame = None

_TRIPLE_TAP_WINDOW = 0.8   # seconds between taps
_INFO_DISPLAY_SEC  = 6.0   # how long the info overlay stays visible


class PhotoFramePygame:
    """
    Minimal fullscreen display. Implements the subset of iFrame that
    PhotoFrameServer actually calls: set_frame(), set_date_time(), set_weather().

    Overlays are already baked into frames by the compositor, so set_date_time
    and set_weather are no-ops here.
    """

    def __init__(self, width: int = 0, height: int = 0,
                 settings: Optional[dict] = None):
        if pygame is None:
            raise ImportError("pygame is required for display mode. "
                              "Install with: pip install pygame")

        self.settings = settings or {}
        self._running = True
        self._frame_lock = threading.Lock()
        self._pending_bgr = None

        # Triple-tap state
        self._tap_times: list = []
        self._info_until: float = 0.0
        self._info_url: str = ""

        # Initialize pygame + display
        os.environ.setdefault("SDL_VIDEO_ALLOW_SCREENSAVER", "0")
        pygame.init()

        # Get actual screen resolution if not specified
        info = pygame.display.Info()
        self.width  = width  or info.current_w
        self.height = height or info.current_h

        flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        try:
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
        except pygame.error:
            self.screen = pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)

        pygame.display.set_caption("Digital Photo Frame")
        pygame.mouse.set_visible(False)

        self.screen.fill((0, 0, 0))
        pygame.display.flip()

        # Font for info overlay (no external file needed)
        pygame.font.init()
        self._info_font_big   = pygame.font.SysFont("monospace", max(28, self.height // 22))
        self._info_font_small = pygame.font.SysFont("monospace", max(20, self.height // 32))

        logging.info("PhotoFramePygame: display %dx%d", self.width, self.height)

    # -----------------------------------------------------------------
    # Frame display (called from compositor thread)
    # -----------------------------------------------------------------
    def set_frame(self, bgr: np.ndarray) -> None:
        if bgr is None:
            return
        with self._frame_lock:
            self._pending_bgr = bgr

    def render_pending_frame(self) -> bool:
        with self._frame_lock:
            bgr = self._pending_bgr
            self._pending_bgr = None

        if bgr is None:
            return False

        try:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            # frombuffer avoids the swapaxes+ascontiguousarray copies used by
            # surfarray.make_surface — roughly 2x faster on ARM.
            h, w = rgb.shape[:2]
            surface = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
            if w != self.width or h != self.height:
                surface = pygame.transform.smoothscale(surface, (self.width, self.height))
            self.screen.blit(surface, (0, 0))
            self._draw_info_overlay()
            pygame.display.flip()
            return True
        except Exception as e:
            logging.error("Pygame render error: %s", e)
            return False

    def _draw_info_overlay(self) -> None:
        if _time.monotonic() >= self._info_until:
            return
        port = self.settings.get("backend_configs", {}).get("server_port", 5002)
        url  = f"http://{self._info_url}:{port}"
        lines_big   = ["Settings & Admin UI"]
        lines_small = [
            f"Open in browser:  {url}",
            "",
            "Settings  •  Gallery  •  Upload photos",
            "",
            "Tap again to dismiss",
        ]
        pad = 24
        surfs = [self._info_font_big.render(l, True, (255, 230, 80)) for l in lines_big]
        surfs += [self._info_font_small.render(l, True, (220, 220, 220)) for l in lines_small]
        total_h = sum(s.get_height() + 6 for s in surfs) + pad * 2
        max_w   = max(s.get_width() for s in surfs) + pad * 2
        overlay = pygame.Surface((max_w, total_h), pygame.SRCALPHA)
        overlay.fill((10, 10, 30, 210))
        # top accent bar
        pygame.draw.rect(overlay, (80, 130, 255, 200), (0, 0, max_w, 4))
        y = pad
        for s in surfs:
            overlay.blit(s, ((max_w - s.get_width()) // 2, y))
            y += s.get_height() + 6
        x  = (self.width  - max_w)  // 2
        yo = (self.height - total_h) // 2
        self.screen.blit(overlay, (x, yo))

    # -----------------------------------------------------------------
    # Event handling (call from main thread)
    # -----------------------------------------------------------------
    def process_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    return False
            if event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_tap()
        return True

    def _handle_tap(self) -> None:
        now = _time.monotonic()
        # If info overlay already showing, dismiss it
        if now < self._info_until:
            self._info_until = 0.0
            self._tap_times.clear()
            return
        self._tap_times = [t for t in self._tap_times if now - t < _TRIPLE_TAP_WINDOW]
        self._tap_times.append(now)
        if len(self._tap_times) >= 3:
            self._tap_times.clear()
            self._activate_info_overlay()

    def _activate_info_overlay(self) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self._info_url = s.getsockname()[0]
            s.close()
        except Exception:
            self._info_url = "?.?.?.?"
        self._info_until = _time.monotonic() + _INFO_DISPLAY_SEC

    # -----------------------------------------------------------------
    # iFrame-compatible stubs (overlays are baked into frames by compositor)
    # -----------------------------------------------------------------
    def set_date_time(self, dt_string: str = "") -> None:
        pass

    def set_weather(self, weather_data: dict = None) -> None:
        pass

    def get_is_running(self) -> bool:
        return self._running

    def get_live_frame(self):
        return None

    def update_images_list(self):
        pass

    def update_frame_to_stream(self, frame=None):
        pass

    def send_log_message(self, msg, logger=None):
        logging.info(msg)

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------
    def stop(self) -> None:
        self._running = False
        try:
            pygame.quit()
        except Exception:
            pass
