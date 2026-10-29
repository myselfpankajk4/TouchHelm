"""Opt-in SDK comparison on transformed public fixtures; no webcam/native input."""
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def check():
    import cv2
    import mediapipe as mp
    from server.aircontrol.worker import models,face_state,prepare_frame
    source=cv2.imread(str(ROOT/'.tmp/aircontrol-reference/portrait.jpg'))
    if source is None:raise RuntimeError('Run native_aircontrol_model_check.py --download-reference first')
    variants={'original':source,'mirrored':cv2.flip(source,1),
        'dim_45_percent':cv2.convertScaleAbs(source,alpha=.45),
        'dim_70_percent':cv2.convertScaleAbs(source,alpha=.7),
        'blur_5px':cv2.GaussianBlur(source,(5,5),0),
        'low_resolution':cv2.resize(source,(96,128)),
        'blank_negative':source*0}
    report={}
    for threshold in (.65,.5):
        results={};times=[]
        for name,frame in variants.items():
            frame=prepare_frame(cv2,frame,False)
            _,model=models(mp,ROOT/'assets/aircontrol','head',face_min=threshold)
            try:
                image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                for i in range(3):
                    started=time.monotonic();raw=model.detect_for_video(image,i*67);times.append((time.monotonic()-started)*1000)
                state,_=face_state(raw)
                results[name]=bool(state and state['tracked'])
            finally:model.close()
        assert results['original'] and results['mirrored'],'Reference face could not be tracked'
        assert not results['blank_negative'],'Blank negative was accepted as a face'
        report[str(threshold)]={'tracked':results,'median_fixture_inference_ms':round(statistics.median(times),1)}
    print(json.dumps({'reference_comparison':report,'camera_opened':False,'native_input_sent':False,
        'limitation':'Synthetic lighting/blur transforms do not measure physical gesture accuracy.'}))

if __name__=='__main__':
    if '--isolated' in sys.argv:check()
    else:
        from server.aircontrol.setup import AirControlSetup
        from server.private_storage import private_storage_root
        setup=AirControlSetup(private_storage_root()/'aircontrol')
        if not setup.snapshot()['ready']:raise RuntimeError('Complete AirControl setup first')
        subprocess.run([str(setup.python),str(Path(__file__).resolve()),'--isolated'],check=True)
