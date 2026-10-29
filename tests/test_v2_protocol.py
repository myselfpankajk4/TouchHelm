"""Authenticated assets and one-use pairing payloads; no Windows mutations."""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from server.config import ConfigManager
from server.web_server import TouchHelmServer, ConnectedClient

class V2ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_aircontrol_blocks_phone_input_without_disconnect_or_camera_endpoint(self):
        self.server.aircontrol.owns_input=True
        socket=await self.client.ws_connect('/ws');await socket.receive_json()
        await socket.send_json({'type':'auth','pin':'5678'})
        self.assertEqual((await socket.receive_json())['input_owner'],'aircontrol')
        await socket.send_json({'type':'move','dx':10,'dy':0})
        self.assertFalse((await socket.receive_json())['success'])
        self.server.input_ctrl.move_rel.assert_not_called()
        await socket.send_json({'type':'ping','t':1})
        self.assertEqual((await socket.receive_json())['type'],'pong')
        await socket.send_json({'type':'aircontrol','action':'start'})
        self.assertFalse((await socket.receive_json())['success'])
        self.assertIsNone(self.server.aircontrol.worker)
        self.server.aircontrol.owns_input=False;await socket.close()

    async def test_aircontrol_transfer_keeps_remote_stream_and_audio(self):
        owner=ConnectedClient(Mock(closed=False),'127.0.0.1')
        self.server.remote.owner=owner;self.server.remote.mode='control';self.server.remote.audio=True
        self.server.remote.worker=Mock();worker=self.server.remote.worker
        self.server.remote._publish=Mock()
        await self.server._air_acquire()
        self.assertEqual(self.server.remote.mode,'view');self.assertTrue(self.server.remote.audio)
        self.assertIs(self.server.remote.worker,worker);worker.stop.assert_not_called()
        self.server.remote.owner=None;self.server.remote.worker=None
    async def test_text_sync_requires_pin_and_a_field_seen_by_this_client(self):
        socket=Mock(closed=False);socket.send_json=AsyncMock()
        client=ConnectedClient(socket,'127.0.0.1');client.authenticated=True
        self.server.clients[socket]=client
        self.server.text_service=Mock(request=AsyncMock(return_value={'available':True,
            'field_id':'opaque','revision':'r1','text':'PC text','editable':True}))
        await self.server._text_request(client,{'type':'text_sync','action':'write','field_id':'other','revision':'r1','text':'phone','request_id':1})
        self.server.text_service.request.assert_not_awaited()
        await self.server._text_request(client,{'type':'text_sync','action':'read','request_id':2})
        self.assertEqual(client.text_field_id,'opaque')
        await self.server._text_request(client,{'type':'text_sync','action':'write','field_id':'opaque','revision':'r1','text':'phone','request_id':3})
        self.assertEqual(self.server.text_service.request.await_count,2)
        self.config.set('require_pin',False)
        await self.server._text_request(client,{'type':'text_sync','action':'read','request_id':4})
        self.assertEqual(self.server.text_service.request.await_count,2)
        self.assertFalse(socket.send_json.call_args.args[0]['available'])

    def test_text_sync_packet_validation(self):
        for packet in ({'action':'execute'}, {'action':'write','text':None},
                {'action':'write','text':'x'*10001}, {'action':'read','request_id':True}):
            self.assertFalse(self.server._valid_packet({'type':'text_sync',**packet}))

    async def test_reads_identify_a_previously_committed_write_without_replaying_it(self):
        socket=Mock(closed=False);socket.send_json=AsyncMock()
        client=ConnectedClient(socket,'127.0.0.1');client.authenticated=True
        client.text_field_id='field';client.text_revision='r1'
        self.server.clients[socket]=client
        self.server.text_service=Mock(request=AsyncMock(return_value={
            'available':True,'field_id':'field','revision':'r2','text':'a'}))
        await self.server._text_request(client,{'action':'write','field_id':'field',
            'revision':'r1','text':'a','request_id':10})
        self.server.text_service.request.return_value={
            'available':True,'field_id':'field','revision':'r3','text':'a PC'}
        await self.server._text_request(client,{'action':'read','request_id':11})
        self.assertEqual(socket.send_json.call_args.args[0].get('acknowledged_write'),10)
        self.server.text_service.request.return_value={
            'available':True,'field_id':'other','revision':'r4','text':'other'}
        await self.server._text_request(client,{'action':'read','request_id':12})
        self.assertNotIn('acknowledged_write',socket.send_json.call_args.args[0])

    async def test_text_state_is_private_to_the_requesting_authenticated_socket(self):
        self.server.text_service=Mock(request=AsyncMock(return_value={'available':True,
            'field_id':'opaque','revision':'r1','text':'scratch text','editable':True}))
        first=await self.client.ws_connect('/ws');await first.receive_json()
        await first.send_json({'type':'text_sync','action':'read','request_id':1})
        await first.send_json({'type':'ping','t':1});self.assertEqual((await first.receive_json())['type'],'pong')
        self.server.text_service.request.assert_not_awaited()
        second=await self.client.ws_connect('/ws');await second.receive_json()
        for ws in (first,second):
            await ws.send_json({'type':'auth','pin':'5678'});await ws.receive_json()
        await first.send_json({'type':'text_sync','action':'read','request_id':2})
        self.assertEqual((await first.receive_json())['text'],'scratch text')
        await second.send_json({'type':'ping','t':2})
        self.assertEqual((await second.receive_json())['type'],'pong')
        await second.send_json({'type':'text_sync','action':'write','field_id':'opaque','revision':'r1','text':'unbound','request_id':3})
        self.assertFalse((await second.receive_json())['available'])
        self.assertEqual(self.server.text_service.request.await_count,1)
        await first.close();await second.close()

    def test_empty_discovery_credentials_do_not_lock_out_refreshes(self):
        for _ in range(30):
            self.assertFalse(self.server._pin_matches(''))
            self.assertFalse(self.server._pin_matches(None))
        self.assertEqual(self.server._pin_failures, [])
        self.assertTrue(self.server._pin_matches('5678'))

    def test_pin_failures_have_global_backoff_even_through_shared_loopback(self):
        with patch('server.web_server.time.monotonic', return_value=1000):
            for _ in range(8):self.assertFalse(self.server._pin_matches('0000'))
            self.assertFalse(self.server._pin_matches('5678'))
        with patch('server.web_server.time.monotonic', return_value=1061):
            self.assertTrue(self.server._pin_matches('5678'))

    async def test_close_result_preserves_identity_and_request_confirmation(self):
        self.services.app_action=AsyncMock(return_value={'success':True,'requested':True,'confirmed':False,'message':'Close requested'})
        socket=Mock();socket.closed=False;socket.send_json=AsyncMock()
        client=ConnectedClient(socket,'127.0.0.1');client.authenticated=True;self.server.clients[socket]=client
        await self.server._desktop_request(client,{'type':'app_action','action':'close','app_id':'app-a','window_id':'window-a'})
        reply=socket.send_json.call_args.args[0]
        self.assertEqual(reply.get('window_id'),'window-a');self.assertEqual(reply.get('app_id'),'app-a');self.assertEqual(reply.get('action'),'close')
        self.assertTrue(reply.get('requested'));self.assertIs(reply.get('confirmed'),False)

    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.config=ConfigManager(str(Path(self.folder.name)/'config.json'))
        self.config.update({'require_pin':True,'pin_code':'5678'})
        self.services=Mock();self.services.assets.get.return_value=b'\x89PNG\r\n\x1a\nfixture'
        with patch('server.web_server.WindowsInputController'),patch('server.web_server.LaserOverlayClient'),patch('server.web_server.DesktopServices',return_value=self.services):
            self.server=TouchHelmServer(self.config)
        self.server.input_ctrl.get_volume.return_value=(None,None)
        self.server.input_ctrl.get_brightness.return_value=None
        app=web.Application()
        app.router.add_get('/api/assets/{asset_id}',self.server.handle_asset)
        app.router.add_get('/preview/desktop/',self.server.handle_desktop_preview)
        app.router.add_get('/preview/desktop/{path:.*}',self.server.handle_desktop_preview)
        app.router.add_get('/ws',self.server.handle_ws)
        app.router.add_route('*','/api/config',self.server.handle_config)
        self.client=TestClient(TestServer(app));await self.client.start_server();self.addAsyncCleanup(self.client.close)

    async def test_desktop_preview_is_fixture_and_never_serves_private_or_native_files(self):
        response=await self.client.get('/preview/desktop/');self.assertEqual(response.status,200)
        source=await response.text();self.assertIn('__TOUCHHELM_DESKTOP_PREVIEW__',source);self.assertIn('preview-disabled',source)
        for path in ('desktop.js','themes/aurora.css'):
            response=await self.client.get('/preview/desktop/'+path);self.assertEqual(response.status,200)
        for path in ('config.json','webview_window.py','server.key'):
            response=await self.client.get('/preview/desktop/'+path);self.assertEqual(response.status,404)

    async def test_private_assets_require_pin_and_valid_server_catalog_id(self):
        response=await self.client.get('/api/assets/'+'a'*32)
        self.assertEqual(response.status,401);self.services.assets.get.assert_not_called()
        response=await self.client.get('/api/assets/'+'a'*32,headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,200);self.assertEqual(response.content_type,'image/png')
        self.services.assets.get.return_value=None
        response=await self.client.get('/api/assets/arbitrary-path',headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,404)

    async def test_phone_cannot_enable_remote_even_with_valid_pin(self):
        response=await self.client.post('/api/config',json={'remote_enabled':True},headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,400)
        self.assertFalse(self.config.get('remote_enabled'))

    def test_newline_and_zoom_protocol_reject_invalid_values(self):
        self.assertFalse(self.server._valid_packet({'type':'text','text':'x','newline_mode':'run shell'}))
        self.assertFalse(self.server._valid_packet({'type':'zoom','delta':float('nan')}))
        self.assertTrue(self.server._valid_packet({'type':'zoom','delta':1}))
        for action,value in [('seek',float('nan')),('seek',True),('rate',0),('shuffle',1),('repeat','anything')]:
            self.assertFalse(self.server._valid_packet({'type':'media','action':action,'value':value}))
        self.assertTrue(self.server._valid_packet({'type':'media','action':'seek','value':42}))

    async def test_advanced_media_reaches_provider_and_returns_confirmation(self):
        self.services.media_command=AsyncMock(return_value={'success':True,'handled':True,'message':'Requested'})
        ws=await self.client.ws_connect('/ws')
        await ws.receive_json()
        await ws.send_json({'type':'auth','pin':'5678'})
        await ws.receive_json()
        await ws.send_json({'type':'media','action':'seek','session_id':'player','value':42})
        try:
            reply=await asyncio.wait_for(ws.receive_json(),.2)
        except asyncio.TimeoutError:
            reply=None
        await ws.close()
        self.assertIsNotNone(reply,'Advanced media was silently dropped instead of confirming the provider result')
        self.assertEqual(reply['type'],'command_result')
        self.services.media_command.assert_awaited_once_with('seek',session_id='player',value=42)
        self.server.input_ctrl.media_action.assert_not_called()

    async def test_pin_revocation_hides_active_laser(self):
        socket=Mock();socket.closed=False;socket.send_json=AsyncMock()
        client=ConnectedClient(socket,'127.0.0.1');client.authenticated=True
        self.server.clients[socket]=client
        await self.server.invalidate_auth_sessions()
        self.server.laser_client.hide.assert_called_once()

    async def test_failed_reauthentication_hides_laser_before_socket_disconnect(self):
        ws=await self.client.ws_connect('/ws')
        await ws.receive_json()
        await ws.send_json({'type':'auth','pin':'5678'});await ws.receive_json()
        await ws.send_json({'type':'auth','pin':'9999'})
        reply=await ws.receive_json()
        self.assertFalse(reply['success'])
        self.server.laser_client.hide.assert_called_once()
        await ws.close()

    async def test_initial_auth_audio_read_does_not_block_event_loop(self):
        def slow_read():
            time.sleep(.12)
            return None,None
        self.server.input_ctrl.get_volume.side_effect=slow_read
        socket=Mock();socket.send_json=AsyncMock()
        client=ConnectedClient(socket,'127.0.0.1')
        task=asyncio.create_task(self.server._send_auth_success(client))
        await asyncio.sleep(0)
        responsive=not task.done()
        await task
        self.assertTrue(responsive,'Auth readback ran synchronously on the input event loop')

    async def test_revoked_auth_cannot_emit_stale_success_after_audio_read(self):
        socket=Mock();socket.closed=False;socket.send_json=AsyncMock()
        client=ConnectedClient(socket,'127.0.0.1');client.authenticated=True
        def revoked_read():
            client.authenticated=False
            return None,None
        self.server.input_ctrl.get_volume.side_effect=revoked_read
        await self.server._send_auth_success(client)
        socket.send_json.assert_not_called()

    async def test_brightness_worker_readback_is_broadcast_after_pending_unknown(self):
        self.server.clients={object():Mock(authenticated=True)}
        broadcasts=[]
        done=asyncio.Event()
        async def broadcast(message):
            broadcasts.append(message)
            if message.get('type')=='brightness_sync':done.set()
        self.server.broadcast=broadcast
        self.server.input_ctrl.get_volume.return_value=(None,None)
        self.server.input_ctrl.get_brightness.side_effect=[None,69]
        monitor=asyncio.create_task(self.server._volume_monitor_loop())
        try:
            try:await asyncio.wait_for(done.wait(),.8)
            except asyncio.TimeoutError:pass
        finally:
            monitor.cancel();await monitor
        self.assertIn({'type':'brightness_sync','level':69},broadcasts)

if __name__=='__main__':unittest.main()
