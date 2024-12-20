from abc import ABC, abstractmethod
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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
    def __init__(self, observer: iBoserver):
        self.observer = observer

    def on_created(self, event):
        """Triggered when a file or directory is created."""
        print(f"File created: {event.src_path}. Reloading images...")
        self.observer.reload_images()

    def on_deleted(self, event):
        """Triggered when a file or directory is deleted."""
        print(f"File deleted: {event.src_path}. Reloading images...")
        self.observer.reload_images()

    def on_moved(self, event):
        """Triggered when a file or directory is renamed or moved."""
        print(f"File moved or renamed from {event.src_path} to {event.dest_path}. Reloading images...")
        self.observer.reload_images()


class ImagesObserver(iBoserver):
    from iFrame import iFrame
    def __init__(self, frame: iFrame):
        self.frame = frame 
    

    def start_observer(self):
        """Starts the directory observer to watch for changes in the Images directory."""
        self.frame.send_log_message("Starting directory observer...", logging.debug)
        event_handler = ImageChangeHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, "Images", recursive=True)
        self.observer.start()
        self.frame.send_log_message("Directory observer started.", logging.info)
    
    def stop_observer(self):
        """Stops the directory observer."""
        self.frame.send_log_message("Stopping directory observer...", logging.debug)
        self.observer.stop()
        self.observer.join()
        self.frame.send_log_message("Directory observer stopped.", logging.info)
   
    def reload_images(self):
        """Reloads images from the directory, stops the current frame, and restarts the transition."""
        self.frame.send_log_message("Reloading images from 'Images' directory...", logging.info)
        self.images = self.get_images_from_directory()
        self.frame.send_log_message(f"Found {len(self.images)} images.", logging.info)