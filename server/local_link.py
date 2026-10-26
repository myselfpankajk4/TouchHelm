"""Host-only DTLS control transport. Public HTTP is limited to bound pairing.

No input APIs live here. The caller supplies the existing authenticated command
loop. The selected-pair seam is pinned to bundled aiortc 1.15/aioice and fails
closed if that implementation's nominated address cannot be inspected.
"""
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time
from aiohttp import web, WSMessage

MAX_WIRE=50000
MAX_INBOUND=256*1024
MAX_OUTBOUND=6*1024*1024
PRIVATE=(ipaddress.ip_network('10.0.0.0/8'),ipaddress.ip_network('172.16.0.0/12'),
         ipaddress.ip_network('192.168.0.0/16'),ipaddress.ip_network('fc00::/7'))


def make_proof(secret,stage,nonce,sdp=''):
    value=(stage+'\n'+nonce+'\n'+sdp).encode('utf-8')
    return hmac.new(secret.encode('ascii'),value,hashlib.sha256).hexdigest()


def verify_proof(secret,stage,nonce,sdp,proof):
    return (isinstance(proof,str) and re.fullmatch('[a-f0-9]{64}',proof) is not None
            and hmac.compare_digest(make_proof(secret,stage,nonce,sdp),proof))


def adapter_networks():
    import ifaddr
    networks=[]
    for adapter in ifaddr.get_adapters():
        for item in adapter.ips:
            address=item.ip if isinstance(item.ip,str) else item.ip[0]
            try:
                host=ipaddress.ip_address(address)
                if any(host.version==network.version and host in network for network in PRIVATE):
                    networks.append(str(ipaddress.ip_network(f'{host}/{item.network_prefix}',strict=False)))
            except ValueError:pass
    return networks


def _local(address,networks):
    try:
        host=ipaddress.ip_address(address)
        return (any(host.version==network.version and host in network for network in PRIVATE)
                and any(host in ipaddress.ip_network(network) for network in networks
                        if ipaddress.ip_network(network).version==host.version))
    except (ValueError,TypeError):return False


def local_peer_address(pc,networks):
    try:
        pairs=pc.sctp.transport.transport._connection._nominated
        addresses=[pair.remote_candidate.host for pair in pairs.values()]
        if addresses and all(_local(address,networks) for address in addresses):return addresses[0]
    except (AttributeError,TypeError):pass
    return None


def local_sdp(sdp,networks):
    lines=[]
    for line in sdp.splitlines():
        if line.startswith('a=candidate:'):
            parts=line.split()
            if (len(parts)<8 or parts[2].lower()!='udp' or parts[7]!='host'
                    or not _local(parts[4],networks)):continue
        lines.append(line)
    return '\r\n'.join(lines)+'\r\n'


def fingerprint(sdp):
    values=set(re.findall(r'^a=fingerprint:sha-256 ([A-Fa-f0-9:]+)\r?$',sdp,re.M))
    if len(values)!=1:raise ValueError('A unique SHA-256 peer fingerprint is required.')
    value=values.pop().replace(':','').lower()
    if not re.fullmatch('[a-f0-9]{64}',value):raise ValueError('Invalid peer fingerprint.')
    return value


def encode_frames(raw):
    payload=raw.encode('utf-8')
    if len(payload)>MAX_OUTBOUND:raise ValueError('Local response exceeded its limit.')
    if len(payload)<MAX_WIRE:return [raw]
    chunks=[payload[i:i+32768] for i in range(0,len(payload),32768)]
    identifier=secrets.randbelow(2**31)
    return [json.dumps({'type':'local_chunk','id':identifier,'index':i,'count':len(chunks),
                        'data':base64.b64encode(chunk).decode('ascii')},separators=(',',':')) for i,chunk in enumerate(chunks)]


class ChannelSocket:
    local_control=True
    def __init__(self,channel):
        self.channel=channel;self.closed=False
        self._queue=asyncio.Queue(maxsize=256);self._bytes=0
        self._assembly=None;self._send_lock=asyncio.Lock()

    def feed(self,raw):
        if self.closed:return
        try:
            if not isinstance(raw,str) or len(raw.encode('utf-8'))>MAX_WIRE:raise ValueError()
            value=json.loads(raw)
            if not isinstance(value,dict):raise ValueError()
            if isinstance(value,dict) and value.get('type')=='local_chunk':
                if (set(value)!={'type','id','index','count','data'} or type(value['id']) is not int
                        or type(value['index']) is not int or type(value['count']) is not int
                        or not 1<=value['count']<=8 or not isinstance(value['data'],str)):raise ValueError()
                if value['index']==0:
                    if self._assembly is not None:raise ValueError()
                    self._assembly=[value['id'],value['count'],0,bytearray(),time.monotonic()]
                group=self._assembly
                if (not group or group[0]!=value['id'] or group[1]!=value['count'] or group[2]!=value['index']
                        or time.monotonic()-group[4]>5):raise ValueError()
                group[3].extend(base64.b64decode(value['data'],validate=True));group[2]+=1
                if len(group[3])>MAX_INBOUND:raise ValueError()
                if group[2]<group[1]:return
                raw=group[3].decode('utf-8');self._assembly=None
                if not isinstance(json.loads(raw),dict):raise ValueError()
            elif self._assembly is not None:raise ValueError()
            size=len(raw.encode('utf-8'))
            if size>MAX_INBOUND or self._bytes+size>2*1024*1024 or self._queue.full():raise ValueError()
            self._bytes+=size;self._queue.put_nowait(raw)
        except (ValueError,TypeError,UnicodeError,KeyError,RecursionError):self.abort()

    def abort(self):
        if self.closed:return
        self.closed=True;self._assembly=None
        while not self._queue.empty():self._queue.get_nowait()
        self._bytes=0;self._queue.put_nowait(None)
        self.channel.close()

    async def close(self,**kwargs):self.abort()
    def __aiter__(self):return self
    async def __anext__(self):
        raw=await self._queue.get()
        if raw is None:raise StopAsyncIteration
        self._bytes-=len(raw.encode('utf-8'))
        return WSMessage(web.WSMsgType.TEXT,raw,'')

    async def send_json(self,data):
        async with self._send_lock:
            for frame in encode_frames(json.dumps(data,separators=(',',':'),ensure_ascii=False)):
                deadline=time.monotonic()+5
                while self.channel.bufferedAmount>256*1024:
                    if self.closed or time.monotonic()>deadline:raise ConnectionError('Local channel backpressure.')
                    await asyncio.sleep(.01)
                if self.closed or self.channel.readyState!='open':raise ConnectionError('Local channel closed.')
                self.channel.send(frame)


class LocalControlLink:
    def __init__(self,serve,on_connected,*,on_ended=None,networks=None,clock=time.monotonic):
        self.serve=serve;self.on_connected=on_connected;self.clock=clock
        self.networks=networks;self._networks=networks;self.on_ended=on_ended
        self.pc=self.socket=self._serve_task=self._monitor=None
        self.offer=self.digest=self.nonce=None
        self.accepted=False;self.connected=False;self.deadline=0
        self._lock=asyncio.Lock()
        self._close_lock=asyncio.Lock()

    async def prepare(self):
        from aiortc import RTCPeerConnection,RTCConfiguration
        await self.close()
        self.networks=adapter_networks() if self._networks is None else self._networks
        if not self.networks:raise ValueError('Connect this PC to a private local network first.')
        self.pc=pc=RTCPeerConnection(RTCConfiguration(iceServers=[]))
        channel=pc.createDataChannel('touchhelm-control',ordered=True)
        self.nonce=secrets.token_urlsafe(32);self.accepted=False
        self.deadline=self.clock()+1800
        self.pairing_deadline=self.clock()+120
        @channel.on('message')
        def message(raw):
            if self.socket:self.socket.feed(raw)
        @channel.on('close')
        def closed():
            if self.socket:self.socket.abort()
        @channel.on('open')
        async def opened():
            address=local_peer_address(pc,self.networks)
            if not address or pc is not self.pc:
                channel.close();return
            self.socket=ChannelSocket(channel);self.connected=True
            self._serve_task=asyncio.create_task(self._run_socket(self.socket,address))
            await self.on_connected()
        await pc.setLocalDescription(await pc.createOffer())
        self.offer=local_sdp(pc.localDescription.sdp,self.networks)
        if 'a=candidate:' not in self.offer:
            await self.close();raise ValueError('No local Wi-Fi or Ethernet route is available.')
        self.digest=fingerprint(self.offer)
        self._monitor=asyncio.create_task(self._watch(pc))

    def proof_valid(self,secret,stage,proof,sdp=''):
        return (self.pc is not None and not self.accepted and self.clock()<self.deadline
                and self.clock()<self.pairing_deadline and self.nonce is not None and verify_proof(secret,stage,self.nonce,sdp,proof))

    async def _run_socket(self,socket,address):
        try:await self.serve(socket,address)
        finally:await socket.close()

    async def answer(self,secret,sdp,proof):
        from aiortc import RTCSessionDescription
        async with self._lock:
            if not isinstance(sdp,str) or len(sdp.encode('utf-8'))>32768 or not self.proof_valid(secret,'answer',proof,sdp):
                raise PermissionError('Pairing proof is invalid or expired.')
            fingerprint(sdp)
            if any(line.startswith(('m=video','m=audio')) for line in sdp.splitlines()):
                raise ValueError('The control pairing channel cannot request capture.')
            self.accepted=True
            await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp,type='answer'))

    async def _watch(self,pc):
        while pc is self.pc:
            await asyncio.sleep(.5)
            if (self.clock()>=self.deadline or not self.connected and self.clock()>=self.pairing_deadline or pc.connectionState in ('closed','failed')
                    or self.connected and (not local_peer_address(pc,self.networks) or self.socket.closed)):
                await self.close()
                if self.on_ended:await self.on_ended()
                return

    async def close(self):
        async with self._close_lock:await self._close()

    async def _close(self):
        self.connected=False;self.offer=self.digest=self.nonce=None;self.accepted=False
        pc,self.pc=self.pc,None
        socket,self.socket=self.socket,None
        if socket:await socket.close()
        task,self._serve_task=self._serve_task,None
        if task and task is not asyncio.current_task():
            try:await asyncio.wait_for(asyncio.shield(task),3)
            except (Exception,asyncio.CancelledError):task.cancel();await asyncio.gather(task,return_exceptions=True)
        monitor,self._monitor=self._monitor,None
        if monitor and monitor is not asyncio.current_task():monitor.cancel();await asyncio.gather(monitor,return_exceptions=True)
        if pc:await pc.close()

    def snapshot(self):
        return {'connected':bool(self.connected and self.socket and not self.socket.closed),
                'expires_in':max(0,int(self.deadline-self.clock())) if self.connected else 0}
