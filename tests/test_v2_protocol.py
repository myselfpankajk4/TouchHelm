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
    def test_pin_failures_have_global_backoff_even_through_shared_loopback(self):
        with patch('server.web_server.time.monotonic', return_value=1000):
            for _ in range(8):self.assertFalse(self.server._pin_matches('0000'))
            self.assertFalse(self.server._pin_matches('5678'))
        with patch('server.web_server.time.monotonic', return_value=1061):
            self.assertTrue(self.server._pin_matches('5678'))

    async def test_local_tls_cannot_impersonate_private_proxy_to_consume_handoff(self):
        origin = self.server.tailscale_origin = 'https://pc.example.ts.net:8443'
        self.server._handoffs['transfer'] = {'expires': time.monotonic()+60,
            'ip': '192.168.1.8', 'target': origin, 'cross_transport': True,
            'data': {'draft': 'private'}}
        request = Mock(method='GET', scheme='https', host='pc.example.ts.net:8443',
            remote='192.168.1.9', headers={'X-TouchHelm-Pin':'5678'},
            query={'token':'transfer'})
        request.transport.get_extra_info.return_value = ('192.168.1.12', 8766)
        response = await self.server.handle_handoff(request)
        self.assertEqual(response.status, 403)
        self.assertIn('transfer', self.server._handoffs)

    async def test_backend_bind_failure_never_configures_serve(self):
        self.server.tailscale.inspect=Mock(return_value={'state':'setup_required','host':'pc.example.ts.net','ready':False})
        self.server.tailscale.enable=Mock()
        with patch('server.web_server.web.TCPSite') as site:
            site.return_value.start=AsyncMock(side_effect=OSError('port occupied'))
            with self.assertRaises(OSError):await self.server.enable_tailscale()
        self.server.tailscale.enable.assert_not_called()
        self.assertIsNone(self.server.tailscale_origin)

    async def test_private_listener_rejects_wrong_host_and_phone_config_cannot_enable(self):
        self.server.tailscale_origin='https://pc.example.ts.net:8443'
        request=Mock(host='attacker.invalid',scheme='http',remote='127.0.0.1',headers={})
        request.transport.get_extra_info.return_value=('127.0.0.1',8767)
        handler=AsyncMock()
        response=await self.server._private_transport(request,handler)
        self.assertEqual(response.status,403);handler.assert_not_awaited()
        request=Mock(method='POST',headers={'X-TouchHelm-Pin':'5678'},json=AsyncMock(return_value={'tailscale_enabled':True}))
        response=await self.server.handle_config(request)
        self.assertEqual(response.status,400);self.assertFalse(self.config.get('tailscale_enabled'))

    async def test_local_ca_transfer_stays_ip_bound_and_expires_after_sixty_seconds(self):
        self.server.https_site=Mock()
        response=await self.client.post('/api/pairing/handoff',json={'draft':'never replay'},headers={'X-TouchHelm-Pin':'5678'})
        token=(await response.json())['token'];stored=self.server._handoffs[token]
        self.assertIsNone(self.server.consume_handoff(token,'192.168.1.99',stored['target']))
        with patch('server.web_server.time.monotonic',return_value=stored['expires']):
            self.assertIsNone(self.server.consume_handoff(token,'127.0.0.1',stored['target']))
        self.assertNotIn(token,self.server._handoffs)

    async def test_close_result_preserves_identity_and_request_confirmation(self):
        self.services.app_action=AsyncMock(return_value={'success':True,'requested':True,'confirmed':False,'message':'Close requested'})
        socket=Mock();socket.closed=False;socket.send_json=AsyncMock()
        client=ConnectedClient(socket,'127.0.0.1');client.authenticated=True;self.server.clients[socket]=client
        await self.server._desktop_request(client,{'type':'app_action','action':'close','app_id':'app-a','window_id':'window-a'})
        reply=socket.send_json.call_args.args[0]
        self.assertEqual(reply.get('window_id'),'window-a');self.assertEqual(reply.get('app_id'),'app-a');self.assertEqual(reply.get('action'),'close')
        self.assertTrue(reply.get('requested'));self.assertIs(reply.get('confirmed'),False)

    async def test_tailscale_handoff_exact_origin_fresh_pin_baseline_and_changed_ip(self):
        self.assertTrue(hasattr(self.server,'tailscale_origin'), 'Server must isolate private HTTPS transport')
        self.server.tailscale_origin='https://pc.example.ts.net:8443'
        response=await self.client.post('/api/pairing/handoff',json={'target_origin':self.server.tailscale_origin,'draft':'unsent','live_baseline':'sent','preferences':{'effects':'calm','live_typing':True}},headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,200); token=(await response.json())['token']
        self.assertIsNone(self.server.consume_handoff(token,'100.20.30.40','https://wrong.ts.net:8443'))
        # A rejected destination does not consume the legitimate transfer.
        value=self.server.consume_handoff(token,'100.20.30.40',self.server.tailscale_origin)
        self.assertEqual(value['live_baseline'],'sent');self.assertEqual(value['preferences']['effects'],'calm')
        self.assertIsNone(self.server.consume_handoff(token,'100.20.30.40',self.server.tailscale_origin))
        response=await self.client.get('/api/pairing/handoff?token=x')
        self.assertEqual(response.status,401)

    async def test_handoff_rejects_arbitrary_target_and_cross_origin_posts(self):
        self.server.https_site=Mock()
        for payload,headers in (({'target_origin':'https://attacker.invalid'},{}), ({},{'Origin':'http://attacker.invalid'})):
            response=await self.client.post('/api/pairing/handoff',json=payload,headers={'X-TouchHelm-Pin':'5678',**headers})
            self.assertIn(response.status,(400,403))
        self.assertFalse(self.server._handoffs)

    def test_only_loopback_backend_exact_host_can_assert_private_https(self):
        self.assertTrue(hasattr(self.server,'request_origin'), 'Proxy transport must be checked')
        self.server.tailscale_origin='https://pc.example.ts.net:8443'
        request=Mock(host='pc.example.ts.net:8443',scheme='http',remote='127.0.0.1',headers={'X-Forwarded-Proto':'https'})
        request.transport.get_extra_info.return_value=('127.0.0.1',8767)
        self.assertEqual(self.server.request_origin(request),self.server.tailscale_origin)
        request.transport.get_extra_info.return_value=('192.168.1.12',8765)
        self.assertEqual(self.server.request_origin(request),'http://pc.example.ts.net:8443')
        request.transport.get_extra_info.return_value=('127.0.0.1',8767);request.host='attacker.invalid'
        self.assertEqual(self.server.request_origin(request),'http://attacker.invalid')

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
        app.router.add_route('*','/api/pairing/handoff',self.server.handle_handoff)
        app.router.add_get('/api/pairing',self.server.handle_pairing)
        app.router.add_get('/preview/desktop/',self.server.handle_desktop_preview)
        app.router.add_get('/preview/desktop/{path:.*}',self.server.handle_desktop_preview)
        app.router.add_get('/ws',self.server.handle_ws)
        self.client=TestClient(TestServer(app));await self.client.start_server();self.addAsyncCleanup(self.client.close)

    async def test_desktop_preview_is_fixture_and_never_serves_private_or_native_files(self):
        response=await self.client.get('/preview/desktop/');self.assertEqual(response.status,200)
        source=await response.text();self.assertIn('__TOUCHHELM_DESKTOP_PREVIEW__',source);self.assertIn('preview-disabled',source)
        for path in ('desktop.js','themes/glass.css'):
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

    async def test_handoff_requires_auth_and_never_transfers_pin_or_oversize_draft(self):
        self.server.https_site=Mock()
        response=await self.client.post('/api/pairing/handoff',json={'draft':'keep'})
        self.assertEqual(response.status,401)
        response=await self.client.post('/api/pairing/handoff',json={'draft':'keep\nme','preferences':{'theme':'clay','pin_code':'5678'}},headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,200);token=(await response.json())['token']
        self.assertNotIn('5678',json.dumps(self.server._handoffs[token]))
        self.assertEqual(self.server.consume_handoff(token,'127.0.0.1')['draft'],'keep\nme')
        self.assertIsNone(self.server.consume_handoff(token,'127.0.0.1'))
        response=await self.client.post('/api/pairing/handoff',json={'draft':'x'*10001},headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,400)

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

    async def test_failed_ca_preparation_returns_pairing_state_instead_of_500(self):
        self.server.secure_pairing=Mock()
        self.server.secure_pairing.public_info.side_effect=FileNotFoundError('no CA yet')
        response=await self.client.get('/api/pairing',headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,200)
        state=await response.json()
        self.assertFalse(state['enabled'])
        self.assertFalse(state['certificate_available'])

    async def test_handoff_unsupported_verbs_do_not_mint_transfer(self):
        self.server.https_site=Mock()
        response=await self.client.put('/api/pairing/handoff',json={'draft':'keep'},headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,405)
        self.assertEqual(self.server._handoffs,{})

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
