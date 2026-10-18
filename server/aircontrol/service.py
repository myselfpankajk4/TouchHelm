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
from .expressions import levels,measure,learn
from .hud import HEAD_ACTIONS,HEAD_SCROLL_ACTIONS,regions,practice_regions
from .practice import PracticeSession
from .metrics import SessionMetrics,bounded

class AirControlService:
    def __init__(self,input_controller,displays,*,folder,setup=None,worker_factory=CameraWorker,
                 acquire=None,release=None,overlay=None,voice=None,desktop_available=None):
        if desktop_available is None:
            from server.remote_media import unlocked_desktop
            desktop_available=unlocked_desktop
        self.desktop_available=desktop_available
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
        self.samples=deque(maxlen=15);self.face_samples=deque(maxlen=15);self.calibration_points={};self.display=None
        self.latencies=deque(maxlen=600);self.times=deque(maxlen=90);self.actions=deque(maxlen=8)
        self.metrics=SessionMetrics(self.latencies)
        self.metrics.stop(time.monotonic())
        self.last_usage={}
        self.started=0.;self._voice_task=None;self._closing=False
        self.expression_neutral=False;self.expression_seen=set();self.expression_candidate='';self.expression_since=0.
        self.expression_baseline=None
        self.geometry_checked=0.
        self.stable_since=None;self.stable_frames=0
        self.observations=0;self.rejected_observations=0;self.observation_age=None;self.last_error=''
        self.practice=PracticeSession();self.practice_viewport=(640,480)

    def snapshot(self,*,frame=False):
        setup=self.setup.snapshot()
        state=self.state
        if not self.worker and setup['ready'] and state=='setup_required':state='ready'
        fresh=time.monotonic()-self.last_frame<=.25
        result={'state':state,'message':self.message,'activation':self.activation_readiness(),'setup':setup,'camera_active':self.worker is not None,
            'owns_input':self.owns_input,'profile':copy.deepcopy(self.profile),'calibrated':self.calibrated,
            'calibration_ready':fresh and (tracked(self.frame.get('hand') or {}) if self.profile['mode']=='hand' else tracked(self.frame.get('face') or {}) and (self.frame.get('face') or {}).get('count')==1),
            'profiles':copy.deepcopy(self.profiles),
            'calibration_points':list(self.calibration_points),'practice_ready':self.practice_frames>=15 and self.practice_actions>0,
            'practice_frames':self.practice_frames,'practice_actions':self.practice_actions,
            'gesture':self.engine.gesture,'gesture_label':GESTURE_LABELS.get(self.engine.gesture,'Move naturally'),
            'hotkey':getattr(self.overlay,'hotkey_status','Ctrl+Alt+Space after enabling control'),
            'expression_practice':{'neutral':self.expression_neutral,'seen':sorted(self.expression_seen),
                'measured_neutral':self.expression_baseline is not None,'values':levels(self.frame.get('face') or {}) if fresh else {}},
            'action':self.profile['bindings'].get(self.engine.gesture,'none'),'progress':self.engine.progress,
            'pose_score':(self.frame.get('hand') or {}).get('gesture_confidence'),
            'pose_name':(self.frame.get('hand') or {}).get('pose') or None,
            'tracking_sources':{'hand':fresh and tracked(self.frame.get('hand') or {}),'face':fresh and tracked(self.frame.get('face') or {}),
                'hand_enabled':self.profile['mode']!='head','face_enabled':self.profile['mode']!='hand'},
            'tracking_details':{'hand':self.frame.get('hand_status',''),'face':self.frame.get('face_status',''),
                'processing_delayed':self.observation_age is not None and self.observation_age>.25,'last_error':self.last_error},
            'point':self.engine.point,'tracking':not self.engine.lost and fresh,'display':self.display,
            'dwell_action':self.engine.dwell_action,'dragging':self.engine.held,'head_scroll':self.engine.head_scroll,
            'practice':self.practice.snapshot(time.monotonic()),
            'scroll_regions':practice_regions(getattr(self,'practice_viewport',(640,480)),scrolling=self.engine.head_scroll) if self.state=='practicing' else [],
            'actions':list(self.actions),'action_catalog':ACTION_LABELS,'gesture_catalog':GESTURE_LABELS,
            'metrics':{'fps':round((len(self.times)-1)/(self.times[-1]-self.times[0]),1) if fresh and len(self.times)>1 and self.times[-1]>self.times[0] else None,
                'median_latency_ms':round(statistics.median(self.latencies),1) if self.latencies else None,
                'inference_ms':self.frame.get('inference_ms'),'capture_fps':self.frame.get('capture_fps'),
                'inference_target_fps':self.frame.get('inference_target_fps'),'frame_age_ms':round(self.observation_age*1000,1) if self.observation_age is not None else None,
                'observations':self.observations,'rejected_observations':self.rejected_observations},
            'voice':self.voice.snapshot() if self.voice else {'message':'Dictation is available from the desktop on Windows.'}}
        result['metrics'].update(self.metrics.snapshot(time.monotonic()))
        if self.worker:
            usage=self.worker.stats()
            if isinstance(usage,dict):
                self.last_usage={k:usage[k] for k,limit in [('cpu_percent',100),('memory_mb',1048576)] if bounded(usage.get(k),limit)}
                result['metrics'].update(self.last_usage)
        if frame:result.update(preview=self.preview,hand_points=self.frame.get('hand_points',[]),face_points=self.frame.get('face_points',[]),seq=self.last_sequence)
        return result

    def activation_readiness(self,*,now=None):
        """Local, side-effect-free guidance shared with the Enable guard."""
        now=time.monotonic() if now is None else now
        checks=[
            (not self.worker,'camera_off','Start the camera to begin calibration.'),
            (self.owns_input,'already_active','PC control is already enabled.'),
            (not self.calibrated,'calibration_required','Capture your comfortable neutral position first.'),
            (self.state!='practicing' or self.practice_frames<15 or not self.practice_actions,'practice_required','Complete calibration and test a click in practice first.'),
            (self.engine.lost or not 0<=now-self.last_frame<=.25,'tracking_required','Hold a steady tracked pose before enabling control.'),
            (self.engine.held or bool(self.engine.gesture and self.profile['bindings'].get(self.engine.gesture,'none')!='none'),'release_gesture','Release the practice gesture, then enable PC control with a neutral pointing pose.'),
            (self.stable_since is None or self.stable_frames<5 or now-self.stable_since<.2,'steady_required','Hold a steady tracked pose for a moment before enabling control.'),
            (not self.display,'monitor_required','No monitor is available. Refresh monitors and restart calibration.')]
        for blocked,code,message in checks:
            if blocked:return {'ready':False,'code':code,'message':message}
        return {'ready':True,'code':'ready','message':'Ready to enable PC control. Your phone will return to View.'}

    def _release_buttons(self,*,consume_dwell=False):
        self.engine.reset(consume_dwell=consume_dwell)
        if self.native_down:
            try:self.input.mouse_up('left')
            except Exception:pass
            else:self.native_down=False
        self.last_point=None

    def pause(self,message='Paused. Resume explicitly when ready.',state='paused'):
        if state=='tracking_lost':self.metrics.mark_lost()
        self.practice.interrupt(time.monotonic())
        if self._voice_task and not self._voice_task.done():self._voice_task.cancel()
        self.stable_since=None;self.stable_frames=0;self.samples.clear();self.face_samples.clear()
        self._release_buttons();self.state=state;self.message=message
        self.engine.hud_blocked=True

    def _stable(self):
        return self.stable_since is not None and self.stable_frames>=5 and time.monotonic()-self.stable_since>=.2

    def _desktop_ready(self):
        try:return bool(self.desktop_available())
        except Exception:return False

    def watchdog(self,now=None):
        now=time.monotonic() if now is None else now
        if self.state=='active' and now-self.last_frame>.25:
            self.pause('Tracking lost. Hold a neutral pose, then Resume.','tracking_lost')

    async def _stop(self):
        self.metrics.stop(time.monotonic())
        self._release_buttons()
        if self._voice_task and not self._voice_task.done():self._voice_task.cancel()
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
        self.task=None
        worker,self.worker=self.worker,None
        if worker:await asyncio.to_thread(worker.stop)
        self.preview='';self.frame={};self.samples.clear();self.face_samples.clear();self.times.clear();self.last_frame=0
        self.calibrated=False;self.calibration_points={};self.practice_frames=0;self.practice_actions=0
        self.practice.start('free',time.monotonic())
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
            elif action=='reset_measurements':
                self.metrics.reset(time.monotonic());self.practice.clear_history()
                if not self.worker:self.metrics.stop(time.monotonic())
            elif action=='export_report':
                rect=self.display['rect'] if self.display else {}
                report=self.metrics.report(at=time.monotonic(),mode=self.profile['mode'],display_size=[rect.get('width'),rect.get('height')],
                    results=list(self.practice.results),build_id=data.get('build_id',''))
                if self.worker:
                    usage=self.worker.stats()
                    if isinstance(usage,dict):
                        for key,limit in [('cpu_percent',100),('memory_mb',1048576)]:
                            if bounded(usage.get(key),limit):report['metrics'][key]=usage[key]
                else:report['metrics'].update(self.last_usage)
                return {'success':True,'report':report}
            elif action=='practice_viewport':
                previous=self.practice.viewport
                self.practice.set_viewport(data.get('width'),data.get('height'),data.get('revision',0))
                self.practice_viewport=self.practice.viewport
                if previous!=self.practice_viewport and self.state=='practicing':self.engine.reset(consume_dwell=True)
            elif action in ('practice_start','practice_reset','practice_pause','practice_resume'):
                if not self.worker or not self.calibrated:raise ValueError('Calibrate before starting a practice exercise.')
                if action=='practice_start':
                    name=data.get('name','click')
                    if name not in ('free','click','drag','scroll'):raise ValueError('Choose a supported practice exercise.')
                    if self.state!='practicing':
                        self.pause('Practice exercises send no Windows input.','practicing')
                        if self.owns_input:
                            self.owns_input=False
                            if self.release:await self.release()
                            if self.overlay:self.overlay.hide()
                    self.engine.reset(consume_dwell=True);self.practice.start(name,time.monotonic())
                    if self.profile['mode']=='head':
                        if name=='drag':self.engine.select_dwell('drag')
                        elif name=='scroll':self.engine.set_head_scroll(True)
                elif self.state!='practicing':raise ValueError('Return to practice before changing the exercise.')
                elif action=='practice_reset':
                    self.engine.reset(consume_dwell=True);self.practice.start(self.practice.name,time.monotonic())
                    if self.profile['mode']=='head':
                        if self.practice.name=='drag':self.engine.select_dwell('drag')
                        elif self.practice.name=='scroll':self.engine.set_head_scroll(True)
                elif action=='practice_pause':
                    self.engine.reset(consume_dwell=True);self.practice.interrupt(time.monotonic())
                else:self.practice.resume(time.monotonic())
                self.message='Practice exercise: '+self.practice.name+'. Windows input is off.'
            elif action=='start':
                if not self._desktop_ready():raise ValueError('Unlock Windows and return to the normal desktop before starting the camera.')
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
                self.expression_baseline=None
                self.practice.start('free',time.monotonic());self.practice.clear_history()
                self.observations=0;self.rejected_observations=0;self.observation_age=None;self.last_error=''
                self.latencies.clear();self.last_sequence=-1;self.started=time.monotonic()
                self.metrics.reset(self.started)
                self.last_usage={}
                self.worker=self.worker_factory(self.setup)
                try:await asyncio.to_thread(self.worker.start,profile)
                except Exception:
                    await self._stop();raise
                self.state='calibrating';self.message='Position yourself comfortably. Capture the calibration targets, then practice.'
                self.task=asyncio.create_task(self._loop())
            elif action=='calibrate':self.calibrate(data.get('target','center'),quick=data.get('quick',False))
            elif action=='practice':
                if not self.worker or not self.calibrated:raise ValueError('Calibrate before starting practice')
                self.pause('Practice mode: pointer and actions are simulated.','practicing')
                if self.owns_input:
                    self.owns_input=False
                    if self.release:await self.release()
                    if self.overlay:self.overlay.hide()
            elif action=='enable':
                if not self._desktop_ready():raise ValueError('Unlock Windows before enabling PC control.')
                readiness=self.activation_readiness()
                if not readiness['ready']:raise ValueError(readiness['message'])
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
            elif action in HEAD_SCROLL_ACTIONS:
                if not self.worker or not self.calibrated or self.profile['mode']!='head' or self.state not in ('active','practicing'):
                    raise ValueError('Calibrate Head & Face, then use Scroll in practice or active control.')
                if self.state=='active' and not self._desktop_ready():
                    self.pause('Unlock Windows before using head scrolling.','tracking_lost')
                    raise ValueError(self.message)
                if action=='head_scroll':
                    if not self.engine.head_scroll:
                        self._release_buttons(consume_dwell=True);self.engine.set_head_scroll(True)
                        if self.state=='active':self.last_point=self.input.get_physical_cursor_pos()
                    self.message='Head scroll: dwell on Up or Down. Done returns to pointing.'
                elif not self.engine.head_scroll:raise ValueError('Choose Scroll before scrolling or returning to pointing.')
                elif action=='scroll_done':
                    self.engine.set_head_scroll(False);self.message='Pointing restored. Move away before dwelling to click.'
                elif self.state=='active':
                    if time.monotonic()-self.last_frame>.25 or not self.display or not self.input.monitor_matches(self.display):
                        self.pause('Tracking or monitor changed. Resume when ready.','tracking_lost');raise ValueError(self.message)
                    actual=self.input.get_physical_cursor_pos()
                    if self.last_point is not None and math.dist(actual,self.last_point)>12:
                        self.pause('Physical mouse took over. Resume when ready.');raise ValueError(self.message)
                    self.input.scroll(0,2 if action=='scroll_up' else -2,scroll_speed=1,invert=False)
                elif action in ('scroll_up','scroll_down'):
                    self.practice.consume([{'kind':'scroll','dy':2 if action=='scroll_up' else -2}],self.engine.point or (.5,.5),time.monotonic())
            elif action in HEAD_ACTIONS:
                if not self.worker or not self.calibrated or self.profile['mode']!='head' or self.state not in ('active','practicing'):
                    raise ValueError('Calibrate Head & Face, then use its practice or active action dock.')
                dropping=self.engine.held and action=='dwell_drag'
                if self.engine.held:self._release_buttons(consume_dwell=True)
                selected='left_click' if dropping else HEAD_ACTIONS[action]
                self.engine.select_dwell(selected)
                self.message='Drag released. Dwell returns to Left click.' if dropping else 'Dwell action: '+('Drag — settle to hold, move, then settle to drop.' if action=='dwell_drag' else ACTION_LABELS[selected])
            elif action=='release_drag':
                self._release_buttons(consume_dwell=True)
                self.message='Drag released. Move away before dwelling to click again.'
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
            elif action in ('expression_sample','expression_bind'):
                if not self.worker or self.state!='practicing' or self.profile['mode']=='hand' or time.monotonic()-self.last_frame>.25:
                    raise ValueError('Use Head & Face or Combined practice with current face tracking.')
                gesture=data.get('gesture','smile')
                candidate=copy.deepcopy(self.profile)
                if action=='expression_bind':
                    target=data.get('action','left_click')
                    if gesture not in candidate['calibrated_expressions'] or target not in ('none','left_click','right_click','double_click','left_drag','dictate'):
                        raise ValueError('Capture the expression first, then choose a supported action.')
                    for key,value in candidate['bindings'].items():
                        if value==target and target!='none':candidate['bindings'][key]='none'
                    candidate['bindings'][gesture]=target
                    self.message='Expression action updated. Test it in practice before enabling PC control.'
                elif data.get('phase')=='neutral':
                    self.expression_baseline=measure(list(self.face_samples));self.expression_neutral=True
                    self.message='Relaxed face captured. Hold your selected expression for a second, then Capture expression.'
                elif data.get('phase')=='gesture':
                    if self.expression_baseline is None:raise ValueError('Capture your relaxed face first.')
                    limits=learn(self.expression_baseline,measure(list(self.face_samples)),gesture)
                    candidate['expression_thresholds'][gesture]=limits
                    candidate['calibrated_expressions']=sorted(set(candidate['calibrated_expressions'])|{gesture})
                    candidate['expressions_calibrated']=True;self.expression_seen.add(gesture)
                    self.message='Personal expression threshold captured. Choose its action and test it in practice.'
                else:raise ValueError('Choose neutral or gesture sampling.')
                self.profile=validate_profile(candidate)
                self.engine=GestureEngine(self.profile)
                if self.display:self.engine.profile['_monitor_scale']=(self.display['rect']['width'],self.display['rect']['height'])
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
        if not self._desktop_ready():raise ValueError('Unlock Windows before resuming PC control.')
        if not self.worker or not self.owns_input:raise ValueError('Enable PC control from practice first')
        if not self.display:raise ValueError('Monitor changed. Stop the camera and recalibrate for the available monitor.')
        if self.engine.lost or time.monotonic()-self.last_frame>.25:raise ValueError('Wait for stable tracking before resuming')
        if not self._stable():raise ValueError('Hold a steady tracked pose for a moment before resuming')
        self._release_buttons();self.engine.hud_blocked=True;self.state='active';self.message='AirControl resumed.'

    def calibrate(self,target,*,quick=False):
        if type(quick) is not bool or quick and (self.profile['mode']!='hand' or target!='center'):raise ValueError('Quick setup captures the hand center only')
        targets=('center',) if self.profile['mode']!='hand' else ('center','top_left','top_right','bottom_left','bottom_right')
        if target not in targets:raise ValueError('Choose a calibration target')
        sample_buffer=self.samples if self.profile['mode']=='hand' else self.face_samples
        if not self.worker or self.state not in ('calibrating','practicing') or len(sample_buffer)<5:raise ValueError('Wait for steady tracking before capturing a target')
        if time.monotonic()-self.last_frame>.25:raise ValueError('Tracking is not current')
        mode=self.profile['mode'];key='hand' if mode=='hand' else 'face'
        values=[s.get(key) for s in sample_buffer if s.get(key)]
        if len(values)<5:raise ValueError('Keep the required hand or face visible')
        candidate=copy.deepcopy(self.profile);points=copy.deepcopy(self.calibration_points)
        if mode=='hand':
            if max(statistics.pstdev([v[c] for v in values]) for c in ('x','y'))>.035:raise ValueError('Hold still briefly, then capture again')
            points[target]=[statistics.mean(v[c] for v in values) for c in ('x','y')]
            if quick:
                x,y=points['center'];left=min(.5,max(0.,x-.25));top=min(.6,max(0.,y-.2))
                points.update(top_left=[left,top],top_right=[left+.5,top],bottom_left=[left,top+.4],bottom_right=[left+.5,top+.4])
        else:
            if max(statistics.pstdev([v[c] for v in values]) for c in ('yaw','pitch'))>3:raise ValueError('Hold your head still briefly')
            points[target]=[statistics.mean(v[c] for v in values) for c in ('yaw','pitch')]
        if target=='center' and mode!='hand':candidate['calibration']['head_neutral']=points[target]
        if all(t in points for t in targets):
            if mode=='hand':
                corners=[points[t] for t in targets if t!='center']
                bounds=[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)]
                candidate['calibration']['hand_bounds']=bounds
            candidate=validate_profile(candidate)
            self.profile=candidate;self.calibration_points=points
            self.engine=GestureEngine(self.profile)
            if self.display:self.engine.profile['_monitor_scale']=(self.display['rect']['width'],self.display['rect']['height'])
            self.calibrated=True;self.state='practicing';self.message='Practice: move the simulated cursor and test a click. Nothing is sent to Windows.'
        else:self.calibration_points=points;self.message='Target captured. Move to the next comfortable position.'

    def observe(self,frame,*,now=None):
        now=time.monotonic() if now is None else now
        stamp=number(frame.get('timestamp'),-100)
        sequence=frame.get('seq')
        self.observations+=1;self.observation_age=now-stamp if stamp>=0 else None
        if type(sequence) is not int or sequence<=self.last_sequence or not 0<=now-stamp<=.25:
            self.rejected_observations+=1;return
        if self.last_frame and stamp-self.last_frame>.25:
            self.stable_since=None;self.stable_frames=0;self.samples.clear();self.face_samples.clear()
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
        if face and tracked(face) and face.get('count')==1:self.face_samples.append(self.frame)
        else:self.face_samples.clear()
        self.engine.hud_regions=(regions(self.display,active=self.state=='active',scrolling=self.engine.head_scroll)
            if self.owns_input and self.profile['mode']=='head' else
            practice_regions(getattr(self,'practice_viewport',(640,480)),scrolling=self.engine.head_scroll) if self.state=='practicing' else [])
        events=self.engine.step(frame,paused=self.state in ('paused','tracking_lost'))
        self.metrics.observe(at=now,tracked=not self.engine.lost,capture_fps=frame.get('capture_fps'),
            inference_ms=frame.get('inference_ms'),frame_age_ms=max(0,now-stamp)*1000)
        if self.engine.lost:
            self.practice.interrupt(now)
            self.stable_since=None;self.stable_frames=0;self.samples.clear();self.times.clear()
            if self.state=='active':self.pause('Tracking lost. Reacquire your pose, then Resume.','tracking_lost')
            return
        if self.stable_since is None:self.stable_since=now
        self.times.append(now)
        self.stable_frames+=1
        if self.state=='practicing':
            self.practice_frames+=1
            accepted=self.practice.accepted_clicks
            self.practice.consume(events,self.engine.point,now)
            clicks=[e for e in events if e['kind']=='button' and e['action']=='down' or
                e['kind']=='action' and e['action'] in ('left_click','right_click','double_click')]
            self.practice_actions+=len(clicks) if self.practice.name=='free' else self.practice.accepted_clicks-accepted
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
                elif event['kind']=='hud_action':
                    if not self.owns_input and event['action']=='scroll_done':self.engine.set_head_scroll(False)
                    elif not self.owns_input and event['action']=='pause':self.engine.reset(consume_dwell=True);self.practice.interrupt(now)
                    elif not self.owns_input and event['action']=='stop':asyncio.create_task(self.command('stop'))
                    elif self.owns_input and self.overlay:self.overlay.callback(event['action'])
            return
        try:
            if not self._desktop_ready():
                self.pause('Windows is locked or showing a secure desktop. Camera control is stopping.','tracking_lost');return
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
                if self.engine.head_scroll and kind not in ('scroll','hud_action'):continue
                if kind=='pointer':
                    self.last_point=physical_point(self.display['rect'],event['x'],event['y'])
                    self.input.set_physical_cursor_pos(*self.last_point)
                    self.metrics.record_latency((time.monotonic()-stamp)*1000)
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
                elif kind=='hud_action' and self.overlay:self.overlay.callback(event['action'])
        except Exception as error:
            self.last_error=type(error).__name__+': '+str(error)[:180]
            self.pause('Windows input is unavailable on this desktop. Resume in a normal signed-in session.','tracking_lost')

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
                if not self._desktop_ready():
                    self.metrics.mark_lost()
                    await self._stop();self.message='Windows is locked or showing a secure desktop. Camera stopped. Unlock, then choose Start camera.';return
                item=self.worker.latest()
                if item:
                    if item.get('type')=='observation':self.observe(item)
                    elif item.get('type')=='error':
                        self.metrics.mark_lost()
                        message=item.get('message','Camera unavailable');await self._stop();self.state='unavailable';self.message=message;return
                if not self.last_frame and time.monotonic()-self.started>25:
                    await self._stop();self.state='unavailable';self.message='No camera observations arrived. Check the selected camera and privacy permissions.';return
                self.watchdog()
                if self.state!='active' and self.native_down:self._release_buttons()
                if self.overlay:self.overlay.update(self.snapshot())
                await asyncio.sleep(.016)
        except asyncio.CancelledError:raise
        except Exception as error:
            self.last_error=type(error).__name__+': '+str(error)[:180]
            await self._stop();self.state='unavailable';self.message='Camera control stopped safely. '+self.last_error+' Restart practice to recover.'

    async def close(self):
        self._closing=True;self.setup.cancel()
        await self._stop()
        if self._voice_task:self._voice_task.cancel()
        if self.voice:await self.voice.close()
        if self.overlay:self.overlay.close()
