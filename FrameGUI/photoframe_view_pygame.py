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
import threading
from typing import Any, Optional

import cv2
import numpy as np

try:
    import pygame
except ImportError:
    pygame = None


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
        self._latest_surface = None

        # Initialize pygame + display
        os.environ.setdefault("SDL_VIDEO_ALLOW_SCREENSAVER", "0")
        pygame.init()

        # Get actual screen resolution if not specified
        info = pygame.display.Info()
        self.width = width or info.current_w
        self.height = height or info.current_h

        # Fullscreen with hardware acceleration
        flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        try:
            self.screen = pygame.display.set_mode(
                (self.width, self.height), flags
            )
        except pygame.error:
            # Fallback without hardware surface
            self.screen = pygame.display.set_mode(
                (self.width, self.height), pygame.FULLSCREEN
            )

        pygame.display.set_caption("Digital Photo Frame")
        pygame.mouse.set_visible(False)

        # Fill black initially
        self.screen.fill((0, 0, 0))
        pygame.display.flip()

        logging.info("PhotoFramePygame: display %dx%d", self.width, self.height)

    # -----------------------------------------------------------------
    # Frame display (called from compositor thread)
    # -----------------------------------------------------------------
    def set_frame(self, bgr: np.ndarray) -> None:
        """Receive a BGR numpy frame and prepare it for display."""
        if bgr is None or not isinstance(bgr, np.ndarray):
            return

        try:
            # BGR -> RGB
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]

            # Create pygame surface from numpy array
            # pygame expects (width, height) shaped data via surfarray
            surface = pygame.surfarray.make_surface(
                np.ascontiguousarray(rgb.swapaxes(0, 1))
            )

            # Scale to screen if needed
            if w != self.width or h != self.height:
                surface = pygame.transform.smoothscale(
                    surface, (self.width, self.height)
                )

            with self._frame_lock:
                self._latest_surface = surface

        except Exception:
            logging.exception("PhotoFramePygame.set_frame failed")

    def render_pending_frame(self) -> bool:
        """Blit the latest frame to screen. Call from the main thread."""
        with self._frame_lock:
            surface = self._latest_surface
            self._latest_surface = None

        if surface is None:
            return False

        self.screen.blit(surface, (0, 0))
        pygame.display.flip()
        return True

    # -----------------------------------------------------------------
    # Event handling (call from main thread)
    # -----------------------------------------------------------------
    def process_events(self) -> bool:
        """Process SDL events. Returns False if quit requested."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    return False
        return True

    # -----------------------------------------------------------------
    # iFrame-compatible stubs (overlays are baked into frames by compositor)
    # -----------------------------------------------------------------
    def set_date_time(self, dt_string: str = "") -> None:
        pass  # Overlay rendered by compositor

    def set_weather(self, weather_data: dict = None) -> None:
        pass  # Overlay rendered by compositor

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
