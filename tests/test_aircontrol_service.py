import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,Mock
from server.aircontrol.service import AirControlService
from server.aircontrol.profiles import default_profile
from server.aircontrol.engine import GestureEngine

class AirServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_exercise_start_returns_ownership_and_viewport_revisions_are_guarded(self):
        self.service.worker=self.worker;self.service.calibrated=True;self.service.state='active';self.service.owns_input=True
        await self.service.command('practice_viewport',{'width':640,'height':480,'revision':1})
        await self.service.command('practice_start',{'name':'click'})
        self.assertEqual(self.service.state,'practicing');self.assertFalse(self.service.owns_input)
        self.release.assert_awaited_once()
        await self.service.command('practice_viewport',{'width':320,'height':240,'revision':2})
        await self.service.command('practice_viewport',{'width':640,'height':480,'revision':1})
        self.assertEqual(self.service.snapshot()['practice']['viewport'],[320,240])
        with self.assertRaises(ValueError):await self.service.command('practice_viewport',{'width':True,'height':240,'revision':3})

    async def test_real_head_dwell_scores_practice_target_without_native_effects(self):
        import time
        from test_aircontrol_head_actions import face
        s=self.service;s.profile=default_profile(mode='head');s.profile.update(smoothing=0,head_stability=0)
        s.engine=GestureEngine(s.profile);s.worker=self.worker;s.calibrated=True;s.state='practicing'
        await s.command('practice_start',{'name':'click'})
        start=time.monotonic()
        for i in range(12):
            frame=face(start+i*.1,yaw=-9);frame['seq']=i;s.observe(frame,now=frame['timestamp'])
        self.assertEqual(s.snapshot()['practice']['successes'],1)
        self.assertEqual(s.practice_actions,1)
        self.input.set_physical_cursor_pos.assert_not_called();self.input.click.assert_not_called()
        self.acquire.assert_not_awaited()
        await s.command('practice_pause');self.assertEqual(s.snapshot()['practice']['status'],'paused')
        await s.command('practice_resume');self.assertEqual(s.snapshot()['practice']['status'],'running')

    async def test_readiness_is_local_and_explains_camera_off(self):
        self.service.worker=None
        result=self.service.activation_readiness(now=10.)
        self.assertEqual(result['code'],'camera_off');self.assertFalse(result['ready'])
        self.acquire.assert_not_awaited();self.service.displays.assert_not_awaited()
        self.input.mouse_down.assert_not_called()

    async def test_readiness_matches_enable_and_repeated_enable_cannot_acquire_twice(self):
        import time
        self.service.worker=self.worker;self.service.state='practicing'
        self.service.calibrated=True;self.service.practice_frames=20;self.service.practice_actions=1
        self.service.engine.lost=False;self.service.last_frame=time.monotonic()
        self.service.stable_since=time.monotonic()-.3;self.service.stable_frames=8
        self.service.display={'id':'m','rect':{'x':-100,'y':0,'width':1000,'height':800}}
        self.assertTrue(self.service.activation_readiness()['ready'])
        await self.service.command('enable')
        self.assertEqual(self.service.activation_readiness()['code'],'already_active')
        with self.assertRaises(ValueError):await self.service.command('enable')
        self.acquire.assert_awaited_once()

    async def test_readiness_freshness_and_required_neutral_pose(self):
        self.service.worker=self.worker;self.service.state='practicing';self.service.calibrated=True
        self.service.practice_frames=20;self.service.practice_actions=1;self.service.engine.lost=False
        self.service.last_frame=10.;self.service.stable_since=9.;self.service.stable_frames=8
        self.service.display={'id':'m','rect':{'x':0,'y':0,'width':1000,'height':800}}
        self.assertEqual(self.service.activation_readiness(now=10.25)['code'],'ready')
        self.assertEqual(self.service.activation_readiness(now=10.251)['code'],'tracking_required')
        self.service.engine.held=True
        self.assertEqual(self.service.activation_readiness(now=10.2)['code'],'release_gesture')

    async def test_readiness_explains_each_remaining_setup_gate(self):
        s=self.service;s.worker=self.worker;s.state='practicing';s.last_frame=10.
        self.assertEqual(s.activation_readiness(now=10.)['code'],'calibration_required')
        s.calibrated=True
        self.assertEqual(s.activation_readiness(now=10.)['code'],'practice_required')
        s.practice_frames=20;s.practice_actions=1
        self.assertEqual(s.activation_readiness(now=10.)['code'],'tracking_required')
        s.engine.lost=False
        self.assertEqual(s.activation_readiness(now=10.)['code'],'steady_required')
        s.stable_since=9.;s.stable_frames=8
        self.assertEqual(s.activation_readiness(now=10.)['code'],'monitor_required')

    async def test_locked_desktop_cannot_start_camera(self):
        self.service.desktop_available=lambda:False
        with self.assertRaisesRegex(ValueError,'Unlock'):await self.service.command('start')
        self.worker.start.assert_not_called()

    async def test_lock_stops_camera_releases_input_and_reports_the_reason(self):
        self.service.desktop_available=lambda:False;self.service.worker=self.worker
        self.service.owns_input=True;self.service.native_down=True;self.service.state='active'
        await self.service._loop()
        self.assertFalse(self.service.owns_input);self.assertIsNone(self.service.worker)
        self.assertIn('locked',self.service.message.lower());self.input.mouse_up.assert_called_once_with('left')

    async def test_combined_can_calibrate_its_face_before_the_hand_enters_view(self):
        import time
        self.service.profile=default_profile(mode='combined');self.service.engine=GestureEngine(self.service.profile)
        self.service.worker=self.worker;self.service.state='calibrating'
        base=time.monotonic()-.24
        for i in range(8):
            stamp=base+i*.03
            self.service.observe({'timestamp':stamp,'seq':i,'face':{'tracked':True,'count':1,'yaw':0.,'pitch':0.}},now=stamp)
        self.service.calibrate('center')
        self.assertTrue(self.service.calibrated);self.assertFalse(self.service.owns_input)
    async def test_enable_does_not_replay_a_still_held_practice_pinch(self):
        import time
        self.service.worker=self.worker;self.service.state='practicing';self.service.calibrated=True;self.service.practice_frames=20;self.service.practice_actions=1
        self.service.last_frame=time.monotonic();self.service.stable_since=time.monotonic()-.3;self.service.stable_frames=8
        self.service.engine.lost=False;self.service.engine.held=True;self.service.engine.gesture='pinch_index'
        self.service.display={'id':'m','rect':{'x':-100,'y':0,'width':1000,'height':800}}
        with self.assertRaisesRegex(ValueError,'Release'):await self.service.command('enable')
        self.assertFalse(self.service.owns_input);self.acquire.assert_not_awaited()

    async def test_personal_expression_sample_is_guarded_and_keeps_input_off(self):
        import time
        from test_aircontrol_expressions import face
        self.service.profile=default_profile(mode='head');self.service.worker=self.worker
        self.service.state='practicing';self.service.last_frame=time.monotonic()
        def sample(smile):
            self.service.face_samples.clear();stamp=time.monotonic()
            for i in range(8):self.service.face_samples.append({'timestamp':stamp-(7-i)/15,'face':face(smile=smile)})
        sample(.1)
        await self.service.command('expression_sample',{'phase':'neutral'})
        sample(.45)
        result=await self.service.command('expression_sample',{'phase':'gesture','gesture':'smile'})
        self.assertIn('smile',result['aircontrol']['profile']['calibrated_expressions'])
        self.assertLess(self.service.profile['expression_thresholds']['smile']['on'],.45)
        self.assertFalse(self.service.owns_input);self.acquire.assert_not_awaited()

    async def test_quick_hand_calibration_enters_practice_without_input(self):
        import time
        self.service.worker=self.worker;self.service.state='calibrating';self.service.last_frame=time.monotonic()
        for _ in range(8):self.service.samples.append({'hand':{'x':.5,'y':.4}})
        self.service.calibrate('center',quick=True)
        self.assertTrue(self.service.calibrated);self.assertEqual(self.service.state,'practicing')
        self.assertFalse(self.service.owns_input);self.acquire.assert_not_awaited()
        for actual,expected in zip(self.service.profile['calibration']['hand_bounds'],[.25,.2,.75,.6]):self.assertAlmostEqual(actual,expected)

    async def test_invalid_fine_calibration_does_not_poison_the_profile(self):
        import time,copy
        self.service.worker=self.worker;self.service.state='calibrating';self.service.last_frame=time.monotonic()
        before=copy.deepcopy(self.service.profile)
        self.service.calibration_points={k:[.5,.5] for k in ('center','top_left','top_right','bottom_left')}
        for _ in range(8):self.service.samples.append({'hand':{'x':.51,'y':.51}})
        with self.assertRaises(ValueError):self.service.calibrate('bottom_right')
        self.assertEqual(self.service.profile,before)
        self.assertNotIn('bottom_right',self.service.calibration_points)

    async def test_camera_failure_preserves_reason_and_releases_control(self):
        self.service.worker=self.worker;self.service.owns_input=True
        self.service.state='active';self.service.native_down=True
        self.worker.latest.return_value={'type':'error','message':'The camera stopped delivering frames.'}
        await self.service._loop()
        self.assertEqual(self.service.state,'unavailable')
        self.assertIn('stopped delivering frames',self.service.message)
        self.assertFalse(self.service.owns_input);self.assertIsNone(self.service.worker)
        self.input.mouse_up.assert_called_once_with('left')
        self.release.assert_awaited_once()

    async def test_recenter_in_practice_does_not_enter_unresumable_pause(self):
        self.service.worker=self.worker;self.service.calibrated=True;self.service.state='practicing'
        await self.service.command('recenter')
        self.assertEqual(self.service.state,'practicing');self.assertFalse(self.service.owns_input)

    async def test_pause_pose_in_practice_does_not_satisfy_click_requirement(self):
        self.service.state='practicing'
        for i in range(25):
            t=1+i*.04
            self.service.observe({'timestamp':t,'seq':i,'hand':{'confidence':1,'x':.5,'y':.5,'pose':'Closed_Fist'}},now=t)
        self.assertEqual(self.service.practice_actions,0)

    async def test_sdk_tracked_hand_does_not_require_a_fabricated_confidence(self):
        self.service.state='practicing'
        self.service.observe({'timestamp':1,'seq':1,'hand':{'tracked':True,'x':.6,'y':.5,'handedness_score':.52}},now=1)
        self.assertFalse(self.service.engine.lost)
        self.assertEqual(self.service.practice_frames,1)

    async def test_snapshot_does_not_label_stale_observations_as_tracked(self):
        self.service.last_frame=1;self.service.engine.lost=False
        self.service.frame={'hand':{'tracked':True}}
        snapshot=self.service.snapshot()
        self.assertFalse(snapshot['tracking']);self.assertFalse(snapshot['tracking_sources']['hand'])

    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.input=Mock()
        self.input.get_physical_cursor_pos.return_value=(500,500)
        self.setup=Mock();self.setup.snapshot.return_value={'state':'ready','ready':True}
        self.worker=Mock();self.worker.latest.return_value=None
        self.acquire=AsyncMock();self.release=AsyncMock()
        self.service=AirControlService(self.input,AsyncMock(return_value={'displays':[{'id':'m','rect':{'x':-100,'y':0,'width':1000,'height':800}}]}),
            folder=Path(self.folder.name),setup=self.setup,worker_factory=lambda _:self.worker,
            acquire=self.acquire,release=self.release,desktop_available=lambda:True)
        self.service.profile=default_profile(mode='hand');self.service.engine=GestureEngine(self.service.profile)
    async def asyncTearDown(self):
        await self.service.close();self.folder.cleanup()

    async def test_start_opens_only_practice_and_never_acquires_input(self):
        await self.service.command('start',{'profile':default_profile(mode='hand')})
        self.assertEqual(self.service.snapshot()['state'],'calibrating')
        self.acquire.assert_not_awaited();self.input.mouse_down.assert_not_called()

    async def test_enable_requires_calibration_and_practice(self):
        await self.service.command('start',{'profile':default_profile(mode='hand')})
        with self.assertRaises(ValueError):await self.service.command('enable')
        self.acquire.assert_not_awaited()

    async def test_watchdog_releases_drag_and_pauses_active_input(self):
        self.service.state='active';self.service.owns_input=True;self.service.engine.held=True;self.service.native_down=True
        self.service.last_frame=1.;self.service.watchdog(now=1.251)
        self.input.mouse_up.assert_called_once_with('left')
        self.assertEqual(self.service.state,'tracking_lost')

    async def test_lost_observation_releases_a_real_drag_even_after_engine_reset(self):
        import time
        self.service.state='active';self.service.owns_input=True;self.service.engine.held=True;self.service.native_down=True
        self.service.observe({'timestamp':time.monotonic(),'seq':1})
        self.input.mouse_up.assert_called_once_with('left')

    async def test_simulated_practice_drag_never_releases_physical_mouse(self):
        self.service.engine.held=True;self.service._release_buttons()
        self.input.mouse_up.assert_not_called()

    async def test_enable_transfers_input_only_after_validated_practice(self):
        import time
        await self.service.command('start',{'profile':default_profile(mode='hand')})
        self.service.state='practicing';self.service.calibrated=True;self.service.practice_frames=20;self.service.practice_actions=1
        self.service.engine.lost=False;self.service.last_frame=time.monotonic()
        self.service.stable_since=time.monotonic()-.3;self.service.stable_frames=8
        await self.service.command('enable')
        self.acquire.assert_awaited_once();self.assertTrue(self.service.owns_input)
        self.assertEqual(self.service.state,'active')

    async def test_combined_calibrates_neutral_head_without_unreachable_hand_targets(self):
        import time
        self.service.profile=default_profile(mode='combined');self.service.worker=self.worker
        self.service.state='calibrating';self.service.last_frame=time.monotonic()
        for _ in range(6):self.service.face_samples.append({'face':{'yaw':2.,'pitch':1.}})
        self.service.calibrate('center')
        self.assertTrue(self.service.calibrated)
        self.assertEqual(self.service.profile['calibration']['head_neutral'],[2.,1.])

    async def test_stale_frames_cannot_move_pointer(self):
        self.service.state='active';self.service.owns_input=True
        self.service.observe({'timestamp':1,'seq':1,'hand':{'confidence':1,'x':.7,'y':.5}},now=1.3)
        self.input.set_physical_cursor_pos.assert_not_called()

    async def test_nonfinite_hand_coordinates_never_become_native_input(self):
        import time
        self.service.state='active';self.service.owns_input=True
        self.service.display={'id':'m','rect':{'x':0,'y':0,'width':1000,'height':800}}
        self.service.observe({'timestamp':time.monotonic(),'seq':1,'hand':{'confidence':1,'x':float('nan'),'y':.5}})
        self.input.set_physical_cursor_pos.assert_not_called()

    async def test_stop_clears_preview_and_returns_phone_ownership(self):
        self.service.worker=self.worker;self.service.preview='data';self.service.owns_input=True
        self.service.calibrated=True;self.service.practice_frames=20;self.service.practice_actions=1
        await self.service.command('stop')
        self.worker.stop.assert_called_once();self.release.assert_awaited_once()
        self.assertFalse(self.service.snapshot()['camera_active']);self.assertFalse(self.service.preview)
        self.assertFalse(self.service.snapshot()['calibrated']);self.assertFalse(self.service.snapshot()['practice_ready'])

    async def test_monitor_removal_pauses_and_requires_new_calibration(self):
        import time
        self.service.state='active';self.service.owns_input=True;self.service.worker=self.worker
        self.service.display={'id':'m','rect':{'x':-100,'y':0,'width':1000,'height':800}}
        self.input.monitor_matches.return_value=False
        self.service.observe({'timestamp':time.monotonic(),'seq':1,'hand':{'confidence':1,'x':.5,'y':.5}})
        self.assertEqual(self.service.state,'tracking_lost');self.assertIsNone(self.service.display)
        self.input.set_physical_cursor_pos.assert_not_called()
        with self.assertRaises(ValueError):self.service.resume()

    async def test_physical_mouse_takeover_pauses_before_next_pointer_event(self):
        import time
        self.service.state='active';self.service.owns_input=True
        self.service.display={'id':'m','rect':{'x':0,'y':0,'width':1000,'height':800}}
        self.service.last_point=(1,1)
        self.service.observe({'timestamp':time.monotonic(),'seq':1,'hand':{'confidence':1,'x':.5,'y':.5}})
        self.assertEqual(self.service.state,'paused')
        self.input.set_physical_cursor_pos.assert_not_called()

    async def test_single_reacquired_frame_cannot_resume_control(self):
        import time
        self.service.worker=self.worker;self.service.owns_input=True;self.service.state='paused'
        self.service.display={'id':'m','rect':{'x':0,'y':0,'width':1000,'height':800}}
        self.service.engine.lost=False;self.service.last_frame=time.monotonic()
        with self.assertRaises(ValueError):self.service.resume()

    async def test_pause_cancels_pending_gesture_dictation(self):
        self.service._voice_task=asyncio.create_task(asyncio.sleep(30))
        task=self.service._voice_task;self.service.pause()
        await asyncio.sleep(0)
        self.assertTrue(task.cancelled())

    async def test_reacquisition_after_a_gap_restarts_stability_even_when_paused(self):
        import time
        stamp=time.monotonic();self.service.state='paused';self.service.last_frame=stamp-2
        self.service.stable_since=stamp-3;self.service.stable_frames=50
        self.service.observe({'timestamp':stamp,'seq':1,'hand':{'confidence':1,'x':.5,'y':.5}})
        self.assertEqual(self.service.stable_frames,1);self.assertFalse(self.service._stable())

    async def test_return_to_practice_releases_ownership_without_stopping_camera(self):
        self.service.worker=self.worker;self.service.owns_input=True;self.service.calibrated=True
        await self.service.command('practice')
        self.assertEqual(self.service.state,'practicing');self.assertFalse(self.service.owns_input)
        self.release.assert_awaited_once();self.worker.stop.assert_not_called()

    async def test_missing_selected_monitor_does_not_silently_target_another_screen(self):
        profile=default_profile(mode='hand');profile['monitor_id']='removed'
        with self.assertRaises(ValueError):await self.service.command('start',{'profile':profile})
        self.worker.start.assert_not_called()

    async def test_slow_accessibility_check_cannot_hold_up_stop(self):
        self.service.voice=Mock(snapshot=Mock(return_value={}),close=AsyncMock())
        self.service.voice.dictate=AsyncMock(side_effect=lambda **_:asyncio.sleep(30))
        # A real coroutine body ensures cancellation can interrupt the request.
        async def slow(**kwargs):await asyncio.sleep(30)
        self.service.voice.dictate.side_effect=slow
        await asyncio.wait_for(self.service.command('dictate'),.2)
        task=self.service._voice_task
        await asyncio.wait_for(self.service.command('stop'),.2)
        await asyncio.sleep(0);self.assertTrue(task.cancelled())
