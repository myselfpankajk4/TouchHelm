"""Lazy WebRTC media worker on its own event loop and bounded capture threads."""
from __future__ import annotations
import asyncio
import ctypes
from ctypes import wintypes
import importlib.util
import threading
import time
from fractions import Fraction
from concurrent.futures import ThreadPoolExecutor

from .remote_service import QUALITIES, private_sdp


def media_peer_matches(pc,peer):
    """Pinned aiortc/aioice seam: all selected RTP transports reach this phone."""
    import ipaddress
    try:
        expected=ipaddress.ip_address(peer);allowed={str(expected)}
        from .discovery import get_local_ip_addresses
        local=get_local_ip_addresses()
        if expected.is_loopback or str(expected) in local:
            # A browser on this PC may nominate its other actual NIC. This never
            # broadens the allowed address set of an external phone.
            allowed.update(local)
        hosts=[]
        for transceiver in pc.getTransceivers():
            connection=transceiver.sender.transport.transport._connection
            pairs=list(connection._nominated.values())
            if not pairs:return False
            hosts.extend(pair.remote_candidate.host for pair in pairs)
        return bool(hosts) and all(str(ipaddress.ip_address(host)) in allowed for host in hosts)
    except (AttributeError,ValueError,TypeError):return False

def configure_video_encoding(quality):
    """aiortc 1.15's stock camera budgets blur desktop text. Retain REMB."""
    from aiortc.codecs import h264, vpx
    budget={'saver':1200000,'balanced':3000000,'clear':6000000,'detail':10000000}[quality]
    for codec in (h264,vpx):
        codec.DEFAULT_BITRATE=budget
        codec.MAX_BITRATE=12000000
    return budget

def release_dxgi_duplicator(self):
    """comtypes pointers release themselves; an explicit Release double-frees."""
    if self.duplicator is not None:
        self.release_frame()
        self.texture = None
        self.duplicator = None


def release_stage_surface(self):
    self.width = self.height = 0
    self.interface = None
    self.texture = None


def fix_dxcam_030_release():
    # Narrow compatibility repair for pinned DXcam 0.3.0 (upstream issue #144).
    # Do not change site-packages or replace cleanup in future library versions.
    from importlib.metadata import version
    if version('dxcam') == '0.3.0':
        from dxcam.core.dxgi_duplicator import DXGIDuplicator
        from dxcam.core.stagesurf import StageSurface
        DXGIDuplicator.release = release_dxgi_duplicator
        StageSurface.release = release_stage_surface


def capabilities():
    video=all(importlib.util.find_spec(name) is not None for name in ('aiortc','av','dxcam','cv2'))
    audio=all(importlib.util.find_spec(name) is not None for name in ('pyaudiowpatch','aiortc','av'))
    return {'video':video,'audio':audio,'message':'Ready for desktop streaming.' if video else
        'Install requirements-remote.txt on this PC to enable streaming.',
        'casting':{'receiver':'unknown','message':'Miracast support depends on this PC and phone. Open Windows Projecting to this PC to check.'}}


def unlocked_desktop():
    """Reject secure desktop and locked sessions; never capture them as live."""
    api=ctypes.windll.user32
    api.OpenInputDesktop.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    api.OpenInputDesktop.restype=wintypes.HANDLE
    api.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    api.CloseDesktop.argtypes=[wintypes.HANDLE]
    handle=api.OpenInputDesktop(0,False,1)
    if not handle:return False
    try:
        name=ctypes.create_unicode_buffer(256); needed=wintypes.DWORD()
        return bool(api.GetUserObjectInformationW(handle,2,name,ctypes.sizeof(name),ctypes.byref(needed)) and name.value=='Default')
    finally:api.CloseDesktop(handle)


class MediaWorker:
    def __init__(self, *, on_state,local_peer=None):
        self.on_state=on_state
        self.local_peer=local_peer;self.media_ready=None;self.audio_requested=False;self.peer_monitor=None
        self.loop=asyncio.new_event_loop()
        self.capture_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='TouchHelm capture')
        self.thread=threading.Thread(target=self._run,name='TouchHelm remote media',daemon=True)
        self.thread.start()
        self.pc=self.video=self.audio=None
        self.closed=False

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        pending=asyncio.all_tasks(self.loop)
        for task in pending:task.cancel()
        if pending:self.loop.run_until_complete(asyncio.gather(*pending,return_exceptions=True))
        self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        self.loop.close()

    async def _call(self, coroutine):
        if self.closed:
            coroutine.close();raise RuntimeError('Remote media worker stopped.')
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coroutine,self.loop))

    async def start(self, display, quality, audio):
        await self._call(self._start(display,quality,audio))

    async def _start(self, display, quality, audio):
        from aiortc import RTCPeerConnection, RTCConfiguration
        configure_video_encoding(quality)
        self.pc=RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.media_ready=asyncio.Event();self.audio_requested=audio
        if not self.local_peer:self.media_ready.set()
        self.video_sender=None
        if display is not None:
            self.video=DesktopTrack(display,quality,self.on_state,self.capture_pool,self.media_ready)
            if not self.local_peer:await self.loop.run_in_executor(self.capture_pool,self.video.capture.open)
            self.video_sender=self.pc.addTrack(self.video.track)
        # Always negotiate an audio transceiver; capture is opt-in, silence otherwise.
        if capabilities()['audio']:
            self.audio=AudioSource(self.on_state,self.media_ready)
            if audio and not self.local_peer:
                try:await asyncio.to_thread(self.audio.enable,True)
                except Exception as error:
                    self.audio.close();self.on_state('audio_unavailable','PC audio unavailable: '+str(error)[:160])
                    if display is None:raise RuntimeError('PC audio could not start: '+str(error)[:160]) from error
            self.pc.addTrack(self.audio.track)
        @self.pc.on('connectionstatechange')
        async def connection():
            state=self.pc.connectionState
            if state=='connected':
                if self.local_peer:
                    try:
                        if not media_peer_matches(self.pc,self.local_peer):raise RuntimeError('The media route is not the paired local phone.')
                        if self.video:await self.loop.run_in_executor(self.capture_pool,self.video.capture.open)
                        if self.audio and self.audio_requested:
                            try:await asyncio.to_thread(self.audio.enable,True)
                            except Exception:
                                self.audio.close();self.on_state('audio_unavailable','PC audio could not start. Check the Windows output device.')
                                if not self.video:raise
                        self.media_ready.set();self.peer_monitor=asyncio.create_task(self._watch_peer())
                    except Exception:
                        self.on_state('failed','A direct local media connection could not be verified. Reconnect on the same Wi-Fi.');return
                self.on_state('live','Desktop stream connected on local Wi-Fi.')
            elif state=='connecting':self.on_state('connecting','Connecting desktop media…')
            elif state=='failed':self.on_state('failed','WebRTC media could not reach the PC. Check Windows Firewall and local Wi-Fi.')
            elif state=='closed' and not self.closed:self.on_state('stopped','Desktop media stopped.')

    async def offer(self, sdp):
        return await self._call(self._offer(sdp))

    async def _offer(self,sdp):
        from aiortc import RTCSessionDescription, RTCRtpSender
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp,type='offer'))
        for transceiver in self.pc.getTransceivers():
            if transceiver.kind=='video':
                codecs=RTCRtpSender.getCapabilities('video').codecs
                ordered=[c for c in codecs if c.mimeType.lower()=='video/h264']+[c for c in codecs if c.mimeType.lower()=='video/vp8']
                transceiver.setCodecPreferences(ordered)
        await self.pc.setLocalDescription(await self.pc.createAnswer())
        return {'sdp':private_sdp(self.pc.localDescription.sdp),'sdp_type':'answer'}

    async def configure(self,display,quality,audio):
        return await self._call(self._configure(display,quality,audio))

    async def _configure(self,display,quality,audio):
        self.audio_requested=audio
        if self.local_peer and not self.media_ready.is_set():raise RuntimeError('Wait for the local media connection.')
        if self.video:await self.loop.run_in_executor(self.capture_pool,self.video.capture.configure,display,quality)
        budget=configure_video_encoding(quality)
        # Pinned aiortc exposes no public encoder policy. Keep this compatibility
        # seam guarded, and let subsequent REMB feedback lower the bitrate.
        encoder=getattr(self.video_sender,'_RTCRtpSender__encoder',None)
        if encoder is not None and hasattr(encoder,'target_bitrate'):encoder.target_bitrate=budget
        message=None
        if self.audio:
            try:await asyncio.to_thread(self.audio.enable,audio)
            except Exception as error:
                self.audio.close();message='PC audio unavailable: '+str(error)[:160]
                self.on_state('audio_unavailable',message)
        return {'audio':bool(self.audio and self.audio.stream),'message':message}

    async def stop(self):
        if self.closed:return
        self.closed=True
        async def cleanup():
            try:
                if self.peer_monitor:self.peer_monitor.cancel()
                if self.pc:await asyncio.wait_for(self.pc.close(),3)
            finally:
                try:
                    if self.video:await self.loop.run_in_executor(self.capture_pool,self.video.capture.close)
                finally:
                    if self.audio:await asyncio.to_thread(self.audio.close)
        future=asyncio.run_coroutine_threadsafe(cleanup(),self.loop)
        def finished(_):
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.capture_pool.shutdown(wait=False,cancel_futures=True)
        future.add_done_callback(finished)
        await asyncio.shield(asyncio.wrap_future(future))
        await asyncio.to_thread(self.thread.join,3)

    async def _watch_peer(self):
        while not self.closed:
            await asyncio.sleep(.5)
            if self.pc.connectionState!='connected' or not media_peer_matches(self.pc,self.local_peer):
                self.media_ready.clear();self.on_state('failed','Local media connection ended. Reconnect on the same Wi-Fi.');return


class DesktopCapture:
    def __init__(self,display,quality):
        self.display,self.quality=display,quality
        self.camera=None;self.lock=threading.RLock();self.last_frame=None
        self.last_seen=time.monotonic();self.checked=0;self.dimensions=None

    def cursor(self):
        point=wintypes.POINT()
        api=ctypes.windll.user32
        if not api.GetPhysicalCursorPos(ctypes.byref(point)):return {'visible':False}
        rect=self.display['rect']
        x=(point.x-rect['x'])/max(1,rect['width']-1);y=(point.y-rect['y'])/max(1,rect['height']-1)
        return {'visible':0<=x<=1 and 0<=y<=1,'x':x,'y':y}

    def open(self):
        import dxcam
        if hasattr(dxcam,'__version__') or getattr(dxcam,'__file__',None):fix_dxcam_030_release()
        # Bind registered GDI monitor identity to a DXGI output, never guess by title/order.
        factory=dxcam.__dict__.get('__factory')
        outputs=getattr(factory,'outputs',None)
        if outputs is None:outputs=getattr(factory,'_outputs',None)
        wanted=self.display['id']
        selected=None
        for device_index,group in enumerate(outputs or []):
            for output_index,output in enumerate(group):
                desc=getattr(output,'desc',None)
                name=getattr(desc,'DeviceName',None)
                if name==wanted:selected=(device_index,output_index)
        if selected is None:
            raise RuntimeError('DXGI could not match the selected monitor. Check the display driver and restart TouchHelm.')
        self.camera=dxcam.create(device_idx=selected[0],output_idx=selected[1],output_color='RGB',max_buffer_len=2,processor_backend='numpy')
        self.dimensions=(self.camera.width,self.camera.height)
        r=self.display['rect']
        if self.dimensions!=(r['width'],r['height']):
            self.close();raise RuntimeError('Monitor geometry changed. Refresh the monitor list.')

    def frame(self):
        with self.lock:
            if time.monotonic()-self.checked>1:
                self.checked=time.monotonic()
                if not unlocked_desktop():raise RuntimeError('Windows is locked or showing a secure desktop. Resume after unlocking.')
                output=getattr(self.camera,'_output',None)
                if output is not None:
                    output.update_desc()
                    desc=output.desc;bounds=desc.DesktopCoordinates
                    if type(bounds.left) is int:
                        geometry={'x':bounds.left,'y':bounds.top,'width':bounds.right-bounds.left,'height':bounds.bottom-bounds.top}
                        if not desc.AttachedToDesktop or geometry!=self.display['rect']:
                            raise RuntimeError('Monitor was removed or moved. Resume with the updated display.')
                if (self.camera.width,self.camera.height)!=self.dimensions:
                    raise RuntimeError('Monitor geometry changed. Resume with the updated display.')
            image=self.camera.grab()
            if (self.camera.width,self.camera.height)!=self.dimensions:
                raise RuntimeError('Monitor geometry changed. Resume with the updated display.')
            if image is not None:self.last_frame=image;self.last_seen=time.monotonic()
            if self.last_frame is None:raise RuntimeError('No desktop frame is available.')
            return self.last_frame

    def configure(self,display,quality):
        with self.lock:
            if display!=self.display:
                self.close();self.display=display;self.open()
            self.quality=quality

    def close(self):
        with self.lock:
            if self.camera:
                self.camera.release();self.camera=None
            self.last_frame=None


class DesktopTrack:
    def __init__(self,display,quality,on_state,capture_pool,ready=None):
        from aiortc import VideoStreamTrack
        from av import VideoFrame
        self.capture=DesktopCapture(display,quality)
        source=self
        class Track(VideoStreamTrack):
            def __init__(self):super().__init__();self.origin=time.monotonic();self.next=self.origin;self.cursor_at=0
            async def recv(self):
                if ready:await ready.wait()
                height,fps=QUALITIES[source.capture.quality]
                await asyncio.sleep(max(0,self.next-time.monotonic()))
                self.next=max(self.next+1/fps,time.monotonic())
                try:
                    image=await asyncio.get_running_loop().run_in_executor(capture_pool,source.capture.frame)
                    if time.monotonic()-self.cursor_at>.1:
                        self.cursor_at=time.monotonic()
                        cursor=await asyncio.get_running_loop().run_in_executor(capture_pool,source.capture.cursor)
                        on_state('cursor',cursor)
                    def convert():
                        frame=VideoFrame.from_ndarray(image,format='rgb24')
                        if frame.height>height:
                            width=max(2,round(frame.width*height/frame.height)//2*2)
                            frame=frame.reformat(width=width,height=height)
                        return frame
                    frame=await asyncio.to_thread(convert)
                    frame.pts=round((time.monotonic()-self.origin)*90000);frame.time_base=Fraction(1,90000)
                    return frame
                except Exception as error:
                    on_state('failed',str(error));raise
        self.track=Track()


class AudioSource:
    def __init__(self,on_state,ready=None):
        from aiortc import AudioStreamTrack
        self.api=self.stream=None;self.lock=threading.RLock();self.on_state=on_state
        self.channels=2;self.rate=48000;self.device=None;self.checked=0
        source=self
        class Track(AudioStreamTrack):
            def __init__(self):super().__init__();self.pts=0;self.next=time.monotonic();self.normalizer=AudioNormalizer()
            async def recv(self):
                if ready:await ready.wait()
                await asyncio.sleep(max(0,self.next-time.monotonic()));self.next=max(self.next+.02,time.monotonic())
                raw,rate,channels=await asyncio.to_thread(source.read)
                try:frame=self.normalizer.frame(raw,rate,channels)
                except Exception as error:
                    await asyncio.to_thread(source.close);source.on_state('audio_unavailable','PC audio conversion failed: '+str(error)[:120])
                    frame=self.normalizer.frame(bytes(3840),48000,2)
                frame.time_base=Fraction(1,48000);frame.pts=self.pts;self.pts+=960
                return frame
        self.track=Track()

    def enable(self,value):
        with self.lock:
            self.close()
            if not value:return
            import pyaudiowpatch as p
            self.api=p.PyAudio()
            device=self.api.get_default_wasapi_loopback()
            self.device=device['index'];self.rate=int(device['defaultSampleRate']);self.channels=min(2,int(device['maxInputChannels']))
            self.stream=self.api.open(format=p.paInt16,channels=self.channels,rate=self.rate,input=True,
                                      input_device_index=self.device,frames_per_buffer=self.rate//50)

    def read(self):
        with self.lock:
            if not self.stream:return bytes(48000//50*2*2),48000,2
            try:
                if time.monotonic()-self.checked>2:
                    self.checked=time.monotonic()
                    if self.api.get_default_wasapi_loopback()['index']!=self.device:self.enable(True)
                return self.stream.read(self.rate//50,exception_on_overflow=False),self.rate,self.channels
            except Exception as error:
                self.close();self.on_state('audio_unavailable','PC audio unavailable: '+str(error)[:160])
                return bytes(48000//50*2*2),48000,2

    def close(self):
        with self.lock:
            if self.stream:
                try:self.stream.stop_stream();self.stream.close()
                finally:self.stream=None
            if self.api:self.api.terminate();self.api=None


class AudioNormalizer:
    """Constant Opus input format even when the Windows output format changes."""
    def __init__(self):self.format=None;self.resampler=self.fifo=None

    def frame(self,raw,rate,channels):
        from av import AudioFrame, AudioResampler, AudioFifo
        if self.format!=(rate,channels):
            self.format=(rate,channels)
            self.resampler=AudioResampler(format='s16',layout='stereo',rate=48000)
            self.fifo=AudioFifo()
        native=AudioFrame(format='s16',layout='stereo' if channels==2 else 'mono',samples=rate//50)
        native.planes[0].update(raw);native.sample_rate=rate
        for frame in self.resampler.resample(native):
            frame.pts=None;self.fifo.write(frame)
        result=self.fifo.read(960,partial=True)
        data=bytes(result.planes[0])[:result.samples*4] if result is not None else b''
        output=AudioFrame(format='s16',layout='stereo',samples=960)
        output.planes[0].update(data.ljust(3840,b'\0'));output.sample_rate=48000
        return output
