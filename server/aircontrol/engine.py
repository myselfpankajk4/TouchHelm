"""Pure gesture state machine. Events are proposals, never native input."""
import math
from .profiles import validate_profile

def clamp(n):return max(0.,min(1.,n))
def number(value,default=0.):
    return float(value) if type(value) in (int,float) and math.isfinite(value) else default
def physical_point(rect,x,y):
    return (rect['x']+round(clamp(number(x))*(rect['width']-1)),
            rect['y']+round(clamp(number(y))*(rect['height']-1)))

class GestureEngine:
    def __init__(self,profile):
        self.profile=validate_profile(profile);self.held=False;self.lost=True
        self.gesture='';self.since=0.;self.fired=False;self.lock='';self.scroll_y=None
        self.point=None;self.dwell_anchor=None;self.dwell_since=0.;self.dwell_fired=False
        self.dwell_exit=None;self.last_action=-10.;self.progress=0.;self.confidence=0.
        self.sequence_time=-1.

    def reset(self):
        events=[{'kind':'button','action':'up','button':'left'}] if self.held else []
        self.held=False;self.gesture='';self.fired=False;self.lock='';self.scroll_y=None
        self.dwell_anchor=None;self.dwell_fired=False;self.dwell_exit=None;self.point=None;self.progress=0.
        return events

    def _gesture(self,hand,face):
        pose=hand.get('pose','')
        if pose=='Closed_Fist':return 'closed_fist'
        if pose=='Open_Palm':return 'open_palm'
        if pose=='Victory':return 'two_fingers'
        pi=number(hand.get('pinch_index'),1);pm=number(hand.get('pinch_middle'),1)
        threshold=self.profile['pinch_open'] if self.lock.startswith('pinch_') else self.profile['pinch_close']
        if pi<threshold and pm<threshold:return 'conflict'
        if pi<threshold and hand.get('index_extended',False):return 'pinch_index'
        if pm<threshold and pose not in ('Thumb_Up','Thumb_Down'):return 'pinch_middle'
        if pose in ('Thumb_Up','Thumb_Down'):return 'thumb_up' if pose=='Thumb_Up' else 'thumb_down'
        if self.profile['expressions_calibrated']:
            e=face.get('expressions',{});left=number(e.get('eyeBlinkLeft'));right=number(e.get('eyeBlinkRight'))
            calibrated=self.profile['calibrated_expressions']
            if 'wink_left' in calibrated and left>.75 and right<.25:return 'wink_left'
            if 'wink_right' in calibrated and right>.75 and left<.25:return 'wink_right'
            if 'smile' in calibrated and min(number(e.get('mouthSmileLeft')),number(e.get('mouthSmileRight')))>.7:return 'smile'
            if 'brows_up' in calibrated and number(e.get('browInnerUp'))>.75:return 'brows_up'
        return ''

    def step(self,frame,*,paused=False):
        events=[];t=number(frame.get('timestamp'),-1)
        if t<=self.sequence_time:return events
        self.sequence_time=t
        hand=frame.get('hand') or {};face=frame.get('face') or {};mode=self.profile['mode']
        hc=number(hand.get('confidence'));fc=number(face.get('confidence'))
        valid=(mode=='hand' and hc>=.65 or mode=='head' and fc>=.65 or mode=='combined' and min(hc,fc)>=.65)
        if mode!='hand' and face.get('count',0)!=1:valid=False
        if not valid:
            events=self.reset();self.lost=True;self.confidence=0.;return events
        self.lost=False;self.confidence=hc if mode=='hand' else fc if mode=='head' else min(hc,fc)
        if mode=='hand':
            x0,y0,x1,y1=self.profile['calibration']['hand_bounds']
            raw=(clamp((number(hand.get('x'),.5)-x0)/(x1-x0)),clamp((number(hand.get('y'),.5)-y0)/(y1-y0)))
        else:
            yaw,pitch=self.profile['calibration']['head_neutral'];span=self.profile['head_range']*2
            raw=(clamp(.5+(number(face.get('yaw'))-yaw)/span),clamp(.5+(number(face.get('pitch'))-pitch)/span))
        raw=tuple(clamp(.5+(v-.5)*self.profile['sensitivity']) for v in raw)
        alpha=1-self.profile['smoothing']
        self.point=raw if self.point is None else tuple(a+alpha*(b-a) for a,b in zip(self.point,raw))
        gesture=self._gesture(hand if mode!='head' else {},face)
        if self.lock=='conflict' and gesture:
            self.progress=0.;return events
        if self.lock and self.lock!=gesture and gesture:
            if self.held:
                events.append({'kind':'button','action':'up','button':'left'});self.held=False
            self.lock='conflict';self.gesture='conflict';self.progress=0.;return events
        if gesture!=self.gesture:
            # A gesture cannot change meaning while a mouse press is held.
            if self.held:
                events.append({'kind':'button','action':'up','button':'left'});self.held=False
            self.gesture=gesture;self.since=t;self.fired=False;self.scroll_y=None;self.progress=0.
            if self.lock and gesture not in (self.lock,'conflict'):
                self.lock=''
        if gesture=='conflict':
            self.lock='conflict';return events
        if self.lock=='conflict' and gesture:self.progress=0.;return events
        action=self.profile['bindings'].get(gesture,'none')
        hold=.1 if gesture.startswith('pinch_') else .2 if gesture=='two_fingers' else .6 if gesture=='closed_fist' else .8 if gesture=='open_palm' else self.profile['hold_ms']/1000
        self.progress=clamp((t-self.since)/hold) if gesture else 0.
        if gesture=='two_fingers' and action=='scroll' and not paused:
            if self.progress>=1:
                self.lock=gesture
                if self.scroll_y is not None:events.append({'kind':'scroll','dy':(number(hand.get('y'))-self.scroll_y)*-12})
                self.scroll_y=number(hand.get('y'))
            return events
        # Closed/Open palm may pause/resume but must not move the PC pointer.
        if gesture not in ('closed_fist','open_palm','thumb_up','thumb_down'):
            events.append({'kind':'pointer','x':self.point[0],'y':self.point[1]})
        if gesture and self.progress>=1 and not self.fired:
            if action=='left_drag' and not paused:
                self.held=True;self.lock=gesture;self.fired=True
                events.append({'kind':'button','action':'down','button':'left'})
            elif action not in ('none','scroll','left_drag') and (not paused or action=='resume'):
                if t-self.last_action>=self.profile['cooldown_ms']/1000 or action in ('pause','resume'):
                    events.append({'kind':'action','action':action});self.last_action=t;self.fired=True;self.lock=gesture
        if mode=='head' and (self.profile['dwell'] or paused) and not gesture:
            # Normalized radius corresponds to 18 physical pixels after mapping.
            scale=self.profile.get('_monitor_scale',(1920,1080))
            distance=lambda a,b:math.hypot((a[0]-b[0])*scale[0],(a[1]-b[1])*scale[1])
            if self.dwell_anchor is None:self.dwell_anchor=self.point;self.dwell_since=t
            if self.dwell_fired:
                if distance(self.point,self.dwell_anchor)>36:
                    if self.dwell_exit is None:self.dwell_exit=t
                    elif t-self.dwell_exit>=.25:self.dwell_fired=False;self.dwell_anchor=self.point;self.dwell_since=t
                else:self.dwell_exit=None
            elif distance(self.point,self.dwell_anchor)>18:
                self.dwell_anchor=self.point;self.dwell_since=t;self.progress=0.
            else:
                self.progress=clamp((t-self.dwell_since)/(self.profile['dwell_ms']/1000))
                if self.progress>=1:
                    events.append({'kind':'hud_dwell' if paused else 'action','action':'left_click','x':self.point[0],'y':self.point[1]})
                    self.dwell_fired=True
        return events
