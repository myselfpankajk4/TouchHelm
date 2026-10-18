"""Daily-use review regressions. Camera, storage and native input are mocked."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from server.aircontrol.engine import GestureEngine
from server.aircontrol.hud import regions
from server.aircontrol.profiles import default_profile
from server.aircontrol.service import AirControlService
from test_aircontrol_head_actions import face


class DailyUseReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.input=Mock()
        self.s=AirControlService(self.input,AsyncMock(),folder=Path(self.folder.name),
            acquire=AsyncMock(),release=AsyncMock(),desktop_available=lambda:True)
        self.s.profile=default_profile(mode='head')
        self.s.profile.update(smoothing=0,head_stability=0,expressions_calibrated=True,calibrated_expressions=['smile'])
        self.s.profile['bindings']['smile']='left_click';self.s.engine=GestureEngine(self.s.profile)
        self.s.worker=Mock();self.s.state='practicing';self.s.calibrated=True
        self.s.display={'id':'m','rect':{'x':0,'y':0,'width':1920,'height':1080}}
        self.s.displays.return_value={'displays':[self.s.display]};self.s.store.save=Mock()
        self.ready()

    def ready(self):
        self.s.engine.lost=False;self.s.last_frame=time.monotonic()
        self.s.stable_since=time.monotonic()-.4;self.s.stable_frames=8
        self.s.practice_frames=20;self.s.practice_actions=1

    def observe(self,t,yaw=0,pitch=0,smile=0):
        frame=face(t,yaw,pitch,smile);frame['seq']=self.s.last_sequence+1
        self.s.observe(frame,now=t)

    async def asyncTearDown(self):
        await self.s.close();self.folder.cleanup()

    async def test_scroll_and_conflict_require_neutral_before_enable(self):
        for gesture in ('conflict','smile'):
            self.s.engine.gesture=gesture
            self.assertEqual(self.s.activation_readiness()['code'],'release_gesture')
        self.s.engine.gesture=''
        await self.s.command('head_scroll')
        self.observe(time.monotonic(),smile=.9);self.ready()
        self.assertEqual(self.s.activation_readiness()['code'],'release_gesture')
        with self.assertRaises(ValueError):await self.s.command('enable')
        await self.s.command('scroll_done');self.ready()
        with self.assertRaises(ValueError):await self.s.command('enable')
        self.s.acquire.assert_not_awaited()
        self.observe(time.monotonic()+.01);self.ready()
        await self.s.command('enable');self.s.acquire.assert_awaited_once()

    async def test_pause_and_tracking_loss_preserve_expression_release_requirement(self):
        for interruption in ('pause','loss'):
            self.s.engine=GestureEngine(self.s.profile);self.s.state='active';self.s.owns_input=True
            self.s.engine.set_head_scroll(True)
            if interruption=='pause':self.s.pause()
            else:
                self.s.engine.step({'timestamp':1.});self.s.pause(state='tracking_lost')
            self.ready()
            with self.assertRaisesRegex(ValueError,'neutral|Release|Relax'):self.s.resume()
            self.observe(time.monotonic(),smile=.9);self.ready()
            with self.assertRaises(ValueError):self.s.resume()
            self.observe(time.monotonic()+.01);self.ready();self.s.resume()
            self.assertEqual(self.s.state,'active')

    async def test_enable_revalidates_after_display_await(self):
        for change in ('tracking','desktop','state','monitor'):
            self.s.state='practicing';self.s.desktop_available=lambda:True;self.ready()
            original=self.s.display
            async def displays():
                if change=='tracking':self.s.engine.lost=True;self.s.stable_since=None
                elif change=='desktop':self.s.desktop_available=lambda:False
                elif change=='state':self.s.pause()
                else:self.s.display=None
                return {'displays':[original]}
            self.s.displays.side_effect=displays
            with self.assertRaises(ValueError,msg=change):await self.s.command('enable')
            self.assertFalse(self.s.owns_input);self.s.acquire.assert_not_awaited()
            self.s.display=original

    async def test_enable_unwinds_if_tracking_changes_during_acquisition(self):
        async def acquire():
            self.s.engine.lost=True;self.s.stable_since=None
        self.s.acquire.side_effect=acquire
        with self.assertRaises(ValueError):await self.s.command('enable')
        self.assertFalse(self.s.owns_input);self.assertNotEqual(self.s.state,'active')
        self.s.release.assert_awaited_once()

    async def test_done_requires_departure_from_restored_hud(self):
        e=self.s.engine;e.set_head_scroll(True)
        scroll=regions(self.s.display,active=True,scrolling=True)
        target=next(r['rect'] for r in scroll if r['action']=='scroll_done')
        yaw=((target[0]+target[2])/2-.5)*36;pitch=((target[1]+target[3])/2-.5)*36
        e.hud_regions=scroll;events=[]
        for i in range(12):events+=e.step(face(i*.1,yaw,pitch))
        self.assertIn({'kind':'hud_action','action':'scroll_done'},events)
        e.set_head_scroll(False);e.hud_regions=regions(self.s.display,active=True)
        events=[]
        for i in range(12,36):events+=e.step(face(i*.1,yaw,pitch))
        self.assertFalse(any(x['kind']=='hud_action' for x in events))
        e.step(face(3.6));events=[]
        for i in range(37,50):events+=e.step(face(i*.1,yaw,pitch))
        self.assertIn({'kind':'hud_action','action':'head_scroll'},events)

    async def test_resume_restores_head_exercise_after_pause_or_tracking_loss(self):
        for name in ('drag','scroll'):
            for interruption in ('pause','loss'):
                await self.s.command('practice_start',{'name':name})
                if interruption=='pause':await self.s.command('practice_pause')
                else:
                    frame={'timestamp':time.monotonic(),'seq':self.s.last_sequence+1}
                    self.s.observe(frame,now=frame['timestamp'])
                self.assertEqual(self.s.practice.status,'paused')
                await self.s.command('practice_resume')
                self.assertEqual(self.s.practice.status,'running')
                self.assertEqual(self.s.engine.head_scroll,name=='scroll')
                self.assertEqual(self.s.engine.dwell_action,'drag' if name=='drag' else 'left_click')
                self.assertEqual(self.s.practice.misses,0)

    async def test_early_head_drag_drop_can_retry_without_new_task(self):
        await self.s.command('practice_start',{'name':'drag'})
        t=time.monotonic()+.1
        for yaw,count in [(-9,12),(0,16),(-9,16),(9,16)]:
            for _ in range(count):self.observe(t,yaw);t+=.1
        self.assertEqual(self.s.practice.misses,1)
        self.assertEqual(self.s.practice.status,'complete')
        self.input.mouse_down.assert_not_called();self.input.click.assert_not_called()

    async def test_resized_exercise_waits_for_resume_with_matching_viewport(self):
        await self.s.command('practice_viewport',{'width':640,'height':480,'revision':40})
        await self.s.command('practice_start',{'name':'drag'})
        await self.s.command('practice_viewport',{'width':320,'height':240,'revision':41})
        self.assertEqual(self.s.practice.status,'paused')
        with self.assertRaisesRegex(ValueError,'area'):
            await self.s.command('practice_resume',{'viewport_revision':40})
        self.assertEqual(self.s.practice.status,'paused')
        await self.s.command('practice_resume',{'viewport_revision':41})
        self.assertEqual(self.s.practice.status,'running')
        self.assertEqual(self.s.engine.dwell_action,'drag')
