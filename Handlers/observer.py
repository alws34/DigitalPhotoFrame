from abc import ABC, abstractmethod
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from iFrame import iFrame
import os

class iBoserver(ABC):
    @abstractmethod
    def start_observer(self):
        pass
    @abstractmethod
    def stop_observer(self):
        pass
    
    @abstractmethod
    def reload_images(self):
        pass
    
class ImageChangeHandler(FileSystemEventHandler):
    def __init__(self, observer: iBoserver, images_dir = "Images"):
        self.observer = observer
        self.old_image_count = self.observer.reload_images()
        self.images_dir = images_dir

    def on_created(self, event):
        """Triggered when a file or directory is created."""
        message = f"Added {self.observer.reload_images() - self.old_image_count} Image\s"
        self.old_image_count = len(self.observer.images)
        self.observer.frame.notification_manager.create_notification(message)

    def on_deleted(self, event):
        """Triggered when a file or directory is deleted."""
        message = f"Removed {self.old_image_count - self.observer.reload_images()} Image\s"
        self.old_image_count = len(self.observer.images)
        self.observer.frame.notification_manager.create_notification(message)

    def on_moved(self, event):
        """Triggered when a file or directory is renamed or moved."""
        message = f"moved/renamed {self.observer.reload_images()} Image\s"
        self.old_image_count = len(self.observer.images)
        self.observer.frame.notification_manager.create_notification(message)


class ImagesObserver(iBoserver):
    
    def __init__(self, frame: iFrame, images_dir = "Images"):
        self.frame = frame 
        self.images_dir = images_dir

    def start_observer(self):
        """Starts the directory observer to watch for changes in the Images directory."""
        self.frame.send_log_message("Starting directory observer...", logging.debug)
        event_handler = ImageChangeHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, self.images_dir, recursive=True)
        self.observer.start()
        self.frame.send_log_message("Directory observer started.", logging.info)
    
    def stop_observer(self):
        """Stops the directory observer."""
        self.frame.send_log_message("Stopping directory observer...", logging.debug)
        self.observer.stop()
        self.observer.join()
        self.frame.send_log_message("Directory observer stopped.", logging.info)
   
    def reload_images(self)->int:
        """Reloads images from the directory, stops the current frame, and restarts the transition."""
        self.frame.send_log_message(f"Reloading images from '{self.images_dir}' directory...", logging.info)
        self.images = self.get_images_from_directory()
        self.frame.send_log_message(f"Found {len(self.images)} images to reload.", logging.info)
        return len(self.images)
        
        
    def get_images_from_directory(self) -> list:
        """Fetch all image file paths from the directory."""
        valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
        images = []
        for root, dirs, files in os.walk(self.images_dir):
            for file in files:
                if file.lower().endswith(valid_extensions):
                    images.append(os.path.join(root, file))
        return images