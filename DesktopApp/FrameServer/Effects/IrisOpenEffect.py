import cv2
import numpy as np
import time

def IrisOpenEffect(img1, img2, duration=5.0):
    """
    Create a generator for the iris open transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.

    Yields:
    numpy.ndarray: The frame with the iris open effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()

    # Center coordinates
    center_x = cols // 2
    center_y = rows // 2

    # Maximum radius is the distance from the center to a corner
    max_radius = int(np.sqrt(center_x ** 2 + center_y ** 2))

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        # Calculate the current radius
        radius = int(progress * max_radius)

        # Create a mask with a filled circle
        mask = np.zeros((rows, cols), dtype=np.uint8)
        cv2.circle(mask, (center_x, center_y), radius, 255, -1)

        # Create a 3-channel mask
        mask_3ch = cv2.merge([mask, mask, mask])

        # Apply the mask to blend the two images
        frame = np.where(mask_3ch == 255, img2, img1)

        # Yield the frame
        yield frame

        # Break the loop when the transition is complete
        if elapsed_time >= duration:
            break
