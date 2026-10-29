"""The new default is real LAN HTTP, not a fabricated secure context."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from server.remote_service import RemoteService
from server.local_network import lan_pair


class LocalModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_local_transport_can_receive_media_without_https(self):
        config={'remote_enabled':True,'require_pin':True}
        client=SimpleNamespace(authenticated=True,ws=SimpleNamespace(closed=False),local_lan=True,remote_ip='192.168.1.20',device_name='Phone')
        worker=Mock(start=AsyncMock(),stop=AsyncMock())
        service=RemoteService(config,AsyncMock(),lambda **kw:worker,Mock(),Mock(),capabilities=lambda:{'audio':True,'video':True})
        result=await service.request(client,{'type':'remote_start','mode':'audio'},secure=False,local=True)
        self.assertTrue(result['success'],result.get('message'))
        await service.stop()

    async def test_private_ip_alone_does_not_grant_local_media(self):
        config={'remote_enabled':True,'require_pin':True}
        client=SimpleNamespace(authenticated=True,ws=SimpleNamespace(closed=False),local_lan=False,remote_ip='192.168.1.20')
        service=RemoteService(config,AsyncMock(),Mock(),Mock(),Mock(),capabilities=lambda:{'audio':True})
        result=await service.request(client,{'type':'remote_start','mode':'audio'},secure=False,local=True)
        self.assertFalse(result['success'])

    def test_lan_policy_excludes_public_peer_foreign_subnet_and_vpn(self):
        self.assertTrue(lan_pair('192.168.1.2','192.168.1.20',['192.168.1.0/24']))
        for peer in ('8.8.8.8','192.168.2.20','100.100.1.2','127.0.0.1'):
            self.assertFalse(lan_pair('192.168.1.2',peer,['192.168.1.0/24']))

    def test_media_guard_uses_actual_nominated_peer_not_sdp_claims(self):
        import server.remote_media as media
        self.assertTrue(hasattr(media,'media_peer_matches'))
        candidate=SimpleNamespace(host='192.168.1.20')
        connection=SimpleNamespace(_nominated={1:SimpleNamespace(remote_candidate=candidate)})
        transceiver=SimpleNamespace(sender=SimpleNamespace(transport=SimpleNamespace(transport=SimpleNamespace(_connection=connection))))
        pc=SimpleNamespace(getTransceivers=lambda:[transceiver])
        self.assertTrue(media.media_peer_matches(pc,'192.168.1.20'))
        candidate.host='192.168.1.99';self.assertFalse(media.media_peer_matches(pc,'192.168.1.20'))
        connection._nominated={};self.assertFalse(media.media_peer_matches(pc,'192.168.1.20'))

    def test_same_pc_browser_can_use_another_actual_local_adapter(self):
        from server.remote_media import media_peer_matches
        candidate=SimpleNamespace(host='192.168.56.1')
        ice=SimpleNamespace(_nominated={1:SimpleNamespace(remote_candidate=candidate)})
        transceiver=SimpleNamespace(sender=SimpleNamespace(transport=SimpleNamespace(transport=SimpleNamespace(_connection=ice))))
        pc=SimpleNamespace(getTransceivers=lambda:[transceiver])
        with patch('server.discovery.get_local_ip_addresses',return_value=['192.168.1.2','192.168.56.1']):
            self.assertTrue(media_peer_matches(pc,'192.168.1.2'))
            self.assertFalse(media_peer_matches(pc,'192.168.1.20'))
