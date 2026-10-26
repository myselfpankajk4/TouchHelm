"""Temporary static/SDP bootstrap. No PC APIs, credentials or control sockets."""
from pathlib import Path
import re
from urllib.parse import urlsplit
from aiohttp import web

WEB=Path(__file__).resolve().parents[1]/'web'
BROWSER_ORIGIN=web.RequestKey('browser_link_origin',str)
BROWSER_SESSION=web.RequestKey('browser_link_session',str)
HEADERS={
    'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
    'X-Content-Type-Options':'nosniff','Cross-Origin-Resource-Policy':'same-origin',
    'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' blob:; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src 'self'; frame-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'",
    'Permissions-Policy':'camera=(), microphone=(), accelerometer=(self), gyroscope=(self), screen-wake-lock=(self)',
}


class BrowserLinkGateway:
    def __init__(self,owner,manager):
        self.owner,self.manager=owner,manager
        self.runner=self.site=self.port=None
        self.app=web.Application(middlewares=[self._transport],client_max_size=40000)
        self.app.on_response_prepare.append(self._headers)
        routes=self.app.router
        routes.add_get('/',self._index);routes.add_get('/index.html',self._index)
        routes.add_get('/api/browser-link/status',self._status)
        routes.add_post('/api/browser-link/offer',self._offer)
        routes.add_post('/api/browser-link/answer',self._answer)
        routes.add_get('/{path:.*}',self._static)

    async def start(self):
        self.runner=web.AppRunner(self.app,access_log=None,shutdown_timeout=3)
        await self.runner.setup();self.site=web.TCPSite(self.runner,'127.0.0.1',0)
        await self.site.start();self.port=self.site._server.sockets[0].getsockname()[1]
        return f'http://127.0.0.1:{self.port}'

    async def close(self):
        runner,self.runner=self.runner,None;self.site=self.port=None
        if runner:await runner.cleanup()

    async def _headers(self,request,response):response.headers.update(HEADERS)

    @web.middleware
    async def _transport(self,request,handler):
        snapshot=self.manager.snapshot();origin=snapshot.get('origin')
        if not snapshot.get('ready') or not origin:raise web.HTTPServiceUnavailable()
        local=request.transport.get_extra_info('sockname') if request.transport else None
        if (not local or local[0]!='127.0.0.1' or local[1]!=self.port or request.remote!='127.0.0.1'
                or request.host!=urlsplit(origin).netloc):raise web.HTTPForbidden()
        if request.method!='GET' and request.headers.get('Origin')!=origin:raise web.HTTPForbidden()
        return await handler(request)

    async def _index(self,request):
        response=await self.owner.handle_index(request)
        source=re.sub(r'<script\s+src="/demo\.js(?:\?[^"]*)?"\s*>\s*</script>','',response.text)
        return web.Response(text=source.replace('</head>','<meta name="touchhelm-browser-link" content="local"></head>'),content_type='text/html')

    async def _status(self,request):
        return web.json_response({'pairing':True,'nonce':self.owner.local_link.nonce})

    async def _data(self,request,fields):
        try:
            data=await request.json()
            if not isinstance(data,dict) or set(data)!=fields:raise ValueError()
            return data
        except (ValueError,TypeError,RecursionError):raise web.HTTPBadRequest() from None

    async def _offer(self,request):
        data=await self._data(request,{'proof'})
        secret=self.manager.pairing_secret()
        if not secret or not self.owner.local_link.proof_valid(secret,'offer',data['proof']):raise web.HTTPUnauthorized()
        return web.json_response({'type':'offer','sdp':self.owner.local_link.offer})

    async def _answer(self,request):
        data=await self._data(request,{'proof','sdp'})
        secret=self.manager.pairing_secret()
        if not secret:raise web.HTTPUnauthorized()
        try:await self.owner.local_link.answer(secret,data['sdp'],data['proof'])
        except PermissionError:raise web.HTTPUnauthorized() from None
        except (ValueError,TypeError):raise web.HTTPBadRequest() from None
        return web.json_response({'accepted':True})

    async def _static(self,request):
        relative=request.match_info['path'];normalized=relative.casefold();parts=Path(relative).parts
        suffix=Path(relative).suffix.lower()
        if (not relative or '\\' in relative or any(part in ('.','..') for part in parts)
                or normalized.startswith(('api/','preview','demo.')) or normalized in ('sw.js','ws')
                or suffix not in ('.js','.css','.svg','.png','.webp','.jpg','.jpeg','.woff2','.woff','.ico')):
            raise web.HTTPNotFound()
        candidate=(WEB/relative).resolve()
        if not candidate.is_relative_to(WEB) or not candidate.is_file():raise web.HTTPNotFound()
        return web.FileResponse(candidate)
