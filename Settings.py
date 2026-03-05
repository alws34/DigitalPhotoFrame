import json
import logging
import os
import sys
import threading

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class SettingsHandler:
    def __init__(self, path, logger: logging):
        self.path = path
        self._lock = threading.Lock()
        self.logger = logger
        self._cache = None
        self.reload()

    def reload(self):
        """Manually refresh settings from disk."""
        data = self._load()
        if data is not None:
            self._cache = data
        return self._cache

    def _load(self):
        try:
            with self._lock:
                # Use current directory or absolute path
                if os.path.isabs(self.path):
                    path = self.path
                else:
                    path = os.path.abspath(os.path.join(os.path.dirname(__file__), self.path))
                
                if not os.path.exists(path):
                    return {}
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not load settings from {self.path}: {e}")
            return None

    def __getitem__(self, key):
        with self._lock:
            if self._cache is None:
                self.reload()
            return self._cache.get(key) if self._cache else None

    def get(self, key, default=None):
        with self._lock:
            if self._cache is None:
                self.reload()
            if self._cache is None:
                return default
            return self._cache.get(key, default)

    @property
    def data(self):
        with self._lock:
            if self._cache is None:
                self.reload()
            return self._cache

    def save(self, data: dict):
        with self._lock:
            self._cache = data
            # Ensure path is absolute for saving
            if os.path.isabs(self.path):
                path = self.path
            else:
                path = os.path.abspath(os.path.join(os.path.dirname(__file__), self.path))
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
