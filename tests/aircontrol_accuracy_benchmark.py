"""Deterministic cursor-accuracy scenarios for AirControl (no camera, models or Windows input).

A synthetic hand is converted with the real worker `hand_state` and replayed through the real
`GestureEngine`, so the numbers describe this code, not a model of it. The hand is a rigid
palm with independent landmark noise; the index fingertip travels toward the thumb as the
pinch closes, which is exactly the motion that drags a fingertip-driven pointer.

Run `python tests/aircontrol_accuracy_benchmark.py` to print the table used in
docs/AIRCONTROL_ACCURACY_RESEARCH.md.
"""
import math
import random
from pathlib import Path
from statistics import mean
from types import SimpleNamespace as Item
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.aircontrol import engine as engine_module
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile
from server.aircontrol.worker import hand_state

SIZE=(1920,1080)

def landmarks(cx,cy,openness,rng=None,sigma=0.):
    """21 normalized landmarks. openness 1 = index extended, 0 = tip on the thumb tip."""
    pts=[[cx,cy] for _ in range(21)]
    for i,dx in {5:-.045,9:-.015,13:.015,17:.045}.items():pts[i]=[cx+dx,cy]
    pts[0]=[cx,cy+.16]
    thumb=(cx-.05,cy-.045);extended=(cx-.045,cy-.16)
    pts[4]=list(thumb)
    pts[8]=[thumb[0]+(extended[0]-thumb[0])*openness,thumb[1]+(extended[1]-thumb[1])*openness]
    pts[12]=[cx-.015,cy-.17]
    pts[6]=[cx-.045,cy-.06]
    if rng and sigma:pts=[[x+rng.gauss(0,sigma),y+rng.gauss(0,sigma)] for x,y in pts]
    return [Item(x=x,y=y) for x,y in pts]

def frame(t,points,pointer):
    result=Item(hand_landmarks=[points],handedness=[[Item(category_name='Right',score=.95)]],
        gestures=[[Item(category_name='Pointing_Up',score=.9)]])
    state,_,_=hand_state(result,'auto',None)
    if pointer=='fingertip':
        state['x']=max(0.,min(1.,points[8].x));state['y']=max(0.,min(1.,points[8].y))
    return {'timestamp':t,'hand':state}

def engine(**changes):
    profile=default_profile(mode='hand');profile.update(changes)
    result=GestureEngine(profile);result.profile['_monitor_scale']=SIZE
    return result

def pinch_click(*,pointer='knuckle',lookback=None,fps=30,seed=1,velocity=(0.,0.),sigma=.004,close_seconds=.2):
    """Cursor error in screen px at the left-button press.

    The target is the cursor position at the moment the user starts closing the pinch, which
    is where they were aiming. velocity is the hand drift in normalized units per second.
    """
    saved=engine_module.HAND_LOOKBACK
    if lookback is not None:engine_module.HAND_LOOKBACK=lookback
    try:
        rng=random.Random(seed);e=engine();settle=2.
        target=None;error=None
        for i in range(int((settle+close_seconds+1.2)*fps)):
            t=i/fps
            openness=1. if t<settle else max(0.,1.-(t-settle)/close_seconds)
            events=e.step(frame(t,landmarks(.5+velocity[0]*t,.5+velocity[1]*t,openness,rng,sigma),pointer))
            if target is None and t>=settle-1e-9 and e.point is not None:target=e.point
            for event in events:
                if event.get('kind')=='button' and event.get('action')=='down' and error is None and target is not None:
                    error=math.hypot((e.point[0]-target[0])*SIZE[0],(e.point[1]-target[1])*SIZE[1])
        return error
    finally:engine_module.HAND_LOOKBACK=saved

def head_smile_click(*,lookback=None,fps=30,seed=1,pose_shift=1.5,onset=.3,noise=.15):
    """Cursor error in px when a calibrated smile fires a click.

    Smiling pulls the face, so the estimated head pose shifts by `pose_shift` degrees while
    the smile builds over `onset` seconds. That magnitude is an assumption, not a measurement
    from a camera; the result shows how much of it the lookback anchor removes.
    """
    saved=engine_module.HEAD_LOOKBACK
    if lookback is not None:engine_module.HEAD_LOOKBACK=lookback
    try:
        rng=random.Random(seed)
        profile=default_profile(mode='head');profile.update(dwell=False,expressions_calibrated=True,calibrated_expressions=['smile'])
        profile['bindings']['smile']='left_click';profile['expression_thresholds']={'smile':{'on':.5,'off':.3}}
        e=GestureEngine(profile);e.profile['_monitor_scale']=SIZE
        settle=2.;target=None;error=None
        for i in range(int((settle+onset+1.5)*fps)):
            t=i/fps;ramp=min(1.,max(0.,(t-settle)/onset))
            smile=.9*ramp
            events=e.step({'timestamp':t,'face':{'tracked':True,'count':1,
                'yaw':3.+rng.gauss(0,noise)+pose_shift*ramp,'pitch':-2.+rng.gauss(0,noise),
                'expressions':{'eyeBlinkLeft':0.,'eyeBlinkRight':0.,'mouthSmileLeft':smile,'mouthSmileRight':smile,'browInnerUp':0.}}})
            if target is None and t>=settle-1e-9 and e.point is not None:target=e.point
            for event in events:
                if event.get('kind')=='action' and event.get('action')=='left_click' and error is None and target is not None:
                    error=math.hypot((e.point[0]-target[0])*SIZE[0],(e.point[1]-target[1])*SIZE[1])
        return error
    finally:engine_module.HEAD_LOOKBACK=saved

def table(seeds=range(1,13)):
    rows=[]
    for label,pointer,lookback in (('fingertip pointer, one-frame anchor (2.2.0)','fingertip',0.),
            ('knuckle-centre pointer, one-frame anchor','knuckle',0.),
            ('knuckle-centre pointer + lookback anchor (2.2.1)','knuckle',None)):
        for fps in (15,30):
            still=[pinch_click(pointer=pointer,lookback=lookback,fps=fps,seed=s) for s in seeds]
            moving=[pinch_click(pointer=pointer,lookback=lookback,fps=fps,seed=s,velocity=(.12,0.)) for s in seeds]
            rows.append((label,fps,mean(still),max(still),mean(moving),max(moving)))
    return rows

if __name__=='__main__':
    print('| Pointer / anchor | fps | still: mean px | still: worst px | moving 0.12/s: mean px | moving: worst px |')
    print('|---|---|---|---|---|---|')
    for label,fps,a,b,c,d in table():print(f'| {label} | {fps} | {a:.1f} | {b:.1f} | {c:.1f} | {d:.1f} |')
    print('\n| Head smile click: pose shift while smiling | one-frame anchor mean / worst px | lookback anchor (2.2.1) mean / worst px |')
    print('|---|---|---|')
    for shift in (1.5,3,6):
        old=[head_smile_click(lookback=0.,seed=s,pose_shift=shift) for s in range(1,13)]
        new=[head_smile_click(seed=s,pose_shift=shift) for s in range(1,13)]
        print(f'| {shift} deg | {mean(old):.1f} / {max(old):.1f} | {mean(new):.1f} / {max(new):.1f} |')
