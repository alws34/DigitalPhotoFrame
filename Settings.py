import json
import logging
import threading
import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class SettingsHandler:
    def __init__(self, path, logger: logging):
        self.path = path
        self._lock = threading.Lock()
        self.logger = logger

    def _load(self):
        try:
            with self._lock:
                path = os.path.abspath(os.path.join(os.path.dirname(__file__), self.path)) 
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not reload settings from {self.path}: {e}")
            return None

    def __getitem__(self, key):
        data = self._load()
        if data is None:
            self.logger.warning(f"Settings file {self.path} is empty or could not be loaded.")
            return None
        return data[key]

    def get(self, key, default=None):
        data = self._load()
        if data is None:
            return default
        return data.get(key, default)

    def save(self, data: dict):
        with self._lock:
            with open(self.path, "w") as f:
                json.dump(data, f, indent=4)
