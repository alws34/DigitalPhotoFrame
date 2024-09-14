import cv2
import numpy as np
import time

def BlindsEffect(img1, img2, duration=5.0, num_strips=16):
    """
    Create a generator for the blinds transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.
    num_strips (int): The number of horizontal strips (lines).

    Yields:
    numpy.ndarray: The frame with the blinds effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()
    strip_height = rows // num_strips

    # Initialize the mask at t=0 with alternating horizontal lines
    mask = np.zeros((rows, cols), dtype=np.uint8)
    strips_to_fill = []

    for i in range(num_strips):
        y_start = i * strip_height
        y_end = y_start + strip_height

        if i % 2 == 0:
            # Strips to show img2 from the start
            mask[y_start:y_end, :] = 1
        else:
            # Strips to fill later; store their coordinates
            strips_to_fill.append((y_start, y_end))

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        # Create a copy of the mask to update
        mask_current = mask.copy()

        for y_start, y_end in strips_to_fill:
            # Compute the current height of the fill for vertical growth
            current_height = int(strip_height * progress)

            # Update the mask to fill from top to bottom within the strip
            y_fill_end = y_start + current_height
            y_fill_end = min(y_fill_end, y_end)  # Ensure we don't exceed the strip

            mask_current[y_start:y_fill_end, :] = 1

        # Apply the mask to blend the two images
        mask_3ch = np.dstack([mask_current]*3)
        frame = np.where(mask_3ch == 1, img2, img1)

        # Yield the frame
        yield frame

        # Stop when the transition is complete
        if elapsed_time >= duration:
            break
