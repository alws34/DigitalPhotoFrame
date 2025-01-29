import cv2
import numpy as np
import time

def dissolve_pixel(img1, img2, mask, block_size):
    """
    Generate the dissolve effect frame based on the current mask.

    Args:
    img1 (numpy.ndarray): The first image (background).
    img2 (numpy.ndarray): The second image (foreground).
    mask (numpy.ndarray): The mask indicating which pixels should be dissolved.
    block_size (int): The size of the blocks used for the dissolve effect.

    Returns:
    numpy.ndarray: The frame with the dissolve effect applied.
    """
    # Ensure mask dimensions match image dimensions
    mask = np.resize(mask, img1.shape[:2])
    dissolve_frame = np.where(mask[:, :, None], img2, img1)
    return dissolve_frame

def PixelDissolveEffect(img1, img2, duration=30.0, block_size=10):
    """
    Create a generator for the pixel dissolve effect with larger pixel blocks.

    Args:
    img1 (numpy.ndarray): The first image (background).
    img2 (numpy.ndarray): The second image (foreground).
    duration (float): The total duration of the dissolve effect in seconds.
    block_size (int): The size of the blocks used for the dissolve effect.

    Yields:
    numpy.ndarray: The dissolve effect frame.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()
    mask = np.zeros((rows, cols), dtype=bool)

    while True:
        elapsed_time = time.time() - start_time
        alpha = min(elapsed_time / duration, 1.0)
        
        # Create or update the dissolve mask based on alpha
        if alpha > 0:
            block_mask = np.random.rand(rows // block_size, cols // block_size) < alpha
            block_mask = np.kron(block_mask, np.ones((block_size, block_size)))
            block_mask = block_mask[:rows, :cols]
            mask = np.logical_or(mask, block_mask)
        
        # Generate the dissolve effect frame with the current mask
        frame = dissolve_pixel(img1, img2, mask, block_size)
        
        # Yield the frame
        yield frame
        
        # Stop when the transition is complete
        if elapsed_time >= duration:
            break