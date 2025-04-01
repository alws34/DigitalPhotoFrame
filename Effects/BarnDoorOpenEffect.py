import cv2
import numpy as np
import time

def BarnDoorOpenEffect(img1, img2, duration=5.0):
    """
    Create a generator for the barn door open transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.

    Yields:
    numpy.ndarray: The frame with the barn door open effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()

    # The maximum shift is half of the image width
    max_shift = cols // 2

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        # Calculate the current shift
        shift = int(progress * max_shift)

        # Create a frame starting with img2 (destination image)
        frame = img2.copy()

        # Left half of img1 slides left
        left_width = cols // 2
        left_half = img1[:, :left_width, :]
        # Calculate the visible width after shifting
        left_visible_width = max(0, left_width - shift)
        if left_visible_width > 0:
            frame[:, :left_visible_width, :] = left_half[:, shift:, :]

        # Right half of img1 slides right
        right_width = cols - left_width
        right_half = img1[:, left_width:, :]
        # Calculate the visible width after shifting
        right_visible_width = max(0, right_width - shift)
        if right_visible_width > 0:
            frame[:, cols - right_visible_width:, :] = right_half[:, :right_visible_width, :]

        # Yield the frame
        yield frame

        # Break the loop when the transition is complete
        if elapsed_time >= duration:
            break
