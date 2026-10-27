"""The new default is real LAN HTTP, not a fabricated secure context."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock
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
