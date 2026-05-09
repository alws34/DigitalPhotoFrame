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

        pygame.font.init()
        self._info_font_title  = pygame.font.SysFont("sans",     max(32, self.height // 18), bold=True)
        self._info_font_url    = pygame.font.SysFont("monospace", max(22, self.height // 28))
        self._info_font_small  = pygame.font.SysFont("sans",     max(18, self.height // 36))
        self._qr_surface: Optional[pygame.Surface] = None

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

        W, H  = self.width, self.height
        pad   = max(20, H // 32)
        panel = pygame.Surface((W, H), pygame.SRCALPHA)

        # ── glass background ──────────────────────────────────────────
        panel.fill((8, 12, 28, 220))
        pygame.draw.rect(panel, (60, 110, 255, 180), (0, 0, W, 5))       # top bar
        pygame.draw.rect(panel, (30, 40, 80, 120),   (0, H - 5, W, 5))   # bottom bar

        # ── header ────────────────────────────────────────────────────
        title_surf = self._info_font_title.render("⚙  Settings & Admin", True, (255, 255, 255))
        panel.blit(title_surf, ((W - title_surf.get_width()) // 2, pad))
        ty = pad + title_surf.get_height() + 8
        pygame.draw.line(panel, (60, 110, 255, 160), (pad * 2, ty), (W - pad * 2, ty), 1)
        ty += 14

        # ── QR code ───────────────────────────────────────────────────
        qr_size = min(W, H) // 2
        if self._qr_surface is not None:
            qr_scaled = pygame.transform.smoothscale(self._qr_surface, (qr_size, qr_size))
            # White rounded-ish border
            border = 8
            qr_bg = pygame.Surface((qr_size + border * 2, qr_size + border * 2))
            qr_bg.fill((255, 255, 255))
            qr_bg.blit(qr_scaled, (border, border))
            qx = (W - qr_bg.get_width()) // 2
            panel.blit(qr_bg, (qx, ty))
            qr_bottom = ty + qr_bg.get_height() + pad // 2
        else:
            qr_bottom = ty + pad

        # ── URL pill ──────────────────────────────────────────────────
        url_surf  = self._info_font_url.render(url, True, (140, 200, 255))
        uw, uh    = url_surf.get_width(), url_surf.get_height()
        pill_pad  = 10
        pill_rect = pygame.Rect((W - uw - pill_pad * 2) // 2, qr_bottom, uw + pill_pad * 2, uh + pill_pad * 2)
        pill_surf = pygame.Surface((pill_rect.w, pill_rect.h), pygame.SRCALPHA)
        pill_surf.fill((20, 30, 70, 180))
        pygame.draw.rect(pill_surf, (60, 110, 255, 120), pill_surf.get_rect(), 1)
        pill_surf.blit(url_surf, (pill_pad, pill_pad))
        panel.blit(pill_surf, pill_rect.topleft)

        # ── sub-labels ────────────────────────────────────────────────
        sub_y = pill_rect.bottom + pad // 2
        for txt, col in [
            ("Scan QR or open URL in any browser on your network", (180, 180, 200)),
            ("Settings  •  Gallery  •  Upload photos", (130, 160, 220)),
            ("Tap anywhere to dismiss", (100, 100, 130)),
        ]:
            s = self._info_font_small.render(txt, True, col)
            panel.blit(s, ((W - s.get_width()) // 2, sub_y))
            sub_y += s.get_height() + 6

        self.screen.blit(panel, (0, 0))

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

        port = self.settings.get("backend_configs", {}).get("server_port", 5002)
        url  = f"http://{self._info_url}:{port}"
        self._qr_surface = self._make_qr_surface(url)
        self._info_until = _time.monotonic() + _INFO_DISPLAY_SEC

    @staticmethod
    def _make_qr_surface(url: str) -> Optional[pygame.Surface]:
        try:
            import qrcode  # type: ignore[import]
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color=(20, 20, 40), back_color=(255, 255, 255))
            rgb = img.convert("RGB")
            w, h = rgb.size
            return pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
        except Exception as e:
            logging.warning("QR code generation failed: %s", e)
            return None

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
