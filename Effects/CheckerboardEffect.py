import cv2
import numpy as np
import time

def CheckerboardEffect(img1, img2, duration=5.0, grid_size=8):
    """
    Create a generator for the checkerboard transition effect.

    Args:
    img1 (numpy.ndarray): The first image (source image).
    img2 (numpy.ndarray): The second image (destination image).
    duration (float): The total duration of the transition in seconds.
    grid_size (int): The number of squares along one dimension (e.g., 8 for an 8x8 grid).

    Yields:
    numpy.ndarray: The frame with the checkerboard effect applied.
    """
    rows, cols, _ = img1.shape
    start_time = time.time()
    cell_width = cols // grid_size
    cell_height = rows // grid_size

    # Initialize the mask at t=0 with the checkerboard pattern
    mask = np.zeros((rows, cols), dtype=np.uint8)
    cells_to_fill = []

    for i in range(grid_size):
        for j in range(grid_size):
            x_start = j * cell_width
            y_start = i * cell_height
            x_end = x_start + cell_width
            y_end = y_start + cell_height

            if (i + j) % 2 == 0:
                # Cells to show img2 from the start
                mask[y_start:y_end, x_start:x_end] = 1
            else:
                # Cells to fill later; store their coordinates
                cells_to_fill.append((y_start, y_end, x_start, x_end))

    while True:
        elapsed_time = time.time() - start_time
        progress = min(elapsed_time / duration, 1.0)

        # Create a copy of the mask to update
        mask_current = mask.copy()

        for y_start, y_end, x_start, x_end in cells_to_fill:
            # Compute the current height of the rectangle for vertical growth
            current_height = int((y_end - y_start) * progress)

            # Update the mask to fill from top to bottom
            mask_current[y_start:y_start+current_height, x_start:x_end] = 1

        # Apply the mask to blend the two images
        mask_3ch = np.dstack([mask_current]*3)
        frame = np.where(mask_3ch == 1, img2, img1)

        # Yield the frame
        yield frame

        # Stop when the transition is complete
        if elapsed_time >= duration:
            break
