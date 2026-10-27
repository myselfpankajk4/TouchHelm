"""Same-origin, live-PIN-session file HTTP. Never forwarded to a public helper."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
import hmac
import os
import secrets
import time
from urllib.parse import quote
from aiohttp import web
from .file_store import FileStore,FileError,CHUNK
from .local_network import local_request

COOKIE='touchhelm_files'


def byte_range(value,size):
    if not value:return 0,size-1,False
    try:
        if not value.startswith('bytes=') or ',' in value:raise ValueError()
        first,last=value[6:].split('-',1)
        if not first:
            count=int(last)
            if count<=0:raise ValueError()
            start,end=max(0,size-count),size-1
        else:start=int(first);end=min(int(last),size-1) if last else size-1
        if not 0<=start<=end<size:raise ValueError()
        return start,end,True
    except (ValueError,TypeError):raise web.HTTPRequestRangeNotSatisfiable(headers={'Content-Range':f'bytes */{size}'})


class FileHTTP:
    def __init__(self,server,store=None):
        self.server=server;self.store=store;self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='TouchHelm files')
        self.tickets={};self.sessions={};self.active={};self.queued=0;self.closed=False
        self.init_lock=asyncio.Lock();self.cleanup_owners=set();self.cleanup_task=None;self.janitor=None

    async def io(self,function,*args,**kwargs):
        if self.queued>=16:raise FileError('Files is busy. Wait for the current transfer.',429)
        self.queued+=1
        try:return await asyncio.get_running_loop().run_in_executor(self.pool,lambda:function(*args,**kwargs))
        finally:self.queued-=1

    def _enabled(self):return bool(self.server.config.get('files_enabled') and self.server.config.get('require_pin'))

    def _alive(self,client):
        return (self._enabled() and client.authenticated and not client.ws.closed
                and any(value is client for value in self.server.clients.values()) and getattr(client,'local_lan',False))

    def ticket(self,client):
        self._prune()
        if not self._alive(client):return None
        for key,value in list(self.tickets.items()):
            if value['client'] is client:self.tickets.pop(key)
        if len(self.tickets)>=32:return None
        token=secrets.token_urlsafe(32)
        self.tickets[token]={'client':client,'expires':time.monotonic()+30,'pin':self.server.config.get('pin_code')}
        return token

    def _prune(self):
        now=time.monotonic()
        for key,value in list(self.tickets.items()):
            if value['expires']<now or not self._alive(value['client']):self.tickets.pop(key,None)
        for key,value in list(self.sessions.items()):
            if not self._valid(value):self.sessions.pop(key,None);self._cancel_owner(key)

    def _valid(self,value):
        return (value['expires']>time.monotonic() and self._alive(value['client'])
                and value['pin']==self.server.config.get('pin_code'))

    def _cancel_owner(self,owner):
        if self.store and not self.closed:
            self.store.deny(owner);self.cleanup_owners.add(owner)
            if not self.cleanup_task or self.cleanup_task.done():self.cleanup_task=asyncio.create_task(self._cleanup())

    async def _cleanup(self):
        while self.cleanup_owners:
            owners=list(self.cleanup_owners);self.cleanup_owners.clear()
            await asyncio.get_running_loop().run_in_executor(self.pool,lambda:[self.store.revoke(owner) for owner in owners])

    def revoke(self,client):
        for key,value in list(self.tickets.items()):
            if value['client'] is client:self.tickets.pop(key,None)
        for key,value in list(self.sessions.items()):
            if value['client'] is client:self.sessions.pop(key,None);self._cancel_owner(key)

    def _route(self,request):
        origin=f'{request.scheme}://{request.host}'
        if not local_request(request) or request.headers.get('Origin',origin)!=origin:
            raise web.HTTPForbidden(text='Connect directly to this PC on the same local Wi-Fi.')
        if not self._enabled():raise web.HTTPForbidden(text='Enable File access in TouchHelm on the PC first.')
        return origin

    def session(self,request,write=False):
        origin=self._route(request);token=request.cookies.get(COOKIE,'');value=self.sessions.get(token)
        if (not value or not self._valid(value) or value['client'].remote_ip!=request.remote
                or value['origin']!=origin):
            if value:self.sessions.pop(token,None);self._cancel_owner(token)
            raise web.HTTPUnauthorized(text='Reconnect and enter the PC PIN to use Files.')
        if write and (request.headers.get('Origin')!=origin or not hmac.compare_digest(request.headers.get('X-TouchHelm-Files',''),value['csrf'])):
            raise web.HTTPForbidden(text='Open Files again before sending.')
        return token,value

    async def _json(self,request,maximum=16384):
        if request.content_length and request.content_length>maximum:raise FileError('This request is too large.',413)
        body=await self._body(request,maximum)
        import json
        try:
            value=json.loads(body)
            if not isinstance(value,dict):raise ValueError()
            return value
        except (ValueError,UnicodeError):raise FileError('Choose valid file options.')

    async def _body(self,request,maximum):
        if request.content_length is not None and request.content_length>maximum:raise FileError('This request is too large.',413)
        parts=[];length=0
        async for part in request.content.iter_chunked(min(maximum+1,65536)):
            length+=len(part)
            if length>maximum:raise FileError('This request is too large.',413)
            parts.append(part)
        return b''.join(parts)

    async def handle(self,request):
        try:
            if request.path=='/api/files/session':
                origin=self._route(request)
                if request.headers.get('Origin')!=origin:raise web.HTTPForbidden()
                body=await self._json(request);ticket=self.tickets.pop(body.get('ticket',''),None)
                if (not ticket or ticket['expires']<time.monotonic() or not self._alive(ticket['client'])
                        or ticket['pin']!=self.server.config.get('pin_code')
                        or ticket['client'].remote_ip!=request.remote or ticket['client'].origin!=origin):raise web.HTTPUnauthorized()
                client=ticket['client'];self.revoke(client);self._prune()
                if len(self.sessions)>=16 or len(self.cleanup_owners)>32:raise FileError('Too many active file sessions. Reconnect later.',429)
                token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                self.sessions[token]={'client':client,'origin':origin,'csrf':csrf,'pin':ticket['pin'],'expires':time.monotonic()+1800}
                response=web.json_response({'csrf':csrf,'expires_in':1800})
                response.set_cookie(COOKIE,token,httponly=True,samesite='Strict',secure=request.secure,path='/api/files',max_age=1800)
                response.headers['Cache-Control']='no-store';return response
            owner,session=self.session(request,request.method not in ('GET','HEAD'))
            if self.store is None:
                async with self.init_lock:
                    if self.store is None:self.store=await self.io(FileStore)
            path=request.path
            if path=='/api/files/locations':result=await self.io(self.store.locations)
            elif path=='/api/files/list':
                result=await self.io(self.store.listing,request.query.get('id'),request.query.get('q',''),request.query.get('sort','name'),int(request.query.get('offset',0)))
            elif path=='/api/files/folders':
                data=await self._json(request);result=await self.io(self.store.mkdir,data.get('parent'),data.get('name'))
            elif path=='/api/files/uploads':
                data=await self._json(request);result=await self.io(self.store.begin,owner,data.get('parent'),data.get('name'),data.get('size'))
            elif path.startswith('/api/files/content/'):
                return await self.content(request,owner,session)
            else:
                identifier=request.match_info['upload']
                if request.method=='PUT':
                    if request.content_length is not None and request.content_length>CHUNK:raise FileError('Use file chunks up to 1 MiB.',413)
                    body=await self._body(request,CHUNK)
                    result=await self.io(self.store.append,owner,identifier,int(request.query.get('offset',-1)),body)
                elif request.method=='DELETE':result=await self.io(self.store.cancel,owner,identifier)
                else:result=await self.io(self.store.finish,owner,identifier)
            if not self._valid(session):
                await self.io(self.store.revoke,owner);raise web.HTTPUnauthorized()
            return web.json_response(result,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
        except FileError as error:return web.json_response({'message':str(error)},status=error.status)
        except FileNotFoundError:return web.json_response({'message':'This file is no longer here. Refresh the folder.'},status=404)
        except PermissionError:return web.json_response({'message':'Windows cannot open this local location. Check its permissions and offline availability on the PC.'},status=403)
        except (ValueError,TypeError,KeyError):return web.json_response({'message':'Choose valid file options and try again.'},status=400)
        except OSError:return web.json_response({'message':'The PC could not access this file. Check permissions, free space or whether it is in use.'},status=409)

    async def content(self,request,owner,session):
        if sum(self.active.values())>=8 or self.active.get(owner,0)>=4:raise FileError('Wait for a file preview or download to finish.',429)
        self.active[owner]=self.active.get(owner,0)+1;context=None;response=None
        try:
            identifier=request.match_info['entry'];entry=await self.io(self.store.describe,identifier)
            context=self.store.open_read(identifier);stream=await self.io(context.__enter__)
            size=os.fstat(stream.fileno()).st_size;start,end,partial=byte_range(request.headers.get('Range'),size)
            disposition='attachment' if request.query.get('download')=='1' or entry['preview']=='download' else 'inline'
            headers={'Content-Type':entry['mime'],'Content-Disposition':f"{disposition}; filename=\"download\"; filename*=UTF-8''{quote(entry['name'],safe='')}",
                     'Accept-Ranges':'bytes','Content-Length':str(max(0,end-start+1)),'Cache-Control':'no-store',
                     'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cross-Origin-Resource-Policy':'same-origin',
                     'Content-Security-Policy':"default-src 'none'; frame-ancestors 'self'"}
            if partial:headers['Content-Range']=f'bytes {start}-{end}/{size}'
            response=web.StreamResponse(status=206 if partial else 200,headers=headers)
            if not self._valid(session):raise web.HTTPUnauthorized()
            await response.prepare(request)
            if request.method=='HEAD':return response
            await self.io(stream.seek,start);remaining=max(0,end-start+1)
            while remaining:
                if not self._valid(session):
                    if request.transport:request.transport.abort()
                    return response
                data=await self.io(stream.read,min(256*1024,remaining))
                if not data:
                    if request.transport:request.transport.abort()
                    return response
                remaining-=len(data);await response.write(data)
            await response.write_eof();return response
        except (ConnectionError,asyncio.CancelledError):
            if request.transport:request.transport.abort()
            if response:return response
            raise
        finally:
            if context:
                with suppress(Exception):await self.io(context.__exit__,None,None,None)
            count=max(0,self.active.get(owner,1)-1)
            if count:self.active[owner]=count
            else:self.active.pop(owner,None)

    def routes(self,app):
        async def start(_):self.janitor=asyncio.create_task(self._expire())
        app.on_startup.append(start)
        app.router.add_post('/api/files/session',self.handle)
        app.router.add_get('/api/files/locations',self.handle)
        app.router.add_get('/api/files/list',self.handle)
        app.router.add_post('/api/files/folders',self.handle)
        app.router.add_post('/api/files/uploads',self.handle)
        app.router.add_get('/api/files/content/{entry}',self.handle)
        app.router.add_put('/api/files/uploads/{upload}',self.handle)
        app.router.add_delete('/api/files/uploads/{upload}',self.handle)
        app.router.add_post('/api/files/uploads/{upload}/finish',self.handle)

    async def close(self):
        self.tickets.clear();self.sessions.clear()
        if self.janitor:
            self.janitor.cancel()
            with suppress(asyncio.CancelledError):await self.janitor
        if self.cleanup_task:await self.cleanup_task
        if self.store:await self.io(self.store.close)
        self.closed=True;self.pool.shutdown(wait=False,cancel_futures=True)

    async def _expire(self):
        while True:
            await asyncio.sleep(15);self._prune()
