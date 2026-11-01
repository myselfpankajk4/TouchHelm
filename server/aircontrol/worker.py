"""Camera/inference subprocess. No Win32 input and no network endpoints.

--check loads models without opening any camera. Normal use requires an explicit
owned-desktop Start camera action. Only the latest capture is retained.
"""
import argparse
import base64
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time
from collections import deque

def emit(value):
    sys.stdout.write(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n');sys.stdout.flush()

def models(mp,folder,mode,*,face_min=.5):
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    hand=None;face=None
    if mode in ('hand','combined'):
        hand=vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
            base_options=python.BaseOptions(model_asset_path=str(folder/'gesture_recognizer.task')),
            running_mode=vision.RunningMode.VIDEO,num_hands=2,
            min_hand_detection_confidence=.65,min_hand_presence_confidence=.65,min_tracking_confidence=.65))
    if mode in ('head','combined'):
        face=vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(folder/'face_landmarker.task')),
            running_mode=vision.RunningMode.VIDEO,num_faces=2,
            min_face_detection_confidence=face_min,min_face_presence_confidence=face_min,min_tracking_confidence=face_min,
            output_face_blendshapes=True,output_facial_transformation_matrixes=True))
    return hand,face

def distance(a,b,aspect=1.):return math.hypot((a.x-b.x)*aspect,a.y-b.y)

def inference_rate(costs,current):
    if len(costs)<15:return current
    average=sum(costs)/len(costs)
    if average>.055:return 15
    if len(costs)>=30 and average<.035:return 30
    return current

def current_usage():
    cpu=os.times();value={'at':time.monotonic(),'cpu_seconds':cpu.user+cpu.system}
    if os.name=='nt':
        try:
            import ctypes
            from ctypes import wintypes
            class MEMORY(ctypes.Structure):
                _fields_=[('size',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak','working','paged_peak','paged','nonpaged_peak','nonpaged','pagefile','pagefile_peak')]
            memory=MEMORY();memory.size=ctypes.sizeof(memory)
            kernel=ctypes.windll.kernel32;kernel.GetCurrentProcess.restype=wintypes.HANDLE
            api=ctypes.windll.psapi
            api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(MEMORY),wintypes.DWORD]
            api.GetProcessMemoryInfo.restype=wintypes.BOOL
            if api.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(memory),memory.size):value['memory_mb']=round(memory.working/1048576,1)
        except (OSError,AttributeError,ValueError,OverflowError):pass
    return value

def prepare_frame(cv2,frame,mirror):
    if mirror:frame=cv2.flip(frame,1)
    height,width=frame.shape[:2]
    scale=min(640/width,480/height);w=max(1,round(width*scale));h=max(1,round(height*scale))
    frame=cv2.resize(frame,(w,h),interpolation=cv2.INTER_AREA)
    top=(480-h)//2;left=(640-w)//2
    return cv2.copyMakeBorder(frame,top,480-h-top,left,640-w-left,cv2.BORDER_CONSTANT,value=(0,0,0))

def hand_state(result,choice,previous,*,image_size=(1,1)):
    aspect=image_size[0]/image_size[1]
    candidates=[]
    for i,points in enumerate(result.hand_landmarks):
        if len(points)!=21 or any(not math.isfinite(p.x) or not math.isfinite(p.y) for p in points):continue
        if i>=len(result.handedness) or not result.handedness[i]:continue
        category=result.handedness[i][0];label=category.category_name.lower()
        if choice!='auto' and choice!=label:continue
        # Bind the same hand spatially rather than jumping to a second person.
        center=(points[9].x,points[9].y)
        if previous and math.hypot(center[0]-previous[0],center[1]-previous[1])>.3:continue
        palm=distance(points[5],points[17],aspect)
        if palm<.02:continue
        pose=result.gestures[i][0] if i<len(result.gestures) and result.gestures[i] else None
        candidates.append((points,category,center,palm,pose))
    if not candidates:return None,previous,[]
    if previous:candidates.sort(key=lambda c:math.hypot(c[2][0]-previous[0],c[2][1]-previous[1]))
    points,category,center,palm,pose=candidates[0]
    # Aim with the knuckle centre (mean of the four finger bases), not the index fingertip:
    # the fingertip is one of the pinching fingers, so it slides toward the thumb while a
    # click forms, and its 4-point mean also halves the landmark noise of any single point.
    knuckles=[points[i] for i in (5,9,13,17)]
    return {'x':max(0.,min(1.,sum(p.x for p in knuckles)/4)),'y':max(0.,min(1.,sum(p.y for p in knuckles)/4)),
        # Handedness is a left/right classification, not hand-presence quality.
        # The SDK already applied configured detection/presence/tracking gates.
        'tracked':True,'handedness_score':category.score,
        'pose':pose.category_name if pose and pose.category_name not in ('None','Unknown') and pose.score>=.7 else '',
        'pose_candidate':pose.category_name if pose else None,
        'gesture_confidence':pose.score if pose else None,
        'pinch_index':distance(points[4],points[8],aspect)/palm,
        'pinch_middle':distance(points[4],points[12],aspect)/palm,
        'index_extended':distance(points[8],points[5],aspect)>distance(points[6],points[5],aspect)*1.2,
        'hand':category.category_name.lower()},center,[[round(p.x,4),round(p.y,4)] for p in points]

def face_state(result,*,mirrored=False):
    if len(result.face_landmarks)!=1:return None,[]
    points=result.face_landmarks[0]
    indices=(1,4,33,133,263,362,61,291,10,152,234,454)
    if len(points)<=max(indices):return None,[]
    landmarks=[[round(points[i].x,4),round(points[i].y,4)] for i in indices]
    if any(not math.isfinite(v) for p in landmarks for v in p):return None,[]
    matrices=getattr(result,'facial_transformation_matrixes',None)
    if not matrices:return None,landmarks
    try:
        matrix=matrices[0];values=[float(matrix[i,2]) for i in range(3)]
        if any(not math.isfinite(v) for v in values):return None,landmarks
        yaw=math.degrees(math.atan2(values[0],values[2]))
        pitch=math.degrees(math.atan2(-values[1],math.hypot(values[0],values[2])))
    except (IndexError,TypeError,AttributeError,ValueError):return None,landmarks
    shapes=getattr(result,'face_blendshapes',None) or []
    expressions={item.category_name:round(max(0.,min(1.,item.score)),4) for item in (shapes[0] if shapes else []) if math.isfinite(item.score)}
    if mirrored:
        # SDK Left/Right coefficients invert on mirrored images. Publish the
        # subject's anatomical wink consistently with the unmirrored camera.
        expressions={key:expressions.get(key[:-4]+'Right',value) if key.endswith('Left') else
            expressions.get(key[:-5]+'Left',value) if key.endswith('Right') else value
            for key,value in expressions.items()}
    # FaceLandmarker exposes thresholded presence, not a calibrated confidence.
    # The internal floor is a gate; no invented percentage is shown in the UI.
    return {'yaw':yaw,'pitch':pitch,'tracked':True,'count':1,'expressions':expressions},landmarks

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--check',action='store_true');parser.add_argument('--config',default='{}')
    args=parser.parse_args()
    import cv2
    import mediapipe as mp
    config=json.loads(args.config);mode=config.get('mode','hand')
    if args.check:
        h,f=models(mp,args.models,'combined')
        h.close();f.close();emit({'type':'ready','opencv':cv2.__version__,'mediapipe':mp.__version__});return
    hand,face=models(mp,args.models,mode)
    cap=cv2.VideoCapture(int(config.get('camera_id','0')),cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release();raise RuntimeError('The selected DirectShow camera could not open. Check its privacy permission, USB connection and whether another app is using it.')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,640);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480);cap.set(cv2.CAP_PROP_FPS,30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
    stopped=threading.Event();requested_stop=threading.Event();reset_hand=threading.Event();frames=queue.Queue(maxsize=1);capture_rate=[None]
    def control():
        for line in sys.stdin:
            if len(line)>256:continue
            try:command=json.loads(line)
            except ValueError:continue
            if command.get('action')=='recenter':reset_hand.set()
            elif command.get('action')=='stop':requested_stop.set();stopped.set();return
    threading.Thread(target=control,daemon=True,name='AirControl worker commands').start()
    def capture():
        stamps=deque(maxlen=31)
        while not stopped.is_set():
            ok,frame=cap.read()
            if not ok:stopped.set();break
            item=(time.monotonic(),frame)
            stamps.append(item[0])
            if len(stamps)>1 and stamps[-1]>stamps[0]:capture_rate[0]=round((len(stamps)-1)/(stamps[-1]-stamps[0]),1)
            try:frames.put_nowait(item)
            except queue.Full:
                try:frames.get_nowait()
                except queue.Empty:pass
                try:frames.put_nowait(item)
                except queue.Full:pass
    threading.Thread(target=capture,daemon=True,name='AirControl capture').start()
    emit({'type':'ready','message':'Camera ready. Calibration and practice do not inject PC input.'})
    seq=0;previous=None;lost_hand_at=0.;last_preview=0.;last_ms=-1;fps=30;costs=[];usage={};last_usage=0.
    try:
        while not stopped.is_set():
            try:stamp,frame=frames.get(timeout=1)
            except queue.Empty:raise RuntimeError('No camera frames. Check camera permissions and reconnect it.')
            started=time.monotonic()
            if started-stamp>.25:continue
            # A fixed letterboxed frame keeps previews/landmarks aligned even
            # when a driver ignores its requested 640x480 capture format.
            frame=prepare_frame(cv2,frame,config.get('mirror',True))
            image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            timestamp=max(last_ms+1,int(stamp*1000));last_ms=timestamp
            result={'type':'observation','timestamp':stamp,'seq':seq,'mode':mode};seq+=1
            if hand:
                if reset_hand.is_set():previous=None;reset_hand.clear()
                detected=hand.recognize_for_video(image,timestamp)
                state,location,landmarks=hand_state(detected,config.get('hand','auto'),previous,image_size=(640,480))
                if state:previous=location;lost_hand_at=0.
                elif not lost_hand_at:lost_hand_at=started
                # Never silently acquire a different hand mid-session. Recenter
                # resets that binding if the tracked hand cannot be reacquired.
                count=len(detected.hand_landmarks)
                reason='' if state else 'No hand detected. Keep the whole hand visible.' if not count else 'Selected hand is unavailable or moved away. Use Recenter to acquire it again.'
                result.update(hand=state,hands_count=count,hand_points=landmarks,hand_status=reason)
            if face:
                detected=face.detect_for_video(image,timestamp);state,landmarks=face_state(detected,mirrored=config.get('mirror',True))
                count=len(detected.face_landmarks)
                reason='' if state else 'No face detected. Face the camera with even light.' if not count else 'More than one face is visible. Keep one person in view.' if count>1 else 'Face detected, but head pose is unavailable. Face the camera and recenter.'
                result.update(face=state,face_points=landmarks,face_status=reason)
            elapsed=time.monotonic()-started;costs.append(elapsed);costs=costs[-30:]
            # Never mutate a DirectShow capture while its reader is running.
            # Some drivers stop delivering frames after an in-flight FPS change.
            # Rate-limit inference, retaining only the newest camera frame.
            fps=inference_rate(costs,fps)
            result.update(inference_ms=round(elapsed*1000,1),age_ms=round((time.monotonic()-stamp)*1000,1),capture_fps=capture_rate[0],inference_target_fps=fps)
            if time.monotonic()-last_usage>=.5:usage=current_usage();last_usage=time.monotonic()
            result['usage']=usage
            if time.monotonic()-last_preview>=.1:
                ok,jpeg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,65])
                if ok:result['preview']=base64.b64encode(jpeg).decode('ascii')
                last_preview=time.monotonic()
            emit(result)
            stopped.wait(max(0.,1/fps-(time.monotonic()-started)))
        if not requested_stop.is_set():raise RuntimeError('The camera stopped delivering frames. Restart it; check its USB connection and whether another app is using it.')
    finally:
        stopped.set();cap.release()
        if hand:hand.close()
        if face:face.close()

if __name__=='__main__':
    try:main()
    except (BrokenPipeError,KeyboardInterrupt):pass
    except Exception as error:
        emit({'type':'error','message':str(error)[:350]});sys.exit(1)
