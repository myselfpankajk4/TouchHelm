"""Bounded UI Automation helper, independent of media and pointer providers.

Only explicitly requested focused editable fields are inspected. No key hooks,
clipboard access, broadcasts, disk cache, or text in diagnostics.
"""
import asyncio
from pathlib import Path
import threading

from .desktop_services import PersistentPowerShellBridge


class FocusedTextService:
    def __init__(self, *, bridge=None):
        self.bridge = bridge or PersistentPowerShellBridge(
            timeout=2, script_path=Path(__file__).with_name('text_bridge.ps1'))
        self._request_lock = asyncio.Lock()
        self._phone_write = None

    @staticmethod
    def _selected_completion(state, typed):
        """Match only the selected suffix of a known phone write, in UTF-16 units."""
        text = state.get('text')
        start, end = state.get('selection_start'), state.get('selection_end')
        if (not typed or not isinstance(text, str) or text == typed
                or not text.startswith(typed) or type(start) is not int or type(end) is not int):
            return False
        units = lambda value: len(value.encode('utf-16-le', errors='surrogatepass')) // 2
        return start == units(typed) and end == units(text)

    def _committed_state(self, packet, state):
        if not state.get('available'):
            return state
        field, text = state.get('field_id'), state.get('text')
        if packet['action'] == 'write':
            typed = packet['text']
            self._phone_write = ((field, typed) if field == packet.get('field_id')
                and (text == typed or self._selected_completion(state, typed)) else None)
        if self._phone_write:
            last_field, typed = self._phone_write
            if field == last_field and self._selected_completion(state, typed):
                # Chrome's inline suggestion is a selected suffix, not a new
                # phone edit. Keep the raw revision for compare-and-write safety.
                return {key: value for key, value in {**state, 'text': typed}.items()
                        if key not in ('selection_start', 'selection_end')}
            if field != last_field or text != typed:
                # Accepted suggestions and actual PC edits become normal text.
                self._phone_write = None
        return state

    async def request(self, packet):
        action = packet.get('action')
        if action not in ('read', 'write'):
            raise ValueError('Unknown text sync action')
        if action == 'write' and (not isinstance(packet.get('text'), str)
                or len(packet['text']) > 10000):
            raise ValueError('Text exceeds synchronization limit')
        payload = {key: packet[key] for key in ('field_id', 'revision', 'text', 'newline_mode') if key in packet}
        # Keep the phone-write context in the same order as native snapshots,
        # including when multiple authenticated phones share the provider.
        async with self._request_lock:
            cancelled = threading.Event()
            try:
                state = await asyncio.wait_for(asyncio.to_thread(self.bridge.request,
                    action, payload, cancelled=cancelled), 2.2 + self.bridge.startup_timeout)
                return self._committed_state(packet, state)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            except Exception:
                cancelled.set()
                return {'available': False, 'message': 'PC text is unavailable. Focus an editable field in a non-elevated app; native typing remains available.'}

    async def close(self):
        await asyncio.to_thread(self.bridge.close)
