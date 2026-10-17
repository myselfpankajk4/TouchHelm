"""Single-owner streaming authority. Media work never runs in the input loop."""
from __future__ import annotations
import asyncio
import math
import secrets
import time
import ipaddress
import re

QUALITIES = {'saver': (540, 15), 'balanced': (720, 30), 'clear': (1080, 30), 'detail': (1440, 24)}


def private_sdp(sdp):
    """No public ICE relay/STUN path. Retain LAN, tailnet and browser mDNS hosts."""
    lines=[];count=0
    for line in sdp.splitlines():
        if not line.startswith('a=candidate:'):
            lines.append(line);continue
        fields=line.split()
        if len(fields)<8 or fields[2].upper()!='UDP' or fields[7]!='host':continue
        address=fields[4]
        try:
            ip=ipaddress.ip_address(address)
            allowed=(ip.is_private or ip.is_loopback or ip in ipaddress.ip_network('100.64.0.0/10'))
            allowed=allowed and not (ip.is_multicast or ip.is_unspecified or ip.is_link_local)
        except ValueError:
            allowed=bool(re.fullmatch(r'[a-zA-Z0-9-]{1,63}\.local',address))
        try:port=int(fields[5])
        except ValueError:continue
        if allowed and 1<=port<=65535:lines.append(line);count+=1
    if not count:raise ValueError('No private WebRTC path is available. Check LAN/Tailscale and browser network permissions.')
    return '\r\n'.join(lines)+'\r\n'


def absolute_point(rect, x, y):
    if not all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 1 for v in (x,y)):
        return None
    return (rect['x'] + round(x * (rect['width']-1)),
            rect['y'] + round(y * (rect['height']-1)))


class RemoteService:
    def __init__(self, config, displays, worker_factory, release, input_controller,
                 *, capabilities, notify=None, before_control=None,control_allowed=None):
        self.config, self.displays, self.worker_factory = config, displays, worker_factory
        self.release, self.input, self.capabilities, self.notify = release, input_controller, capabilities, notify
        self.owner = self.worker = self.display = None
        self.session_id = self.revision = ''
        self.mode, self.quality, self.audio, self.state = 'view', 'balanced', False, 'stopped'
        self.message = 'No remote session.'
        self._timeout = None
        self._configuring = False
        self._closing = 0
        self.before_control = before_control
        self.control_allowed=control_allowed

    def snapshot(self):
        return {'type':'remote_state','session_id':self.session_id,'revision':self.revision,
                'state':self.state,'message':self.message,'mode':self.mode,'quality':self.quality,
                'audio':self.audio,'display':self.display,
                'device':getattr(self.owner,'device_name',None)}

    def _publish(self):
        if self.notify: self.notify(self.snapshot())

    async def stop(self, reason='Stopped', state='stopped'):
        owner, worker = self.owner, self.worker
        if worker:self._closing+=1
        self.owner = self.worker = self.display = None
        self.session_id = self.revision = ''
        self.state, self.message, self.audio = state, reason, False
        if self._timeout: self._timeout.cancel(); self._timeout = None
        if owner: self.release(owner)
        self._publish()
        if worker:
            try:
                await asyncio.wait_for(worker.stop(), 8)
                self._closing-=1
            except Exception:
                self.state='unavailable';self.message='Media cleanup did not finish. Restart TouchHelm before starting another stream.'
                self._publish()

    def blocks_input(self, client):
        return self.owner is not None and self.mode == 'control' and self.owner is not client

    def accept_input(self, client, data):
        return bool(self.owner is client and self.mode=='control' and self.state=='live'
                    and self.config.get('remote_enabled') and self.config.get('require_pin')
                    and client.authenticated and not client.ws.closed
                    and data.get('session_id')==self.session_id and data.get('revision')==self.revision)

    def point(self, client, data):
        if not self.accept_input(client,data): return None
        return absolute_point(self.display['rect'], data.get('x'), data.get('y'))

    def _owned(self, client, data):
        return self.owner is client and data.get('session_id')==self.session_id

    async def _monitor(self, display_id=None):
        result = await self.displays()
        displays = result.get('displays',[])
        if display_id is None:displays=sorted(displays,key=lambda value:not value.get('primary',False))
        for display in displays:
            if (display_id is None or display['id']==display_id) and all(
                type(display.get('rect',{}).get(k)) is int for k in ('x','y','width','height')):
                if display['rect']['width']>0 and display['rect']['height']>0: return display
        raise ValueError('Selected monitor is unavailable. Refresh and choose another monitor.')

    @staticmethod
    def _options(data, mode='control', quality='balanced', audio=False):
        mode, quality, audio = data.get('mode',mode), data.get('quality',quality), data.get('audio',audio)
        if mode not in ('control','view','audio') or quality not in QUALITIES or type(audio) is not bool:
            raise ValueError('Choose a valid remote mode, quality and audio setting.')
        if mode=='audio':audio=True
        return mode, quality, audio

    async def request(self, client, data, secure=False):
        kind = data.get('type')
        try:
            caps=self.capabilities()
            if kind=='remote_query':
                return {'type':'remote_capabilities','success':True,**caps,
                    'enabled':bool(self.config.get('remote_enabled')),
                    'pin_required':True,'secure':bool(secure), **await self.displays()}
            if not (client.authenticated and not client.ws.closed and secure and
                    self.config.get('require_pin') and self.config.get('remote_enabled')):
                raise PermissionError('Enable Remote screen access on the desktop, set a host PIN, and use trusted HTTPS.')
            if kind=='remote_start':
                if self.owner or self._closing: raise ValueError('A remote session is active or still stopping. Wait or stop it on the desktop first.')
                mode, quality, audio=self._options(data)
                if mode=='audio' and not caps.get('audio'):raise RuntimeError('PC audio streaming is unavailable. Check the desktop audio provider.')
                if mode!='audio' and not caps.get('video'): raise RuntimeError(caps.get('message','Install remote streaming dependencies on the PC.'))
                display=None if mode=='audio' else await self._monitor(data.get('display_id'))
                if mode=='control' and self.control_allowed and not self.control_allowed():mode='view'
                if not (client.authenticated and not client.ws.closed and self.config.get('remote_enabled') and self.config.get('require_pin')):
                    raise PermissionError('Remote access or pairing changed while monitors were loading.')
                if self.owner or self._closing: raise ValueError('A remote session is active or still stopping.')
                self.owner, self.display = client, display
                self.session_id, self.revision = secrets.token_urlsafe(24), secrets.token_urlsafe(12)
                sid=self.session_id
                self.mode, self.quality, self.audio = mode, quality, audio and bool(caps.get('audio'))
                self.state, self.message = 'connecting','Negotiating desktop stream…'
                loop=asyncio.get_running_loop()
                def event(state, message):
                    def apply():
                        if self.session_id!=sid: return
                        if state=='cursor':
                            if self.notify:self.notify({'type':'remote_cursor','session_id':sid,'revision':self.revision,**message})
                        elif state=='audio_unavailable':
                            self.audio=False; self.message=message; self._publish()
                            if self.mode=='audio':asyncio.create_task(self.stop(message,'unavailable'))
                        elif state in ('failed','stopped'):
                            asyncio.create_task(self.stop(message,'unavailable'))
                        else:
                            self.state,self.message=state,message; self._publish()
                    loop.call_soon_threadsafe(apply)
                try:
                    self.worker=self.worker_factory(on_state=event)
                    # Release preexisting app input before granting exclusive control.
                    self.release(client)
                    if mode=='control' and self.before_control:self.before_control()
                    await self.worker.start(display,self.quality,self.audio)
                    if self.session_id!=sid or not client.authenticated or client.ws.closed or not self.config.get('remote_enabled') or not self.config.get('require_pin'):
                        raise PermissionError('Pairing changed while the stream was starting.')
                except BaseException:
                    if self.session_id==sid: await self.stop('Stream could not start.','unavailable')
                    raise
                self._timeout=loop.call_later(30,lambda:asyncio.create_task(self.stop('WebRTC did not connect. Check Windows Firewall and LAN/tailnet connectivity.','unavailable')) if self.session_id==sid and self.state!='live' else None)
                self._publish()
                return {'success':True,'request':kind,**self.snapshot(),'capabilities':caps}
            if kind in ('remote_stop','remote_pause') and not self.owner:
                return {'success':True,'request':kind,**self.snapshot()}
            stopping_own_start=kind in ('remote_stop','remote_pause') and self.owner is client and not data.get('session_id')
            if not self._owned(client,data) and not stopping_own_start: raise PermissionError('Remote session is stale or belongs to another device.')
            sid=self.session_id
            if kind in ('remote_stop','remote_pause'):
                await self.stop('Paused. Tap Resume to reconnect.' if kind=='remote_pause' else 'Stopped',
                                'paused' if kind=='remote_pause' else 'stopped')
            elif kind=='remote_offer':
                sdp=data.get('sdp')
                if not isinstance(sdp,str) or len(sdp)>100000 or not sdp.startswith('v=0'):
                    raise ValueError('Invalid WebRTC offer.')
                answer=await self.worker.offer(private_sdp(sdp))
                if self.session_id!=sid: raise ValueError('Session ended during negotiation.')
                return {'type':'remote_answer','success':True,'session_id':sid,**answer}
            elif kind=='remote_config':
                if self._configuring: raise ValueError('Remote settings are still being applied.')
                mode,quality,audio=self._options(data,self.mode,self.quality,self.audio)
                if (mode=='audio') != (self.mode=='audio'):raise ValueError('Stop the current stream before switching between audio-only and screen access.')
                audio=audio and bool(caps.get('audio'))
                self._configuring=True
                try:
                    previous_state=self.state
                    display=None if mode=='audio' else await self._monitor(data.get('display_id',self.display['id']))
                    if mode=='control' and self.control_allowed and not self.control_allowed():mode='view'
                    if self.session_id!=sid: raise ValueError('Session ended while settings were changing.')
                    self.release(client)
                    if mode=='control' and self.mode!='control' and self.before_control:self.before_control()
                    self.state='connecting';self._publish()
                    readback=await self.worker.configure(display,quality,audio)
                    if self.session_id!=sid: raise ValueError('Session ended while settings were changing.')
                    if isinstance(readback,dict):audio=audio and bool(readback.get('audio',audio))
                    if mode=='control' and self.control_allowed and not self.control_allowed():mode='view'
                    self.display,self.mode,self.quality,self.audio=display,mode,quality,audio
                    self.revision=secrets.token_urlsafe(12)
                    self.state,self.message=previous_state,(readback.get('message') if isinstance(readback,dict) else None) or 'Remote settings applied.'
                    self._publish()
                except Exception:
                    if self.session_id==sid: await self.stop('Monitor or media settings could not be applied.','unavailable')
                    raise
                finally: self._configuring=False
            else: raise ValueError('Unsupported remote request.')
            return {'success':True,'request':kind,**self.snapshot()}
        except Exception as error:
            return {'type':'remote_result','success':False,'request':kind,'message':str(error)[:500]}
