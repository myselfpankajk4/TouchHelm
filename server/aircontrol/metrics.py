"""Bounded measurements and explicitly allowlisted, image-free reports."""
from collections import deque
import math
import re
import statistics
import time


def bounded(value,maximum=60000):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=maximum


class SessionMetrics:
    def __init__(self,latencies=None):
        self.latencies=latencies if latencies is not None else deque(maxlen=600)
        self.times=deque(maxlen=600);self.reset(time.monotonic())

    def reset(self,at):
        self.latencies.clear();self.times.clear();self.started=at;self.last=-1.;self.stopped=None
        self.tracking=None;self.interruptions=0
        self.latest={'capture_fps':None,'inference_ms':None,'frame_age_ms':None}

    def stop(self,at):
        if self.stopped is None:self.stopped=at

    def record_latency(self,value):
        if bounded(value):
            self.latencies.append(value)
            while len(self.latencies)>600:self.latencies.popleft()

    def mark_lost(self):
        if self.tracking is True:self.interruptions+=1
        self.tracking=False

    def observe(self,*,at,tracked,capture_fps=None,inference_ms=None,frame_age_ms=None):
        if not bounded(at,1e12) or at<=self.last:return
        if tracked is False:self.mark_lost()
        else:self.tracking=tracked
        self.last=at;self.times.append(at)
        for key,value in [('capture_fps',capture_fps),('inference_ms',inference_ms),('frame_age_ms',frame_age_ms)]:
            if bounded(value,240 if key=='capture_fps' else 60000):self.latest[key]=value

    def snapshot(self,at):
        samples=sorted(v for v in self.latencies if bounded(v))[-600:]
        fps=(len(self.times)-1)/(self.times[-1]-self.times[0]) if len(self.times)>1 and self.times[-1]>self.times[0] else None
        return dict(self.latest,latency_window_limit=600,latency_sample_count=len(samples),
            median_latency_ms=round(statistics.median(samples),2) if samples else None,
            p95_latency_ms=round(samples[math.ceil(.95*len(samples))-1],2) if samples else None,
            tracking_interruptions=self.interruptions,duration_seconds=round(max(0,(self.stopped if self.stopped is not None else at)-self.started),1),
            observation_fps=round(fps,1) if fps is not None else None)

    def report(self,*,at,mode,display_size,results,build_id):
        exercises=[]
        for item in results[-100:]:
            if not isinstance(item,dict) or item.get('name') not in ('click','drag','scroll'):continue
            if not bounded(item.get('elapsed_ms'),86400000):continue
            if any(type(item.get(k)) is not int or not 0<=item[k]<=1000000 for k in ('misses','successes')):continue
            exercises.append({k:item[k] for k in ('name','elapsed_ms','misses','successes')})
        size=list(display_size) if isinstance(display_size,(tuple,list)) and len(display_size)==2 and all(type(n) is int and 1<=n<=32768 for n in display_size) else []
        build=build_id if isinstance(build_id,str) and re.fullmatch('[a-f0-9]{16,64}',build_id) else ''
        metrics=self.snapshot(at)
        return {'version':1,'build':build,'mode':mode if mode in ('hand','head','combined') else 'unknown',
            'display_size':size,'duration_seconds':metrics['duration_seconds'],'metrics':metrics,'exercises':exercises}
