"""Desktop-only AirControl lifecycle and validated input execution."""
import asyncio
from collections import deque
import copy
import math
from pathlib import Path
import statistics
import time

from .engine import GestureEngine,number,physical_point,tracked
from .profiles import ProfileStore,default_profile,validate_profile,ACTION_LABELS,GESTURE_LABELS
from .process import CameraWorker
from .setup import AirControlSetup

class AirControlService:
    def __init__(self,input_controller,displays,*,folder,setup=None,worker_factory=CameraWorker,
                 acquire=None,release=None,overlay=None,voice=None):
        self.input=input_controller;self.displays=displays;self.folder=Path(folder)
        self.setup=setup or AirControlSetup(self.folder);self.worker_factory=worker_factory
        self.store=ProfileStore(self.folder/'profile.json');self.profile=self.store.read()
        self.profiles=self.store.all()
        self.engine=GestureEngine(self.profile);self.acquire=acquire;self.release=release
        self.overlay=overlay;self.voice=voice;self.worker=None;self.task=None;self.lock=asyncio.Lock()
        self.state='ready' if self.setup.snapshot().get('ready') else 'setup_required'
        self.message='Choose Start camera. Calibration and practice do not control the PC.'
        self.preview='';self.frame={};self.last_frame=0.;self.last_sequence=-1;self.last_point=None
        self.owns_input=False;self.calibrated=False;self.practice_frames=0;self.practice_actions=0
        self.native_down=False
        self.press_point=None;self.press_at=0.
        self.samples=deque(maxlen=15);self.calibration_points={};self.display=None
        self.latencies=deque(maxlen=600);self.times=deque(maxlen=90);self.actions=deque(maxlen=8)
        self.started=0.;self._voice_task=None;self._closing=False
        self.expression_neutral=False;self.expression_seen=set();self.expression_candidate='';self.expression_since=0.
        self.geometry_checked=0.
        self.stable_since=None;self.stable_frames=0

    def snapshot(self,*,frame=False):
        setup=self.setup.snapshot()
        state=self.state
        if not self.worker and setup['ready'] and state=='setup_required':state='ready'
        fresh=time.monotonic()-self.last_frame<=.25
        result={'state':state,'message':self.message,'setup':setup,'camera_active':self.worker is not None,
            'owns_input':self.owns_input,'profile':copy.deepcopy(self.profile),'calibrated':self.calibrated,
            'profiles':copy.deepcopy(self.profiles),
            'calibration_points':list(self.calibration_points),'practice_ready':self.practice_frames>=15 and self.practice_actions>0,
            'practice_frames':self.practice_frames,'practice_actions':self.practice_actions,
            'gesture':self.engine.gesture,'gesture_label':GESTURE_LABELS.get(self.engine.gesture,'Move naturally'),
            'hotkey':getattr(self.overlay,'hotkey_status','Ctrl+Alt+Space after enabling control'),
            'expression_practice':{'neutral':self.expression_neutral,'seen':sorted(self.expression_seen)},
            'action':self.profile['bindings'].get(self.engine.gesture,'none'),'progress':self.engine.progress,
            'pose_score':(self.frame.get('hand') or {}).get('gesture_confidence'),
            'pose_name':(self.frame.get('hand') or {}).get('pose') or None,
            'tracking_sources':{'hand':fresh and tracked(self.frame.get('hand') or {}),'face':fresh and tracked(self.frame.get('face') or {}),
                'hand_enabled':self.profile['mode']!='head','face_enabled':self.profile['mode']!='hand'},
            'point':self.engine.point,'tracking':not self.engine.lost and fresh,'display':self.display,
            'actions':list(self.actions),'action_catalog':ACTION_LABELS,'gesture_catalog':GESTURE_LABELS,
            'metrics':{'fps':round((len(self.times)-1)/(self.times[-1]-self.times[0]),1) if fresh and len(self.times)>1 and self.times[-1]>self.times[0] else None,
                'median_latency_ms':round(statistics.median(self.latencies),1) if self.latencies else None,
                'inference_ms':self.frame.get('inference_ms'),'capture_fps':self.frame.get('capture_fps')},
            'voice':self.voice.snapshot() if self.voice else {'message':'Dictation is available from the desktop on Windows.'}}
        if self.worker:
            usage=self.worker.stats()
            if isinstance(usage,dict):result['metrics'].update(usage)
        if frame:result.update(preview=self.preview,hand_points=self.frame.get('hand_points',[]),face_points=self.frame.get('face_points',[]),seq=self.last_sequence)
        return result

    def _release_buttons(self):
        self.engine.reset()
        if self.native_down:
            try:self.input.mouse_up('left')
            except Exception:pass
            else:self.native_down=False
        self.last_point=None

    def pause(self,message='Paused. Resume explicitly when ready.',state='paused'):
        if self._voice_task and not self._voice_task.done():self._voice_task.cancel()
        self.stable_since=None;self.stable_frames=0;self.samples.clear()
        self._release_buttons();self.state=state;self.message=message

    def _stable(self):
        return self.stable_since is not None and self.stable_frames>=5 and time.monotonic()-self.stable_since>=.2

    def watchdog(self,now=None):
        now=time.monotonic() if now is None else now
        if self.state=='active' and now-self.last_frame>.25:
            self.pause('Tracking lost. Hold a neutral pose, then Resume.','tracking_lost')

    async def _stop(self):
        self._release_buttons()
        if self._voice_task and not self._voice_task.done():self._voice_task.cancel()
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
        self.task=None
        worker,self.worker=self.worker,None
        if worker:await asyncio.to_thread(worker.stop)
        self.preview='';self.frame={};self.samples.clear();self.times.clear();self.last_frame=0
        self.stable_since=None;self.stable_frames=0
        if self.owns_input:
            self.owns_input=False
            if self.release:await self.release()
        if self.overlay:self.overlay.hide()
        self.state='ready' if self.setup.snapshot().get('ready') else 'setup_required'
        self.message='Camera stopped. Phone controls are available.'

    async def command(self,action,data=None):
        data=data or {}
        async with self.lock:
            if self._closing:raise RuntimeError('AirControl is stopping')
            if action=='setup':self.setup.start()
            elif action=='cancel_setup':self.setup.cancel()
            elif action=='start':
                profile=validate_profile(data.get('profile',self.profile))
                if not self.setup.snapshot().get('ready'):raise ValueError('Complete AirControl setup first')
                await self._stop();self.profile=profile;self.engine=GestureEngine(profile)
                displays=await self.displays();values=displays.get('displays',[])
                if profile['monitor_id'] and not any(d.get('id')==profile['monitor_id'] for d in values):
                    raise ValueError('The selected monitor is unavailable. Refresh monitors and choose one before starting.')
                self.display=next((d for d in values if d.get('id')==profile['monitor_id']),next((d for d in values if d.get('primary')),values[0] if values else None))
                if self.display:self.engine.profile['_monitor_scale']=(self.display['rect']['width'],self.display['rect']['height'])
                self.calibrated=False;self.calibration_points={};self.practice_frames=self.practice_actions=0
                self.expression_neutral=False;self.expression_seen.clear();self.expression_candidate='';self.expression_since=0.
                self.latencies.clear();self.last_sequence=-1;self.started=time.monotonic()
                self.worker=self.worker_factory(self.setup)
                try:await asyncio.to_thread(self.worker.start,profile)
                except Exception:
                    await self._stop();raise
                self.state='calibrating';self.message='Position yourself comfortably. Capture the calibration targets, then practice.'
                self.task=asyncio.create_task(self._loop())
            elif action=='calibrate':self.calibrate(data.get('target','center'))
            elif action=='practice':
                if not self.worker or not self.calibrated:raise ValueError('Calibrate before starting practice')
                self.pause('Practice mode: pointer and actions are simulated.','practicing')
                if self.owns_input:
                    self.owns_input=False
                    if self.release:await self.release()
                    if self.overlay:self.overlay.hide()
            elif action=='enable':
                if not self.worker or not self.calibrated or self.practice_frames<15 or not self.practice_actions:raise ValueError('Complete calibration and test a click in practice first')
                if self.engine.lost or time.monotonic()-self.last_frame>.25:raise ValueError('Hold a steady tracked pose before enabling control')
                if not self._stable():raise ValueError('Hold a steady tracked pose for a moment before enabling control')
                if not self.display:raise ValueError('No monitor is available')
                current=await self.displays()
                if not any(d.get('id')==self.display['id'] and d.get('rect')==self.display['rect'] for d in current.get('displays',[])):raise ValueError('Monitor geometry changed. Restart camera calibration.')
                self._release_buttons();self.owns_input=True
                try:
                    if self.acquire:await self.acquire()
                except BaseException:
                    self.owns_input=False
                    if self.release:await self.release()
                    raise
                self.state='active'
                self.message='AirControl is active. Ctrl+Alt+Space pauses or resumes.'
                self.store.save(self.profile)
                self.profiles[self.profile['name']]=copy.deepcopy(self.profile)
            elif action=='pause':
                if self.worker:self.pause()
            elif action=='resume':self.resume()
            elif action=='recenter':
                if not self.worker:raise ValueError('Start the camera first')
                if self.profile['mode'] in ('hand','combined'):self.worker.recenter()
                if self.profile['mode']!='hand':
                    face=self.frame.get('face') or {}
                    if not face or time.monotonic()-self.last_frame>.25:raise ValueError('Face tracking is not ready')
                    self.profile['calibration']['head_neutral']=[number(face.get('yaw')),number(face.get('pitch'))]
                    self.engine.profile['calibration']=copy.deepcopy(self.profile['calibration'])
                if self.owns_input:self.pause('Recentered. Hold a neutral pose and Resume.')
                else:self.pause('Recentered. Continue with the practice cursor; Windows input is off.',
                    'practicing' if self.calibrated else 'calibrating')
            elif action=='save':
                profile=validate_profile(data.get('profile'))
                await self._stop();self.profile=self.store.save(profile);self.engine=GestureEngine(profile)
                self.profiles[profile['name']]=copy.deepcopy(profile)
                self.message='Settings saved. Start camera to calibrate and practice the updated controls.'
            elif action=='expression_calibrate':
                if self.state!='practicing' or not self.expression_neutral or not self.expression_seen:raise ValueError('In Head/Combined practice, hold a neutral face, then a deliberate expression for 400 ms.')
                self.profile['calibrated_expressions']=sorted(set(self.profile['calibrated_expressions'])|self.expression_seen)
                self.profile['expressions_calibrated']=True
                self.engine.profile['expressions_calibrated']=True
                self.engine.profile['calibrated_expressions']=list(self.profile['calibrated_expressions'])
                self.message='Observed facial expressions calibrated. You can now assign their actions in Gesture mappings.'
            elif action=='stop':await self._stop()
            elif action=='dictate':
                if not self.voice:raise ValueError('Windows dictation is unavailable')
                if not self._voice_task or self._voice_task.done():
                    self.voice.message='Checking the selected Windows text field…'
                    self._voice_task=asyncio.create_task(self.voice.dictate(explicit=True))
            elif action=='voice_access':
                if not self.voice:raise ValueError('Voice Access is unavailable')
                await self.voice.open_voice_access()
            else:raise ValueError('Unsupported AirControl action')
            return {'success':True,'aircontrol':self.snapshot()}

    def resume(self):
        if not self.worker or not self.owns_input:raise ValueError('Enable PC control from practice first')
        if not self.display:raise ValueError('Monitor changed. Stop the camera and recalibrate for the available monitor.')
        if self.engine.lost or time.monotonic()-self.last_frame>.25:raise ValueError('Wait for stable tracking before resuming')
        if not self._stable():raise ValueError('Hold a steady tracked pose for a moment before resuming')
        self._release_buttons();self.state='active';self.message='AirControl resumed.'

    def calibrate(self,target):
        targets=('center',) if self.profile['mode']!='hand' else ('center','top_left','top_right','bottom_left','bottom_right')
        if target not in targets:raise ValueError('Choose a calibration target')
        if not self.worker or self.state not in ('calibrating','practicing') or len(self.samples)<5:raise ValueError('Wait for steady tracking before capturing a target')
        if time.monotonic()-self.last_frame>.25:raise ValueError('Tracking is not current')
        mode=self.profile['mode'];key='hand' if mode=='hand' else 'face'
        values=[s.get(key) for s in self.samples if s.get(key)]
        if len(values)<5:raise ValueError('Keep the required hand or face visible')
        if mode=='hand':
            if max(statistics.pstdev([v[c] for v in values]) for c in ('x','y'))>.035:raise ValueError('Hold still briefly, then capture again')
            self.calibration_points[target]=[statistics.mean(v[c] for v in values) for c in ('x','y')]
        else:
            if max(statistics.pstdev([v[c] for v in values]) for c in ('yaw','pitch'))>3:raise ValueError('Hold your head still briefly')
            self.calibration_points[target]=[statistics.mean(v[c] for v in values) for c in ('yaw','pitch')]
        if target=='center' and mode!='hand':self.profile['calibration']['head_neutral']=self.calibration_points[target]
        if all(t in self.calibration_points for t in targets):
            if mode=='hand':
                corners=[self.calibration_points[t] for t in targets if t!='center']
                bounds=[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)]
                self.profile['calibration']['hand_bounds']=bounds
                validate_profile(self.profile)
            self.engine=GestureEngine(self.profile)
            if self.display:self.engine.profile['_monitor_scale']=(self.display['rect']['width'],self.display['rect']['height'])
            self.calibrated=True;self.state='practicing';self.message='Practice: move the simulated cursor and test a click. Nothing is sent to Windows.'
        else:self.message='Target captured. Move to the next comfortable position.'

    def observe(self,frame,*,now=None):
        now=time.monotonic() if now is None else now
        stamp=number(frame.get('timestamp'),-100)
        sequence=frame.get('seq')
        if type(sequence) is not int or sequence<=self.last_sequence or not 0<=now-stamp<=.25:return
        if self.last_frame and stamp-self.last_frame>.25:
            self.stable_since=None;self.stable_frames=0;self.samples.clear()
        hand=frame.get('hand');face=frame.get('face')
        def valid_number(value,minimum,maximum):return type(value) in (int,float) and math.isfinite(value) and minimum<=value<=maximum
        if hand is not None and (not isinstance(hand,dict) or any(not valid_number(hand.get(k),0,1) for k in ('x','y'))
                or ('tracked' in hand and type(hand['tracked']) is not bool)
                or ('confidence' in hand and not valid_number(hand['confidence'],0,1))):
            self.stable_since=None;self.stable_frames=0;self.samples.clear()
            if self.state=='active':self.pause('Invalid hand tracking result. Reacquire your hand before resuming.','tracking_lost')
            return
        if face is not None and (not isinstance(face,dict) or any(not valid_number(face.get(k),-90,90) for k in ('yaw','pitch'))):
            self.stable_since=None;self.stable_frames=0;self.samples.clear()
            if self.state=='active':self.pause('Invalid face tracking result. Reacquire your pose before resuming.','tracking_lost')
            return
        self.last_sequence=sequence;self.last_frame=stamp
        self.frame={k:v for k,v in frame.items() if k!='preview'}
        if isinstance(frame.get('preview'),str) and len(frame['preview'])<=300000:self.preview=frame['preview']
        self.samples.append(self.frame)
        events=self.engine.step(frame,paused=self.state in ('paused','tracking_lost'))
        if self.engine.lost:
            self.stable_since=None;self.stable_frames=0;self.samples.clear();self.times.clear()
            if self.state=='active':self.pause('Tracking lost. Reacquire your pose, then Resume.','tracking_lost')
            return
        if self.stable_since is None:self.stable_since=now
        self.times.append(now)
        self.stable_frames+=1
        if self.state=='practicing':
            self.practice_frames+=1
            clicks=[e for e in events if e['kind']=='button' and e['action']=='down' or
                e['kind']=='action' and e['action'] in ('left_click','right_click','double_click')]
            self.practice_actions+=len(clicks)
            for event in clicks:self.actions.appendleft('Practice: '+('Left press / drag' if event['kind']=='button' else ACTION_LABELS[event['action']]))
            e=(frame.get('face') or {}).get('expressions',{})
            left=number(e.get('eyeBlinkLeft'));right=number(e.get('eyeBlinkRight'))
            smile=min(number(e.get('mouthSmileLeft')),number(e.get('mouthSmileRight')))
            brow=number(e.get('browInnerUp'))
            if e and max(left,right,smile,brow)<.25:self.expression_neutral=True
            candidate='wink_left' if left>.75 and right<.25 else 'wink_right' if right>.75 and left<.25 else 'smile' if smile>.7 else 'brows_up' if brow>.75 else ''
            if candidate!=self.expression_candidate:self.expression_candidate=candidate;self.expression_since=now
            if candidate and self.expression_neutral and now-self.expression_since>=.4:self.expression_seen.add(candidate)
        if self.state!='active':
            for event in events:
                if self.owns_input and event.get('action')=='resume':
                    try:self.resume()
                    except ValueError:pass
                elif event['kind']=='hud_dwell' and self.overlay:self.overlay.dwell(event.get('x',0),event.get('y',0),self.display)
            return
        try:
            self.input.ensure_input_desktop()
            if self.display and now-self.geometry_checked>.2:
                self.geometry_checked=now
                if not self.input.monitor_matches(self.display):
                    self.pause('Monitor layout changed. Stop the camera and recalibrate.','tracking_lost');self.display=None;return
            if self.last_point is not None:
                actual=self.input.get_physical_cursor_pos()
                if math.hypot(actual[0]-self.last_point[0],actual[1]-self.last_point[1])>12:
                    self.pause('Physical mouse took over. Resume when ready.');return
            for event in events:
                if self.state!='active':break
                kind=event['kind']
                if kind=='pointer':
                    self.last_point=physical_point(self.display['rect'],event['x'],event['y'])
                    self.input.set_physical_cursor_pos(*self.last_point)
                    self.latencies.append((time.monotonic()-stamp)*1000)
                elif kind=='button':
                    if event['action']=='down':
                        self.input.mouse_down(event['button']);self.native_down=True
                        self.press_point=self.last_point;self.press_at=now
                    else:
                        self.input.mouse_up(event['button']);self.native_down=False
                        if (self.press_point and self.last_point and now-self.press_at<=.5
                                and math.dist(self.press_point,self.last_point)<12 and not self.engine.gesture):self._auto_dictate()
                elif kind=='scroll':self.input.scroll(0,max(-2,min(2,event['dy'])),scroll_speed=1,invert=False)
                elif kind=='action':self._action(event['action'])
        except Exception:self.pause('Windows input is unavailable on this desktop. Resume in a normal signed-in session.','tracking_lost')

    def _auto_dictate(self):
        if self.voice and (not self._voice_task or self._voice_task.done()):
            self._voice_task=asyncio.create_task(self.voice.dictate(explicit=False) if self.profile['auto_dictation'] else self.voice.remember())

    def _action(self,action):
        self.actions.appendleft(ACTION_LABELS.get(action,action))
        if action=='pause':self.pause()
        elif action in ('left_click','right_click','double_click'):
            if action=='double_click':self.input.double_click('left')
            else:self.input.click('left' if action=='left_click' else 'right')
            if action!='right_click':self._auto_dictate()
        elif action=='dictate':
            if self.voice and (not self._voice_task or self._voice_task.done()):self._voice_task=asyncio.create_task(self.voice.dictate(explicit=True))
        elif action=='recenter':
            face=self.frame.get('face') or {}
            if face:self.profile['calibration']['head_neutral']=[number(face.get('yaw')),number(face.get('pitch'))];self.engine.profile['calibration']=copy.deepcopy(self.profile['calibration'])
            self.pause('Recentered. Resume when ready.')
        elif action in ('play_pause','next_track','previous_track'):self.input.media_action({'play_pause':'playpause','next_track':'nexttrack','previous_track':'prevtrack'}[action])
        elif action in ('next_slide','previous_slide'):self.input.key_tap('right' if action=='next_slide' else 'left')
        else:
            keys={'copy':('ctrl','c'),'paste':('ctrl','v'),'undo':('ctrl','z'),'switch_app':('alt','tab'),'keyboard':('win','ctrl','o')}.get(action)
            if keys:self.input.hotkey(*keys)

    async def _loop(self):
        try:
            while self.worker:
                item=self.worker.latest()
                if item:
                    if item.get('type')=='observation':self.observe(item)
                    elif item.get('type')=='error':
                        message=item.get('message','Camera unavailable');await self._stop();self.state='unavailable';self.message=message;return
                if not self.last_frame and time.monotonic()-self.started>25:
                    await self._stop();self.state='unavailable';self.message='No camera observations arrived. Check the selected camera and privacy permissions.';return
                self.watchdog()
                if self.state!='active' and self.native_down:self._release_buttons()
                if self.overlay:self.overlay.update(self.snapshot())
                await asyncio.sleep(.016)
        except asyncio.CancelledError:raise
        except Exception:
            await self._stop();self.state='unavailable';self.message='Camera control stopped safely. Restart practice to recover.'

    async def close(self):
        self._closing=True;self.setup.cancel()
        await self._stop()
        if self._voice_task:self._voice_task.cancel()
        if self.voice:await self.voice.close()
        if self.overlay:self.overlay.close()
