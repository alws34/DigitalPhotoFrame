import cv2
import numpy as np
import time
import random

def StretchEffect(img1, img2, duration=5.0):
    """
    Create a generator for the stretch transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.

    Yields:
    numpy.ndarray: The frame with the stretch effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()

    # Randomly select a direction
    directions = ['top', 'bottom', 'left', 'right']
    direction = random.choice(directions)
    print(f"Stretch direction: {direction}")

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        # Calculate the current size
        if direction in ['left', 'right']:
            current_width = int(cols * progress)
            current_width = max(1, current_width)
            current_height = rows
        else:
            current_height = int(rows * progress)
            current_height = max(1, current_height)
            current_width = cols

        # Resize img1 to the current size
        img1_resized = cv2.resize(img1, (current_width, current_height), interpolation=cv2.INTER_LINEAR)

        # Create a frame starting with img2
        frame = img2.copy()

        # Overlay the resized img1 based on direction
        if direction == 'left':
            frame[:, :current_width, :] = img1_resized
        elif direction == 'right':
            frame[:, cols - current_width:, :] = img1_resized
        elif direction == 'top':
            frame[:current_height, :, :] = img1_resized
        elif direction == 'bottom':
            frame[rows - current_height:, :, :] = img1_resized

        # Yield the frame
        yield frame

        # Break the loop when the transition is complete
        if elapsed_time >= duration:
            break
