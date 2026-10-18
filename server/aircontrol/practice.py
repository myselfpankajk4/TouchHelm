"""Pure, bounded practice tasks. Events are proposals, never Windows input."""
from collections import deque
from copy import deepcopy
import math


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


class PracticeSession:
    def __init__(self):
        self.viewport=(640,480);self.revision=-1;self.results=deque(maxlen=100)
        self.name='free';self.status='idle';self.targets=[];self.target_index=0
        self.misses=0;self.successes=0;self.accepted_clicks=0;self.document_position=0.
        self.goal=.75;self._press=None;self._elapsed=0.;self._started=0.;self._stamp=-1.

    def set_viewport(self,width,height,revision=0):
        if any(type(v) is not int or not 160<=v<=8192 for v in (width,height)):
            raise ValueError('Practice area dimensions must be between 160 and 8192 pixels.')
        if type(revision) is not int or not 0<=revision<=2147483647:raise ValueError('Invalid practice area revision.')
        if revision<self.revision:return
        if revision==self.revision and (width,height)!=self.viewport:raise ValueError('Practice area changed. Send a newer revision.')
        changed=self.viewport!=(width,height)
        self.viewport=(width,height);self.revision=revision
        if changed:self._press=None
        self._targets()

    def _targets(self):
        centers=[(.25,.5),(.75,.5),(.5,.25)] if self.name=='click' else [(.25,.5),(.75,.5)] if self.name=='drag' else []
        w,h=self.viewport;self.targets=[]
        for x,y in centers:
            x=max(48,min(w-48,x*w));y=max(48,min(h-48,y*h))
            self.targets.append({'x':(x-32)/w,'y':(y-32)/h,'width':64/w,'height':64/h})

    def start(self,name,at):
        if name not in ('free','click','drag','scroll') or not finite(at) or at<0:raise ValueError('Choose a supported practice exercise.')
        self.name=name;self.status='idle' if name=='free' else 'running'
        self.target_index=0;self.misses=0;self.successes=0;self.accepted_clicks=0
        self.document_position=0.;self._press=None;self._elapsed=0.;self._started=at;self._stamp=at-1
        self._targets()

    def _inside(self,point,index):
        target=self.targets[index]
        return target['x']<=point[0]<=target['x']+target['width'] and target['y']<=point[1]<=target['y']+target['height']

    def _distance(self,a,b):
        return math.hypot((a[0]-b[0])*self.viewport[0],(a[1]-b[1])*self.viewport[1])

    def _finish(self,at):
        self._elapsed+=max(0,at-self._started);self.status='complete';self._press=None
        self.results.append({'name':self.name,'elapsed_ms':round(self._elapsed*1000),
            'misses':self.misses,'successes':self.successes})

    def consume(self,events,point,at):
        if self.status!='running' or not finite(at) or at<=self._stamp:return
        self._stamp=at
        if not isinstance(point,(tuple,list)) or len(point)!=2 or any(not finite(v) or not 0<=v<=1 for v in point):return
        for event in events:
            if self.status!='running':break
            kind=event.get('kind');action=event.get('action')
            if kind in ('action','hud_action') and action=='pause':self.interrupt(at);break
            if self.name=='scroll':
                if kind=='scroll' and finite(event.get('dy')):
                    self.document_position=max(0.,min(1.,self.document_position-event['dy']*.04))
                    if self.document_position>=self.goal:self.successes=1;self._finish(at)
                continue
            click=kind=='action' and action in ('left_click','double_click')
            if kind=='button' and event.get('button')=='left':
                if action=='down':
                    self._press=(tuple(point),at,self._inside(point,0) if self.name=='drag' else True)
                elif action=='up' and self._press:
                    origin,stamp,valid=self._press;self._press=None
                    if self.name=='drag':
                        if valid and self._inside(point,1):self.successes=1;self._finish(at)
                        else:self.misses+=1
                    else:click=at-stamp<=.5 and self._distance(origin,point)<=12
            if self.name=='click' and click:
                if self._inside(point,self.target_index):
                    self.successes+=1;self.accepted_clicks+=1;self.target_index+=1
                    if self.target_index==len(self.targets):self._finish(at)
                else:self.misses+=1

    def interrupt(self,at):
        if self.status=='running':
            self._elapsed+=max(0,at-self._started);self.status='paused';self._press=None

    def resume(self,at):
        if self.status=='paused':self.status='running';self._started=at;self._stamp=at-1

    def clear_history(self):
        self.results.clear()

    def snapshot(self,at):
        elapsed=self._elapsed+(max(0,at-self._started) if self.status=='running' else 0)
        return deepcopy({'name':self.name,'status':self.status,'viewport_revision':self.revision,
            'viewport':list(self.viewport),'targets':self.targets,'target_index':self.target_index,
            'misses':self.misses,'successes':self.successes,'accepted_clicks':self.accepted_clicks,
            'elapsed_ms':round(elapsed*1000),'document_position':self.document_position,
            'goal':self.goal,'results':list(self.results)})
