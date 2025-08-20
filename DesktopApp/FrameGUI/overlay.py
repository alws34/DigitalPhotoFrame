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
    ) -> None:
        self.desired_w, self.desired_h = desired_size
        self.time_font = ImageFont.truetype(font_path, time_font_size)
        self.date_font = ImageFont.truetype(font_path, date_font_size)
        self.stats_font = ImageFont.truetype(font_path, stats_font_size)

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
    def resize_and_letterbox(src_bgr: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        h, w = src_bgr.shape[:2]
        aspect_src = w / float(h)
        aspect_dst = target_w / float(target_h)

        if aspect_src > aspect_dst:
            new_w = target_w
            new_h = int(round(target_w / aspect_src))
        else:
            new_h = target_h
            new_w = int(round(target_h * aspect_src))

        resized = cv2.resize(src_bgr, (new_w, new_h))
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        x = (target_w - new_w) // 2
        y = (target_h - new_h) // 2
        canvas[y:y + new_h, x:x + new_w] = resized
        return canvas

    def render_datetime_and_weather(
        self,
        frame_bgr: np.ndarray,
        margins: Dict[str, int],
        weather: Dict,
        font_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> np.ndarray:
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%d/%m/%y")

        ml = margins.get("left", 50)
        mb = margins.get("bottom", 50)
        mr = margins.get("right", 50)
        spacing = margins.get("spacing", 10)

        pil_img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        time_bbox = draw.textbbox((0, 0), current_time, font=self.time_font)
        date_bbox = draw.textbbox((0, 0), current_date, font=self.date_font)
        time_w, time_h = time_bbox[2] - time_bbox[0], time_bbox[3] - time_bbox[1]
        date_w, date_h = date_bbox[2] - date_bbox[0], date_bbox[3] - date_bbox[1]

        baseline_y = self.desired_h - mb
        x_date = ml
        y_date_top = baseline_y - date_h
        x_time = x_date + (date_w - time_w) // 2
        y_time_top = y_date_top - spacing - time_h

        draw.text((x_time, y_time_top), current_time, font=self.time_font, fill=font_color)
        draw.text((x_date, y_date_top), current_date, font=self.date_font, fill=font_color)

        if weather:
            temp_text = f"{weather.get('temp', '--')}°{weather.get('unit', '')}"
            desc_text = str(weather.get("description", "")).strip()
            line1 = f"{temp_text}  •  {desc_text}" if desc_text else temp_text

            extras = []
            wind = weather.get("wind_speed") or weather.get("wind_kmh") or weather.get("wind_mph")
            if wind is not None:
                wu = (weather.get("wind_unit") or "").lower()
                wind_str = f"Wind: {wind}"
                if "wind_kmh" in weather or wu == "kmh":
                    extras.append(f"{wind_str} km/h")
                elif "wind_mph" in weather or wu == "mph":
                    extras.append(f"{wind_str} mph")
                elif wu == "ms":
                    extras.append(f"{wind_str} m/s")
                elif wu == "kn":
                    extras.append(f"{wind_str} kn")
                else:
                    extras.append(wind_str)

            humidity = weather.get("humidity")
            if humidity is not None:
                extras.append(f"Humidity {humidity}%")

            line2 = " • ".join(extras) if extras else None
            lines = [line1] + ([line2] if line2 else [])

            line_spacing = 6
            line_bboxes = [draw.textbbox((0, 0), ln, font=self.date_font) for ln in lines]
            line_heights = [bb[3] - bb[1] for bb in line_bboxes]
            block_height = sum(line_heights) + (len(lines) - 1) * line_spacing

            x_right = self.desired_w - mr
            y_top = baseline_y - block_height

            y = y_top
            for ln in lines:
                bb = draw.textbbox((0, 0), ln, font=self.date_font)
                w = bb[2] - bb[0]
                x = x_right - w
                draw.text((x, y), ln, font=self.date_font, fill=font_color)
                y += (bb[3] - bb[1]) + line_spacing

        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def render_stats(self, frame_bgr: np.ndarray, text: str, color_name: str) -> np.ndarray:
        color = self._color_from_name(color_name)
        pil_image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)
        draw.text((10, 10), text, font=self.stats_font, fill=color)
        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
