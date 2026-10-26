"""Public browser entry is a separate, capability-gated HTTP surface."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from aiohttp import ClientSession, WSServerHandshakeError, web


class Manager:
    def __init__(self):
        self.origin='https://fixture.trycloudflare.com'
        self.ticket='t'*43
        self.sessions=set()
    def snapshot(self):return {'origin':self.origin,'ready':True,'state':'ready'}
    def exchange(self,token):
        if token != self.ticket:return None
        self.ticket='next'*10+'abc';self.sessions.add('s'*43);return 's'*43
    def valid_session(self,token):return token in self.sessions


class BrowserGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from server.browser_gateway import BrowserLinkGateway,BROWSER_ORIGIN
        self.manager=Manager()
        async def index(request):return web.Response(text='<html><head></head><body>Phone controls</body></html>',content_type='text/html')
        async def ws_handler(request):
            ws=web.WebSocketResponse();await ws.prepare(request)
            await ws.send_json({'secure_origin':request.get(BROWSER_ORIGIN)})
            async for _ in ws:pass
            return ws
        self.owner=SimpleNamespace(handle_index=index,handle_ws=ws_handler,
            handle_info=AsyncMock(return_value=web.json_response({'service':'touchhelm'})),
            handle_version=AsyncMock(return_value=web.json_response({'build':'test'})),
            handle_config=AsyncMock(return_value=web.json_response({'saved':True})),
            handle_asset=AsyncMock(return_value=web.Response(body=b'image')),
            local_link=SimpleNamespace(nonce='synthetic-nonce'))
        self.gateway=BrowserLinkGateway(self.owner,self.manager)
        self.base=await self.gateway.start()
        self.client=ClientSession()
        self.addAsyncCleanup(self.gateway.close);self.addAsyncCleanup(self.client.close)
        self.headers={'Host':'fixture.trycloudflare.com'}
    def authorized(self,**extra):return {**self.headers,'Cookie':'th_browser_link='+'s'*43,**extra}

    async def test_public_root_loads_gate_but_pin_alone_cannot_reach_api(self):
        async with self.client.get(self.base+'/',headers=self.headers) as response:
            self.assertEqual(response.status,200)
            self.assertIn('touchhelm-browser-link',await response.text())
            self.assertEqual(response.headers['Referrer-Policy'],'no-referrer')
        async with self.client.get(self.base+'/api/info',headers={**self.headers,'X-TouchHelm-Pin':'5678'}) as response:
            self.assertEqual(response.status,404)
        self.owner.handle_info.assert_not_awaited()

    async def test_legacy_pairing_cookie_route_remains_inaccessible(self):
        for origin in ('http://fixture.trycloudflare.com','https://other.trycloudflare.com',None):
            headers={**self.headers,**({'Origin':origin} if origin else {})}
            async with self.client.post(self.base+'/api/browser-link/pair',headers=headers,json={'token':'t'*43}) as response:self.assertEqual(response.status,403)
        headers={**self.headers,'Origin':self.manager.origin}
        async with self.client.post(self.base+'/api/browser-link/pair',headers=headers,json={'token':'t'*43}) as response:
            self.assertEqual(response.status,405)
            self.assertNotIn('Set-Cookie',response.headers)
            self.assertNotIn('s'*43,await response.text())
        async with self.client.post(self.base+'/api/browser-link/pair',headers=headers,json={'token':'t'*43}) as response:self.assertEqual(response.status,405)
        async with self.client.get(self.base+'/api/info',headers=self.authorized()) as response:self.assertEqual(response.status,404)

    async def test_wrong_host_and_forwarded_headers_never_establish_trust(self):
        self.manager.sessions.add('s'*43)
        for host in ('127.0.0.1','other.trycloudflare.com','fixture.trycloudflare.com.evil.invalid'):
            async with self.client.get(self.base+'/api/info',headers=self.authorized(Host=host,**{'X-Forwarded-Proto':'https','X-Forwarded-Host':'fixture.trycloudflare.com'})) as response:self.assertEqual(response.status,403)
        self.owner.handle_info.assert_not_awaited()

    async def test_unlisted_routes_and_mutating_pairing_settings_are_not_exposed(self):
        self.manager.sessions.add('s'*43)
        for path in ('/api/pairing/certificate','/api/pairing/handoff','/preview/desktop/','/server/text_native.cs','/config.json','/sw.js','/SW.js','/Demo.js'):
            async with self.client.get(self.base+path,headers=self.authorized()) as response:self.assertEqual(response.status,404,path)
        for settings in ({'require_pin':False},{'pin_code':'0000'},{'remote_enabled':True},{'https_enabled':True}):
            async with self.client.post(self.base+'/api/config',headers={**self.authorized(),'Origin':self.manager.origin},json=settings) as response:self.assertEqual(response.status,405)
        self.owner.handle_config.assert_not_awaited()

    async def test_websocket_stays_unavailable_even_with_a_legacy_session(self):
        for headers,status in ((self.headers,404),({**self.authorized(),'Origin':'https://evil.invalid'},404)):
            with self.assertRaises(WSServerHandshakeError) as error:await self.client.ws_connect(self.base+'/ws',headers=headers)
            self.assertEqual(error.exception.status,status)
        self.manager.sessions.add('s'*43)
        headers={**self.authorized(),'Origin':self.manager.origin}
        with self.assertRaises(WSServerHandshakeError) as error:await self.client.ws_connect(self.base+'/ws',headers=headers)
        self.assertEqual(error.exception.status,404)

    async def test_revoked_session_cannot_fetch_private_data(self):
        self.manager.sessions.add('s'*43)
        async with self.client.get(self.base+'/api/browser-link/status',headers=self.authorized()) as response:self.assertEqual(await response.json(),{'pairing':True,'nonce':'synthetic-nonce'})
        self.manager.sessions.clear()
        async with self.client.get(self.base+'/api/assets/asset-id',headers=self.authorized()) as response:self.assertEqual(response.status,404)
        self.owner.handle_asset.assert_not_awaited()
