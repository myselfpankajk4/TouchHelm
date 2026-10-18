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

# Hand landmarks are noisy at 10-15 camera frames per second. A low resting
# cutoff steadies a held finger; beta opens the filter quickly for deliberate
# movement so tracking does not feel dragged behind the finger.
HAND_BETA=9.
# Head pose is steadied the same way. 0.12 Hz is the resting cutoff at
# maximum smoothing; it widens as Smoothing is lowered. The reference range is
# the default head_range, so a tighter range or higher sensitivity steadies more.
HEAD_CUTOFF=.12
HEAD_BETA=16.
# Head pose speed below this (about 3.6 deg/s at the default range) is treated as
# tracking noise and does not open the filter.
HEAD_FLOOR=.1
HEAD_RANGE_REFERENCE=18.
HEAD_SPIKE=1.5
HEAD_ADAPT=3.
HEAD_ADAPT_TAU=1.5

class GestureEngine:
    def __init__(self,profile):
        self.profile=validate_profile(profile);self.held=False;self.lost=True
        self.gesture='';self.since=0.;self.fired=False;self.lock='';self.scroll_y=None
        self.point=None;self.dwell_anchor=None;self.dwell_since=0.;self.dwell_fired=False
        self.dwell_exit=None;self.last_action=-10.;self.progress=0.;self.confidence=0.
        self.sequence_time=-1.
        self.pinch_anchor=None;self.pinch_origin=None
        self.hand_rebase=None
        self.dwell_action='left_click';self.drag_latched=False;self.hud_regions=[];self.dwell_target=None
        self.steady_point=None;self.pose_accepted=None;self.pose_suspect=None;self.jitter=0.;self.jitter_from=None;self.jitter_time=None
        self.hud_blocked=False
        self.head_scroll=False;self.scroll_target='';self.scroll_since=0.;self.scroll_last=None
        self.scroll_expression_blocked=False
        smoothing=self.profile['smoothing'];head=self.profile['mode']!='hand'
        self.filters=[OneEuro(self._cutoff(1.),HAND_BETA if not head else HEAD_BETA) for _ in range(2)]

    def _hand_gain(self,axis):
        # A smaller calibrated hand range, a smaller head range or higher
        # sensitivity magnifies tracking noise on screen, so steady it in proportion.
        if self.profile['mode']!='hand':return max(1.,self.profile['sensitivity']*HEAD_RANGE_REFERENCE/self.profile['head_range'])
        bounds=self.profile['calibration']['hand_bounds'];span=(bounds[2]-bounds[0],bounds[3]-bounds[1])[axis]
        return max(1.,self.profile['sensitivity']*.7/max(span,.05))

    def _cutoff(self,resolution,axis=0):
        smoothing=self.profile['smoothing']
        if self.profile['mode']=='hand':return (.15+(1-smoothing)*.65)/self._hand_gain(axis)
        return (HEAD_CUTOFF+(1-smoothing)*HEAD_CUTOFF*4.6)/resolution/self._hand_gain(axis)

    def _pose_gate(self,pose,t):
        # Face tracking sometimes glitches for one frame (a blink or a lost landmark).
        # A jump over HEAD_SPIKE degrees waits one frame: if the next frame is back near
        # the last good pose the glitch is dropped, otherwise the move was real and the
        # delayed frame is replayed so the filter ends up exactly where it would have.
        # Returns (pose to use, delayed pose to replay first, hold the filters this frame).
        accepted,suspect=self.pose_accepted,self.pose_suspect
        far=lambda a,b:math.hypot(a[0]-b[0],a[1]-b[1])>HEAD_SPIKE
        if accepted is None or t-accepted[2]>.25:
            self.pose_accepted=(*pose,t);self.pose_suspect=None;return pose,None,False
        if suspect is None:
            if not far(pose,accepted):self.pose_accepted=(*pose,t);return pose,None,False
            self.pose_suspect=(*pose,t);return accepted[:2],None,True
        self.pose_suspect=None;self.pose_accepted=(*pose,t)
        if t-suspect[2]>.25 or not far(pose,accepted):return pose,None,False
        return pose,suspect,False

    def _noisy_radius(self,filtered,scale,radius,t,dwell_cap):
        # How far the filtered pose moves between frames is the noise a hold must absorb
        # when the head is meant to be still; widen the hold in proportion, but keep it
        # inside the dwell radius so dwell clicking still works.
        if self.jitter_from is not None and t>self.jitter_time:
            moved=math.hypot(*((filtered[i]-self.jitter_from[i])*scale[i] for i in range(2)))
            weight=1-math.exp(-(t-self.jitter_time)/HEAD_ADAPT_TAU)
            if moved<=radius:self.jitter+=weight*(moved-self.jitter)
        self.jitter_from=filtered;self.jitter_time=t
        return min(max(radius,radius+HEAD_ADAPT*self.jitter),max(radius,min(2*radius,.8*dwell_cap)))

    def reset(self,*,consume_dwell=False):
        point=self.point if consume_dwell else None
        blocked=consume_dwell and bool(self.gesture)
        neutral_required=(self.scroll_expression_blocked or self.head_scroll or
            self.profile['mode']!='hand' and self.gesture in ('smile','wink_left','wink_right','brows_up','conflict'))
        events=[{'kind':'button','action':'up','button':'left'}] if self.held else []
        self.held=False;self.gesture='';self.fired=False;self.lock='';self.scroll_y=None
        self.dwell_anchor=None;self.dwell_fired=False;self.dwell_exit=None;self.point=None;self.progress=0.
        self.pinch_anchor=None;self.pinch_origin=None
        self.dwell_action='left_click';self.drag_latched=False;self.dwell_target=None;self.steady_point=None;self.pose_accepted=None;self.pose_suspect=None;self.jitter=0.;self.jitter_from=None;self.jitter_time=None
        self.hand_rebase=None
        self.head_scroll=False;self.scroll_target='';self.scroll_last=None
        # Interruption must not turn an uninterrupted expression into a new
        # press. Only a valid, neutral observation below releases this latch.
        self.scroll_expression_blocked=neutral_required
        if blocked:self.gesture=self.lock='conflict'
        if point is not None:
            # An explicit drop consumes the dwell at this location just like a
            # dwell drop does. Departure is required before another PC click.
            self.point=self.dwell_anchor=point;self.dwell_fired=True;self.dwell_target=''
        for filter in self.filters:filter.reset()
        return events

    def set_head_scroll(self,enabled):
        if type(enabled) is not bool or self.profile['mode']!='head':
            raise ValueError('Head scrolling requires Head & Face mode.')
        previous=self.point
        events=self.reset(consume_dwell=True)
        self.point=previous;self.head_scroll=enabled
        self.scroll_expression_blocked=not enabled or self.scroll_expression_blocked
        if not enabled:self.hud_blocked=True
        return events

    def _head_scroll_step(self,hud,t,*,gap=False):
        self.gesture='';self.progress=0.
        if gap or hud!=self.scroll_target:
            self.scroll_target=hud;self.scroll_since=t;self.scroll_last=None
        if not hud:return []
        self.progress=clamp((t-self.scroll_since)/(self.profile['dwell_ms']/1000))
        if self.progress<1:return []
        if hud in ('scroll_up','scroll_down'):
            if self.scroll_last is None or t-self.scroll_last>=.15:
                self.scroll_last=t
                return [{'kind':'scroll','dy':2 if hud=='scroll_up' else -2}]
        elif hud in ('scroll_done','pause','stop') and self.scroll_last is None:
            self.scroll_last=t
            return [{'kind':'hud_action','action':hud}]
        return []

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
        gap=self.sequence_time>=0 and t-self.sequence_time>.25
        self.sequence_time=t
        hand=frame.get('hand') or {};face=frame.get('face') or {};mode=self.profile['mode']
        hand_ok=tracked(hand);face_ok=tracked(face)
        valid=(mode=='hand' and hand_ok or mode=='head' and face_ok or mode=='combined' and hand_ok and face_ok)
        if mode!='hand' and face.get('count',0)!=1:valid=False
        if not valid:
            events=self.reset();self.lost=True;self.confidence=0.;return events
        self.lost=False;self.confidence=None
        replay=None;hold_filters=False
        if mode=='hand':
            x0,y0,x1,y1=self.profile['calibration']['hand_bounds']
            raw=(clamp((number(hand.get('x'),.5)-x0)/(x1-x0)),clamp((number(hand.get('y'),.5)-y0)/(y1-y0)))
        else:
            yaw,pitch=self.profile['calibration']['head_neutral'];span=self.profile['head_range']*2
            pose=(number(face.get('yaw')),number(face.get('pitch')))
            if self.profile['smoothing']:pose,replay,hold_filters=self._pose_gate(pose,t)
            raw=(clamp(.5+(pose[0]-yaw)/span),clamp(.5+(pose[1]-pitch)/span))
            if replay:replay=(*(clamp(.5+(v-n)/span) for v,n in zip(replay,(yaw,pitch))),replay[2])
        raw=tuple(clamp(.5+(v-.5)*self.profile['sensitivity']) for v in raw)
        if replay:replay=(*(clamp(.5+(v-.5)*self.profile['sensitivity']) for v in replay[:2]),replay[2])
        width,height=self.profile.get('_monitor_scale',(1920,1080))
        resolution=1. if mode=='hand' else max(1.,width/1920,height/1080)
        for axis,filter in enumerate(self.filters):
            filter.minimum=self._cutoff(resolution,axis)
            filter.beta=(HAND_BETA if mode=='hand' else HEAD_BETA)/self._hand_gain(axis)
            if mode!='hand':filter.floor=HEAD_FLOOR*self._hand_gain(axis)
        previous_point=self.point
        if replay:
            for filter,value in zip(self.filters,replay):filter.step(value,replay[2])
        if hold_filters and all(f.value is not None for f in self.filters):filtered=tuple(f.value for f in self.filters)
        else:filtered=raw if not self.profile['smoothing'] else tuple(filter.step(value,t) for filter,value in zip(self.filters,raw))
        if mode=='hand' and self.hand_rebase is not None:
            origin,target=self.hand_rebase
            # Re-anchor after finger release. Interpolate toward both screen
            # edges so the retained drag offset cannot strand an edge.
            anchored=[];origins=list(origin);targets=list(target)
            for i,(v,a,b) in enumerate(zip(filtered,origin,target)):
                if v<a:mapped=v*b/a
                elif a<1:mapped=b+(v-a)*(1-b)/(1-a)
                else:mapped=b
                anchored.append(clamp(mapped))
                # A release exactly at a boundary needs departure before that
                # edge can be reached again, without a stationary-pointer jump.
                if a in (0.,1.) and v!=a:origins[i]=v;targets[i]=clamp(mapped)
            self.hand_rebase=(tuple(origins),tuple(targets));filtered=tuple(anchored)
        hand_hold=mode=='hand' and self.profile['smoothing'] and self.profile['hand_stability']
        if mode!='hand' or hand_hold:
            scale=self.profile.get('_monitor_scale',(1920,1080));radius=self.profile['hand_stability' if mode=='hand' else 'head_stability']*(self._hand_gain(0)+self._hand_gain(1))/2
            if mode!='hand':radius=self._noisy_radius(filtered,scale,radius,t,dwell_cap=self.profile['dwell_radius'])
            if self.steady_point is None:self.steady_point=filtered
            dx,dy=((filtered[i]-self.steady_point[i])*scale[i] for i in range(2))
            distance=math.hypot(dx,dy)
            if distance>radius:
                self.steady_point=tuple(filtered[i]-(dx,dy)[i]/scale[i]*radius/distance for i in range(2))
            self.steady_point=tuple(raw[i] if raw[i] in (0.,1.) and abs(filtered[i]-raw[i])*scale[i]<=radius else self.steady_point[i] for i in range(2))
            filtered=self.steady_point
        self.point=filtered
        hud=next((r['action'] for r in self.hud_regions if r['rect'][0]<=self.point[0]<=r['rect'][2] and r['rect'][1]<=self.point[1]<=r['rect'][3]),'') if mode=='head' else ''
        if self.head_scroll:return self._head_scroll_step(hud,t,gap=gap)
        if not hud:self.hud_blocked=False
        gesture=self._gesture(hand if mode!='head' else {},face,paused=paused)
        if self.scroll_expression_blocked:
            if gesture:
                self.gesture=self.lock='conflict';self.progress=0.
                return [{'kind':'pointer','x':self.point[0],'y':self.point[1]}]
            self.scroll_expression_blocked=False
        if hud or self.drag_latched:gesture=''
        # Resume is meaningful only while paused; an open hand must not freeze
        # ordinary pointing in active control or the practice simulator.
        if gesture=='open_palm' and not paused:gesture=''
        if gesture!='conflict' and self.profile['bindings'].get(gesture,'none')=='none':gesture=''
        target_gesture=(mode in ('hand','combined') and gesture.startswith('pinch_') or mode=='head' and gesture in ('smile','wink_left','wink_right','brows_up') and self.profile['bindings'].get(gesture) in ('left_click','right_click','double_click','left_drag'))
        if target_gesture:
            if self.pinch_anchor is None or self.gesture!=gesture:
                self.pinch_anchor=previous_point or filtered;self.pinch_origin=filtered
            if self.gesture!=gesture or not self.fired or self.profile['bindings'][gesture]!='left_drag':self.point=self.pinch_anchor
            else:self.point=tuple(clamp(a+b-c) for a,b,c in zip(self.pinch_anchor,filtered,self.pinch_origin))
        elif self.pinch_anchor is not None:
            self.pinch_anchor=None;self.pinch_origin=None
            if previous_point is not None:
                self.point=previous_point
                if mode=='hand':self.hand_rebase=(raw,previous_point)
                self.steady_point=previous_point
                for filter,value,held in zip(self.filters,raw,previous_point):
                    filter.reset();filter.step(value,t)
                    # Head pose keeps the held point as its starting value and then
                    # eases toward the head; seeding the held point as a sample
                    # would read the gap as a fast move and jump the pointer.
                    if mode!='hand':filter.value=held
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
