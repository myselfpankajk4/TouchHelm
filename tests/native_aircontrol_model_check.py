"""Opt-in actual SDK/reference-image check. No webcam or native input.

python tests/native_aircontrol_model_check.py --download-reference
Subsequent runs use the cached public Google reference images without downloads.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def check(download):
    import cv2
    import mediapipe as mp
    from server.aircontrol.worker import models,hand_state,face_state,prepare_frame
    from server.aircontrol.engine import GestureEngine
    from server.aircontrol.profiles import default_profile
    folder=ROOT/'.tmp/aircontrol-reference';folder.mkdir(parents=True,exist_ok=True)
    fixtures={'thumbs_down.jpg':'Thumb_Down','victory.jpg':'Victory','thumbs_up.jpg':'Thumb_Up','pointing_up.jpg':'Pointing_Up'}
    elapsed=[];accepted={}
    def load(name,url):
        path=folder/name
        if not path.exists():
            if not download:raise RuntimeError('Missing public fixture. Run with --download-reference once.')
            path.write_bytes(urllib.request.urlopen(url,timeout=20).read())
        frame=cv2.imread(str(path));assert frame is not None,'Reference image could not decode'
        return prepare_frame(cv2,frame,False)
    for name,expected in fixtures.items():
        frame=load(name,'https://storage.googleapis.com/mediapipe-tasks/gesture_recognizer/'+name)
        assert frame.shape[:2]==(480,640)
        image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        recognizer,_=models(mp,ROOT/'assets/aircontrol','hand')
        try:
            for i in range(4):
                start=time.monotonic();result=recognizer.recognize_for_video(image,i*34)
                elapsed.append((time.monotonic()-start)*1000)
            state,_,points=hand_state(result,'auto',None,image_size=(640,480))
            assert state and state['tracked'] and len(points)==21,'Reference hand was not tracked'
            assert state['pose']==expected,f'{name}: expected {expected}, received {state["pose"]!r}'
            engine=GestureEngine(default_profile('media'))
            engine.step({'timestamp':1,'hand':state});events=engine.step({'timestamp':1.5,'hand':state})
            assert not engine.lost,'Tracked reference was rejected by the engine'
            if expected=='Pointing_Up':assert any(e['kind']=='pointer' for e in events)
            accepted[name]=state['pose']
        finally:recognizer.close()
    frame=load('portrait.jpg','https://storage.googleapis.com/mediapipe-assets/portrait.jpg')
    _,recognizer=models(mp,ROOT/'assets/aircontrol','head')
    try:
        image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        result=recognizer.detect_for_video(image,0);state,points=face_state(result)
        assert state and state['tracked'] and len(points)==12,'Reference head was not tracked'
        profile=default_profile(mode='head');profile['calibration']['head_neutral']=[state['yaw'],state['pitch']]
        engine=GestureEngine(profile);events=engine.step({'timestamp':1,'face':state})
        point=next(e for e in events if e['kind']=='pointer')
        assert abs(point['x']-.5)<.01 and abs(point['y']-.5)<.01,'Head recenter did not map to screen center'
    finally:recognizer.close()
    print(json.dumps({'sdk_reference_check':'passed','hand_images':accepted,'head_reference_faces':1,
        'median_reference_inference_ms':round(statistics.median(elapsed),1),'camera_opened':False,'native_input_sent':False}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--download-reference',action='store_true');parser.add_argument('--isolated',action='store_true')
    args=parser.parse_args()
    if args.isolated:check(args.download_reference)
    else:
        from server.aircontrol.setup import AirControlSetup
        from server.secure_pairing import private_storage_root
        setup=AirControlSetup(private_storage_root()/'aircontrol')
        if not setup.snapshot()['ready']:raise RuntimeError('Complete AirControl runtime setup first.')
        command=[str(setup.python),str(Path(__file__).resolve()),'--isolated']
        if args.download_reference:command.append('--download-reference')
        subprocess.run(command,check=True)
