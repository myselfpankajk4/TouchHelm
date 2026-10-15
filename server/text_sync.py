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

    async def request(self, packet):
        action = packet.get('action')
        if action not in ('read', 'write'):
            raise ValueError('Unknown text sync action')
        if action == 'write' and (not isinstance(packet.get('text'), str)
                or len(packet['text']) > 10000):
            raise ValueError('Text exceeds synchronization limit')
        payload = {key: packet[key] for key in ('field_id', 'revision', 'text', 'newline_mode') if key in packet}
        cancelled = threading.Event()
        try:
            return await asyncio.wait_for(asyncio.to_thread(self.bridge.request,
                action, payload, cancelled=cancelled), 2.2 + self.bridge.startup_timeout)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except Exception:
            cancelled.set()
            return {'available': False, 'message': 'PC text is unavailable. Focus an editable field in a non-elevated app; native typing remains available.'}

    async def close(self):
        await asyncio.to_thread(self.bridge.close)
