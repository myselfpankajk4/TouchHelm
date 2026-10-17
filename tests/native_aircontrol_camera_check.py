"""Opt-in camera observation check; images stay in RAM and PC input is mocked.

Run explicitly with --camera 0. This does not verify physical gesture accuracy.
"""
import argparse
import asyncio
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

async def check(camera,seconds):
    from server.aircontrol.service import AirControlService
    from server.aircontrol.setup import AirControlSetup
    from server.aircontrol.profiles import default_profile
    from server.secure_pairing import private_storage_root
    setup=AirControlSetup(private_storage_root()/'aircontrol')
    if not setup.snapshot()['ready']:raise RuntimeError('Complete AirControl setup first')
    async def displays():return {'displays':[{'id':'observation-only','primary':True,'rect':{'x':0,'y':0,'width':1920,'height':1080}}]}
    for mode in ('hand','head','combined'):
        with tempfile.TemporaryDirectory() as directory:
            native=Mock();service=AirControlService(native,displays,folder=directory,setup=setup)
            profile=default_profile(mode=mode);profile['camera_id']=camera
            stamps=[];ages=[];cpu=[];memory=[];hand=face=0;previous=-1;state='';message=''
            try:
                await service.command('start',{'profile':profile})
                deadline=time.monotonic()+seconds
                while time.monotonic()<deadline and service.worker:
                    await asyncio.sleep(.05);s=service.snapshot()
                    if service.last_sequence!=previous:
                        previous=service.last_sequence
                        if previous>=0:
                            stamps.append(service.last_frame)
                            hand+=bool(s['tracking_sources']['hand']);face+=bool(s['tracking_sources']['face'])
                    metrics=s['metrics']
                    if isinstance(metrics.get('frame_age_ms'),(int,float)):ages.append(metrics['frame_age_ms'])
                    if isinstance(metrics.get('cpu_percent'),(int,float)):cpu.append(metrics['cpu_percent'])
                    if isinstance(metrics.get('memory_mb'),(int,float)):memory.append(metrics['memory_mb'])
                    if mode=='head' and not service.calibrated:
                        try:service.calibrate('center')
                        except ValueError:pass
                final=service.snapshot();state=final['state'];message=final['message']
                assert not service.owns_input and not native.mock_calls,'Observation check attempted native input'
                print(json.dumps({'mode':mode,'state':state,'message':message,'accepted_observations':len(stamps),
                    'hand_observations':hand,'face_observations':face,'practice_clicks':service.practice_actions,
                    'observed_fps':round((len(stamps)-1)/(stamps[-1]-stamps[0]),1) if len(stamps)>1 and stamps[-1]>stamps[0] else None,
                    'median_observation_age_ms':statistics.median(ages) if ages else None,
                    'median_cpu_percent_of_pc':statistics.median(cpu) if cpu else None,'peak_worker_memory_mb':max(memory) if memory else None,
                    'rejected_observations':final['metrics']['rejected_observations'],'images_saved':False,'native_input_sent':False}),flush=True)
            finally:await service.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--camera',required=True,choices=[str(i) for i in range(33)])
    parser.add_argument('--seconds',type=int,default=15,choices=range(10,61));args=parser.parse_args()
    asyncio.run(check(args.camera,args.seconds))
