import time
from typing import Dict, Tuple
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


class OverlayRenderer:
    def __init__(
        self,
        font_path: str,
        time_font_size: int,
        date_font_size: int,
        stats_font_size: int,
        desired_size: Tuple[int, int],
        enable_panels: bool = False,
        panel_alpha: int = 128,     # 0..255
        panel_padding: int = 12,    # px around text
        panel_radius: int = 10,     # rounded corners
    ) -> None:
        self.desired_w, self.desired_h = desired_size
        self.time_font = ImageFont.truetype(font_path, time_font_size)
        self.date_font = ImageFont.truetype(font_path, date_font_size)
        self.stats_font = ImageFont.truetype(font_path, stats_font_size)

        # Panel controls
        self.enable_panels = bool(enable_panels)
        self.panel_alpha = max(0, min(255, int(panel_alpha)))
        self.panel_padding = max(0, int(panel_padding))
        self.panel_radius = max(0, int(panel_radius))

        # Cache sizes for layout
        self.time_font_size = time_font_size
        self.date_font_size = date_font_size

    @staticmethod
    def _color_from_name(name: str) -> Tuple[int, int, int]:
        cmap = {
            "yellow": (255, 255, 0),
            "white": (255, 255, 255),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
        }
        return cmap.get((name or "").lower(), (255, 255, 255))

    @staticmethod
    def resize_and_crop(src_bgr: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        h, w = src_bgr.shape[:2]
        aspect_src = w / float(h)
        aspect_dst = target_w / float(target_h)

        if aspect_src > aspect_dst:
            # crop width
            new_w = int(h * aspect_dst)
            x0 = (w - new_w) // 2
            src_bgr = src_bgr[:, x0:x0 + new_w]
        else:
            # crop height
            new_h = int(w / aspect_dst)
            y0 = (h - new_h) // 2
            src_bgr = src_bgr[y0:y0 + new_h, :]

        return cv2.resize(src_bgr, (target_w, target_h))

    @staticmethod
    def _textbbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int, int, int]:
        return draw.textbbox((0, 0), text, font=font)

    @staticmethod
    def _expand_bbox(b: Tuple[int, int, int, int], pad: int) -> Tuple[int, int, int, int]:
        x0, y0, x1, y1 = b
        return (x0 - pad, y0 - pad, x1 + pad, y1 + pad)

    def _draw_rounded_rect(self, draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], radius: int, fill_rgba: Tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = box
        w = max(0, x1 - x0)
        h = max(0, y1 - y0)
        if w == 0 or h == 0:
            return
        r = max(0, min(radius, min(w, h) // 2))
        draw.rounded_rectangle(box, radius=r, fill=fill_rgba)

    def render_datetime_and_weather(
        self,
        frame_bgr: np.ndarray,
        margins: Dict[str, int],
        weather: Dict,
        font_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> np.ndarray:
        base_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        base = Image.fromarray(base_rgb).convert("RGBA")
        overlay = self.render_overlay_rgba(base.width, base.height, margins, weather, font_color)
        out_rgba = Image.alpha_composite(base, overlay)
        return cv2.cvtColor(np.array(out_rgba.convert("RGB")), cv2.COLOR_RGB2BGR)
        # Clock strings
        # current_time = time.strftime("%H:%M:%S")
        # current_date = time.strftime("%d/%m/%y")

        # # Margins
        # ml = int(margins.get("left", 50))
        # mb = int(margins.get("bottom", 50))
        # mr = int(margins.get("right", 50))
        # spacing = int(margins.get("spacing", 10))

        # # Base image (RGB) and a fully transparent overlay (RGBA)
        # base_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        # base = Image.fromarray(base_rgb)  # mode RGB
        # w, h = base.size
        # overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        # draw = ImageDraw.Draw(overlay)

        # # Measure text
        # def bbox(txt: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int, int, int]:
        #     return draw.textbbox((0, 0), txt, font=font)

        # tb = bbox(current_time, self.time_font)
        # db = bbox(current_date, self.date_font)
        # t_w, t_h = tb[2] - tb[0], tb[3] - tb[1]
        # d_w, d_h = db[2] - db[0], db[3] - db[1]

        # # Left block (time above date, aligned to date width)
        # baseline_y = h - mb
        # x_date = ml
        # y_date = baseline_y - d_h
        # x_time = x_date + (d_w - t_w) // 2
        # y_time = y_date - spacing - t_h

        # # Right block (temperature on top, condition below)
        # right_positions = []
        # temp_text = None
        # cond_text = None
        # if weather:
        #     temp_text = f"{weather.get('temp', '--')}°{weather.get('unit', '')}"
        #     cond_text = (weather.get('description') or '').strip() or None

        # if temp_text:
        #     temp_bb = bbox(temp_text, self.date_font)
        #     temp_w = temp_bb[2] - temp_bb[0]
        #     temp_h = temp_bb[3] - temp_bb[1]

        #     cond_w = cond_h = 0
        #     if cond_text:
        #         cond_bb = bbox(cond_text, self.date_font)
        #         cond_w = cond_bb[2] - cond_bb[0]
        #         cond_h = cond_bb[3] - cond_bb[1]

        #     block_w = max(temp_w, cond_w)
        #     block_h = temp_h + (6 + cond_h if cond_text else 0)

        #     x_right = w - mr
        #     y_block_top = baseline_y - block_h
        #     x_block_left = x_right - block_w

        #     # Center each line within the block
        #     x_temp = x_block_left + (block_w - temp_w) // 2
        #     y_temp = y_block_top
        #     right_positions.append((temp_text, x_temp, y_temp))

        #     if cond_text:
        #         x_cond = x_block_left + (block_w - cond_w) // 2
        #         y_cond = y_temp + temp_h + 6
        #         right_positions.append((cond_text, x_cond, y_cond))

        # # Draw text ON THE TRANSPARENT OVERLAY ONLY
        # rgba_fill = (font_color[0], font_color[1], font_color[2], 255)
        # draw.text((x_time, y_time), current_time, font=self.time_font, fill=rgba_fill)
        # draw.text((x_date, y_date), current_date, font=self.date_font, fill=rgba_fill)
        # for ln, x, y in right_positions:
        #     draw.text((x, y), ln, font=self.date_font, fill=rgba_fill)

        # # Composite overlay over base; nothing but glyph pixels are applied
        # out_rgba = Image.alpha_composite(base.convert("RGBA"), overlay)
        # return cv2.cvtColor(np.array(out_rgba.convert("RGB")), cv2.COLOR_RGB2BGR)

    # overlay.py  --- add this new method inside OverlayRenderer
    def render_overlay_rgba(
        self,
        width: int,
        height: int,
        margins: Dict[str, int],
        weather: Dict,
        font_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Image.Image:
        # Transparent canvas
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Clock strings
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%d/%m/%y")

        # Margins
        ml = int(margins.get("left", 50))
        mb = int(margins.get("bottom", 50))
        mr = int(margins.get("right", 50))
        spacing = int(margins.get("spacing", 10))

        # Measure
        tb = draw.textbbox((0, 0), current_time, font=self.time_font)
        db = draw.textbbox((0, 0), current_date, font=self.date_font)
        t_w, t_h = tb[2] - tb[0], tb[3] - tb[1]
        d_w, d_h = db[2] - db[0], db[3] - db[1]

        # Left block
        baseline_y = height - mb
        x_date = ml
        y_date = baseline_y - d_h
        x_time = x_date + (d_w - t_w) // 2
        y_time = y_date - spacing - t_h

        # Right block
        right_positions = []
        temp_text = None
        cond_text = None
        if weather:
            temp_text = f"{weather.get('temp', '--')}°{weather.get('unit', '')}"
            cond_text = (weather.get('description') or '').strip() or None

        if temp_text:
            temp_bb = draw.textbbox((0, 0), temp_text, font=self.date_font)
            temp_w = temp_bb[2] - temp_bb[0]
            temp_h = temp_bb[3] - temp_bb[1]

            cond_w = cond_h = 0
            if cond_text:
                cond_bb = draw.textbbox((0, 0), cond_text, font=self.date_font)
                cond_w = cond_bb[2] - cond_bb[0]
                cond_h = cond_bb[3] - cond_bb[1]

            block_w = max(temp_w, cond_w)
            block_h = temp_h + (6 + cond_h if cond_text else 0)

            x_right = width - mr
            y_block_top = baseline_y - block_h
            x_block_left = x_right - block_w

            x_temp = x_block_left + (block_w - temp_w) // 2
            y_temp = y_block_top
            right_positions.append((temp_text, x_temp, y_temp))
            if cond_text:
                x_cond = x_block_left + (block_w - cond_w) // 2
                y_cond = y_temp + temp_h + 6
                right_positions.append((cond_text, x_cond, y_cond))

        rgba_fill = (font_color[0], font_color[1], font_color[2], 255)
        draw.text((x_time, y_time), current_time, font=self.time_font, fill=rgba_fill)
        draw.text((x_date, y_date), current_date, font=self.date_font, fill=rgba_fill)
        for ln, x, y in right_positions:
            draw.text((x, y), ln, font=self.date_font, fill=rgba_fill)

        return overlay


    def render_stats(self, frame_bgr: np.ndarray, text: str, color_name: str) -> np.ndarray:
        color = self._color_from_name(color_name)
        pil = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
        draw = ImageDraw.Draw(pil)
        draw.text((10, 10), text, font=self.stats_font, fill=(*color, 255))
        return cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
