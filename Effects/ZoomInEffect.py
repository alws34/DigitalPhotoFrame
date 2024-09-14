import cv2
import numpy as np
import time

def ZoomInEffect(img1, img2, duration=5.0):
    """
    Create a generator for the zoom-in transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.

    Yields:
    numpy.ndarray: The frame with the zoom-in effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()

    # Define the starting and ending scales
    min_scale = 1.0  # Start at 100% of the image size
    max_scale = 0.0  # End at 0% of the image size (a point)

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        # Calculate the current scale
        scale = min_scale - (min_scale - max_scale) * progress

        # Calculate the current rectangle size
        current_width = int(cols * scale)
        current_height = int(rows * scale)

        # Ensure the dimensions are at least 1 pixel
        current_width = max(1, current_width)
        current_height = max(1, current_height)

        # Calculate the top-left corner coordinates to center the rectangle
        x_start = (cols - current_width) // 2
        y_start = (rows - current_height) // 2

        # Resize img2 to the current rectangle size
        img2_resized = cv2.resize(img2, (current_width, current_height), interpolation=cv2.INTER_LINEAR)

        # Create a frame by copying img1
        frame = img1.copy()

        # Overlay the resized img2 onto the frame
        frame[y_start:y_start+current_height, x_start:x_start+current_width] = img2_resized

        # Yield the frame
        yield frame

        # Break the loop when the transition is complete
        if elapsed_time >= duration:
            break
