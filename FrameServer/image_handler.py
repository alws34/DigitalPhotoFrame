import cv2
import numpy as np
import random as rand
class Image_Utils():
    def __init__(self, settings: dict):
        self.settings = settings

    def shuffle_images(self, images):
        images_copy = list(images)
        rand.shuffle(images_copy)
        return images_copy


    def resize_image(self, image, target_width, target_height):
        # Get the original dimensions of the image
        original_height, original_width = image.shape[:2]

        # Calculate the aspect ratio of the image
        aspect_ratio = original_width / original_height

        # Calculate new dimensions to maintain the aspect ratio
        if target_width / target_height > aspect_ratio:
            new_height = target_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = target_width
            new_height = int(new_width / aspect_ratio)

        # Resize the image
        resized_image = cv2.resize(image, (new_width, new_height))

        # Create a black background with target dimensions
        final_image = np.zeros(
            (target_height, target_width, 3), dtype=np.uint8)

        # Center the resized image on the background
        y_offset = (target_height - new_height) // 2
        x_offset = (target_width - new_width) // 2
        final_image[y_offset:y_offset + new_height,
                    x_offset:x_offset + new_width] = resized_image

        return final_image

    def create_translucent_background(self, image, target_width, target_height, alpha=1.0):
        # Resize the image to fill the screen, ignoring the aspect ratio
        background = cv2.resize(image, (target_width, target_height))

        # Apply a blur to the background image
        blurred_background = cv2.GaussianBlur(background, (21, 21), 0)

        # Adjust the opacity (alpha) of the blurred background
        overlay = blurred_background.copy()
        cv2.addWeighted(overlay, alpha, background, 1 - alpha, 0, background)

        return background

    def resize_image_with_background(self, image, target_width, target_height):
        # Get the original dimensions of the image
        if image is None:
            return
        
        original_height, original_width = image.shape[:2]

        # Calculate the aspect ratio of the image
        aspect_ratio = original_width / original_height

        # Calculate new dimensions to maintain the aspect ratio
        if target_width / target_height > aspect_ratio:
            new_height = target_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = target_width
            new_height = int(new_width / aspect_ratio)

        # Resize the main image to maintain aspect ratio
        resized_image = cv2.resize(image, (new_width, new_height))

        background = np.zeros((target_height, target_width, 3), dtype=np.uint8)
       
        if self.settings.get('allow_translucent_background', True):
            background = self.create_translucent_background(image, target_width, target_height)

        # Overlay the resized image onto the background
        y_offset = (target_height - new_height) // 2
        x_offset = (target_width - new_width) // 2
        background[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized_image

        return background
