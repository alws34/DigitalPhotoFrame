import cv2
import numpy as np
import random as rand

class Image_Utils():
    def __init__(self, settings: dict):
        self.settings = settings

    def _get_effect_val(self, key, default):
        """Helper: Try 'effects' dict first, then root, then default."""
        eff = self.settings.get('effects', {})
        # 1. Try inside 'effects'
        if key in eff:
            return eff[key]
        # 2. Try root (legacy)
        if key in self.settings:
            return self.settings[key]
        # 3. Default
        return default

    def shuffle_images(self, images):
        images_copy = list(images)
        rand.shuffle(images_copy)
        return images_copy

    def create_translucent_background(self, image, target_width, target_height):
        # 1. Resize/Crop to fill screen
        h, w = image.shape[:2]
        aspect_src = w / h
        aspect_target = target_width / target_height

        if aspect_src > aspect_target:
            new_w = int(h * aspect_target)
            offset = (w - new_w) // 2
            crop = image[:, offset:offset + new_w]
        else:
            new_h = int(w / aspect_target)
            offset = (h - new_h) // 2
            crop = image[offset:offset + new_h, :]

        background = cv2.resize(crop, (target_width, target_height))

        # 2. Blur Background
        bg_blur = int(self._get_effect_val('background_blur_radius', 61))
        if bg_blur % 2 == 0: bg_blur += 1
        background = cv2.GaussianBlur(background, (bg_blur, bg_blur), 0)

        # 3. Dim Background
        bg_opacity = float(self._get_effect_val('background_opacity', 0.4)) 
        
        if bg_opacity < 1.0:
            background = (background.astype(np.float32) * bg_opacity).astype(np.uint8)

        return background

    def _apply_shadow(self, background, x, y, w, h):
        """
        Applies a centered shadow (outer glow) around the image.
        """
        shadow_opacity = float(self._get_effect_val('shadow_opacity', 0.8))
        shadow_blur = int(self._get_effect_val('shadow_blur_radius', 61))
        
        if shadow_opacity <= 0:
            return background
            
        if shadow_blur % 2 == 0: shadow_blur += 1
        
        bg_h, bg_w = background.shape[:2]

        # 1. Create a Shadow Mask (Black canvas)
        shadow_mask = np.zeros((bg_h, bg_w), dtype=np.uint8)

        # 2. Draw the white box exactly where the image sits
        cv2.rectangle(shadow_mask, (x, y), (x + w, y + h), (255), thickness=-1)

        # 3. Blur the Mask
        shadow_mask = cv2.GaussianBlur(shadow_mask, (shadow_blur, shadow_blur), 0)

        # 4. Blend it into the background
        norm_mask = shadow_mask.astype(np.float32) / 255.0
        
        # Burn/Darken logic
        burn_factor = 1.0 - (norm_mask * shadow_opacity)
        burn_factor = np.dstack([burn_factor] * 3)

        shadowed_bg = (background.astype(np.float32) * burn_factor).astype(np.uint8)
        
        return shadowed_bg

    def resize_image_with_background(self, image, target_width, target_height):
        if image is None:
            return np.zeros((target_height, target_width, 3), dtype=np.uint8)
        
        original_height, original_width = image.shape[:2]
        aspect_ratio = original_width / original_height

        # 1. Resize Main Image
        if target_width / target_height > aspect_ratio:
            new_height = target_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = target_width
            new_height = int(new_width / aspect_ratio)

        resized_image = cv2.resize(image, (new_width, new_height))

        # Check enabled setting
        allow_translucent = self._get_effect_val('allow_translucent_background', True)

        # 2. Create Background
        if allow_translucent:
            background = self.create_translucent_background(image, target_width, target_height)
        else:
            background = np.zeros((target_height, target_width, 3), dtype=np.uint8)

        # 3. Calculate Centering
        y_offset = (target_height - new_height) // 2
        x_offset = (target_width - new_width) // 2

        # 4. Apply Shadow (BEFORE pasting the image)
        if allow_translucent:
            background = self._apply_shadow(background, x_offset, y_offset, new_width, new_height)

        # 5. Paste Main Image
        y1, y2 = y_offset, y_offset + new_height
        x1, x2 = x_offset, x_offset + new_width
        
        # Safety Clipping
        y1, x1 = max(0, y1), max(0, x1)
        y2, x2 = min(target_height, y2), min(target_width, x2)
        
        img_h = y2 - y1
        img_w = x2 - x1
        
        if img_h > 0 and img_w > 0:
            if img_h != resized_image.shape[0] or img_w != resized_image.shape[1]:
                 resized_image = cv2.resize(image, (img_w, img_h))
            background[y1:y2, x1:x2] = resized_image

        return background