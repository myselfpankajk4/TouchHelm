"""Bounded, in-memory PNG assets. No asset identifier is a filesystem path."""
from collections import OrderedDict
import hashlib
import io
import re
import threading
import warnings

from PIL import Image, ImageOps


class AssetStore:
    def __init__(self, *, max_items=256, max_bytes=16 * 1024 * 1024, max_dimension=1024):
        self.max_items = max(1, int(max_items))
        self.max_bytes = max(1, int(max_bytes))
        self.max_dimension = max(1, min(2048, int(max_dimension)))
        self._items = OrderedDict()
        self._sources = {}
        self._size = 0
        self._lock = threading.RLock()

    def put(self, data):
        if not isinstance(data, bytes) or not data or len(data) > 4 * 1024 * 1024:
            return None
        source = hashlib.sha256(data).digest()
        with self._lock:
            previous = self._sources.get(source)
            if previous in self._items:
                self._items.move_to_end(previous)
                return previous
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 16 * 1024 * 1024:
                        return None
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((self.max_dimension, self.max_dimension))
                    image = image.convert('RGBA')
                    output = io.BytesIO()
                    image.save(output, format='PNG')
                    normalized = output.getvalue()
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            return None
        if len(normalized) > self.max_bytes:
            return None
        identifier = hashlib.sha256(normalized).hexdigest()[:32]
        with self._lock:
            if identifier not in self._items:
                self._items[identifier] = normalized
                self._size += len(normalized)
            self._items.move_to_end(identifier)
            self._sources[source] = identifier
            while len(self._items) > self.max_items or self._size > self.max_bytes:
                removed, payload = self._items.popitem(last=False)
                self._size -= len(payload)
                self._sources = {key: value for key, value in self._sources.items() if value != removed}
            # Different encodings of a resident asset cannot grow this map forever.
            if len(self._sources) > self.max_items * 4:
                self._sources = {source: identifier}
        return identifier

    def get(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
            return None
        with self._lock:
            payload = self._items.get(identifier)
            if payload is not None:
                self._items.move_to_end(identifier)
            return payload
