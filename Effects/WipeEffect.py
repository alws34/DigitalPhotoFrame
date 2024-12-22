import cv2
import numpy as np
import time
import random

def WipeEffect(img1, img2, duration=5.0):
    """
    Create a generator for the wipe transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.

    Yields:
    numpy.ndarray: The frame with the wipe effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()

    # Randomly select a direction
    directions = ['left', 'right', 'up', 'down']
    direction = random.choice(directions)
    #print(f"Wipe direction: {direction}")

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        frame = img1.copy()

        if direction == 'left':
            # Wipe from left to right
            wipe_width = int(progress * cols)
            frame[:, :wipe_width, :] = img2[:, :wipe_width, :]
        elif direction == 'right':
            # Wipe from right to left
            wipe_width = int(progress * cols)
            frame[:, cols - wipe_width:, :] = img2[:, cols - wipe_width:, :]
        elif direction == 'up':
            # Wipe from top to bottom
            wipe_height = int(progress * rows)
            frame[:wipe_height, :, :] = img2[:wipe_height, :, :]
        elif direction == 'down':
            # Wipe from bottom to top
            wipe_height = int(progress * rows)
            frame[rows - wipe_height:, :, :] = img2[rows - wipe_height:, :, :]

        # Yield the frame
        yield frame

        # Break the loop when the transition is complete
        if elapsed_time >= duration:
            break
