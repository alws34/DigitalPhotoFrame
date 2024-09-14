import tkinter as tk
from PIL import Image, ImageTk
import cv2
import random as rand
import os
from Effects.CheckerboardEffect import CheckerboardEffect
from Effects.AlphaDissolveEffect import AlphaDissolveEffect
from Effects.PixelDissolveEffect import PixelDissolveEffect
from Effects.BlindsEffect import BlindsEffect
from Effects.LinearEffect import LinearEffect
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


class PhotoFrame:
    def __init__(self):
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

        self.effects = {0: AlphaDissolveEffect, 1: PixelDissolveEffect, 2: CheckerboardEffect, 
                        3: BlindsEffect, 4: LinearEffect, 5: ScrollEffect, 6: WipeEffect,
                        7: ZoomOutEffect, 8: ZoomInEffect, 9: IrisOpenEffect, 10: IrisCloseEffect,
                        11: BarnDoorOpenEffect, 12: BarnDoorCloseEffect, 13: ShrinkEffect,
                        14: StretchEffect, 15: PlainEffect}

    def get_images_from_directory(self, directory_path="images\\"):
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
            # Get the next frame from the generator
            frame = next(generator)

            # Convert OpenCV image to PIL ImageTk format
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)
            image_tk = ImageTk.PhotoImage(image)

            # Update the label with the new image
            self.label.config(image=image_tk)
            self.label.image = image_tk

            # Schedule the next frame update
            self.root.after(10, self.update_frame, generator)
        except StopIteration:
            print("Animation complete. Starting a new transition...")
            self.start_transition(None, None, duration=20)
            return

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
                self.current_image = cv2.resize(
                    cv2.imread(self.get_random_image()), (500, 500))
            image1 = self.current_image
        else:
            image1 = cv2.resize(cv2.imread(image1_path), (500, 500))

        # Select a new image for image2
        if image2_path is None:
            image2_path = self.get_random_image()
        image2 = cv2.resize(cv2.imread(image2_path), (500, 500))

        # Update the current image
        self.current_image = image2

        # Create the generator
        gen = self.effects[self.get_random_effect()](image1, image2, duration)

        # Reuse the existing label
        if self.label is None:
            self.label = tk.Label(self.frame)
            self.label.pack()

        # Start updating the frame using the generator
        self.update_frame(gen)

    def main(self):
        self.shuffled_images = list(self.images)
        rand.shuffle(self.shuffled_images)
        self.shuffled_effects = list(self.effects.keys())
        rand.shuffle(self.shuffled_effects)

        # Create the Tkinter root window and frame
        self.root = tk.Tk()
        self.root.title("Image Transition")

        # Create a frame in the window
        self.frame = tk.Frame(self.root, width=500, height=500)
        self.frame.pack()

        # Start the transition with a random image pair
        self.start_transition(None, None, duration=5)

        # Start the Tkinter main loop
        self.root.mainloop()


if __name__ == "__main__":
    frame = PhotoFrame()
    frame.main()
