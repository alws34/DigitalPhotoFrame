import time
import cv2
import numpy as np

def PlainEffect(img1, img2, duration=5.0):
    """
    A no-op transition that simply renders the source image.

    Args:
    img1 (numpy.ndarray): The source image.
    img2 (numpy.ndarray): The destination image (not used).
    duration (float): The total duration to display the image in seconds.

    Yields:
    numpy.ndarray: The frame displaying the source image.
    """
    start_time = time.time()
    while True:
        elapsed_time = time.time() - start_time
        # Just yield the source image
        yield img1.copy()

        # Break the loop when the duration is exceeded
        if elapsed_time >= duration:
            break
