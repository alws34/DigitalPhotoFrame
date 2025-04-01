from abc import ABC, abstractmethod
import logging

class iFrame(ABC):
    @abstractmethod
    def send_log_message(self, msg, logger: logging):
        pass