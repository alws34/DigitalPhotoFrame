import cv2
import numpy as np
import time
import random

def ScrollEffect(img1, img2, duration=5.0):
    """
    Create a generator for the scroll transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.

    Yields:
    numpy.ndarray: The frame with the scroll effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()

    # Randomly select a direction
    directions = ['left', 'right', 'up', 'down']
    direction = random.choice(directions)
    print(f"Scroll direction: {direction}")

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        frame = np.zeros_like(img1)

        if direction == 'left':
            # Scroll from right to left
            offset = int(progress * cols)
            if offset > cols:
                offset = cols
            # Left part from img2
            frame[:, :cols - offset, :] = img2[:, offset:, :]
            # Right part from img1
            frame[:, cols - offset:, :] = img1[:, :offset, :]
        elif direction == 'right':
            # Scroll from left to right
            offset = int(progress * cols)
            if offset > cols:
                offset = cols
            # Left part from img1
            frame[:, :offset, :] = img1[:, cols - offset:, :]
            # Right part from img2
            frame[:, offset:, :] = img2[:, :cols - offset, :]
        elif direction == 'up':
            # Scroll from bottom to top
            offset = int(progress * rows)
            if offset > rows:
                offset = rows
            # Top part from img2
            frame[:rows - offset, :, :] = img2[offset:, :, :]
            # Bottom part from img1
            frame[rows - offset:, :, :] = img1[:offset, :, :]
        elif direction == 'down':
            # Scroll from top to bottom
            offset = int(progress * rows)
            if offset > rows:
                offset = rows
            # Top part from img1
            frame[:offset, :, :] = img1[rows - offset:, :, :]
            # Bottom part from img2
            frame[offset:, :, :] = img2[:rows - offset, :, :]

        # Yield the frame
        yield frame

        # Break the loop when the transition is complete
        if elapsed_time >= duration:
            break
