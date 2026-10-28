"""Server regressions. All native input/overlay side effects are substituted."""
import asyncio
import ctypes
import io
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from server.config import ConfigManager
from server.web_server import TouchHelmServer
from server import windows_input as native
from server.laser_overlay import LaserOverlayClient


class ConfigTests(unittest.TestCase):
    def test_invalid_saved_values_fall_back_without_poisoning_valid_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'config.json')
            with open(path, 'w') as stream:
                json.dump({'mouse_sensitivity': 'fast', 'port': -1,
                           'invert_scroll': 'false', 'scroll_speed': 1.7}, stream)
            config = ConfigManager(path)
            self.assertEqual(config.get('mouse_sensitivity'), 1.3)
            self.assertEqual(config.get('port'), 8765)
            self.assertIs(config.get('invert_scroll'), False)
            self.assertEqual(config.get('scroll_speed'), 1.7)


class AuthenticationFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_broken_socket_does_not_leave_other_clients_authorized(self):
        with tempfile.TemporaryDirectory() as folder:
            config = ConfigManager(os.path.join(folder, 'config.json'))
            config.update({'require_pin': True, 'pin_code': '5678'})
            with patch('server.web_server.WindowsInputController'), \
                 patch('server.web_server.LaserOverlayClient'):
                server = TouchHelmServer(config)

            class Socket:
                closed = False
                def __init__(self, fail):
                    self.fail = fail
                    self.messages = []
                async def send_json(self, message):
                    if self.fail:
                        raise ConnectionResetError('client disconnected')
                    self.messages.append(message)

            from server.web_server import ConnectedClient
            broken, healthy = Socket(True), Socket(False)
            first, second = ConnectedClient(broken, '1'), ConnectedClient(healthy, '2')
            first.authenticated = second.authenticated = True
            second.held_keys.add('ctrl')
            server.clients = {broken: first, healthy: second}
            await server.invalidate_auth_sessions()
            self.assertFalse(first.authenticated)
            self.assertFalse(second.authenticated)
            self.assertFalse(second.held_keys)
            server.input_ctrl.key_up.assert_called_once_with('ctrl')
            self.assertEqual(healthy.messages, [{'type': 'auth_required'}])


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_reauthentication_revokes_existing_file_cookie_session(self):
        self.config.update({'require_pin':True,'pin_code':'5678','files_enabled':True})
        ws=await self.http.ws_connect('/ws');await ws.receive_json()
        await ws.send_json({'type':'auth','pin':'5678'})
        await self.receive_kind(ws,'auth_res')
        client=self.server.clients[next(iter(self.server.clients))]
        session={'client':client,'pin':'5678','expires':time.monotonic()+60}
        self.server.files.sessions['fixture-session']=session
        await ws.send_json({'type':'auth','pin':'0000'})
        response=await self.receive_kind(ws,'auth_res')
        self.assertFalse(response['success'])
        self.assertTrue(session.get('revoked'))
        self.assertNotIn('fixture-session',self.server.files.sessions)
    async def test_phone_settings_cannot_grant_native_file_access(self):
        self.config.update({'require_pin':True,'pin_code':'5678'})
        response=await self.http.post('/api/config',json={'files_enabled':True},headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,400)
        self.assertFalse(self.config.get('files_enabled'))
    async def test_browser_link_qr_waits_for_verified_public_https_and_stop_cancels_probe(self):
        from types import SimpleNamespace
        self.config.set('require_pin',True)
        status={'state':'stopped','ready':False,'origin':None,'pairing_url':None,'expires_in':0}
        async def start(backend):
            status.update(state='ready',ready=True,origin='https://fixture.trycloudflare.com',pairing_url='https://fixture.trycloudflare.com/#browser-link=synthetic')
            return dict(status)
        async def stop(*args):status.update(state='stopped',ready=False,origin=None,pairing_url=None)
        self.server.browser_link=SimpleNamespace(snapshot=lambda:dict(status),start=start,stop=stop)
        self.server.local_link=SimpleNamespace(snapshot=lambda:{'connected':False},prepare=AsyncMock(),close=AsyncMock(),digest='a'*64)
        entered=asyncio.Event();release=asyncio.Event()
        async def response_enter():entered.set();await release.wait();return response
        response=AsyncMock();response.status=200;response.json.return_value={'pairing':True}
        request=AsyncMock();request.__aenter__.side_effect=response_enter
        probe=Mock();probe.get.return_value=request
        session=AsyncMock();session.__aenter__.return_value=probe
        gateway=Mock();gateway.start=AsyncMock(return_value='http://127.0.0.1:32100');gateway.close=AsyncMock()
        with patch('server.web_server.BrowserLinkGateway',return_value=gateway),patch('server.web_server.ClientSession',return_value=session):
            await self.server._legacy_request_browser_link(True)
            await asyncio.wait_for(entered.wait(),1)
            pending=self.server.browser_link_status()
            self.assertFalse(pending['ready']);self.assertIsNone(pending['pairing_url'])
            release.set()
            await asyncio.wait_for(self.server._browser_link_task,1)
            self.assertTrue(self.server.browser_link_status()['ready'])
            await self.server.request_browser_link(False)
            self.assertFalse(self.server.browser_link_status()['ready'])
            gateway.close.assert_awaited()
            entered.clear();release.clear()
            await self.server._legacy_request_browser_link(True)
            await asyncio.wait_for(entered.wait(),1)
            task=self.server._browser_link_task
            await self.server.request_browser_link(False)
            self.assertTrue(task.done())
            self.assertFalse(self.server.browser_link_status()['ready'])

    async def test_local_control_outlives_bootstrap_but_disconnect_releases_input_and_preserves_lan(self):
        from server.local_link import ChannelSocket
        from types import SimpleNamespace
        self.config.update({'require_pin':True,'pin_code':'5678'})
        sent=[];channel=SimpleNamespace(readyState='open',bufferedAmount=0,send=sent.append,close=lambda:None)
        socket=ChannelSocket(channel)
        task=asyncio.create_task(self.server._serve_local(socket,'192.168.1.30'))
        await asyncio.sleep(0)
        socket.feed(json.dumps({'type':'auth','pin':'5678'}))
        for _ in range(100):
            await asyncio.sleep(.01)
            if any(json.loads(raw).get('success') for raw in sent):break
        client=self.server.clients[socket]
        self.assertTrue(client.authenticated);self.assertTrue(client.remote_secure)
        client.held_keys.add('ctrl')
        lan=await self.http.ws_connect('/ws');await lan.receive_json()
        await lan.send_json({'type':'auth','pin':'5678'});await self.receive_kind(lan,'auth_res')
        await self.server._browser_link_stopped()
        self.assertTrue(client.authenticated);self.assertFalse(socket.closed)
        await socket.close();await asyncio.wait_for(task,2)
        self.assertEqual(client.held_keys,set());self.native.key_up.assert_called_with('ctrl')
        await self.roundtrip(lan);await lan.close()

    async def test_pending_browser_link_cannot_disable_pin_over_lan_api(self):
        self.config.update({'require_pin':True,'pin_code':'5678'})
        self.server._browser_link_task=Mock()
        response=await self.http.post('/api/config',headers={'X-TouchHelm-Pin':'5678'},json={'require_pin':False})
        self.assertEqual(response.status,400)
        self.assertTrue(self.config.get('require_pin'))
        self.server._browser_link_task=None

    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.config = ConfigManager(os.path.join(self.folder.name, 'config.json'))
        self.native = Mock()
        self.native.get_volume.return_value = (50, False)
        self.native.get_brightness.return_value = 80
        self.native.get_screen_size.return_value = (1920, 1080)
        with patch('server.web_server.WindowsInputController', return_value=self.native), \
             patch('server.web_server.LaserOverlayClient'):
            self.server = TouchHelmServer(self.config)
        self.services = Mock()
        self.services.snapshot = AsyncMock(return_value={
            'presentation': {'available': True, 'title': 'Demo deck', 'slide': 3, 'total': 12},
            'media': {'available': False, 'message': 'No media session'}})
        self.services.list_apps = AsyncMock(return_value=[{'id': 'calculator', 'name': 'Calculator'}])
        self.services.launch_app = AsyncMock(return_value={'success': True, 'message': 'Opened Calculator'})
        self.services.list_media = AsyncMock(return_value={'sessions': [], 'items': [],
            'playlist_supported': False, 'playlist_message': 'No exposed queue'})
        self.services.close = AsyncMock()
        self.server.desktop_services = self.services
        app = web.Application()
        app.router.add_get('/ws', self.server.handle_ws)
        app.router.add_route('*', '/api/config', self.server.handle_config)
        self.http = TestClient(TestServer(app))
        await self.http.start_server()

    async def asyncTearDown(self):
        await self.http.close()
        self.folder.cleanup()

    async def connect(self):
        ws = await self.http.ws_connect('/ws')
        await ws.receive_json(timeout=1)
        return ws

    async def roundtrip(self, ws):
        await ws.send_json({'type': 'ping', 't': 1})
        reply = await ws.receive_json(timeout=1)
        self.assertEqual(reply['type'], 'pong')

    async def receive_kind(self, ws, kind):
        try:
            for _ in range(10):
                message = await ws.receive_json(timeout=1)
                if message.get('type') == kind:
                    return message
        except asyncio.TimeoutError:
            self.fail(f'Server did not deliver {kind}')
        self.fail(f'Server did not deliver {kind}')

    async def test_authenticated_app_catalog_and_launch_report_results(self):
        ws = await self.connect()
        await ws.send_json({'type': 'get_apps'})
        catalog = await self.receive_kind(ws, 'apps_sync')
        self.assertEqual(catalog['apps'][0]['name'], 'Calculator')
        await ws.send_json({'type': 'launch_app', 'app_id': 'calculator'})
        result = await self.receive_kind(ws, 'command_result')
        self.assertTrue(result['success'])
        self.assertEqual(result['command'], 'launch_app')
        self.services.launch_app.assert_awaited_once_with('calculator')

    async def test_desktop_state_and_real_media_catalog_reach_phone(self):
        ws = await self.connect()
        await ws.send_json({'type': 'get_desktop_state'})
        state = await self.receive_kind(ws, 'desktop_state')
        self.assertEqual(state['presentation']['slide'], 3)
        await ws.send_json({'type': 'get_media_library'})
        media = await self.receive_kind(ws, 'media_library')
        self.assertFalse(media['playlist_supported'])
        self.assertEqual(media['items'], [])

    async def test_slow_desktop_query_cannot_block_same_socket_pointer_input(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def delayed():
            started.set()
            await release.wait()
            return {'presentation': {}, 'media': {}}
        self.services.snapshot.side_effect = delayed
        ws = await self.connect()
        await ws.send_json({'type': 'get_desktop_state'})
        try:
            await asyncio.wait_for(started.wait(), .3)
        except asyncio.TimeoutError:
            self.fail('Desktop query was not dispatched')
        try:
            await ws.send_json({'type': 'move', 'dx': 8, 'dy': 2})
            await self.roundtrip(ws)
            self.native.move_rel.assert_called_once()
        finally:
            release.set()

    async def test_unauthenticated_catalog_and_launch_commands_never_reach_desktop(self):
        self.config.update({'require_pin': True, 'pin_code': '5678'})
        ws = await self.http.ws_connect('/ws')
        self.assertEqual((await ws.receive_json(timeout=1))['type'], 'auth_required')
        for packet in ({'type': 'get_apps'}, {'type': 'get_media_library'},
                       {'type': 'get_desktop_state'}, {'type': 'launch_app', 'app_id': 'calculator'}):
            await ws.send_json(packet)
            await self.roundtrip(ws)
        self.services.list_apps.assert_not_called()
        self.services.launch_app.assert_not_called()
        self.services.snapshot.assert_not_called()

    async def test_revoked_client_cannot_execute_a_queued_desktop_launch(self):
        from server.web_server import ConnectedClient
        socket = Mock()
        socket.closed = False
        socket.send_json = AsyncMock()
        client = ConnectedClient(socket, '1')
        client.authenticated = True
        self.server.clients[socket] = client
        await self.server._queue_desktop_request(client, {'type': 'launch_app', 'app_id': 'calculator'})
        client.authenticated = False
        await asyncio.sleep(.01)
        self.services.launch_app.assert_not_called()
        del self.server.clients[socket]

    async def test_desktop_overload_reports_busy_without_creating_more_jobs(self):
        release = asyncio.Event()
        async def delayed_launch(_app_id):
            await release.wait()
            return {'success': True, 'message': 'Opened'}
        self.services.launch_app.side_effect = delayed_launch
        ws = await self.connect()
        try:
            for _ in range(8):
                await ws.send_json({'type': 'launch_app', 'app_id': 'calculator'})
            await self.roundtrip(ws)
            self.assertEqual(len(self.server._service_tasks), 8)
            await ws.send_json({'type': 'launch_app', 'app_id': 'calculator'})
            result = await self.receive_kind(ws, 'command_result')
            self.assertFalse(result['success'])
            self.assertEqual(result['command'], 'launch_app')
            self.assertIn('busy', result['message'].lower())
            self.assertEqual(len(self.server._service_tasks), 8)
            self.assertEqual(self.services.launch_app.await_count, 8)
        finally:
            release.set()
            await asyncio.gather(*list(self.server._service_tasks), return_exceptions=True)

    async def test_volume_monitor_native_reads_leave_event_loop_responsive(self):
        # A thread releases each blocked mock after a safe deadline even on the
        # broken synchronous implementation, so this regression cannot hang.
        for blocked_read in (1, 2):
            with self.subTest(read=blocked_read):
                entered, release = threading.Event(), threading.Event()
                reads = 0
                def volume():
                    nonlocal reads
                    reads += 1
                    if reads == blocked_read:
                        entered.set()
                        release.wait(.4)
                    return (50, False)
                self.native.get_volume.side_effect = volume
                self.server.clients = {Mock(): Mock(authenticated=True)}
                monitor = asyncio.create_task(self.server._volume_monitor_loop())
                async def heartbeat():
                    while not entered.is_set():
                        await asyncio.sleep(.002)
                    started = time.monotonic()
                    await asyncio.sleep(.01)
                    self.assertFalse(release.is_set())
                    return time.monotonic() - started
                beat = asyncio.create_task(heartbeat())
                fallback = threading.Timer(.25 if blocked_read == 1 else .75, release.set)
                fallback.start()
                try:
                    elapsed = await asyncio.wait_for(beat, 1)
                    self.assertLess(elapsed, .15)
                finally:
                    release.set(); fallback.cancel()
                    monitor.cancel()
                    await asyncio.gather(monitor, beat, return_exceptions=True)
                    self.server.clients.clear()

    def test_catalog_command_fields_reject_structures_and_unbounded_ids(self):
        for packet in ({'type': 'launch_app', 'app_id': ['cmd.exe']},
                       {'type': 'play_media', 'item_id': {'path': 'cmd.exe'}},
                       {'type': 'media', 'session_id': 'x' * 1025}):
            self.assertFalse(TouchHelmServer._valid_packet(packet))

    async def test_bad_packets_do_not_disconnect_or_emit_input(self):
        ws = await self.connect()
        for packet in [[], None, {'type': 'move', 'dx': 'bad'},
                       {'type': 'move', 'dx': float('nan')},
                       {'type': 'ping', 't': 10 ** 500},
                       {'type': 'keydown', 'key': []},
                       {'type': 'hotkey', 'keys': 'ctrl'},
                       {'type': 'text', 'text': {}},
                       {'type': 'ping', 't': 'bad'}]:
            await ws.send_json(packet)
            await self.roundtrip(ws)
        self.native.move_rel.assert_not_called()
        self.native.key_down.assert_not_called()
        self.native.hotkey.assert_not_called()
        self.native.type_text.assert_not_called()

    async def test_disconnect_releases_held_input(self):
        ws = await self.connect()
        await ws.send_json({'type': 'mousedown', 'button': 'left'})
        await ws.send_json({'type': 'keydown', 'key': 'ctrl'})
        await self.roundtrip(ws)
        await ws.close()
        for _ in range(20):
            if not self.server.clients:
                break
            await asyncio.sleep(.01)
        self.native.mouse_up.assert_called_once_with('left')
        self.native.key_up.assert_called_once_with('ctrl')

    async def test_invalid_config_update_is_atomic(self):
        response = await self.http.post('/api/config', json={
            'scroll_speed': 1.7, 'mouse_sensitivity': 'bad'})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.config.get('scroll_speed'), 1.0)
        self.assertEqual(self.config.get('mouse_sensitivity'), 1.3)

    async def test_pin_blocks_input_and_config_until_authenticated(self):
        self.config.update({'require_pin': True, 'pin_code': '5678'})
        ws = await self.http.ws_connect('/ws')
        self.assertEqual((await ws.receive_json(timeout=1))['type'], 'auth_required')
        await ws.send_json({'type': 'move', 'dx': 20, 'dy': 10})
        await self.roundtrip(ws)
        self.native.move_rel.assert_not_called()
        response = await self.http.post('/api/config', json={'scroll_speed': 1.2})
        self.assertEqual(response.status, 401)
        for pin in ('wrong', '😀'):
            await ws.send_json({'type': 'auth', 'pin': pin})
            self.assertFalse((await ws.receive_json(timeout=1))['success'])
        await ws.send_json({'type': 'auth', 'pin': '5678'})
        auth = await ws.receive_json(timeout=1)
        self.assertTrue(auth['success'])
        self.assertNotIn('pin_code', auth['config'])
        await ws.send_json({'type': 'move', 'dx': 20, 'dy': 10})
        await self.roundtrip(ws)
        self.native.move_rel.assert_called_once()
        response = await self.http.get('/api/config', headers={'X-TouchHelm-Pin': '5678'})
        self.assertNotIn('pin_code', await response.json())

    async def test_pin_change_revokes_clients_and_releases_input(self):
        ws = await self.connect()
        await ws.send_json({'type': 'keydown', 'key': 'ctrl'})
        await self.roundtrip(ws)
        response = await self.http.post('/api/config', json={
            'require_pin': True, 'pin_code': '5678'})
        self.assertEqual(response.status, 200)
        self.assertEqual((await ws.receive_json(timeout=1))['type'], 'auth_required')
        self.native.key_up.assert_called_once_with('ctrl')
        await ws.send_json({'type': 'move', 'dx': 5})
        await self.roundtrip(ws)
        self.native.move_rel.assert_not_called()

    async def test_disconnect_does_not_release_other_clients_shared_hold(self):
        first, second = await self.connect(), await self.connect()
        for ws in (first, second):
            await ws.send_json({'type': 'mousedown', 'button': 'left'})
            await self.roundtrip(ws)
        await first.close()
        await self.roundtrip(second)
        self.native.mouse_up.assert_not_called()
        await second.send_json({'type': 'mouseup', 'button': 'left'})
        await self.roundtrip(second)
        self.native.mouse_up.assert_called_once_with('left')

    async def test_config_cors_preflight_allows_pin_header(self):
        response = await self.http.options('/api/config', headers={
            'Origin': 'http://another-pc:8765',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-touchhelm-pin'})
        self.assertEqual(response.status, 204)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], '*')
        self.assertIn('X-TouchHelm-Pin', response.headers['Access-Control-Allow-Headers'])

    async def test_server_stop_closes_sockets_and_awaits_monitor(self):
        ws = await self.connect()
        await ws.send_json({'type': 'mousedown', 'button': 'left'})
        await self.roundtrip(ws)
        monitor = asyncio.create_task(asyncio.sleep(60))
        await asyncio.sleep(0)
        self.server.volume_monitor_task = monitor
        await self.server.stop()
        self.assertTrue(monitor.done())
        self.assertFalse(self.server.clients)
        self.native.mouse_up.assert_called_once_with('left')


class NativeTests(unittest.TestCase):
    def test_interrupted_hotkey_releases_every_key_that_may_have_been_pressed(self):
        with patch.object(native.user32,'keybd_event') as events,patch.object(native.time,'sleep',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):self.controller().hotkey('ctrl','c')
        self.assertIn((0x11,0,2,0),[call.args for call in events.call_args_list])

    def test_interrupted_key_tap_still_attempts_key_release(self):
        with patch.object(native.user32,'keybd_event') as events,patch.object(native.time,'sleep',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):self.controller().key_tap('right')
        self.assertIn((0x27,0,3,0),[call.args for call in events.call_args_list])

    def controller(self):
        ctrl = native.WindowsInputController.__new__(native.WindowsInputController)
        ctrl.ensure_input_desktop = lambda: None
        return ctrl

    def test_emoji_emits_utf16_surrogate_pair(self):
        scans = []
        def capture(count, pointer, size):
            inputs = ctypes.cast(pointer, ctypes.POINTER(native.INPUT))
            scans.extend((inputs[i].i.ki.wScan, inputs[i].i.ki.dwFlags)
                         for i in range(count))
        with patch.object(native.user32, 'SendInput', side_effect=capture):
            self.controller().type_unicode_char('😀')
        self.assertEqual(scans, [(0xD83D, 4), (0xD83D, 6), (0xDE00, 4), (0xDE00, 6)])

    def test_hotkey_uses_extended_flags_for_windows_key(self):
        with patch.object(native.user32, 'keybd_event') as events, \
             patch.object(native.time, 'sleep'):
            self.controller().hotkey('win', 'd')
        self.assertEqual([call.args for call in events.call_args_list],
                         [(0x5B, 0, 1, 0), (0x44, 0, 0, 0),
                          (0x44, 0, 2, 0), (0x5B, 0, 3, 0)])


class LaserTests(unittest.TestCase):
    def test_first_update_preserves_selected_color(self):
        process = Mock()
        process.poll.return_value = None
        process.stdin = io.StringIO()
        client = LaserOverlayClient()
        with patch('subprocess.Popen', return_value=process):
            client.set_color('blue')
            client.update(.2, .3)
        commands = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
        self.assertEqual(commands[0], {'cmd': 'color', 'color': 'blue'})
        self.assertEqual(commands[1]['cmd'], 'update')


if __name__ == '__main__':
    unittest.main()
