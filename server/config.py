"""
TouchHelm - Configuration Manager
"""

import json
import os
import socket
import math
import threading
import tempfile

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

DEFAULT_CONFIG = {
    "server_name": socket.gethostname(),
    "port": 8765,
    "mouse_sensitivity": 1.3,
    "mouse_acceleration": 1.25,
    "scroll_speed": 1.0,
    "invert_scroll": False,
    "require_pin": False,
    "pin_code": "1234",
    "laser_color": "red",
    "theme": "cyber",
    "haptics_enabled": True
}


class ConfigManager:
    def __init__(self, file_path: str = CONFIG_FILE):
        self.file_path = file_path
        self._lock = threading.RLock()
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if not isinstance(saved, dict):
                    raise ValueError("Configuration must be an object")
                for key, value in saved.items():
                    if key in DEFAULT_CONFIG:
                        try:
                            self._validate(key, value)
                        except ValueError:
                            continue
                        self.data[key] = value
                if self.data["require_pin"] and not self._valid_pin(self.data["pin_code"]):
                    self.data["pin_code"] = DEFAULT_CONFIG["pin_code"]
            except Exception as e:
                print(f"Error loading config: {e}")

    def save(self):
        with self._lock:
            folder = os.path.dirname(os.path.abspath(self.file_path))
            fd, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(self.data, stream, indent=2, allow_nan=False)
                os.replace(temporary, self.file_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key, value):
        self.update({key: value})

    @staticmethod
    def _valid_pin(value):
        return isinstance(value, str) and len(value) == 4 and value.isascii() and value.isdigit()

    @classmethod
    def _validate(cls, key, value):
        if key not in DEFAULT_CONFIG:
            raise ValueError(f"Unknown setting: {key}")
        numeric = {"mouse_sensitivity": (.4, 3.5), "mouse_acceleration": (1., 2.5),
                   "scroll_speed": (.3, 2.5)}
        if key in numeric:
            low, high = numeric[key]
            valid = type(value) in (int, float) and low <= value <= high and math.isfinite(value)
        elif key == "port":
            valid = type(value) is int and 1 <= value <= 65535
        elif key in ("require_pin", "invert_scroll", "haptics_enabled"):
            valid = type(value) is bool
        elif key == "pin_code":
            valid = value == "" or cls._valid_pin(value)
        elif key == "laser_color":
            valid = isinstance(value, str) and value in ("red", "green", "blue", "amber")
        elif key == "theme":
            valid = isinstance(value, str) and value in ("cyber", "oled", "matrix", "nordic", "light")
        else:
            valid = isinstance(value, str) and 1 <= len(value.strip()) <= 100
        if not valid:
            raise ValueError(f"Invalid value for {key}")

    def update(self, settings):
        if not isinstance(settings, dict):
            raise ValueError("Settings must be an object")
        with self._lock:
            for key, value in settings.items():
                self._validate(key, value)
            updated = dict(self.data, **settings)
            if updated["require_pin"] and not self._valid_pin(updated["pin_code"]):
                raise ValueError("A four-digit PIN is required")
            previous = self.data
            self.data = updated
            try:
                self.save()
            except Exception:
                self.data = previous
                raise

    def public_data(self):
        with self._lock:
            return {key: value for key, value in self.data.items() if key != "pin_code"}
