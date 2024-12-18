from cv2 import resize, GaussianBlur, addWeighted
from numpy import zeros, uint8

class Image_Utils():
    def __init__(self):
        pass

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
        resized_image = resize(image, (new_width, new_height))

        # Create a black background with target dimensions
        final_image = zeros(
            (target_height, target_width, 3), dtype=uint8)

        # Center the resized image on the background
        y_offset = (target_height - new_height) // 2
        x_offset = (target_width - new_width) // 2
        final_image[y_offset:y_offset + new_height,
                    x_offset:x_offset + new_width] = resized_image

        return final_image

    def create_translucent_background(self, image, target_width, target_height, alpha=1.0):
        # Resize the image to fill the screen, ignoring the aspect ratio
        background = resize(image, (target_width, target_height))

        # Apply a blur to the background image
        blurred_background = GaussianBlur(background, (21, 21), 0)

        # Adjust the opacity (alpha) of the blurred background
        overlay = blurred_background.copy()
        addWeighted(overlay, alpha, background, 1 - alpha, 0, background)

        return background

    def resize_image_with_background(self, image, target_width, target_height):
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

        # Resize the main image to maintain aspect ratio
        resized_image = resize(image, (new_width, new_height))

        # Create a fit-to-screen translucent background of the image
        background = self.create_translucent_background(
            image, target_width, target_height)

        # Overlay the resized image onto the background
        y_offset = (target_height - new_height) // 2
        x_offset = (target_width - new_width) // 2
        background[y_offset:y_offset + new_height,
                x_offset:x_offset + new_width] = resized_image

        return background