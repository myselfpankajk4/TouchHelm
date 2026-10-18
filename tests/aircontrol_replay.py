"""Deterministic control replay, without camera/models/Windows input imports."""
import argparse
import importlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile


def run_replay(*,engine_factory,fps,size,scenario):
    if fps not in (10,15,30) or scenario not in ('stationary','jitter','step','conflict','loss','edges'):
        raise ValueError('Choose a documented replay scenario and delivery rate.')
    profile=default_profile(mode='head')
    if scenario=='conflict':
        profile.update(expressions_calibrated=True,calibrated_expressions=['smile','wink_left'])
        profile['bindings'].update(smile='left_click',wink_left='right_click',pinch_middle='none')
    if scenario=='edges':profile['smoothing']=0
    engine=engine_factory(profile);engine.profile['_monitor_scale']=size
    if scenario=='loss':engine.select_dwell('drag')
    points=[];events=[];response=None;lost_index=None;release_index=None
    for i in range(fps*3):
        at=i/fps;yaw=0.;pitch=0.
        if scenario=='jitter' and i:yaw=.65 if i%2 else -.65
        if scenario=='step' and at>=1.:yaw=5.
        if scenario=='edges':yaw,pitch=(36.,-36.) if at<1.5 else (-36.,36.)
        face={'tracked':True,'count':1,'yaw':yaw,'pitch':pitch,'expressions':{
            'eyeBlinkLeft':.9 if scenario=='conflict' else 0.,'eyeBlinkRight':0.,
            'mouthSmileLeft':.9 if scenario=='conflict' else 0.,
            'mouthSmileRight':.9 if scenario=='conflict' else 0.,'browInnerUp':0.}}
        frame={'timestamp':at,'face':face}
        if scenario=='loss' and at>=1.5:
            frame.pop('face')
            if lost_index is None:lost_index=i
        sample=engine.step(frame);events.extend(sample)
        if any(e.get('kind')=='button' and e.get('action')=='up' for e in sample) and release_index is None:release_index=i
        if engine.point is not None:
            point=engine.point;points.append((at,*point))
            if scenario=='step' and at>=1 and response is None and point[0]>=.5+.9*5/36:response=round((at-1)*1000,3)
    steady=[(x*size[0],y*size[1]) for t,x,y in points if t>=1]
    if steady:
        cx=sum(x for x,y in steady)/len(steady);cy=sum(y for x,y in steady)/len(steady)
        jitter=math.sqrt(sum((x-cx)**2+(y-cy)**2 for x,y in steady)/len(steady))
    else:jitter=None
    return {'jitter_rms_px':round(jitter,4) if jitter is not None else None,'step_90_ms':response,
        'actions':[e['action'] for e in events if e['kind']=='action'],
        'button_downs':sum(e['kind']=='button' and e['action']=='down' for e in events),
        'button_ups':sum(e['kind']=='button' and e['action']=='up' for e in events),'samples':fps*3,
        'release_delay_samples':release_index-lost_index if release_index is not None and lost_index is not None else None,
        'edges_reachable':any(x==1 and y==0 for t,x,y in points) and any(x==0 and y==1 for t,x,y in points)}


def baseline_engine(ref,folder):
    package=folder/'aircontrol_baseline';package.mkdir()
    for name in ('__init__.py','engine.py','profiles.py','expressions.py','filters.py'):
        result=subprocess.run(['git','show',f'{ref}:server/aircontrol/{name}'],cwd=ROOT,capture_output=True,check=True)
        (package/name).write_bytes(result.stdout)
    spec=importlib.util.spec_from_file_location('aircontrol_baseline',package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules['aircontrol_baseline']=module;spec.loader.exec_module(module)
    return importlib.import_module('aircontrol_baseline.engine').GestureEngine


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-ref');args=parser.parse_args()
    build=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    dirty=subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode!=0
    report={'version':1,'build':build+('+working-tree' if dirty else ''),'kind':'synthetic control replay; not physical recognition accuracy','seed':0,
        'profile':default_profile(mode='head'),'baseline_ref':args.baseline_ref,'measurements':[],'comparison_passed':True}
    with tempfile.TemporaryDirectory() as folder:
        before=baseline_engine(args.baseline_ref,Path(folder)) if args.baseline_ref else None
        for size in ((1920,1080),(3840,2160)):
            for fps in (10,15,30):
                for scenario in ('stationary','jitter','step','conflict','loss','edges'):
                    measured=run_replay(engine_factory=GestureEngine,fps=fps,size=size,scenario=scenario)
                    row={'size':list(size),'fps':fps,'scenario':scenario,'current':measured}
                    if before:
                        base=run_replay(engine_factory=before,fps=fps,size=size,scenario=scenario);row['baseline']=base
                        if scenario=='step':
                            report['comparison_passed'] &= measured['step_90_ms'] is not None and measured['step_90_ms']<=base['step_90_ms']+1000/fps
                        if scenario in ('stationary','jitter','conflict'):
                            report['comparison_passed'] &= measured['actions']==base['actions'] and measured['button_downs']==base['button_downs']
                        if scenario=='loss':report['comparison_passed'] &= measured['release_delay_samples']==0
                        if scenario=='edges':report['comparison_passed'] &= measured['edges_reachable']
                    report['measurements'].append(row)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'report':str(args.output),'scenarios':len(report['measurements']),'comparison_passed':bool(report['comparison_passed'])}))
    return 0 if report['comparison_passed'] else 1


if __name__=='__main__':sys.exit(main())
