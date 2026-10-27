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
