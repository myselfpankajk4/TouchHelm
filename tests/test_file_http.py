"""Authenticated local file routes against temporary data only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from aiohttp import web,CookieJar
from aiohttp.test_utils import TestClient,TestServer


class FileHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(importlib.util.find_spec('server.file_http'),'Files HTTP transport is missing')
        from server.file_store import FileStore
        from server.file_http import FileHTTP
        self.work=tempfile.TemporaryDirectory(dir='build');self.root=Path(self.work.name).absolute()
        self.disk=self.root/'disk';self.disk.mkdir();(self.disk/'movie.mp4').write_bytes(bytes(range(256))*2048)
        (self.disk/'unsafe.html').write_text('<script>alert(1)</script>')
        self.config={'files_enabled':True,'require_pin':True,'pin_code':'5678'}
        self.client=SimpleNamespace(authenticated=True,ws=SimpleNamespace(closed=False),remote_ip='127.0.0.1',local_lan=True,origin=None)
        self.host=SimpleNamespace(config=self.config,clients={id(self.client):self.client})
        self.files=FileHTTP(self.host,FileStore(roots=[{'path':self.disk,'name':'Downloads','kind':'downloads'}],temporary=self.root/'journal'))
        app=web.Application();self.files.routes(app)
        self.http=TestClient(TestServer(app),cookie_jar=CookieJar(unsafe=True));await self.http.start_server()
        self.client.origin=str(self.http.make_url('/')).rstrip('/')
        await self.exchange()

    async def exchange(self):
        ticket=self.files.ticket(self.client)
        self.assertIsInstance(ticket,str)
        response=await self.http.post('/api/files/session',json={'ticket':ticket},headers={'Origin':self.client.origin})
        self.assertEqual(response.status,200)
        self.csrf=(await response.json())['csrf']
        self.headers={'Origin':self.client.origin,'X-TouchHelm-Files':self.csrf}

    async def asyncTearDown(self):
        if hasattr(self,'http'):await self.http.close();await self.files.close();self.work.cleanup()

    async def entry(self,name):
        result=await (await self.http.get('/api/files/locations')).json()
        location=result['locations'][0]['id']
        listing=await (await self.http.get('/api/files/list',params={'id':location})).json()
        return location,next(e for e in listing['entries'] if e['name']==name)

    async def test_range_head_and_unsafe_attachment(self):
        _,entry=await self.entry('movie.mp4');path='/api/files/content/'+entry['id']
        response=await self.http.get(path,headers={'Range':'bytes=100-199'})
        self.assertEqual(response.status,206);self.assertEqual(len(await response.read()),100)
        self.assertEqual(response.headers['Content-Range'],'bytes 100-199/524288')
        response=await self.http.head(path);self.assertEqual(response.headers['Content-Length'],'524288')
        response=await self.http.get(path,headers={'Range':'bytes=999999-'})
        self.assertEqual(response.status,416)
        _,unsafe=await self.entry('unsafe.html')
        response=await self.http.get('/api/files/content/'+unsafe['id'])
        self.assertIn('attachment',response.headers['Content-Disposition'])
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')

    async def test_chunk_upload_and_csrf(self):
        location,_=await self.entry('movie.mp4')
        payload={'parent':location,'name':'sent.txt','size':4}
        response=await self.http.post('/api/files/uploads',json=payload)
        self.assertEqual(response.status,403)
        response=await self.http.post('/api/files/uploads',json=payload,headers=self.headers)
        self.assertEqual(response.status,200);upload=(await response.json())['id']
        response=await self.http.put('/api/files/uploads/'+upload,params={'offset':0},data=b'test',headers=self.headers)
        self.assertEqual(response.status,200)
        response=await self.http.post('/api/files/uploads/'+upload+'/finish',json={},headers=self.headers)
        self.assertEqual(response.status,200);self.assertEqual((self.disk/'sent.txt').read_bytes(),b'test')

    async def test_inline_media_policy_allows_native_player_but_not_scripts(self):
        _,entry=await self.entry('movie.mp4')
        response=await self.http.get('/api/files/content/'+entry['id'])
        policy=response.headers['Content-Security-Policy']
        self.assertIn("media-src 'self'",policy);self.assertIn("default-src 'none'",policy)
        self.assertNotIn('unsafe-inline',policy);self.assertNotIn('https:',policy)
        await response.read()
        response=await self.http.get('/api/files/content/'+entry['id']+'?download=1')
        self.assertNotIn('media-src',response.headers['Content-Security-Policy']);await response.read()
        _,unsafe=await self.entry('unsafe.html')
        response=await self.http.get('/api/files/content/'+unsafe['id'])
        self.assertNotIn('media-src',response.headers['Content-Security-Policy'])

    async def test_full_megabyte_chunk_is_not_truncated_to_one_socket_read(self):
        location,_=await self.entry('movie.mp4');body=bytes(range(256))*4096
        response=await self.http.post('/api/files/uploads',json={'parent':location,'name':'large.bin','size':len(body)},headers=self.headers)
        upload=(await response.json())['id']
        response=await self.http.put('/api/files/uploads/'+upload,params={'offset':0},data=body,headers=self.headers)
        self.assertEqual((await response.json())['offset'],len(body))
        response=await self.http.post('/api/files/uploads/'+upload+'/finish',json={},headers=self.headers)
        self.assertEqual(response.status,200);self.assertEqual((self.disk/'large.bin').read_bytes(),body)

    async def test_revocation_and_cross_origin_block_every_read(self):
        _,entry=await self.entry('movie.mp4');path='/api/files/content/'+entry['id']
        response=await self.http.get(path,headers={'Origin':'http://foreign.example'})
        self.assertEqual(response.status,403)
        self.config['files_enabled']=False
        response=await self.http.get(path);self.assertEqual(response.status,403)
        self.config['files_enabled']=True;self.config['pin_code']='9876'
        response=await self.http.get(path);self.assertEqual(response.status,401)

    async def test_ticket_single_use_and_live_socket_required(self):
        ticket=self.files.ticket(self.client)
        response=await self.http.post('/api/files/session',json={'ticket':ticket},headers={'Origin':self.client.origin})
        self.assertEqual(response.status,200)
        response=await self.http.post('/api/files/session',json={'ticket':ticket},headers={'Origin':self.client.origin})
        self.assertEqual(response.status,401)
        self.client.ws.closed=True
        response=await self.http.get('/api/files/locations');self.assertEqual(response.status,401)

    async def test_pin_header_alone_and_rebinding_host_cannot_authorize(self):
        self.http.session.cookie_jar.clear()
        response=await self.http.get('/api/files/locations',headers={'X-TouchHelm-Pin':'5678'})
        self.assertEqual(response.status,401)
        response=await self.http.get('/api/files/locations',headers={'Host':'evil.example'})
        self.assertEqual(response.status,403)

    async def test_revoked_session_object_cannot_reactivate_when_access_returns(self):
        session=next(iter(self.files.sessions.values()))
        self.files.revoke(self.client)
        self.assertFalse(self.files._valid(session))

    async def test_slow_folder_request_cannot_create_after_native_revocation(self):
        import asyncio
        location,_=await self.entry('movie.mp4');entered=asyncio.Event();release=asyncio.Event()
        original=self.files._json
        async def body(request,*args):
            value=await original(request,*args);entered.set();await release.wait();return value
        self.files._json=body
        request=asyncio.create_task(self.http.post('/api/files/folders',json={'parent':location,'name':'Revoked folder'},headers=self.headers))
        await entered.wait();self.config['files_enabled']=False;self.files.revoke(self.client);release.set()
        response=await request;self.assertIn(response.status,(401,403));self.assertFalse((self.disk/'Revoked folder').exists())

    async def test_http_download_interruption_is_reported_on_live_control_socket(self):
        import asyncio
        from unittest.mock import AsyncMock
        self.client.ws.send_json=AsyncMock()
        with (self.disk/'large.bin').open('wb') as stream:stream.truncate(16*1024**2)
        _,entry=await self.entry('large.bin')
        response=await self.http.get('/api/files/content/'+entry['id'],params={'download':'1','transfer':'b'*24})
        await response.content.readexactly(1000);response.close()
        for _ in range(50):
            if any(call.args[0].get('state')=='interrupted' for call in self.client.ws.send_json.call_args_list):break
            await asyncio.sleep(.01)
        self.assertTrue(any(call.args[0].get('state')=='interrupted' for call in self.client.ws.send_json.call_args_list))

    async def test_revocation_during_disk_read_does_not_send_the_completed_chunk(self):
        import asyncio
        from aiohttp import ClientPayloadError,ClientConnectionError
        _,entry=await self.entry('movie.mp4');entered=asyncio.Event();release=asyncio.Event();original=self.files.io
        async def delayed(function,*args,**kwargs):
            result=await original(function,*args,**kwargs)
            if getattr(function,'__name__','')=='read':entered.set();await release.wait()
            return result
        self.files.io=delayed
        response=await self.http.get('/api/files/content/'+entry['id'])
        await entered.wait();self.config['files_enabled']=False;self.files.revoke(self.client);release.set()
        chunks=[]
        try:
            async for chunk in response.content.iter_any():chunks.append(chunk)
        except (ClientPayloadError,ClientConnectionError):pass
        self.assertEqual(sum(map(len,chunks)),0)

    async def test_host_shutdown_closes_active_read_leases_and_is_idempotent(self):
        with (self.disk/'large.bin').open('wb') as stream:stream.truncate(16*1024**2)
        _,entry=await self.entry('large.bin')
        response=await self.http.get('/api/files/content/'+entry['id'])
        self.assertTrue(self.files.active)
        await self.files.close()
        self.assertFalse(self.files.active)
        (self.disk/'large.bin').rename(self.disk/'closed.bin')
        response.close();await self.files.close()

    async def test_download_cancel_before_chrome_starts_the_request_is_respected(self):
        _,entry=await self.entry('movie.mp4');identifier='c'*24
        response=await self.http.post('/api/files/downloads/'+identifier+'/cancel',json={},headers=self.headers)
        self.assertEqual(response.status,200)
        response=await self.http.get('/api/files/content/'+entry['id'],params={'download':'1','transfer':identifier})
        self.assertEqual(response.status,410)
