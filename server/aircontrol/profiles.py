"""Validated device-local mappings; no arbitrary commands or executable paths."""
from copy import deepcopy
import json
import math
from pathlib import Path

ACTION_LABELS = {
    'none':'No action','left_drag':'Left press / drag','left_click':'Left click',
    'right_click':'Right click','double_click':'Double click','scroll':'Scroll',
    'pause':'Pause','resume':'Resume','dictate':'Windows dictation','recenter':'Recenter',
    'play_pause':'Play / pause','next_track':'Next track','previous_track':'Previous track',
    'next_slide':'Next slide','previous_slide':'Previous slide','copy':'Copy','paste':'Paste',
    'undo':'Undo','switch_app':'Switch app','keyboard':'Windows keyboard'}
GESTURE_LABELS={'pinch_index':'Thumb + index pinch','pinch_middle':'Thumb + middle pinch',
    'two_fingers':'Two fingers','closed_fist':'Closed fist','open_palm':'Open palm',
    'thumb_up':'Thumbs up','thumb_down':'Thumbs down','smile':'Deliberate smile',
    'wink_left':'Left wink','wink_right':'Right wink','brows_up':'Raised eyebrows'}
LIMITS={'sensitivity':(.3,3),'smoothing':(0, .9),'pinch_close':(.08,.5),
    'pinch_open':(.2,.9),'dwell_ms':(400,2500),'hold_ms':(200,1800),
    'cooldown_ms':(250,2500),'head_range':(8,35),'head_stability':(0,20),'hand_stability':(0,16),'dwell_radius':(12,40)}

def default_profile(name='everyday',mode='head'):
    bindings={'pinch_index':'left_drag','pinch_middle':'right_click','two_fingers':'scroll',
        'closed_fist':'pause','open_palm':'resume','thumb_up':'none','thumb_down':'none',
        'smile':'none','wink_left':'none','wink_right':'none','brows_up':'none'}
    if name=='presenter':bindings.update(thumb_up='next_slide',thumb_down='previous_slide')
    if name=='media':bindings.update(thumb_up='play_pause',thumb_down='next_track')
    return dict(version=1,name=name,mode=mode,hand='auto',camera_id='0',monitor_id='',mirror=True,
        landmarks=True,auto_dictation=True,sensitivity=1.,smoothing=.6 if mode=='head' else .45,pinch_close=.25,
        pinch_open=.4,dwell_ms=900,hold_ms=400,cooldown_ms=700,head_range=18,
        dwell=True,head_stability=8.,hand_stability=6.,dwell_radius=22.,expressions_calibrated=False,calibrated_expressions=[],expression_thresholds={},bindings=bindings,
        calibration={'hand_bounds':[.15,.15,.85,.85],'head_neutral':[0.,0.]})

def validate_profile(profile):
    if not isinstance(profile,dict) or set(profile)-set(default_profile()):raise ValueError('Invalid profile fields')
    value=deepcopy(default_profile());value.update(deepcopy(profile))
    if value['name'] not in ('everyday','presenter','media','custom') or value['mode'] not in ('hand','head','combined'):
        raise ValueError('Choose a supported profile and control mode')
    if value['hand'] not in ('auto','left','right'):raise ValueError('Choose a hand')
    if not isinstance(value['camera_id'],str) or not value['camera_id'].isdigit() or int(value['camera_id'])>32:raise ValueError('Invalid camera')
    if not isinstance(value['monitor_id'],str) or len(value['monitor_id'])>128:raise ValueError('Invalid monitor')
    for key in ('mirror','landmarks','auto_dictation','dwell','expressions_calibrated'):
        if type(value[key]) is not bool:raise ValueError('Invalid preference')
    for key,(minimum,maximum) in LIMITS.items():
        n=value[key]
        if type(n) not in (int,float) or not math.isfinite(n) or not minimum<=n<=maximum:raise ValueError('Invalid '+key)
    if value['pinch_open']<=value['pinch_close']+.05:raise ValueError('Pinch release must be above its close threshold')
    bindings=value['bindings']
    if not isinstance(bindings,dict) or set(bindings)!=set(GESTURE_LABELS) or any(a not in ACTION_LABELS for a in bindings.values()):raise ValueError('Choose supported gesture actions')
    # These controls are reserved so every profile has a predictable escape path.
    if bindings['closed_fist']!='pause' or bindings['open_palm']!='resume':raise ValueError('Keep Closed fist = Pause and Open palm = Resume')
    for gesture,action in bindings.items():
        if action=='left_drag' and gesture not in ('pinch_index','pinch_middle','smile','wink_left','wink_right','brows_up'):raise ValueError('Only pinches or calibrated expressions can hold a drag')
        if action=='scroll' and gesture!='two_fingers':raise ValueError('Two fingers provide scrolling')
        if gesture not in ('closed_fist','open_palm') and action in ('pause','resume'):raise ValueError('Pause and Resume have reserved gestures')
    assigned=[v for k,v in bindings.items() if v not in ('none','pause','resume')]
    if len(assigned)!=len(set(assigned)):raise ValueError('Assign an action to only one gesture')
    expressions=value['calibrated_expressions']
    if not isinstance(expressions,list) or len(expressions)>4 or any(k not in ('smile','wink_left','wink_right','brows_up') for k in expressions):raise ValueError('Invalid expression calibration')
    thresholds=value['expression_thresholds']
    if not isinstance(thresholds,dict) or set(thresholds)-{'smile','wink_left','wink_right','brows_up'}:raise ValueError('Invalid expression thresholds')
    for limits in thresholds.values():
        if not isinstance(limits,dict) or not {'on','off'}<=set(limits) or set(limits)-{'on','off','other_max'} or any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in limits.values()) or limits['on']-limits['off']<.03:raise ValueError('Invalid expression thresholds')
    if any(bindings[k]!='none' and k not in expressions for k in ('smile','wink_left','wink_right','brows_up')):raise ValueError('Practice and calibrate each assigned facial expression first')
    if value['mode']=='head' and not value['dwell'] and not any(bindings[k] in ('left_click','double_click') for k in expressions):raise ValueError('Head mode needs dwell clicking or a calibrated click expression')
    calibration=value['calibration']
    if not isinstance(calibration,dict) or set(calibration)!= {'hand_bounds','head_neutral'}:raise ValueError('Invalid calibration')
    bounds=calibration['hand_bounds'];neutral=calibration['head_neutral']
    if not isinstance(bounds,list) or len(bounds)!=4 or any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in bounds):raise ValueError('Invalid movement bounds')
    if bounds[2]-bounds[0]<.2 or bounds[3]-bounds[1]<.2:raise ValueError('Use a wider comfortable movement area')
    if not isinstance(neutral,list) or len(neutral)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) or abs(n)>90 for n in neutral):raise ValueError('Invalid neutral head pose')
    value['version']=1
    return value

class ProfileStore:
    def __init__(self,path):self.path=Path(path)
    def _data(self):
        try:
            value=json.loads(self.path.read_text(encoding='utf-8'))
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}
    def all(self):
        data=self._data();profiles={name:default_profile(name) for name in ('everyday','presenter','media','custom')}
        candidates=data.get('profiles',{}) if 'profiles' in data else {data.get('name','everyday'):data}
        if isinstance(candidates,dict):
            for name,profile in candidates.items():
                try:
                    if name in profiles:profiles[name]=validate_profile(profile)
                except (TypeError,ValueError):pass
        return profiles
    def read(self):
        try:
            data=self._data()
            if 'profiles' in data:return self.all().get(data.get('active'),default_profile())
            return validate_profile(data)
        except (OSError,ValueError,TypeError):return default_profile()
    def save(self,profile):
        value=validate_profile(profile)
        profiles=self.all();profiles[value['name']]=value
        self.path.parent.mkdir(parents=True,exist_ok=True)
        from server.secure_pairing import protect_user_path
        protect_user_path(self.path.parent)
        temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps({'version':1,'active':value['name'],'profiles':profiles}),encoding='utf-8')
        protect_user_path(temporary);temporary.replace(self.path)
        return value
