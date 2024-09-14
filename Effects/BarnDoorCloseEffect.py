import cv2
import numpy as np
import time

def BarnDoorCloseEffect(img1, img2, duration=5.0):
    """
    Create a generator for the barn door close transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.

    Yields:
    numpy.ndarray: The frame with the barn door close effect applied.
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

        # Start with the destination image
        frame = img2.copy()

        # Left half of img1 slides in from the left
        left_width = cols // 2
        left_half = img1[:, :left_width, :]
        # Calculate how much of the left half has slid in
        left_visible_width = min(shift, left_width)
        if left_visible_width > 0:
            frame[:, :left_visible_width, :] = left_half[:, left_width - left_visible_width:, :]

        # Right half of img1 slides in from the right
        right_width = cols - left_width
        right_half = img1[:, left_width:, :]
        # Calculate how much of the right half has slid in
        right_visible_width = min(shift, right_width)
        if right_visible_width > 0:
            frame[:, cols - right_visible_width:, :] = right_half[:, :right_visible_width, :]

        # Yield the frame
        yield frame

        # Break the loop when the transition is complete
        if elapsed_time >= duration:
            break
