import logging
import json
import threading
import time
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import cv2
import random as rand
import os
from enum import Enum
import numpy as np
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from flask import Flask, Response


# region Logging Setup
log_file_path = os.path.join(os.path.dirname(__file__), "PhotoFrame.log")
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,  # Exclude DEBUG messages
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Exclude DEBUG messages from console
console_formatter = logging.Formatter("%(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)
logging.getLogger().addHandler(console_handler)
logging.info("PhotoFrame application starting...")
# endregion Logging Setup

# region Importing Effects
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
# endregion Importing Effects


class AnimationStatus(Enum):
    ANIMATION_FINISHED = 1
    ANIMATION_ERROR = 2

class ImageChangeHandler(FileSystemEventHandler):
    def __init__(self, photoframe_instance):
        self.photoframe_instance = photoframe_instance

    def on_created(self, event):
        """Triggered when a file or directory is created."""
        print(f"File created: {event.src_path}. Reloading images...")
        self.photoframe_instance.reload_images()

    def on_deleted(self, event):
        """Triggered when a file or directory is deleted."""
        print(f"File deleted: {event.src_path}. Reloading images...")
        self.photoframe_instance.reload_images()

    def on_moved(self, event):
        """Triggered when a file or directory is renamed or moved."""
        print(f"File moved or renamed from {event.src_path} to {event.dest_path}. Reloading images...")
        self.photoframe_instance.reload_images()

class PhotoFrame:
    def __init__(self):
        logging.debug("Initializing PhotoFrame...")
        try:
            with open("settings.json", 'r') as file:
                self.settings = json.load(file)
            logging.info("Loaded settings from settings.json.")
        except FileNotFoundError:
            logging.error("settings.json not found. Exiting.")
            raise

        if not os.path.exists('Images'):
            os.mkdir('Images')
            logging.warning("'Images' directory not found. Created a new one.")
            return

        self.effects = self.set_effects()
        self.images = self.get_images_from_directory()
        self.shuffled_images = list(self.images)
        self.shuffled_effects = list(self.effects.keys())
        self.current_image_idx = -1
        self.current_effect_idx = -1
        self.root = None
        self.frame = None
        self.label = None
        self.screen_width = None
        self.screen_height = None
        self.current_image = None
        self.next_image = None

        self.wait_time = self.settings["delay_between_images"]
        self.is_running = True

        self.mjpeg_server_thread = None
        self.is_running = True

        # Start the directory observer
        self.start_observer()
        
    def start_observer(self):
        """Starts the directory observer to watch for changes in the Images directory."""
        logging.debug("Starting directory observer...")
        event_handler = ImageChangeHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, "Images", recursive=True)
        self.observer.start()
        logging.info("Directory observer started.")

    def stop_observer(self):
        """Stops the directory observer."""
        logging.debug("Stopping directory observer...")
        self.observer.stop()
        self.observer.join()
        logging.info("Directory observer stopped.")

    def reload_images(self):
        """Reloads images from the directory, stops the current frame, and restarts the transition."""
        logging.info("Reloading images from 'Images' directory...")
        self.images = self.get_images_from_directory()
        logging.info(f"Found {len(self.images)} images.")

#region mjpeg stream
    def generate_frame(self):
        """
        Generator to serve MJPEG frames from the live frame.
        Streams the live frame directly without resizing.
        """
        while self.is_running:
            if hasattr(self, 'live_frame') and self.live_frame is not None:
                try:
                    # Ensure the frame is a valid NumPy array
                    if isinstance(self.live_frame, np.ndarray) and self.live_frame.size > 0:
                        # Ensure the frame has the correct type and format
                        if self.live_frame.dtype != np.uint8:
                            self.live_frame = self.live_frame.astype(np.uint8)

                        # Encode the frame as JPEG
                        _, jpeg = cv2.imencode('.jpg', self.live_frame)
                        frame = jpeg.tobytes()

                        # Yield the MJPEG frame
                        yield (b'--frame\r\n'
                            b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                    else:
                        logging.warning("Invalid live_frame: Not a proper image array")
                except Exception as e:
                    logging.error(f"Error encoding frame: {e}")
            else:
                logging.warning("No live frame available to stream.")

            time.sleep(1/10)  # Maintain ~30 FPS


    def start_mjpeg_server(self):
        """
        Starts an MJPEG server using Flask.
        """
        app = Flask(__name__)

        @app.route('/video_feed')
        def video_feed():
            return Response(self.generate_frame(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

        # Run the Flask app in a separate thread
        self.mjpeg_server_thread = threading.Thread(target=lambda: app.run(
            host='0.0.0.0', port=5001, debug=False, use_reloader=False))
        self.mjpeg_server_thread.start()
#endregion mjpeg stream

# region Utils

    def on_touch_event(self, event):
        """Handler for touchscreen events. Does nothing."""
        logging.info(f"Touch event detected: {event}. Ignored.")
        
    def set_effects(self):
        return {
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
            # 14: PlainEffect
        }
   
    def get_images_from_directory(self, directory_path="Images/"):
        """Gets all image files (as paths) from a given directory.

        Args:
            directory_path: The path to the directory to search for images.

        Returns:
            A list of paths to image files found in the directory.
        """
        image_extensions = [".jpg", ".jpeg", ".png",
                            ".gif"]  # Add more extensions if needed
        image_paths = []

        for root, dirs, files in os.walk(directory_path):
            for file in files:
                if file.lower().endswith(tuple(image_extensions)):
                    image_path = os.path.join(root, file)
                    image_paths.append(image_path)

        return image_paths

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
# endregion Utils


# region DateTime


    def add_time_date_to_frame(self, frame):
        """
        Adds the current time and date to the frame using the settings from the JSON file.

        Args:
            frame: The image frame to modify.

        Returns:
            The modified frame with time and date added.
        """
        # Get current time and date
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%d/%m/%y")

        # Load font settings
        font_path = self.settings['font_name']
        time_font_size = self.settings['time_font_size']
        date_font_size = self.settings['date_font_size']
        margin_left = self.settings['margin_left']
        margin_bottom = self.settings['margin_bottom']
        spacing_between = self.settings['spacing_between']

        # Load the fonts
        time_font = ImageFont.truetype(font_path, time_font_size)
        date_font = ImageFont.truetype(font_path, date_font_size)

        # Convert frame to PIL Image
        pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)

        # Calculate text sizes
        time_bbox = draw.textbbox((0, 0), current_time, font=time_font)
        date_bbox = draw.textbbox((0, 0), current_date, font=date_font)

        time_text_size = (time_bbox[2] - time_bbox[0],
                          time_bbox[3] - time_bbox[1])
        date_text_size = (date_bbox[2] - date_bbox[0],
                          date_bbox[3] - date_bbox[1])

        # Calculate positions based on settings
        x_date = margin_left
        x_time = x_date + (date_text_size[0] - time_text_size[0]) // 2
        y_date = self.screen_height - margin_bottom
        y_time = y_date - date_text_size[1] - spacing_between

        # Set font color
        font_color = (255, 255, 255)  # White color

        # Draw the time and date on the image
        draw.text((x_time, y_time), current_time,
                  font=time_font, fill=font_color)
        draw.text((x_date, y_date), current_date,
                  font=date_font, fill=font_color)

        # Convert back to OpenCV format
        frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        return frame

    def display_image_with_time(self, image, duration):
        """
        Displays the image and updates the time and date labels during the specified duration.

        Args:
            image: The image to display.
            duration: The duration to display the image in seconds.
        """
        start_time = time.time()
        while time.time() - start_time < duration and self.is_running:
            # Copy the image to avoid modifying the original
            frame = image.copy()

            # Add time and date to the frame
            frame = self.add_time_date_to_frame(frame)
            self.live_frame = frame 
            # Convert OpenCV image to PIL ImageTk format
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image_pil = Image.fromarray(frame_rgb)
            image_tk = ImageTk.PhotoImage(image_pil)

            # Update the label with the new image
            self.label.config(image=image_tk)
            self.label.image = image_tk

            # Update the GUI
            self.root.update_idletasks()
            self.root.update()

            # Sleep for a short time to update every second
            time.sleep(1)
# endregion DateTime


# region ImageHandling

    def resize_image(self, image, target_width, target_height):
        # Get the original dimensions of the image
        original_height, original_width = image.shape[:2]

        # Calculate the aspect ratio of the image
        aspect_ratio = original_width / original_height

        # Calculate new dimensions to maintain the aspect ratio
        if target_width / target_height > aspect_ratio:
            new_height = target_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = target_width
            new_height = int(new_width / aspect_ratio)

        # Resize the image
        resized_image = cv2.resize(image, (new_width, new_height))

        # Create a black background with target dimensions
        final_image = np.zeros(
            (target_height, target_width, 3), dtype=np.uint8)

        # Center the resized image on the background
        y_offset = (target_height - new_height) // 2
        x_offset = (target_width - new_width) // 2
        final_image[y_offset:y_offset + new_height,
                    x_offset:x_offset + new_width] = resized_image

        return final_image

    def create_translucent_background(self, image, target_width, target_height, alpha=1.0):
        # Resize the image to fill the screen, ignoring the aspect ratio
        background = cv2.resize(image, (target_width, target_height))

        # Apply a blur to the background image
        blurred_background = cv2.GaussianBlur(background, (21, 21), 0)

        # Adjust the opacity (alpha) of the blurred background
        overlay = blurred_background.copy()
        cv2.addWeighted(overlay, alpha, background, 1 - alpha, 0, background)

        return background

    def resize_image_with_background(self, image, target_width, target_height):
        # Get the original dimensions of the image
        original_height, original_width = image.shape[:2]

        # Calculate the aspect ratio of the image
        aspect_ratio = original_width / original_height

        # Calculate new dimensions to maintain the aspect ratio
        if target_width / target_height > aspect_ratio:
            new_height = target_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = target_width
            new_height = int(new_width / aspect_ratio)

        # Resize the main image to maintain aspect ratio
        resized_image = cv2.resize(image, (new_width, new_height))

        # Create a fit-to-screen translucent background of the image
        background = self.create_translucent_background(
            image, target_width, target_height)

        # Overlay the resized image onto the background
        y_offset = (target_height - new_height) // 2
        x_offset = (target_width - new_width) // 2
        background[y_offset:y_offset + new_height,
                   x_offset:x_offset + new_width] = resized_image

        return background
# endregion ImageHandling


# region Events

    def on_closing(self):
        """Handler for window close event."""
        logging.info("Closing application...")
        self.is_running = False
        self.stop_observer()  # Stop the observer before closing
        self.root.destroy()  # Destroy the root window to close the application

# endregion Events

# region Main
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
                #for frame in gen:
                self.live_frame = frame  # Update live frame for streaming

                # Convert OpenCV image to PIL ImageTk format
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                image_tk = ImageTk.PhotoImage(image)

                # Update the label with the new image
                self.label.config(image=image_tk)
                self.label.image = image_tk
                # Update the live frame during the transition
                
                # Update the GUI
                self.root.update_idletasks()
                self.root.update()
            return AnimationStatus.ANIMATION_FINISHED
        except Exception as e:
            print(f"Error during frame update: {e}")
            return AnimationStatus.ANIMATION_ERROR

    def start_transition(self, image1_path=None, image2_path=None, duration=5):
        """
        Start the image transition inside a Tkinter frame.
        """
        # Ensure the current image is set
        if self.current_image is None:
            # First run or no current image, get a random image
            self.current_image = cv2.imread(self.get_random_image())
            self.current_image = self.resize_image_with_background(
                self.current_image, self.screen_width, self.screen_height)

        # Select a new image for image2
        if image2_path is None:
            image2_path = self.get_random_image()

        self.next_image = cv2.imread(image2_path)
        self.next_image = self.resize_image_with_background(
            self.next_image, self.screen_width, self.screen_height)

        # Create the generator using the current effect
        effect_function = self.effects[self.get_random_effect()]
        gen = effect_function(self.current_image, self.next_image, duration)

        # Reuse the existing label, or create it if it doesn't exist
        if self.label is None:
            self.label = tk.Label(self.frame)
            self.label.pack()

        # Start updating the frame using the generator
        self.status = self.update_frame(gen)

        # Update the live frame during the transition
        #for frame in gen:
        #self.live_frame = frame  # Update live frame for streaming

        if self.status == AnimationStatus.ANIMATION_FINISHED:
            self.current_image = self.next_image
            # Update the current image to image2 after the transition completes
            return AnimationStatus.ANIMATION_FINISHED

    def run(self):
        while self.is_running:
            # Start the transition with a random image pair
            self.start_transition(duration=self.settings["animation_duration"])
            # Display the current image with time and date during the wait time
            self.display_image_with_time(
                self.current_image, self.wait_time)
            self.live_frame = frame
            time.sleep(1)

    def main(self):
        logging.info("Starting main application...")
        self.shuffled_images = list(self.images)
        rand.shuffle(self.shuffled_images)
        self.shuffled_effects = list(self.effects.keys())
        rand.shuffle(self.shuffled_effects)

        # Create the Tkinter root window and frame
        self.root = tk.Tk()
        self.root.title("Digital Photo Frame V2.0")

        # Make the window full-screen and borderless
        self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
        self.root.attributes("-fullscreen", True)
        self.root.wm_attributes("-topmost", True)  # Ensure it's always on top
        self.root.configure(bg='black')

        # Hide the mouse cursor
        self.root.config(cursor="none")
        self.root.option_add('*Cursor', 'none')

        # Get screen dimensions
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        # Create a full-screen frame
        self.frame = tk.Frame(
            self.root, width=self.screen_width, height=self.screen_height, bg='black')
        self.frame.pack(fill="both", expand=True)

        # Bind the close event (Alt+F4)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Bind Ctrl+C to terminate the application
        self.root.bind_all('<Control-c>', lambda e: self.on_closing())

        # Start the MJPEG server
        self.start_mjpeg_server()

        # Start the transition thread
        logging.info("Starting transition thread...")
        transition_thread = threading.Thread(target=self.run)
        transition_thread.start()

        try:
            # Start the Tkinter main loop
            logging.info("Entering Tkinter main loop.")
            self.root.mainloop()
        except KeyboardInterrupt:
            logging.warning("Keyboard interrupt received. Exiting application...")
            self.on_closing()


# endregion Main


if __name__ == "__main__":
    try:
        frame = PhotoFrame()
        frame.main()
    except Exception as e:
        logging.critical(f"Unhandled exception occurred: {e}")
        raise