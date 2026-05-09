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
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    import pygame
except ImportError:
    pygame = None

_TRIPLE_TAP_WINDOW = 0.8   # seconds between taps

# Tab bar: index 0 is always QR, 1+ are settings tabs
_TABS = ["QR", "Playback", "Display", "Weather", "Network", "System"]

# Which top-level settings sections go in each tab (tab index → list of section keys)
_TAB_SECTIONS: Dict[int, List[str]] = {
    1: ["playback"],
    2: ["ui", "screen", "stats", "effects"],
    3: ["open_meteo"],
    4: ["backend_configs", "mqtt"],
    5: ["system", "autoupdate"],
}

# Keys never shown (complex, sensitive, read-only strings, or needs keyboard)
_SKIP_KEYS = frozenset({
    "supersecretkey", "password", "schedules", "days",
    "repo_path", "image_path", "log_file_path", "service_name", "image_dir",
    "host", "text", "version", "client_id", "base_topic", "discovery_prefix",
    "username", "branch", "remote", "timeformat", "timezone", "date_format",
    "font_name", "latitude", "longitude",
})

# String fields that can be cycled through a fixed set of options
_STRING_CYCLES: Dict[str, List[str]] = {
    "stats.font_color":             ["yellow", "white", "red", "green", "blue"],
    "open_meteo.temperature_unit":  ["celsius", "fahrenheit"],
    "open_meteo.units":             ["metric", "imperial"],
    "open_meteo.wind_speed_unit":   ["kmh", "mph", "ms", "kn"],
    "open_meteo.precipitation_unit":["mm", "inch"],
}

# (step, min, max) overrides; None → skip the field entirely
_FIELD_CONFIG: Dict[str, Optional[Tuple]] = {
    "screen.brightness":              (5,    0,   100),
    "screen.orientation":             (90,   0,   270),  # stored as int (0/90/180/270)
    "screen.off_hour":                (1,    0,    23),
    "screen.on_hour":                 (1,    0,    23),
    "screen.schedule_enabled":        None,   # managed via web UI
    "playback.animation_duration":    (1,    1,   120),
    "playback.delay_between_images":  (5,    1,   600),
    "playback.animation_fps":         (1,    1,    60),
    "ui.time_font_size":              (5,   10,   300),
    "ui.date_font_size":              (5,   10,   200),
    "ui.spacing_between":             (5,    0,   300),
    "ui.margins.bottom":              (5,    0,   300),
    "ui.margins.left":                (5,    0,   300),
    "ui.margins.right":               (5,    0,   300),
    "ui.text_shadow.alpha":           (5,    0,   255),
    "ui.text_shadow.blur":            (1,    0,    50),
    "ui.text_shadow.offset_x":       (1,  -50,    50),
    "ui.text_shadow.offset_y":       (1,  -50,    50),
    "stats.font_size":                (2,    8,   100),
    "effects.background_opacity":     (0.05, 0.0,  1.0),
    "effects.shadow_opacity":         (0.05, 0.0,  1.0),
    "effects.background_blur_radius": (2,    0,   200),
    "effects.shadow_blur_radius":     (2,    0,   200),
    "open_meteo.cache_ttl_minutes":   (5,    1,  1440),
    "backend_configs.server_port":    (1,    1, 65535),
    "backend_configs.stream_fps":     (1,    1,    60),
    "backend_configs.idle_fps":       (1,    1,    30),
    "backend_configs.stream_width":   (10,  100,  7680),
    "backend_configs.stream_height":  (10,  100,  4320),
    "mqtt.port":                      (1,    1, 65535),
    "mqtt.interval_seconds":          (1,    1,  3600),
    "autoupdate.hour":                (1,    0,    23),
    "autoupdate.minute":              (1,    0,    59),
    "system.image_quality_encoding":  (5,    1,   100),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_nested(d: dict, path: str, default=None):
    parts = path.split(".")
    cur = d
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _set_nested(d: dict, path: str, value) -> None:
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _deep_update(base: dict, updates: dict) -> None:
    for key, val in updates.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], val)
        else:
            base[key] = val


def _build_fields(settings: dict, sections: List[str]) -> List[tuple]:
    """
    Return a flat list of field descriptors for the given section keys.
    Each entry is one of:
      ("header", label_text)                          — non-interactive divider
      (path, label, ftype, step, fmin, fmax)          — interactive field
    """
    result: List[tuple] = []
    show_headers = len(sections) > 1

    def _recurse(data: dict, prefix: str, depth: int) -> None:
        for key, val in data.items():
            if key in _SKIP_KEYS:
                continue
            path = f"{prefix}.{key}"

            # Explicitly skipped paths
            if path in _FIELD_CONFIG and _FIELD_CONFIG[path] is None:
                continue

            label = "  " * depth + key.replace("_", " ").title()

            if isinstance(val, bool):
                result.append((path, label, bool, None, None, None))

            elif isinstance(val, int):
                cfg = _FIELD_CONFIG.get(path, (1, -999999, 999999))
                if cfg is None:
                    continue
                result.append((path, label, int, *cfg))

            elif isinstance(val, float):
                cfg = _FIELD_CONFIG.get(path, (0.05, -9999.0, 9999.0))
                if cfg is None:
                    continue
                result.append((path, label, float, *cfg))

            elif isinstance(val, str):
                if path in _STRING_CYCLES:
                    result.append((path, label, "cycle", _STRING_CYCLES[path], None, None))
                # plain strings skipped (no on-screen keyboard)

            elif isinstance(val, dict):
                result.append(("header", label))
                _recurse(val, path, depth + 1)

            # lists skipped

    for section_key in sections:
        section_data = settings.get(section_key)
        if not isinstance(section_data, dict):
            continue
        if show_headers:
            result.append(("header", section_key.replace("_", " ").upper()))
        _recurse(section_data, section_key, 0)

    return result


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

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
        self._last_bgr = None       # cached for panel redraws between frames

        # Triple-tap
        self._tap_times: list = []

        # Panel / settings form state
        self._panel_visible = False
        self._active_tab = 0
        self._live_settings: dict = {}
        self._pending_changes: dict = {}
        self._save_msg: str = ""
        self._save_msg_until: float = 0.0
        self._scroll_offsets: Dict[int, int] = {i: 0 for i in range(len(_TABS))}
        # Cached field lists per tab (rebuilt when panel opens)
        self._tab_fields: Dict[int, List[tuple]] = {}

        # QR
        self._info_url: str = ""
        self._qr_surface: Optional[pygame.Surface] = None

        # Interactive element hit rects: (pygame.Rect, action, data)
        self._ui_rects: List[Tuple[pygame.Rect, str, Any]] = []

        # pygame init
        os.environ.setdefault("SDL_VIDEO_ALLOW_SCREENSAVER", "0")
        pygame.init()

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
        H = self.height
        self._font_title   = pygame.font.SysFont("sans",      max(32, H // 18), bold=True)
        self._font_tab     = pygame.font.SysFont("sans",      max(18, H // 36))
        self._font_label   = pygame.font.SysFont("sans",      max(16, H // 40))
        self._font_value   = pygame.font.SysFont("monospace", max(18, H // 36), bold=True)
        self._font_url     = pygame.font.SysFont("monospace", max(22, H // 28))
        self._font_section = pygame.font.SysFont("sans",      max(14, H // 48), bold=True)

        logging.info("PhotoFramePygame: display %dx%d", self.width, self.height)

    # ------------------------------------------------------------------
    # Frame display
    # ------------------------------------------------------------------
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
            # Re-render from cache so button-tap feedback is immediate
            if self._panel_visible:
                with self._frame_lock:
                    bgr = self._last_bgr
                if bgr is not None:
                    self._blit_frame(bgr)
                    return True
            return False

        with self._frame_lock:
            self._last_bgr = bgr
        self._blit_frame(bgr)
        return True

    def _blit_frame(self, bgr: np.ndarray) -> None:
        try:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            surface = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
            if w != self.width or h != self.height:
                surface = pygame.transform.smoothscale(surface, (self.width, self.height))
            self.screen.blit(surface, (0, 0))
            if self._panel_visible:
                self._draw_panel()
            pygame.display.flip()
        except Exception as e:
            logging.error("Pygame render error: %s", e)

    # ------------------------------------------------------------------
    # Panel drawing
    # ------------------------------------------------------------------
    def _draw_panel(self) -> None:
        W, H = self.width, self.height
        pad = max(14, H // 45)

        panel = pygame.Surface((W, H), pygame.SRCALPHA)
        panel.fill((8, 12, 28, 235))

        self._ui_rects = []

        # ── Tab bar ────────────────────────────────────────────────
        TAB_H  = max(48, H // 14)
        n_tabs = len(_TABS)
        avail  = W - TAB_H - 4           # leave room for X button
        tab_w  = avail // n_tabs

        for i, name in enumerate(_TABS):
            tr = pygame.Rect(i * tab_w + 3, 3, tab_w - 6, TAB_H - 6)
            active = (i == self._active_tab)
            pygame.draw.rect(panel,
                             (60, 110, 255, 220) if active else (30, 40, 80, 180),
                             tr, border_radius=8)
            t = self._font_tab.render(name, True, (255, 255, 255))
            panel.blit(t, (tr.centerx - t.get_width() // 2,
                           tr.centery - t.get_height() // 2))
            self._ui_rects.append((tr, "tab", i))

        xr = pygame.Rect(W - TAB_H + 3, 3, TAB_H - 6, TAB_H - 6)
        pygame.draw.rect(panel, (160, 40, 40, 220), xr, border_radius=8)
        xt = self._font_tab.render("X", True, (255, 255, 255))
        panel.blit(xt, (xr.centerx - xt.get_width() // 2,
                        xr.centery - xt.get_height() // 2))
        self._ui_rects.append((xr, "close", None))

        pygame.draw.line(panel, (60, 110, 255, 100), (0, TAB_H), (W, TAB_H), 1)

        content_top    = TAB_H + pad // 2
        content_bottom = H - pad

        if self._active_tab == 0:
            self._draw_qr_tab(panel, content_top, content_bottom, pad)
        else:
            self._draw_settings_tab(panel, content_top, content_bottom, pad)

        self.screen.blit(panel, (0, 0))

    # ------------------------------------------------------------------
    # QR tab
    # ------------------------------------------------------------------
    def _draw_qr_tab(self, panel, top: int, bottom: int, pad: int) -> None:
        W = self.width
        port = self.settings.get("backend_configs", {}).get("server_port", 5002)
        url  = f"http://{self._info_url}:{port}"
        y    = top

        title = self._font_title.render("  Settings & Admin", True, (255, 255, 255))
        panel.blit(title, ((W - title.get_width()) // 2, y))
        y += title.get_height() + pad

        if self._qr_surface is not None:
            avail_h  = bottom - y - 80   # leave room for URL + labels
            qr_size  = max(120, min(W - pad * 4, avail_h) * 7 // 10)
            qr_scaled = pygame.transform.smoothscale(self._qr_surface, (qr_size, qr_size))
            border    = 10
            bg_w, bg_h = qr_size + border * 2, qr_size + border * 2
            qr_bg = pygame.Surface((bg_w, bg_h))
            qr_bg.fill((255, 255, 255))
            qr_bg.blit(qr_scaled, (border, border))
            panel.blit(qr_bg, ((W - bg_w) // 2, y))
            y += bg_h + pad

        url_surf = self._font_url.render(url, True, (140, 200, 255))
        uw, uh   = url_surf.get_size()
        pp       = 12
        pill     = pygame.Surface((uw + pp * 2, uh + pp * 2), pygame.SRCALPHA)
        pill.fill((20, 30, 70, 180))
        pygame.draw.rect(pill, (60, 110, 255, 120), pill.get_rect(), 1)
        pill.blit(url_surf, (pp, pp))
        panel.blit(pill, ((W - pill.get_width()) // 2, y))
        y += pill.get_height() + pad // 2

        for txt, col in [
            ("Scan QR or open URL in any browser on your network", (180, 180, 200)),
            ("Settings  |  Gallery  |  Upload photos",             (130, 160, 220)),
        ]:
            s = self._font_label.render(txt, True, col)
            panel.blit(s, ((W - s.get_width()) // 2, y))
            y += s.get_height() + 6

    # ------------------------------------------------------------------
    # Settings form tab
    # ------------------------------------------------------------------
    def _draw_settings_tab(self, panel, top: int, bottom: int, pad: int) -> None:
        W       = self.width
        tab_idx = self._active_tab
        fields  = self._tab_fields.get(tab_idx, [])

        ROW_H   = max(46, self.height // 16)
        HDR_H   = max(26, self.height // 28)
        BTN_W   = max(44, self.height // 16)
        VAL_W   = max(72, self.height // 10)
        SAVE_H  = max(44, self.height // 16)

        content_top    = top
        content_bottom = bottom - SAVE_H - pad
        avail_h        = content_bottom - content_top

        # Compute total scrollable height
        total_h = sum(HDR_H + 4 if f[0] == "header" else ROW_H + 4
                      for f in fields)
        max_scroll = max(0, total_h - avail_h)
        scroll     = max(0, min(self._scroll_offsets.get(tab_idx, 0), max_scroll))
        self._scroll_offsets[tab_idx] = scroll

        # Merged current + pending
        merged: dict = {}
        _deep_update(merged, self._live_settings)
        _deep_update(merged, self._pending_changes)

        panel.set_clip(pygame.Rect(0, content_top, W, avail_h))

        y_cursor = content_top - scroll

        for field in fields:
            if field[0] == "header":
                _, hdr_label = field
                row_h = HDR_H + 4
                ry    = y_cursor
                y_cursor += row_h
                if ry + row_h < content_top or ry > content_bottom:
                    continue
                hs = self._font_section.render(hdr_label, True, (100, 150, 255))
                panel.blit(hs, (pad + 4, ry + (HDR_H - hs.get_height()) // 2))
                pygame.draw.line(panel, (60, 90, 180, 120),
                                 (pad, ry + HDR_H), (W - pad, ry + HDR_H), 1)
                continue

            path, label, ftype, step, fmin, fmax = field
            row_h  = ROW_H + 4
            row_y  = y_cursor
            y_cursor += row_h
            if row_y + row_h <= content_top or row_y >= content_bottom:
                continue

            row_rect = pygame.Rect(pad, row_y, W - pad * 2, ROW_H)
            rs = pygame.Surface((row_rect.w, row_rect.h), pygame.SRCALPHA)
            rs.fill((20, 28, 55, 150))
            panel.blit(rs, row_rect.topleft)
            pygame.draw.rect(panel, (60, 90, 180, 70), row_rect, 1)

            lbl = self._font_label.render(label, True, (200, 210, 240))
            panel.blit(lbl, (pad + 8, row_y + (ROW_H - lbl.get_height()) // 2))

            val     = _get_nested(merged, path)
            btn_h   = ROW_H - pad
            btn_y   = row_y + (ROW_H - btn_h) // 2
            right_x = W - pad

            if ftype is bool:
                cur   = bool(val) if val is not None else False
                tgl_w = max(72, self.height // 14)
                tgl   = pygame.Rect(right_x - tgl_w, btn_y, tgl_w, btn_h)
                pygame.draw.rect(panel,
                                 (30, 160, 80, 220) if cur else (100, 40, 40, 220),
                                 tgl, border_radius=8)
                ts = self._font_value.render("ON" if cur else "OFF", True, (255, 255, 255))
                panel.blit(ts, (tgl.centerx - ts.get_width() // 2,
                                tgl.centery  - ts.get_height() // 2))
                self._ui_rects.append((tgl, "toggle", path))

            elif ftype == "cycle":
                choices = step
                cur_str = str(val) if val is not None else (choices[0] if choices else "")
                next_r  = pygame.Rect(right_x - BTN_W, btn_y, BTN_W, btn_h)
                vw      = VAL_W + 16
                val_r   = pygame.Rect(next_r.left - vw - 4, btn_y, vw, btn_h)
                prev_r  = pygame.Rect(val_r.left - BTN_W - 4, btn_y, BTN_W, btn_h)
                for r, txt, act, dat in [
                    (prev_r, "<", "cycle_prev", (path, choices)),
                    (next_r, ">", "cycle_next", (path, choices)),
                ]:
                    pygame.draw.rect(panel, (40, 60, 140, 220), r, border_radius=6)
                    s = self._font_value.render(txt, True, (255, 255, 255))
                    panel.blit(s, (r.centerx - s.get_width() // 2,
                                   r.centery  - s.get_height() // 2))
                    self._ui_rects.append((r, act, dat))
                pygame.draw.rect(panel, (15, 22, 50, 200), val_r)
                vs = self._font_value.render(cur_str, True, (200, 230, 255))
                panel.blit(vs, (val_r.centerx - vs.get_width() // 2,
                                val_r.centery  - vs.get_height() // 2))

            else:  # int or float — +/- buttons
                try:
                    cur_num = ftype(val) if val is not None else ftype(0)
                except Exception:
                    cur_num = ftype(0)
                plus_r  = pygame.Rect(right_x - BTN_W, btn_y, BTN_W, btn_h)
                val_r   = pygame.Rect(plus_r.left - VAL_W - 4, btn_y, VAL_W, btn_h)
                minus_r = pygame.Rect(val_r.left  - BTN_W - 4, btn_y, BTN_W, btn_h)
                for r, txt in [(minus_r, "-"), (plus_r, "+")]:
                    pygame.draw.rect(panel, (40, 60, 140, 220), r, border_radius=6)
                    s = self._font_value.render(txt, True, (255, 255, 255))
                    panel.blit(s, (r.centerx - s.get_width() // 2,
                                   r.centery  - s.get_height() // 2))
                pygame.draw.rect(panel, (15, 22, 50, 200), val_r)
                v_text = f"{cur_num:.2f}" if ftype is float else str(int(cur_num))
                vs = self._font_value.render(v_text, True, (200, 230, 255))
                panel.blit(vs, (val_r.centerx - vs.get_width() // 2,
                                val_r.centery  - vs.get_height() // 2))
                self._ui_rects.append((minus_r, "dec", (path, ftype, step, fmin, fmax)))
                self._ui_rects.append((plus_r,  "inc", (path, ftype, step, fmin, fmax)))

        panel.set_clip(None)

        # Scroll indicators / buttons
        if scroll > 0:
            up = self._font_value.render("^", True, (160, 180, 255))
            ux, uy = W - pad - up.get_width(), content_top + 4
            panel.blit(up, (ux, uy))
            self._ui_rects.append((
                pygame.Rect(ux - 6, uy, up.get_width() + 12, up.get_height() + 6),
                "scroll_up", tab_idx,
            ))
        if scroll < max_scroll:
            dn = self._font_value.render("v", True, (160, 180, 255))
            dx, dy = W - pad - dn.get_width(), content_bottom - dn.get_height() - 4
            panel.blit(dn, (dx, dy))
            self._ui_rects.append((
                pygame.Rect(dx - 6, dy, dn.get_width() + 12, dn.get_height() + 6),
                "scroll_down", tab_idx,
            ))

        # Save button
        save_w    = max(160, W // 5)
        save_rect = pygame.Rect((W - save_w) // 2, bottom - SAVE_H, save_w, SAVE_H)
        pygame.draw.rect(panel, (30, 160, 80, 220), save_rect, border_radius=8)
        sv = self._font_label.render("Save", True, (255, 255, 255))
        panel.blit(sv, (save_rect.centerx - sv.get_width() // 2,
                        save_rect.centery  - sv.get_height() // 2))
        self._ui_rects.append((save_rect, "save", None))

        if _time.monotonic() < self._save_msg_until and self._save_msg:
            col = (100, 255, 150) if "!" in self._save_msg else (255, 140, 100)
            msg = self._font_label.render(self._save_msg, True, col)
            panel.blit(msg, (save_rect.right + 8,
                             save_rect.centery - msg.get_height() // 2))

    # ------------------------------------------------------------------
    # Event handling (main thread)
    # ------------------------------------------------------------------
    def process_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self._panel_visible:
                        self._close_panel()
                    else:
                        return False
                elif event.key == pygame.K_q and not self._panel_visible:
                    return False
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self._panel_visible:
                    self._handle_panel_tap(event.pos)
                else:
                    self._handle_triple_tap()
            if event.type == pygame.MOUSEWHEEL and self._panel_visible:
                tab = self._active_tab
                if tab > 0:
                    ROW_H = max(46, self.height // 16)
                    self._scroll_offsets[tab] = max(
                        0, self._scroll_offsets.get(tab, 0) - event.y * ROW_H
                    )
        return True

    def _handle_triple_tap(self) -> None:
        now = _time.monotonic()
        self._tap_times = [t for t in self._tap_times if now - t < _TRIPLE_TAP_WINDOW]
        self._tap_times.append(now)
        if len(self._tap_times) >= 3:
            self._tap_times.clear()
            self._open_panel()

    def _open_panel(self) -> None:
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

        try:
            from Utilities.config_store import load_settings
            self._live_settings = load_settings()
        except Exception:
            self._live_settings = dict(self.settings)

        # Build field lists for all settings tabs once
        for tab_idx, sections in _TAB_SECTIONS.items():
            self._tab_fields[tab_idx] = _build_fields(self._live_settings, sections)

        self._pending_changes = {}
        self._scroll_offsets  = {i: 0 for i in range(len(_TABS))}
        self._active_tab      = 0
        self._panel_visible   = True

    def _close_panel(self) -> None:
        self._panel_visible   = False
        self._pending_changes = {}

    # ------------------------------------------------------------------
    # Panel tap dispatch
    # ------------------------------------------------------------------
    def _handle_panel_tap(self, pos: Tuple[int, int]) -> None:
        px, py = pos
        for rect, action, data in self._ui_rects:
            if rect.collidepoint(px, py):
                self._dispatch(action, data)
                return

    def _dispatch(self, action: str, data: Any) -> None:
        if action == "close":
            self._close_panel()

        elif action == "tab":
            self._active_tab = int(data)

        elif action == "toggle":
            path = data
            merged: dict = {}
            _deep_update(merged, self._live_settings)
            _deep_update(merged, self._pending_changes)
            _set_nested(self._pending_changes, path,
                        not bool(_get_nested(merged, path, False)))

        elif action in ("inc", "dec"):
            path, ftype, step, fmin, fmax = data
            merged: dict = {}
            _deep_update(merged, self._live_settings)
            _deep_update(merged, self._pending_changes)
            try:
                cur = ftype(_get_nested(merged, path, 0))
            except Exception:
                cur = ftype(0)
            new_val = cur + (step if action == "inc" else -step)
            if fmin is not None:
                new_val = max(ftype(fmin), new_val)
            if fmax is not None:
                new_val = min(ftype(fmax), new_val)
            _set_nested(self._pending_changes, path, new_val)

        elif action in ("cycle_next", "cycle_prev"):
            path, choices = data
            merged: dict = {}
            _deep_update(merged, self._live_settings)
            _deep_update(merged, self._pending_changes)
            cur = str(_get_nested(merged, path, choices[0]))
            try:
                idx = choices.index(cur)
            except ValueError:
                idx = 0
            delta = 1 if action == "cycle_next" else -1
            _set_nested(self._pending_changes, path,
                        choices[(idx + delta) % len(choices)])

        elif action == "save":
            self._save_settings()

        elif action == "scroll_up":
            tab = int(data)
            ROW_H = max(46, self.height // 16)
            self._scroll_offsets[tab] = max(0, self._scroll_offsets.get(tab, 0) - ROW_H)

        elif action == "scroll_down":
            tab = int(data)
            ROW_H = max(46, self.height // 16)
            self._scroll_offsets[tab] = self._scroll_offsets.get(tab, 0) + ROW_H

    def _save_settings(self) -> None:
        try:
            from Utilities.config_store import load_settings, save_settings
            from Utilities.config_events import notify_settings_changed
            current = load_settings()
            _deep_update(current, self._pending_changes)
            save_settings(current)
            # Fire callbacks immediately — don't wait for watchdog
            notify_settings_changed(current)
            self._live_settings   = current
            self._pending_changes = {}
            # Rebuild field lists to reflect saved values
            for tab_idx, sections in _TAB_SECTIONS.items():
                self._tab_fields[tab_idx] = _build_fields(self._live_settings, sections)
            self._save_msg       = "Saved!"
            self._save_msg_until = _time.monotonic() + 3.0
        except Exception as e:
            self._save_msg       = f"Error: {e}"
            self._save_msg_until = _time.monotonic() + 5.0
            logging.error("Settings save error: %s", e)

    # ------------------------------------------------------------------
    # QR code generation
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # iFrame-compatible stubs
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def stop(self) -> None:
        self._running = False
        try:
            pygame.quit()
        except Exception:
            pass
