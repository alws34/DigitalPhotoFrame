import threading
import time
import tkinter as tk
from PIL import Image, ImageTk
import cv2
import random as rand
import os
from enum import Enum
import numpy as np

# Importing Effects
from Effects.CheckerboardEffect import CheckerboardEffect
from Effects.AlphaDissolveEffect import AlphaDissolveEffect
from Effects.PixelDissolveEffect import PixelDissolveEffect
from Effects.BlindsEffect import BlindsEffect
from Effects.ScrollEffect import ScrollEffect
from Effects.WipeEffect import WipeEffect
from Effects.ZoomOutEffect import ZoomOutEffect
from Effects.ZoomInEffect import ZoomInEffect
from Effects.IrisOpenEffect import IrisOpenEffect
from Effects.IrisCloseEffect import IrisCloseEffect
from Effects.BarnDoorOpenEffect import BarnDoorOpenEffect
from Effects.BarnDoorCloseEffect import BarnDoorCloseEffect
from Effects.ShrinkEffect import ShrinkEffect
from Effects.StretchEffect import StretchEffect
from Effects.PlainEffect import PlainEffect

class AnimationStatus(Enum):
    ANIMATION_FINISHED = 1
    ANIMATION_ERROR = 2

class PhotoFrame:
    def __init__(self, wait_time=30):
        self.effects = {}
        self.images = self.get_images_from_directory()
        self.shuffled_images = list(self.images)
        self.shuffled_effects = list(self.effects.keys())
        self.current_image_idx = -1
        self.current_effect_idx = -1
        self.root = None
        self.frame = None
        self.label = None
        self.current_image = None
        self.screen_width = None
        self.screen_height = None
        self.wait_time = wait_time  # Wait time between transitions in seconds

        self.effects = {
            0: AlphaDissolveEffect,
            1: PixelDissolveEffect,
            2: CheckerboardEffect,
            3: BlindsEffect,
            4: ScrollEffect,
            5: WipeEffect,
            6: ZoomOutEffect,
            7: ZoomInEffect,
            8: IrisOpenEffect,
            9: IrisCloseEffect,
            10: BarnDoorOpenEffect,
            11: BarnDoorCloseEffect,
            12: ShrinkEffect,
            13: StretchEffect,
            14: PlainEffect
        }

    def get_images_from_directory(self, directory_path="images/"):
        """Gets all image files (as paths) from a given directory.

        Args:
            directory_path: The path to the directory to search for images.

        Returns:
            A list of paths to image files found in the directory.
        """
        image_extensions = [".jpg", ".jpeg", ".png",
                            ".gif", ".heic", ".heif"]  # Add more extensions if needed
        image_paths = []

        for root, dirs, files in os.walk(directory_path):
            for file in files:
                if file.lower().endswith(tuple(image_extensions)):
                    image_path = os.path.join(root, file)
                    image_paths.append(image_path)

        return image_paths

    def update_frame(self, generator):
        """
        Update the frame in the Tkinter window by fetching the next frame from the generator.

        Args:
        generator: The generator yielding transition frames.
        """
        if generator is None:
            return
        try:
            # Iterate over frames from the generator
            for frame in generator:
                # Add time and date to the frame
                frame = self.add_time_date_to_frame(frame)

                # Convert OpenCV image to PIL ImageTk format
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                image_tk = ImageTk.PhotoImage(image)

                # Update the label with the new image
                self.label.config(image=image_tk)
                self.label.image = image_tk

                # Update the GUI
                self.root.update_idletasks()
                self.root.update()
        except Exception as e:
            print(f"Error during frame update: {e}")
            return AnimationStatus.ANIMATION_ERROR

    def add_time_date_to_frame(self, frame):
        """
        Adds the current time and date to the frame.

        Args:
            frame: The image frame to modify.

        Returns:
            The modified frame with time and date added.
        """
        # Get current time and date
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%d/%m/%y")

        # Set font parameters
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_color = (255, 255, 255)  # White color
        font_thickness = 10

        # Desired text heights
        desired_time_height = 60
        desired_date_height = 30

        # Calculate font scales
        def get_font_scale(desired_height, font, font_thickness):
            for scale in np.arange(0.1, 10.0, 0.1):
                text_size = cv2.getTextSize("A", font, scale, font_thickness)[0]
                if text_size[1] >= desired_height:
                    return scale
            return scale  # Return the last scale if not found

        time_font_scale = get_font_scale(desired_time_height, font, font_thickness)
        date_font_scale = get_font_scale(desired_date_height, font, font_thickness)

        # Get text sizes
        (time_text_width, time_text_height), _ = cv2.getTextSize(current_time, font, time_font_scale, font_thickness)
        (date_text_width, date_text_height), _ = cv2.getTextSize(current_date, font, date_font_scale, font_thickness)

        # Calculate x positions
        x_date = 50  # Left margin
        x_time = x_date + (date_text_width - time_text_width) // 2

        # Calculate y positions
        y_date = self.screen_height - 50  # 10 pixels from bottom
        y_time = y_date - date_text_height - 20  # 10 pixels between time and date

        # Put the time and date onto the frame
        cv2.putText(frame, current_time, (x_time, y_time), font, time_font_scale, font_color, font_thickness, cv2.LINE_AA)
        cv2.putText(frame, current_date, (x_date, y_date), font, date_font_scale, font_color, font_thickness, cv2.LINE_AA)

        return frame

    def display_image_with_time(self, image, duration):
        """
        Displays the image and updates the time and date labels during the specified duration.

        Args:
            image: The image to display.
            duration: The duration to display the image in seconds.
        """
        start_time = time.time()
        while time.time() - start_time < duration:
            # Copy the image to avoid modifying the original
            frame = image.copy()

            # Add time and date to the frame
            frame = self.add_time_date_to_frame(frame)

            # Convert OpenCV image to PIL ImageTk format
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image_pil = Image.fromarray(frame_rgb)
            try:
                image_tk = ImageTk.PhotoImage(image_pil)
            except:
                exit(1)

            # Update the label with the new image
            self.label.config(image=image_tk)
            self.label.image = image_tk

            # Update the GUI
            self.root.update_idletasks()
            self.root.update()

            # Sleep for a short time to update every second
            time.sleep(1)

    def get_random_image(self):
        '''Returns a different image path each time.'''
        if len(self.shuffled_images) == 0:
            self.shuffled_images = list(self.images)
            rand.shuffle(self.shuffled_images)
        self.current_image_idx = (
            self.current_image_idx + 1) % len(self.shuffled_images)
        return self.shuffled_images[self.current_image_idx]

    def get_random_effect(self):
        '''Returns a different effect each time.'''
        if len(self.shuffled_effects) == 0:
            self.shuffled_effects = list(self.effects.keys())
            rand.shuffle(self.shuffled_effects)
        self.current_effect_idx = (
            self.current_effect_idx + 1) % len(self.shuffled_effects)
        return self.shuffled_effects[self.current_effect_idx]

    def start_transition(self, image1_path, image2_path, duration=5):
        """
        Start the image transition inside a Tkinter frame.

        Args:
        image1_path: Path to the first image (or None to select randomly).
        image2_path: Path to the second image (or None to select randomly).
        duration: Duration of the transition in seconds.
        """
        # Use the current image as image1
        if image1_path is None:
            if self.current_image is None:
                self.current_image = cv2.imread(self.get_random_image())
                self.current_image = cv2.resize(
                    self.current_image, (self.screen_width, self.screen_height))
            image1 = self.current_image
        else:
            image1 = cv2.imread(image1_path)
            image1 = cv2.resize(image1, (self.screen_width, self.screen_height))

        # Select a new image for image2
        if image2_path is None:
            image2_path = self.get_random_image()
        image2 = cv2.imread(image2_path)
        image2 = cv2.resize(image2, (self.screen_width, self.screen_height))

        # Update the current image
        self.current_image = image2

        # Create the generator
        effect_function = self.effects[self.get_random_effect()]
        gen = effect_function(image1, image2, duration)

        # Reuse the existing label
        if self.label is None:
            self.label = tk.Label(self.frame)
            self.label.pack()

        # Start updating the frame using the generator
        status = self.update_frame(gen)

        if status == AnimationStatus.ANIMATION_FINISHED:
            return AnimationStatus.ANIMATION_FINISHED

    def main(self):
        self.shuffled_images = list(self.images)
        rand.shuffle(self.shuffled_images)
        self.shuffled_effects = list(self.effects.keys())
        rand.shuffle(self.shuffled_effects)

        # Create the Tkinter root window and frame
        self.root = tk.Tk()
        self.root.title("Image Transition")

        # Make the window full-screen and borderless
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg='black')

        # Get screen dimensions
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        # Create a full-screen frame
        self.frame = tk.Frame(self.root, width=self.screen_width, height=self.screen_height)
        self.frame.pack()

        # Start the transition thread
        transition_thread = threading.Thread(target=self.run)
        transition_thread.start()

        # Start the Tkinter main loop
        self.root.mainloop()

    def run(self):
        while True:
            # Start the transition with a random image pair
            self.start_transition(None, None, duration=15)

            # Display the current image with time and date during the wait time
            self.display_image_with_time(self.current_image, self.wait_time)

if __name__ == "__main__":
    frame = PhotoFrame(wait_time=30)  # Set wait time between transitions to 30 seconds
    frame.main()
