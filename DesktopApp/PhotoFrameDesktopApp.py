import tkinter as tk
from PIL import Image, ImageTk
import threading
import requests
import cv2
import numpy as np
import time

class MJPEGClient:
    """
    Handles connection to the MJPEG server and yields frames.
    
    It connects to a Flask endpoint that streams MJPEG data. The get_frames()
    method reads chunks of bytes from the response and searches for JPEG frame boundaries.
    """
    def __init__(self, url):
        self.url = url
        self.session = requests.Session()

    def get_frames(self):
        # Connect to the MJPEG stream URL
        response = self.session.get(self.url, stream=True)
        bytes_buffer = bytes()
        for chunk in response.iter_content(chunk_size=1024):
            bytes_buffer += chunk
            # Find the start and end of the JPEG frame in the stream
            a = bytes_buffer.find(b'\xff\xd8')  # JPEG start
            b = bytes_buffer.find(b'\xff\xd9')  # JPEG end
            if a != -1 and b != -1:
                jpg = bytes_buffer[a:b+2]
                bytes_buffer = bytes_buffer[b+2:]
                # Decode the JPEG image to a NumPy array (BGR format)
                img_array = np.frombuffer(jpg, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if frame is not None:
                    yield frame

class PhotoFrame(tk.Frame):
    """
    A tkinter frame that fetches frames from an MJPEG server, resizes them,
    and displays the live video stream.
    
    The image handling (fetching and resizing) is decoupled from the frame display.
    """
    def __init__(self, parent, stream_url, desired_width, desired_height, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.stream_url = stream_url
        self.desired_width = desired_width
        self.desired_height = desired_height
        
        # Configure the parent window if it's a Tk instance
        if isinstance(self.parent, tk.Tk):
            self.parent.title("Digital Photo Frame V2.0")
            self.parent.geometry(f"{self.parent.winfo_screenwidth()}x{self.parent.winfo_screenheight()}+0+0")
            self.parent.attributes("-fullscreen", True)
            self.parent.wm_attributes("-topmost", True)
            self.parent.configure(bg='black')
            self.parent.config(cursor="none")
            self.parent.option_add('*Cursor', 'none')
            self.parent.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.parent.bind_all('<Control-c>', lambda e: self.on_closing())
        
        # Label for displaying the video stream
        self.label = tk.Label(self, bg='black')
        self.label.pack(fill="both", expand=True)
        
        # Create an MJPEG client for fetching frames
        self.mjpeg_client = MJPEGClient(self.stream_url)
        self.current_frame = None
        self.stop_event = threading.Event()
        
        # Start a background thread to fetch and process frames from the server
        self.fetch_thread = threading.Thread(target=self.frame_fetch_loop, daemon=True)
        self.fetch_thread.start()
        
        # Schedule GUI updates (approximately 30 FPS)
        self.update_display()

    def on_closing(self):
        """Handler for window close event."""
        self.stop_event.set()
        self.parent.destroy()

    def resize_image(self, cv_img):
        """
        Resizes the given OpenCV image to fit within the desired dimensions while
        preserving its aspect ratio. It also centers the resized image on a black background.
        """
        h, w, _ = cv_img.shape
        aspect_ratio = w / h
        desired_aspect = self.desired_width / self.desired_height

        # Determine new size preserving the aspect ratio
        if aspect_ratio > desired_aspect:
            new_w = self.desired_width
            new_h = int(self.desired_width / aspect_ratio)
        else:
            new_h = self.desired_height
            new_w = int(self.desired_height * aspect_ratio)
        
        # Resize the image
        resized_img = cv2.resize(cv_img, (new_w, new_h))
        
        # Create a black background and center the resized image on it
        background = np.zeros((self.desired_height, self.desired_width, 3), dtype=np.uint8)
        x_offset = (self.desired_width - new_w) // 2
        y_offset = (self.desired_height - new_h) // 2
        background[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized_img
        
        return background

    def frame_fetch_loop(self):
        """
        Continuously fetch frames from the MJPEG client, resize them,
        and update the current_frame variable.
        """
        for frame in self.mjpeg_client.get_frames():
            if self.stop_event.is_set():
                break
            # Resize the incoming frame
            resized_frame = self.resize_image(frame)
            self.current_frame = resized_frame
            # Sleep briefly to allow a consistent fetch rate (~30 FPS)
            time.sleep(0.03)

    def update_display(self):
        """
        Periodically updates the tkinter label with the latest frame.
        This method is scheduled using after() to ensure updates occur in the GUI thread.
        """
        if self.current_frame is not None:
            # Convert the BGR image to RGB
            cv_img_rgb = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(cv_img_rgb)
            image_tk = ImageTk.PhotoImage(pil_image)
            self.label.config(image=image_tk)
            self.label.image = image_tk  # Keep a reference to avoid garbage collection
        # Schedule the next update (about every 33 ms for ~30 FPS)
        self.after(33, self.update_display)

    def stop(self):
        """Stops the background frame fetching thread."""
        self.stop_event.set()


if __name__ == "__main__":
    # Example usage:
    # Set the MJPEG server URL (make sure this matches your Flask server configuration)
    MJPEG_SERVER_URL = "http://localhost:5001/video_feed"
    
    # Create the main Tkinter window
    root = tk.Tk()
    
    # Define desired display dimensions (full screen)
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    # Create an instance of PhotoFrame, passing the root as the parent
    mjpeg_frame = PhotoFrame(root, stream_url=MJPEG_SERVER_URL, desired_width=screen_width, desired_height=screen_height)
    mjpeg_frame.pack(fill="both", expand=True)
    
    # Start the Tkinter main loop
    try:
        root.mainloop()
    except KeyboardInterrupt:
        mjpeg_frame.stop()
        root.destroy()
