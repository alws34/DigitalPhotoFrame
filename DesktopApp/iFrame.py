from abc import ABC, abstractmethod
import logging

class iFrame(ABC):
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def send_log_message(self, msg, logger: logging):
        pass
