import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,Mock
from server.aircontrol.service import AirControlService
from server.aircontrol.profiles import default_profile

class AirServiceTests(unittest.IsolatedAsyncioTestCase):
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
            acquire=self.acquire,release=self.release)
    async def asyncTearDown(self):
        await self.service.close();self.folder.cleanup()

    async def test_start_opens_only_practice_and_never_acquires_input(self):
        await self.service.command('start',{'profile':default_profile()})
        self.assertEqual(self.service.snapshot()['state'],'calibrating')
        self.acquire.assert_not_awaited();self.input.mouse_down.assert_not_called()

    async def test_enable_requires_calibration_and_practice(self):
        await self.service.command('start',{'profile':default_profile()})
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
        await self.service.command('start',{'profile':default_profile()})
        self.service.calibrated=True;self.service.practice_frames=20;self.service.practice_actions=1
        self.service.engine.lost=False;self.service.last_frame=time.monotonic()
        self.service.stable_since=time.monotonic()-.3;self.service.stable_frames=8
        await self.service.command('enable')
        self.acquire.assert_awaited_once();self.assertTrue(self.service.owns_input)
        self.assertEqual(self.service.state,'active')

    async def test_combined_calibrates_neutral_head_without_unreachable_hand_targets(self):
        import time
        self.service.profile=default_profile(mode='combined');self.service.worker=self.worker
        self.service.state='calibrating';self.service.last_frame=time.monotonic()
        for _ in range(6):self.service.samples.append({'face':{'yaw':2.,'pitch':1.}})
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
        await self.service.command('stop')
        self.worker.stop.assert_called_once();self.release.assert_awaited_once()
        self.assertFalse(self.service.snapshot()['camera_active']);self.assertFalse(self.service.preview)

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
        profile=default_profile();profile['monitor_id']='removed'
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
