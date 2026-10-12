"""Remote session authority and coordinate mapping. No real PC effects."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from server.remote_service import RemoteService, absolute_point, private_sdp


class RemoteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = {'remote_enabled': True, 'require_pin': True}
        self.client = SimpleNamespace(authenticated=True, ws=SimpleNamespace(closed=False), device_name='Phone')
        self.other = SimpleNamespace(authenticated=True, ws=SimpleNamespace(closed=False), device_name='Other')
        self.worker = Mock(start=AsyncMock(), offer=AsyncMock(return_value={'type':'answer','sdp':'answer'}),
                           stop=AsyncMock(), configure=AsyncMock())
        self.display = {'id':'display-1','name':'Left','rect':{'x':-1920,'y':-200,'width':1920,'height':1080}}
        self.release, self.input = Mock(), Mock()
        self.service = RemoteService(self.config, AsyncMock(return_value={'displays':[self.display]}),
            lambda **kw:self.worker, self.release, self.input,
            capabilities=lambda:{'video':True,'audio':True})

    async def start(self, mode='control'):
        result=await self.service.request(self.client, {'type':'remote_start','mode':mode}, True)
        if result['success']:self.service.state='live' # Simulate the worker's connected event.
        return result

    async def test_requires_host_enable_pin_and_secure_transport(self):
        for field in ('remote_enabled','require_pin'):
            self.config[field] = False
            self.assertFalse((await self.start())['success'])
            self.config[field] = True
        self.assertFalse((await self.service.request(self.client, {'type':'remote_start'}, False))['success'])
        self.client.authenticated = False
        self.assertFalse((await self.start())['success'])
        self.worker.start.assert_not_awaited()

    async def test_single_session_and_wrong_owner_stop(self):
        result = await self.start()
        self.assertTrue(result['success'])
        self.assertFalse((await self.service.request(self.other, {'type':'remote_start'}, True))['success'])
        self.assertFalse((await self.service.request(self.other, {'type':'remote_stop','session_id':result['session_id']}, True))['success'])
        self.worker.stop.assert_not_awaited()
        await self.service.stop('done')

    async def test_view_rejects_input_and_switch_releases(self):
        result = await self.start()
        sid = result['session_id']
        await self.service.request(self.client, {'type':'remote_config','session_id':sid,'mode':'view'}, True)
        self.release.assert_called_with(self.client)
        self.assertFalse(self.service.accept_input(self.client, {'session_id':sid,'revision':result['revision']}))
        self.assertFalse(self.service.blocks_input(self.other))
        await self.service.stop('done')

    async def test_input_lease_and_stale_geometry(self):
        result = await self.start()
        packet = {'session_id':result['session_id'],'revision':result['revision']}
        self.assertTrue(self.service.blocks_input(self.other))
        self.assertTrue(self.service.accept_input(self.client, packet))
        self.assertFalse(self.service.accept_input(self.other, packet))
        self.assertFalse(self.service.accept_input(self.client, dict(packet, revision='old')))
        self.assertEqual(self.service.point(self.client, dict(packet,x=0,y=1)), (-1920,879))
        for x in (-.1,1.1,float('nan'),True,'0'):
            self.assertIsNone(self.service.point(self.client,dict(packet,x=x,y=.5)))
        await self.service.stop('done')

    async def test_stale_session_and_removed_monitor(self):
        result=await self.start()
        self.assertFalse((await self.service.request(self.client,{'type':'remote_offer','session_id':'stale','sdp':'offer'},True))['success'])
        self.service.displays.return_value={'displays':[]}
        self.assertFalse((await self.service.request(self.client,{'type':'remote_config','session_id':result['session_id'],'quality':'clear'},True))['success'])
        self.assertIsNone(self.service.owner)

    async def test_failed_worker_releases_reservation(self):
        self.worker.start.side_effect = RuntimeError('capture unavailable')
        result = await self.start()
        self.assertFalse(result['success'])
        self.assertIsNone(self.service.owner)
        self.worker.stop.assert_awaited()

    async def test_disconnect_while_starting_cannot_restore_session(self):
        async def fail_auth(*args, **kwargs):
            self.client.authenticated=False
        self.worker.start.side_effect=fail_auth
        self.assertFalse((await self.start())['success'])
        self.assertIsNone(self.service.owner)

    async def test_disable_during_monitor_lookup_cannot_start_capture(self):
        async def lookup():
            self.config['remote_enabled']=False
            return {'displays':[self.display]}
        self.service.displays.side_effect=lookup
        self.assertFalse((await self.start())['success'])
        self.worker.start.assert_not_awaited()

    async def test_disable_during_capture_start_cannot_restore_session(self):
        async def start_capture(*args):self.config['remote_enabled']=False
        self.worker.start.side_effect=start_capture
        self.assertFalse((await self.start())['success'])
        self.assertIsNone(self.service.owner)

    async def test_audio_unavailable_does_not_prevent_video(self):
        self.service.capabilities=lambda:{'video':True,'audio':False}
        result=await self.service.request(self.client,{'type':'remote_start','audio':True},True)
        self.assertTrue(result['success'])
        self.assertFalse(result['audio'])
        await self.service.stop('done')

    async def test_audio_config_uses_worker_readback_on_driver_failure(self):
        result=await self.start()
        self.worker.configure.return_value={'audio':False,'message':'Audio device unavailable.'}
        response=await self.service.request(self.client,{'type':'remote_config','session_id':result['session_id'],'audio':True},True)
        self.assertTrue(response['success'])
        self.assertFalse(response['audio'])
        self.assertIn('unavailable',response['message'])

    async def test_worker_construction_failure_does_not_leave_owner(self):
        self.service.worker_factory=Mock(side_effect=RuntimeError('worker thread could not start'))
        self.assertFalse((await self.start())['success'])
        self.assertIsNone(self.service.owner)

    async def test_pause_releases_and_closes_worker(self):
        result=await self.start()
        await self.service.request(self.client,{'type':'remote_pause','session_id':result['session_id']},True)
        self.assertIsNone(self.service.owner)
        self.release.assert_called_with(self.client)
        self.worker.stop.assert_awaited_once()

    async def test_control_acquisition_releases_other_app_owned_inputs(self):
        self.service.before_control=Mock()
        await self.start()
        self.service.before_control.assert_called_once()

    async def test_new_session_cannot_reuse_capture_while_old_worker_stops(self):
        import asyncio
        await self.start()
        closing=asyncio.Event();finish=asyncio.Event()
        async def slow_stop():closing.set();await finish.wait()
        self.worker.stop.side_effect=slow_stop
        task=asyncio.create_task(self.service.stop('closing'))
        await closing.wait()
        result=await self.service.request(self.other,{'type':'remote_start'},True)
        self.assertFalse(result['success'])
        finish.set();await task

    async def test_cleanup_failure_blocks_new_capture_and_reports_restart(self):
        await self.start();self.worker.stop.side_effect=RuntimeError('driver refused cleanup')
        await self.service.stop('done')
        self.assertIsNone(self.service.owner)
        self.assertEqual(self.service.state,'unavailable')
        self.assertIn('Restart',self.service.message)
        self.assertFalse((await self.service.request(self.other,{'type':'remote_start'},True))['success'])

    def test_pixel_mapping_negative_origins_and_no_outside_pixels(self):
        self.assertEqual(absolute_point(self.display['rect'],1,0),(-1,-200))
        self.assertEqual(absolute_point(self.display['rect'],.5,.5),(-960,340))

    def test_ice_candidates_restrict_media_to_private_paths(self):
        def offer(ip):return 'v=0\r\na=candidate:1 1 UDP 123 '+ip+' 5000 typ host\r\n'
        for ip in ('192.168.1.5','100.90.1.2','127.0.0.1','fd7a:115c:a1e0::1','peer.local'):
            self.assertIn('a=candidate',private_sdp(offer(ip)))
        for ip in ('8.8.8.8','224.1.1.1','0.0.0.0','example.com'):
            with self.assertRaises(ValueError):private_sdp(offer(ip))

    async def test_sdp_and_options_validation(self):
        for packet in ({'mode':'invalid'},{'quality':'huge'},{'audio':'true'}):
            self.assertFalse((await self.service.request(self.client,dict(type='remote_start',**packet),True))['success'])
        self.assertIsNone(self.service.owner)

    async def asyncTearDown(self):
        await self.service.stop('test complete')
