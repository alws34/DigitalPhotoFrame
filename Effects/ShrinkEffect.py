import cv2
import numpy as np
import time
import random

def ShrinkEffect(img1, img2, duration=5.0):
    """
    Create a generator for the shrink transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.

    Yields:
    numpy.ndarray: The frame with the shrink effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()

    # Randomly select a direction
    directions = ['top', 'bottom', 'left', 'right']
    direction = random.choice(directions)
    print(f"Shrink direction: {direction}")

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        # Calculate the current size
        if direction in ['left', 'right']:
            current_width = int(cols * (1 - progress))
            current_width = max(1, current_width)
            current_height = rows
        else:
            current_height = int(rows * (1 - progress))
            current_height = max(1, current_height)
            current_width = cols

        # Resize img1 to the current size
        if direction == 'left':
            img1_resized = cv2.resize(img1, (current_width, current_height), interpolation=cv2.INTER_AREA)
            # Create a frame starting with img2
            frame = img2.copy()
            # Overlay the resized img1 on the left side
            frame[:, :current_width, :] = img1_resized
        elif direction == 'right':
            img1_resized = cv2.resize(img1, (current_width, current_height), interpolation=cv2.INTER_AREA)
            frame = img2.copy()
            # Overlay the resized img1 on the right side
            frame[:, cols - current_width:, :] = img1_resized
        elif direction == 'top':
            img1_resized = cv2.resize(img1, (current_width, current_height), interpolation=cv2.INTER_AREA)
            frame = img2.copy()
            # Overlay the resized img1 at the top
            frame[:current_height, :, :] = img1_resized
        elif direction == 'bottom':
            img1_resized = cv2.resize(img1, (current_width, current_height), interpolation=cv2.INTER_AREA)
            frame = img2.copy()
            # Overlay the resized img1 at the bottom
            frame[rows - current_height:, :, :] = img1_resized

        # Yield the frame
        yield frame

        # Break the loop when the transition is complete
        if elapsed_time >= duration:
            break
