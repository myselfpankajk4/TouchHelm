"""Generated video and test-tone audio. Never captures the PC."""
from aiortc import RTCPeerConnection,RTCConfiguration,RTCSessionDescription,VideoStreamTrack,AudioStreamTrack
from av import VideoFrame
from server.remote_service import private_sdp


class GeneratedCapture:
    """Native capture boundary substitute for the real MediaWorker test."""
    def __init__(self,display,quality):self.display=display;self.quality=quality;self.counter=0;self.opened=False
    def open(self):self.opened=True
    def frame(self):
        if not self.opened:raise RuntimeError('Capture opened before local route validation')
        import numpy as np
        self.counter+=1;return np.full((360,640,3),60+self.counter%100,dtype=np.uint8)
    def cursor(self):return {'visible':False}
    def configure(self,display,quality):self.display=display;self.quality=quality
    def close(self):self.opened=False


class GeneratedAudio:
    def __init__(self,on_state,ready=None):
        self.stream=None;self.device=None
        source=self
        class Track(AudioStreamTrack):
            async def recv(self):
                if ready:await ready.wait()
                frame=await super().recv()
                import math,struct
                raw=b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*440*(frame.pts+i)/frame.sample_rate)) if source.stream else 0) for i in range(frame.samples))
                for plane in frame.planes:plane.update(raw.ljust(plane.buffer_size,b'\0'))
                return frame
        self.track=Track()
    def enable(self,value):self.stream=object() if value else None
    def close(self):self.stream=None


class GeneratedVideo(VideoStreamTrack):
    def __init__(self):super().__init__();self.counter=0
    async def recv(self):
        pts,time_base=await self.next_timestamp();self.counter+=1
        frame=VideoFrame(width=640,height=360,format='yuv420p')
        for index,plane in enumerate(frame.planes):plane.update(bytes([(self.counter%120)+60 if index==0 else 128])*plane.buffer_size)
        frame.pts=pts;frame.time_base=time_base;return frame


class SyntheticMediaWorker:
    def __init__(self,on_state):self.on_state=on_state;self.pc=None
    async def start(self,display,quality,audio):
        self.pc=pc=RTCPeerConnection(RTCConfiguration(iceServers=[]))
        if display is not None:pc.addTrack(GeneratedVideo())
        pc.addTrack(AudioStreamTrack())
        @pc.on('connectionstatechange')
        def state():
            if pc.connectionState=='connected':self.on_state('live','Synthetic media connected.')
            elif pc.connectionState=='failed':self.on_state('failed','Synthetic media failed.')
    async def offer(self,sdp):
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp,type='offer'))
        await self.pc.setLocalDescription(await self.pc.createAnswer())
        return {'sdp':private_sdp(self.pc.localDescription.sdp),'sdp_type':'answer'}
    async def configure(self,display,quality,audio):return {'audio':audio,'message':'Synthetic settings applied.'}
    async def stop(self):
        if self.pc:await self.pc.close()
