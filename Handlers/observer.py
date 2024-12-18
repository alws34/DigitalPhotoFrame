from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


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


class ImagesObserver():
    def __init__(self, i_photoframe):
        self.PhotoFrame = i_photoframe 

    def start_observer(self):
        """Starts the directory observer to watch for changes in the Images directory."""
        self.PhotoFrame.logger.debug("Starting directory observer...")
        event_handler = ImageChangeHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, "Images", recursive=True)
        self.observer.start()
        self.PhotoFrame.logger.info("Directory observer started.")

    def stop_observer(self):
        """Stops the directory observer."""
        self.PhotoFrame.logger.debug("Stopping directory observer...")
        self.observer.stop()
        self.observer.join()
        self.PhotoFrame.logger.info("Directory observer stopped.")

    def reload_images(self):
        """Reloads images from the directory, stops the current frame, and restarts the transition."""
        self.PhotoFrame.logger.info("Reloading images from 'Images' directory...")
        self.images = self.get_images_from_directory()
        self.PhotoFrame.logger.info(f"Found {len(self.images)} images.")