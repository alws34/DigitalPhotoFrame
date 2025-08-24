import cv2
import time

def AlphaDissolveEffect(img1, img2, duration=30.0):
    start_time = time.time()
    while True:
        # Calculate the elapsed time
        elapsed_time = time.time() - start_time
        
        # Calculate the alpha value based on the elapsed time and total duration
        alpha = min(elapsed_time / duration, 1.0)
        
        # Blend the two images using the calculated alpha
        blended_frame = cv2.addWeighted(img1, 1 - alpha, img2, alpha, 0)
        
        # Display the blended frame
        yield blended_frame
        #cv2.imshow('Image Transition', blended_frame)
        
        # Break the loop when the transition is complete (alpha reaches 1.0)
        if elapsed_time >= duration:
            break
        
        # Wait for a short time (1 ms) between frames to allow for smooth display
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
