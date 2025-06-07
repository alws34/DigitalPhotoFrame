import json
import logging
import threading


class SettingsHandler:
    def __init__(self, path, logger: logging):
        self.path = path
        self._lock = threading.Lock()
        self.logger = logger

    def _load(self):
        try:
            with self._lock:
                with open(self.path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not reload settings from {self.path}: {e}")
            return {}

    def __getitem__(self, key):
        data = self._load()
        return data[key]

    def get(self, key, default=None):
        data = self._load()
        return data.get(key, default)

    def save(self, data: dict):
        with self._lock:
            with open(self.path, "w") as f:
                json.dump(data, f, indent=4)
