"""Local transport security. No real input or public listeners."""
import asyncio
import base64
import hashlib
import hmac
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock


class ProofTests(unittest.TestCase):
    def test_hmac_binds_stage_nonce_and_exact_sdp(self):
        from server.local_link import verify_proof, make_proof
        secret='s'*43;nonce='n'*43;sdp='v=0\r\na=fingerprint:sha-256 AA:BB\r\n'
        proof=make_proof(secret,'answer',nonce,sdp)
        self.assertTrue(verify_proof(secret,'answer',nonce,sdp,proof))
        for stage,n,text in [('offer',nonce,sdp),('answer','x'*43,sdp),('answer',nonce,sdp+'x')]:
            self.assertFalse(verify_proof(secret,stage,n,text,proof))
        for bad in (None,[],{},False,'x'*10000):self.assertFalse(verify_proof(secret,'answer',nonce,sdp,bad))

    def test_selected_peer_must_be_on_a_local_adapter_subnet(self):
        from server.local_link import local_peer_address
        def peer(host):
            connection=SimpleNamespace(_nominated={1:SimpleNamespace(remote_candidate=SimpleNamespace(host=host))})
            ice=SimpleNamespace(_connection=connection)
            return SimpleNamespace(sctp=SimpleNamespace(transport=SimpleNamespace(transport=ice)))
        self.assertEqual(local_peer_address(peer('192.168.2.8'),['192.168.2.0/24']),'192.168.2.8')
        for host in ('8.8.8.8','192.168.3.8','127.0.0.1','::1','example.com'):
            self.assertIsNone(local_peer_address(peer(host),['192.168.2.0/24']))
        self.assertIsNone(local_peer_address(SimpleNamespace(),['192.168.2.0/24']))

    def test_offer_candidates_exclude_public_loopback_relay_and_reflexive_addresses(self):
        from server.local_link import local_sdp
        sdp='v=0\r\n'+''.join('a=candidate:x 1 udp 123 '+host+' 1234 typ '+kind+'\r\n' for host,kind in [('192.168.2.3','host'),('8.8.8.8','host'),('127.0.0.1','host'),('192.168.2.3','relay'),('192.168.2.3','srflx')])
        filtered=local_sdp(sdp,['192.168.2.0/24'])
        self.assertEqual(filtered.count('a=candidate:'),1)
        self.assertIn('192.168.2.3',filtered)


class SocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_ordered_frames_reassemble_and_queue_is_bounded(self):
        from server.local_link import ChannelSocket, encode_frames
        channel=SimpleNamespace(readyState='open',bufferedAmount=0,send=lambda value:None,close=lambda:None)
        socket=ChannelSocket(channel)
        raw=json.dumps({'type':'text','text':'界'*32000})
        frames=encode_frames(raw)
        self.assertGreater(len(frames),1)
        for frame in frames:socket.feed(frame)
        self.assertEqual((await socket.__anext__()).data,raw)
        for _ in range(300):socket.feed('{"type":"ping"}')
        self.assertTrue(socket.closed)

    async def test_corrupt_or_oversized_frames_fail_closed(self):
        from server.local_link import ChannelSocket
        for raw in ('x'*65000,'['*1500+']'*1500,json.dumps({'type':'local_chunk','id':1,'index':5,'count':1,'data':'!'})):
            channel=SimpleNamespace(readyState='open',bufferedAmount=0,send=lambda value:None,close=lambda:None)
            socket=ChannelSocket(channel);socket.feed(raw);self.assertTrue(socket.closed)

    async def test_command_loop_failure_closes_channel_and_is_consumed_during_cleanup(self):
        from server.local_link import ChannelSocket,LocalControlLink
        channel=SimpleNamespace(readyState='open',bufferedAmount=0,send=lambda value:None,close=lambda:None)
        socket=ChannelSocket(channel)
        async def fail(*args):raise RuntimeError('Synthetic command failure')
        link=LocalControlLink(fail,AsyncMock(),networks=[])
        link.socket=socket;link._serve_task=asyncio.create_task(link._run_socket(socket,'192.168.2.8'))
        await asyncio.sleep(0)
        self.assertTrue(socket.closed)
        await link.close()
