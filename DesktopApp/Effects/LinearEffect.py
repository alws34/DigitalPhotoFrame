import cv2
import numpy as np
import time

def LinearEffect(img1, img2, duration=5.0, num_blinds=16, direction='vertical'):
    """
    Create a generator for the blinds transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.
    num_blinds (int): The number of blinds (vertical or horizontal strips).
    direction (str): 'vertical' or 'horizontal' blinds.

    Yields:
    numpy.ndarray: The frame with the blinds effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()

    if direction == 'vertical':
        blind_size = cols // num_blinds
        max_dimension = rows  # Blinds open vertically (height increases)
    else:
        blind_size = rows // num_blinds
        max_dimension = cols  # Blinds open horizontally (width increases)

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        # Compute current opening size of the blinds
        current_size = int(progress * max_dimension)

        # Create a mask
        mask = np.zeros((rows, cols), dtype=np.uint8)

        for i in range(num_blinds):
            if direction == 'vertical':
                x_start = i * blind_size
                x_end = x_start + blind_size if i != num_blinds - 1 else cols

                # Fill the mask for this blind
                y_end = current_size
                mask[0:y_end, x_start:x_end] = 1
                continue
            # horizontal blinds
            y_start = i * blind_size
            y_end = y_start + blind_size if i != num_blinds - 1 else rows 

            # Fill the mask for this blind
            x_end = current_size
            mask[y_start:y_end, 0:x_end] = 1

        # Apply the mask to blend the two images
        mask_3ch = np.dstack([mask]*3)
        frame = np.where(mask_3ch == 1, img2, img1)

        # Yield the frame
        yield frame

        # Stop when the transition is complete
        if elapsed_time >= duration:
            break
