"""Narrow loopback origin for an opt-in HTTPS browser link, never the LAN app."""
from pathlib import Path
import re
from urllib.parse import urlsplit
from aiohttp import web

WEB = Path(__file__).resolve().parents[1]/'web'
COOKIE = 'th_browser_link'
BROWSER_ORIGIN = web.RequestKey('browser_link_origin', str)
BROWSER_SESSION = web.RequestKey('browser_link_session', str)
HEADERS = {
    'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer',
    'X-Content-Type-Options':'nosniff', 'Cross-Origin-Resource-Policy':'same-origin',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src 'self'; frame-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'",
    'Permissions-Policy':'camera=(), microphone=(), accelerometer=(self), gyroscope=(self), screen-wake-lock=(self)',
}


class BrowserLinkGateway:
    def __init__(self, owner, manager):
        self.owner,self.manager=owner,manager
        self.runner=self.site=self.port=None
        self._sockets=set()
        self.app=web.Application(middlewares=[self._transport],client_max_size=8192)
        self.app.on_response_prepare.append(self._headers)
        routes=self.app.router
        routes.add_get('/',self._index);routes.add_get('/index.html',self._index)
        routes.add_post('/api/browser-link/pair',self._pair)
        routes.add_get('/api/browser-link/status',self._status)
        routes.add_get('/api/info',self._info);routes.add_get('/api/version',self._version)
        routes.add_get('/api/assets/{asset_id}',self._asset)
        routes.add_get('/api/config',self._config);routes.add_post('/api/config',self._config)
        routes.add_get('/api/pairing',self._pairing_info)
        routes.add_get('/ws',self._ws)
        routes.add_get('/{path:.*}',self._static)

    async def start(self):
        self.runner=web.AppRunner(self.app,access_log=None,shutdown_timeout=3)
        await self.runner.setup()
        self.site=web.TCPSite(self.runner,'127.0.0.1',0)
        await self.site.start()
        self.port=self.site._server.sockets[0].getsockname()[1]
        return f'http://127.0.0.1:{self.port}'

    async def close(self):
        runner,self.runner=self.runner,None
        self.site=self.port=None
        if runner:await runner.cleanup()

    async def _headers(self,request,response):
        response.headers.update(HEADERS)

    @web.middleware
    async def _transport(self,request,handler):
        snapshot=self.manager.snapshot()
        origin=snapshot.get('origin')
        if not snapshot.get('ready') or not origin:raise web.HTTPServiceUnavailable(text='Browser link is not ready. Start it on the PC.')
        local=request.transport.get_extra_info('sockname') if request.transport else None
        if (not local or local[0]!='127.0.0.1' or local[1]!=self.port
                or request.remote!='127.0.0.1' or request.host!=urlsplit(origin).netloc):
            raise web.HTTPForbidden(text='Invalid browser link destination.')
        # This trusted marker is set only by this dedicated listener. Headers on
        # the LAN listener cannot manufacture HTTPS or session authorization.
        request[BROWSER_ORIGIN]=origin
        return await handler(request)

    def _session(self,request):
        token=request.cookies.get(COOKIE)
        if not self.manager.valid_session(token):raise web.HTTPUnauthorized(text='Scan a fresh secure QR code on the PC.')
        request[BROWSER_SESSION]=token
        return token

    def _origin(self,request):
        if request.headers.get('Origin')!=request[BROWSER_ORIGIN]:
            raise web.HTTPForbidden(text='Invalid browser link origin.')

    async def _index(self,request):
        response=await self.owner.handle_index(request)
        source=re.sub(r'<script\s+src="/demo\.js(?:\?[^"]*)?"\s*>\s*</script>', '', response.text)
        source=source.replace('</head>','<meta name="touchhelm-browser-link" content="1"></head>')
        return web.Response(text=source,content_type='text/html')

    async def _pair(self,request):
        self._origin(request)
        try:
            data=await request.json()
            if not isinstance(data,dict) or set(data)!={'token'}:raise ValueError()
        except (ValueError,TypeError):raise web.HTTPBadRequest(text='Invalid pairing request.') from None
        token=self.manager.exchange(data['token'])
        if not token:raise web.HTTPUnauthorized(text='This QR code expired or was already used. Scan the current code on the PC.')
        response=web.json_response({'ready':True})
        response.set_cookie(COOKIE,token,secure=True,httponly=True,samesite='Strict',path='/',max_age=1800)
        return response

    async def _status(self,request):
        return web.json_response({'ready':self.manager.valid_session(request.cookies.get(COOKIE))})

    async def _info(self,request):
        self._session(request)
        return await self.owner.handle_info(request)

    async def _version(self,request):
        self._session(request)
        return await self.owner.handle_version(request)

    async def _asset(self,request):
        self._session(request)
        return await self.owner.handle_asset(request)

    async def _config(self,request):
        self._session(request)
        if request.method=='POST':
            self._origin(request)
            try:data=await request.json()
            except (ValueError,TypeError):raise web.HTTPBadRequest(text='Invalid settings.') from None
            allowed={'theme','mouse_sensitivity','mouse_acceleration','scroll_speed','invert_scroll','haptics_enabled','laser_color'}
            if not isinstance(data,dict) or not set(data)<=allowed:
                raise web.HTTPBadRequest(text='Change PC security and access settings on the desktop.')
        return await self.owner.handle_config(request)

    async def _pairing_info(self,request):
        self._session(request)
        if not self.owner._http_authorized(request):raise web.HTTPUnauthorized()
        # No CA download, local address, helper control or handoff endpoint.
        return web.json_response({'browser_link':True,'enabled':True,'certificate_available':False,
            'message':'Secure browser link is active. No phone certificate or app is required.'})

    async def _ws(self,request):
        session=self._session(request)
        self._origin(request)
        if session in self._sockets:raise web.HTTPConflict(text='This browser session is already connected.')
        self._sockets.add(session)
        try:return await self.owner.handle_ws(request)
        finally:self._sockets.discard(session)

    async def _static(self,request):
        relative=request.match_info['path']
        normalized=relative.casefold()
        parts=Path(relative).parts
        suffix=Path(relative).suffix.lower()
        if (not relative or '\\' in relative or any(part in ('.','..') for part in parts)
                or normalized.startswith(('preview','demo.')) or normalized=='sw.js'
                or suffix not in ('.js','.css','.svg','.png','.webp','.jpg','.jpeg','.woff2','.woff','.ico') and relative!='manifest.json'):
            raise web.HTTPNotFound()
        candidate=(WEB/relative).resolve()
        if not candidate.is_relative_to(WEB) or not candidate.is_file():raise web.HTTPNotFound()
        return web.FileResponse(candidate)
