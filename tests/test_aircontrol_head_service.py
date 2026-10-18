import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile
from server.aircontrol.service import AirControlService
from test_aircontrol_head_actions import face


class HeadServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.input=Mock();self.input.get_physical_cursor_pos.return_value=(500,400)
        self.service=AirControlService(self.input,AsyncMock(return_value={'displays':[]}),folder=Path(self.folder.name),desktop_available=lambda:True)
        self.service.profile=default_profile(mode='head');self.service.engine=GestureEngine(self.service.profile)
        self.service.worker=Mock();self.service.state='practicing';self.service.calibrated=True
        self.service.display={'id':'m','rect':{'x':0,'y':0,'width':1000,'height':800}}

    async def asyncTearDown(self):
        await self.service.close();self.folder.cleanup()

    def observe(self,t,yaw=0):
        frame=face(t,yaw);frame['seq']=int(t*1000);self.service.observe(frame,now=t)

    async def test_action_selection_in_practice_never_acquires_or_injects_input(self):
        await self.service.command('dwell_drag')
        self.observe(1);self.observe(2)
        self.assertTrue(self.service.engine.held);self.assertFalse(self.service.native_down)
        self.input.mouse_down.assert_not_called();self.assertEqual(self.service.practice_actions,1)

    async def test_head_drag_snapshot_and_explicit_release_match_native_button(self):
        await self.service.command('dwell_drag');self.service.state='active';self.service.owns_input=True
        self.service.input.get_physical_cursor_pos.side_effect=lambda:self.service.last_point or (500,400)
        self.observe(1);self.observe(2)
        self.input.mouse_down.assert_called_once_with('left')
        self.assertTrue(self.service.snapshot()['dragging'])
        await self.service.command('release_drag')
        self.input.mouse_up.assert_called_once_with('left')
        self.assertFalse(self.service.snapshot()['dragging'])

    async def test_floating_drop_action_releases_and_returns_to_left_click(self):
        self.service.engine.held=True;self.service.engine.drag_latched=True;self.service.native_down=True
        await self.service.command('dwell_drag')
        self.input.mouse_up.assert_called_once_with('left')
        self.assertEqual(self.service.engine.dwell_action,'left_click')

    async def test_explicit_release_does_not_dwell_click_again_until_departure(self):
        self.service.profile.update(smoothing=0,head_stability=0)
        self.service.engine=GestureEngine(self.service.profile)
        await self.service.command('dwell_drag')
        self.observe(1);self.observe(2)
        self.assertTrue(self.service.engine.held)
        await self.service.command('release_drag')
        actions=self.service.practice_actions
        self.observe(2.1);self.observe(3.2);self.observe(4.2)
        self.assertEqual(self.service.practice_actions,actions)
        self.observe(4.3,yaw=8);self.observe(4.6,yaw=8);self.observe(5.6,yaw=8)
        self.assertEqual(self.service.practice_actions,actions+1)

    async def test_explicit_release_requires_held_expression_to_relax_before_rearming(self):
        self.service.profile.update(expressions_calibrated=True,calibrated_expressions=['smile'])
        self.service.profile['bindings'].update(pinch_index='none',smile='left_drag')
        self.service.engine=GestureEngine(self.service.profile)
        def smile(t,value):
            frame=face(t,smile=value);frame['seq']=int(t*1000);self.service.observe(frame,now=t)
        smile(1,.9);smile(1.5,.9)
        self.assertTrue(self.service.engine.held)
        await self.service.command('release_drag')
        smile(1.6,.9);smile(2.2,.9)
        self.assertFalse(self.service.engine.held)
        smile(2.3,0);smile(2.4,.9);smile(3,.9)
        self.assertTrue(self.service.engine.held)

    async def test_action_selection_rejects_camera_off_and_hand_mode(self):
        self.service.worker=None
        with self.assertRaises(ValueError):await self.service.command('dwell_drag')
        self.service.worker=Mock();self.service.profile['mode']='hand'
        with self.assertRaises(ValueError):await self.service.command('dwell_drag')

    async def test_hud_dwell_routes_selection_without_a_native_click(self):
        from server.aircontrol.hud import regions
        region=next(r for r in regions(self.service.display,active=True) if r['action']=='dwell_right')
        x=(region['rect'][0]+region['rect'][2])/2;y=(region['rect'][1]+region['rect'][3])/2
        self.service.profile.update(smoothing=0,head_stability=0);self.service.engine=GestureEngine(self.service.profile)
        self.service.state='active';self.service.owns_input=True;self.service.overlay=Mock()
        self.service.input.get_physical_cursor_pos.side_effect=lambda:self.service.last_point or (500,400)
        for seq,t in enumerate([1,2]):
            frame=face(t,(x-.5)*36,(y-.5)*36);frame['seq']=seq;self.service.observe(frame,now=t)
        self.service.overlay.callback.assert_called_once_with('dwell_right')
        self.input.click.assert_not_called();self.input.mouse_down.assert_not_called()
