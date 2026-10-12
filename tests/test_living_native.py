"""Living controls at the provider boundary, with native effects replaced."""
import base64
import io
import time
import unittest
from unittest.mock import patch

from PIL import Image

from server.desktop_services import DesktopServices


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.result = {}

    def request(self, command, payload=None, *, cancelled=None):
        self.calls.append((command, payload or {}))
        return self.result

    def close(self):
        pass


class LivingNativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge = FakeBridge()
        self.service = DesktopServices(bridge=self.bridge)

    async def asyncTearDown(self):
        await self.service.close()

    async def test_playing_position_is_sampled_from_raw_timestamp_with_unknown_rate(self):
        self.bridge.result = {'media': {'available': True, 'status': 'Playing',
                              'position': 12, 'updated_at': 1000, 'duration': 100,
                              'playback_rate': None}}
        with patch('server.desktop_services.time.time', return_value=1003):
            media = (await self.service.snapshot())['media']
        self.assertEqual(media['position'], 15)
        self.assertEqual(media['sampled_at'], 1003)
        self.assertEqual(media['updated_at'], 1000)
        self.assertIsNone(media['playback_rate'])

    async def test_position_clamps_and_does_not_advance_paused_or_future_snapshot(self):
        for status, updated, expected in [('Playing', 1000, 20),
                                          ('Paused', 1000, 18),
                                          ('Playing', 1003, 18)]:
            with self.subTest(status=status, updated=updated):
                self.bridge.result = {'media': {'available': True, 'status': status,
                    'position': 18, 'updated_at': updated, 'min_seek': 3,
                    'max_seek': 20, 'duration': 30, 'playback_rate': 1.5}}
                with patch('server.desktop_services.time.time', return_value=1002):
                    media = (await self.service.snapshot())['media']
                self.assertEqual(media['position'], expected)

    async def test_selected_sessions_and_picker_share_the_sampled_clock(self):
        session = {'id': 'player', 'available': True, 'status': 'Playing',
                   'position': 12, 'updated_at': 1000, 'duration': 100,
                   'playback_rate': None}
        self.bridge.result = {'media': dict(session, sessions=[session])}
        with patch('server.desktop_services.time.time', return_value=1003):
            media = (await self.service.snapshot())['media']
        self.assertEqual(media['sessions'][0]['position'], media['position'])
        self.assertEqual(media['sessions'][0]['sampled_at'], 1003)
        self.bridge.result = {'sessions': [session], 'current': session}
        with patch('server.desktop_services.time.time', return_value=1003):
            library = await self.service.list_media()
        self.assertEqual(library['sessions'][0]['position'], 15)
        self.assertEqual(library['sessions'][0]['sampled_at'], 1003)

    async def test_artwork_status_tracks_valid_decode_and_bad_stream(self):
        image = Image.new('RGB', (2, 2), 'red')
        output = io.BytesIO(); image.save(output, 'PNG')
        valid = base64.b64encode(output.getvalue()).decode()
        for data, expected in [(None, 'not_provided'), (valid, 'available'),
                               ('not-base64', 'read_error'),
                               (base64.b64encode(b'not-image').decode(), 'read_error')]:
            with self.subTest(expected=expected, data=data):
                self.bridge.result = {'media': {'available': True, 'artwork_data': data,
                                               'artwork_status': 'available' if data else 'not_provided'}}
                media = (await self.service.snapshot())['media']
                self.assertEqual(media['artwork_status'], expected)
                self.assertEqual(bool(media['artwork_id']), expected == 'available')

    async def test_close_requires_verified_window_and_preserves_requested_state(self):
        self.bridge.result = {'apps': [{'id': 'app', 'name': 'App',
                                       'windows': [{'id': 'opaque', 'title': 'Scratch'}]}]}
        await self.service.list_apps()
        self.bridge.calls.clear()
        self.assertFalse((await self.service.app_action('app', 'close', 'forged'))['success'])
        self.assertEqual(self.bridge.calls, [])
        self.bridge.result = {'success': True, 'requested': True, 'confirmed': False,
                              'message': 'Close requested.'}
        result = await self.service.app_action('app', 'close', 'opaque')
        self.assertTrue(result['requested'])
        self.assertFalse(result['confirmed'])
        self.assertEqual(self.bridge.calls, [('app_action', {'app_id': 'app',
            'action': 'close', 'window_id': 'opaque'})])

    async def test_close_requires_explicit_window_even_for_single_window(self):
        self.bridge.result = {'apps': [{'id': 'app', 'name': 'App',
                                       'windows': [{'id': 'opaque', 'title': 'Scratch'}]}]}
        await self.service.list_apps()
        self.bridge.calls.clear()
        self.assertFalse((await self.service.app_action('app', 'close'))['success'])
        self.assertEqual(self.bridge.calls, [])
