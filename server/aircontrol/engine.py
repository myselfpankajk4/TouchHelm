"""Pure gesture state machine. Events are proposals, never native input."""
import math
from .profiles import validate_profile
from .filters import OneEuro
from .expressions import recognize

def clamp(n):return max(0.,min(1.,n))
def number(value,default=0.):
    return float(value) if type(value) in (int,float) and math.isfinite(value) else default
def physical_point(rect,x,y):
    return (rect['x']+round(clamp(number(x))*(rect['width']-1)),
            rect['y']+round(clamp(number(y))*(rect['height']-1)))

def tracked(source):
    """Tasks returns accepted landmarks, not a per-hand presence percentage."""
    if 'tracked' in source:return source['tracked'] is True
    # Older synthetic/provider observations remain compatible during migration.
    return number(source.get('confidence'))>=.65

class GestureEngine:
    def __init__(self,profile):
        self.profile=validate_profile(profile);self.held=False;self.lost=True
        self.gesture='';self.since=0.;self.fired=False;self.lock='';self.scroll_y=None
        self.point=None;self.dwell_anchor=None;self.dwell_since=0.;self.dwell_fired=False
        self.dwell_exit=None;self.last_action=-10.;self.progress=0.;self.confidence=0.
        self.sequence_time=-1.
        self.pinch_anchor=None;self.pinch_origin=None
        self.dwell_action='left_click';self.drag_latched=False;self.hud_regions=[];self.dwell_target=None
        self.steady_point=None
        self.hud_blocked=False
        smoothing=self.profile['smoothing'];head=self.profile['mode']!='hand'
        self.filters=[OneEuro((.3 if head else 1.)+(1-smoothing)*(1.4 if head else 2.),6.) for _ in range(2)]

    def reset(self):
        events=[{'kind':'button','action':'up','button':'left'}] if self.held else []
        self.held=False;self.gesture='';self.fired=False;self.lock='';self.scroll_y=None
        self.dwell_anchor=None;self.dwell_fired=False;self.dwell_exit=None;self.point=None;self.progress=0.
        self.pinch_anchor=None;self.pinch_origin=None
        self.dwell_action='left_click';self.drag_latched=False;self.dwell_target=None;self.steady_point=None
        for filter in self.filters:filter.reset()
        return events

    def select_dwell(self,action):
        if action not in ('left_click','right_click','double_click','drag'):raise ValueError('Choose a supported dwell action')
        if self.held:raise ValueError('Release the current drag before choosing another action')
        self.dwell_action=action;self.dwell_anchor=self.point;self.dwell_since=self.sequence_time
        self.profile['dwell']=True
        self.hud_blocked=True
        self.dwell_fired=self.point is not None;self.dwell_exit=None;self.progress=0.

    def _gesture(self,hand,face,*,paused=False):
        pose=hand.get('pose','')
        if pose=='Closed_Fist':return 'closed_fist'
        if pose=='Open_Palm' and paused:return 'open_palm'
        pi=number(hand.get('pinch_index'),1);pm=number(hand.get('pinch_middle'),1)
        index_threshold=self.profile['pinch_open'] if self.lock=='pinch_index' else self.profile['pinch_close']
        middle_threshold=self.profile['pinch_open'] if self.lock=='pinch_middle' else self.profile['pinch_close']
        if pi<index_threshold and pm<middle_threshold:return 'conflict'
        if pi<index_threshold:return 'pinch_index'
        if pm<middle_threshold and pose not in ('Thumb_Up','Thumb_Down'):return 'pinch_middle'
        if pose=='Victory':return 'two_fingers'
        if pose in ('Thumb_Up','Thumb_Down'):
            gesture='thumb_up' if pose=='Thumb_Up' else 'thumb_down'
            if self.profile['bindings'][gesture]!='none':return gesture
        expression=recognize(face,self.profile,self.gesture)
        return expression or ('open_palm' if pose=='Open_Palm' else '')

    def step(self,frame,*,paused=False):
        events=[];t=number(frame.get('timestamp'),-1)
        if t<=self.sequence_time:return events
        self.sequence_time=t
        hand=frame.get('hand') or {};face=frame.get('face') or {};mode=self.profile['mode']
        hand_ok=tracked(hand);face_ok=tracked(face)
        valid=(mode=='hand' and hand_ok or mode=='head' and face_ok or mode=='combined' and hand_ok and face_ok)
        if mode!='hand' and face.get('count',0)!=1:valid=False
        if not valid:
            events=self.reset();self.lost=True;self.confidence=0.;return events
        self.lost=False;self.confidence=None
        if mode=='hand':
            x0,y0,x1,y1=self.profile['calibration']['hand_bounds']
            raw=(clamp((number(hand.get('x'),.5)-x0)/(x1-x0)),clamp((number(hand.get('y'),.5)-y0)/(y1-y0)))
        else:
            yaw,pitch=self.profile['calibration']['head_neutral'];span=self.profile['head_range']*2
            raw=(clamp(.5+(number(face.get('yaw'))-yaw)/span),clamp(.5+(number(face.get('pitch'))-pitch)/span))
        raw=tuple(clamp(.5+(v-.5)*self.profile['sensitivity']) for v in raw)
        if mode!='hand':
            width,height=self.profile.get('_monitor_scale',(1920,1080))
            resolution=max(1.,width/1920,height/1080)
            for filter in self.filters:filter.minimum=(.3+(1-self.profile['smoothing'])*1.4)/resolution
        previous_point=self.point
        filtered=raw if not self.profile['smoothing'] else tuple(filter.step(value,t) for filter,value in zip(self.filters,raw))
        if mode!='hand':
            scale=self.profile.get('_monitor_scale',(1920,1080));radius=self.profile['head_stability']
            if self.steady_point is None:self.steady_point=filtered
            dx,dy=((filtered[i]-self.steady_point[i])*scale[i] for i in range(2))
            distance=math.hypot(dx,dy)
            if distance>radius:
                self.steady_point=tuple(filtered[i]-(dx,dy)[i]/scale[i]*radius/distance for i in range(2))
            self.steady_point=tuple(raw[i] if raw[i] in (0.,1.) and abs(filtered[i]-raw[i])*scale[i]<=radius else self.steady_point[i] for i in range(2))
            filtered=self.steady_point
        self.point=filtered
        hud=next((r['action'] for r in self.hud_regions if r['rect'][0]<=self.point[0]<=r['rect'][2] and r['rect'][1]<=self.point[1]<=r['rect'][3]),'') if mode=='head' else ''
        if not hud:self.hud_blocked=False
        gesture=self._gesture(hand if mode!='head' else {},face,paused=paused)
        if hud or self.drag_latched:gesture=''
        # Resume is meaningful only while paused; an open hand must not freeze
        # ordinary pointing in active control or the practice simulator.
        if gesture=='open_palm' and not paused:gesture=''
        if gesture!='conflict' and self.profile['bindings'].get(gesture,'none')=='none':gesture=''
        target_gesture=(mode=='hand' and gesture.startswith('pinch_') or mode=='head' and gesture in ('smile','wink_left','wink_right','brows_up') and self.profile['bindings'].get(gesture) in ('left_click','right_click','double_click','left_drag'))
        if target_gesture:
            if self.pinch_anchor is None or self.gesture!=gesture:
                self.pinch_anchor=previous_point or filtered;self.pinch_origin=filtered
            if self.gesture!=gesture or not self.fired or self.profile['bindings'][gesture]!='left_drag':self.point=self.pinch_anchor
            else:self.point=tuple(clamp(a+b-c) for a,b,c in zip(self.pinch_anchor,filtered,self.pinch_origin))
        elif self.pinch_anchor is not None:
            self.pinch_anchor=None;self.pinch_origin=None
            if previous_point is not None:
                self.point=previous_point
                for filter,value in zip(self.filters,previous_point):filter.reset();filter.step(value,t)
        if self.lock=='conflict' and gesture:
            self.progress=0.;return events
        if self.lock and self.lock!=gesture and gesture:
            if self.held and not self.drag_latched:
                events.append({'kind':'button','action':'up','button':'left'});self.held=False
            self.lock='conflict';self.gesture='conflict';self.progress=0.;return events
        if gesture!=self.gesture:
            # A gesture cannot change meaning while a mouse press is held.
            if self.held and not self.drag_latched:
                events.append({'kind':'button','action':'up','button':'left'});self.held=False
                if mode=='head':self.dwell_anchor=self.point;self.dwell_fired=True;self.dwell_exit=None
            self.gesture=gesture;self.since=t;self.fired=False;self.scroll_y=None;self.progress=0.
            if mode=='head' and gesture:self.dwell_anchor=None;self.dwell_since=t
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
                if target_gesture:self.pinch_origin=filtered;self.pinch_anchor=self.point
                if mode=='head':self.dwell_anchor=self.point;self.dwell_fired=True;self.dwell_exit=None
                events.append({'kind':'button','action':'down','button':'left'})
            elif action not in ('none','scroll','left_drag') and (not paused or action=='resume'):
                if t-self.last_action>=self.profile['cooldown_ms']/1000 or action in ('pause','resume'):
                    events.append({'kind':'action','action':action});self.last_action=t;self.fired=True;self.lock=gesture
                    if mode=='head' and action in ('left_click','double_click','right_click'):
                        self.dwell_anchor=self.point;self.dwell_fired=True;self.dwell_exit=None
        if mode=='head' and (self.profile['dwell'] or paused or hud) and not gesture:
            # Remain disarmed across Pause/Resume or Drop until leaving the HUD.
            if hud and self.hud_blocked:self.progress=0.;return events
            # Keep the configured dwell radius in physical monitor pixels.
            scale=self.profile.get('_monitor_scale',(1920,1080))
            distance=lambda a,b:math.hypot((a[0]-b[0])*scale[0],(a[1]-b[1])*scale[1])
            if hud!=self.dwell_target:
                self.dwell_target=hud;self.dwell_anchor=self.point;self.dwell_since=t;self.dwell_fired=False;self.dwell_exit=None
            if self.dwell_anchor is None:self.dwell_anchor=self.point;self.dwell_since=t
            radius=self.profile['dwell_radius']
            if self.dwell_fired:
                if distance(self.point,self.dwell_anchor)>radius*1.5:
                    if self.dwell_exit is None:self.dwell_exit=t
                    elif t-self.dwell_exit>=.25:self.dwell_fired=False;self.dwell_anchor=self.point;self.dwell_since=t
                else:self.dwell_exit=None
            elif distance(self.point,self.dwell_anchor)>radius:
                self.dwell_anchor=self.point;self.dwell_since=t;self.progress=0.
            else:
                self.progress=clamp((t-self.dwell_since)/(self.profile['dwell_ms']/1000))
                if self.progress>=1:
                    if hud:events.append({'kind':'hud_action','action':hud});self.hud_blocked=True
                    elif paused:events.append({'kind':'hud_dwell','action':'left_click','x':self.point[0],'y':self.point[1]})
                    elif self.dwell_action=='drag':
                        self.held=not self.held;self.drag_latched=self.held
                        events.append({'kind':'button','action':'down' if self.held else 'up','button':'left'})
                        if not self.held:self.dwell_action='left_click'
                    else:
                        events.append({'kind':'action','action':self.dwell_action});self.dwell_action='left_click'
                    self.dwell_fired=True
        return events
