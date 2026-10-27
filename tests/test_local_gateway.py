"""The temporary bootstrap exposes SDP proofs, never PC control or credentials."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from aiohttp import ClientSession,web
from server.local_link import make_proof,verify_proof


class LocalGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_phone_brand_icon_is_embedded_before_the_public_origin_closes(self):
        async def index(request):return web.Response(text='<html><head><link rel="icon" href="/icons/icon.svg"></head><body><img src="/icons/icon.svg"></body></html>',content_type='text/html')
        self.owner.handle_index=index
        async with self.client.get(self.base+'/',headers=self.headers) as response:
            source=await response.text()
            self.assertEqual(response.status,200)
            self.assertNotIn('"/icons/icon.svg"',source)
            self.assertIn('data:image/svg+xml;base64,',source)

    async def asyncSetUp(self):
        from server.browser_gateway import BrowserLinkGateway
        self.origin='https://fixture.trycloudflare.com';self.accepted=False
        manager=SimpleNamespace(snapshot=lambda:{'ready':True,'origin':self.origin},pairing_secret=lambda:'t'*43)
        async def index(request):return web.Response(text='<html><head></head><body>Phone</body></html>',content_type='text/html')
        def valid(secret,stage,proof,sdp=''):return not self.accepted and verify_proof(secret,stage,'n'*43,sdp,proof)
        async def answer(secret,sdp,proof):
            if not valid(secret,'answer',proof,sdp):raise PermissionError()
            self.accepted=True
        self.owner=SimpleNamespace(handle_index=index,handle_ws=AsyncMock(),handle_info=AsyncMock(),local_link=SimpleNamespace(nonce='n'*43,offer='synthetic offer',proof_valid=valid,answer=answer))
        self.gateway=BrowserLinkGateway(self.owner,manager);self.base=await self.gateway.start()
        self.client=ClientSession();self.addAsyncCleanup(self.gateway.close);self.addAsyncCleanup(self.client.close)
        self.headers={'Host':'fixture.trycloudflare.com','Origin':self.origin}

    async def test_status_contains_only_public_nonce_and_never_secret_or_pc_state(self):
        async with self.client.get(self.base+'/api/browser-link/status',headers=self.headers) as response:
            data=await response.json();self.assertEqual(data,{'pairing':True,'nonce':'n'*43});self.assertNotIn('t'*43,str(data))

    async def test_offer_requires_proof_and_does_not_establish_an_http_session(self):
        for proof in ('t'*43,'5678','x'*64,None):
            async with self.client.post(self.base+'/api/browser-link/offer',headers=self.headers,json={'proof':proof}) as response:self.assertEqual(response.status,401)
        async with self.client.post(self.base+'/api/browser-link/offer',headers=self.headers,json={'proof':make_proof('t'*43,'offer','n'*43)}) as response:
            self.assertEqual(response.status,200);self.assertNotIn('Set-Cookie',response.headers);self.assertEqual((await response.json())['sdp'],'synthetic offer')

    async def test_answer_binds_exact_sdp_and_cannot_be_replayed(self):
        proof=make_proof('t'*43,'answer','n'*43,'answer')
        async with self.client.post(self.base+'/api/browser-link/answer',headers=self.headers,json={'proof':proof,'sdp':'tampered'}) as response:self.assertEqual(response.status,401)
        for expected in (200,401):
            async with self.client.post(self.base+'/api/browser-link/answer',headers=self.headers,json={'proof':proof,'sdp':'answer'}) as response:self.assertEqual(response.status,expected)

    async def test_pairing_cannot_be_requested_by_foreign_origin(self):
        proof=make_proof('t'*43,'offer','n'*43)
        for headers in ({**self.headers,'Host':'evil.invalid'},{**self.headers,'Origin':'https://evil.invalid'},{'Host':'fixture.trycloudflare.com'}):
            async with self.client.post(self.base+'/api/browser-link/offer',headers=headers,json={'proof':proof}) as response:self.assertEqual(response.status,403)

    async def test_no_public_command_or_api_even_with_legacy_pin_cookie_and_ticket(self):
        headers={**self.headers,'Cookie':'th_browser_link='+'s'*43,'X-TouchHelm-Pin':'5678'}
        for path in ('/ws','/api/info','/api/config','/api/assets/example','/api/pairing/certificate','/SW.js','/Demo.js'):
            async with self.client.get(self.base+path,headers=headers) as response:self.assertEqual(response.status,404,path)
        self.owner.handle_ws.assert_not_awaited();self.owner.handle_info.assert_not_awaited()
