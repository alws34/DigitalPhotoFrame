from abc import ABC, abstractmethod
import logging

class iFrame(ABC):
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def send_log_message(self, msg, logger: logging):
        pass
    
    @abstractmethod
    def get_live_frame(self):
        pass

    @abstractmethod
    def get_is_running(self):
        pass

    @abstractmethod
    def update_images_list(self):
        pass

    @abstractmethod
    def update_frame_to_stream(self):
        pass
    @abstractmethod
    def get_live_frame(self):
        pass
    # @abstractmethod
    # def get_metadata(self):
    #     pass