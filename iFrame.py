from abc import ABC, abstractmethod
import logging

class iFrame(ABC):
    @abstractmethod
    def send_log_message(self, msg, logger: logging):
        pass
    
    @abstractmethod
    def get_live_frame(self):
        pass

    @abstractmethod
    def get_is_running(self):
        pass