import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
from server.aircontrol.service import AirControlService
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile
from server.aircontrol.hud import layout,regions,practice_regions
from test_aircontrol_head_actions import face


class ScrollServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.input=Mock()
        self.input.get_physical_cursor_pos.return_value=(500,400)
        self.s=AirControlService(self.input,AsyncMock(return_value={'displays':[]}),
            folder=Path(self.folder.name),desktop_available=lambda:True)
        self.s.profile=default_profile(mode='head');self.s.profile.update(smoothing=0,head_stability=0)
        self.s.engine=GestureEngine(self.s.profile);self.s.worker=Mock()
        self.s.engine.lost=False;self.s.last_frame=time.monotonic()
        self.s.state='active';self.s.calibrated=True;self.s.owns_input=True
        self.s.display={'id':'m','rect':{'x':0,'y':0,'width':1000,'height':800}}

    async def asyncTearDown(self):
        await self.s.close();self.folder.cleanup()

    async def test_entry_releases_once_and_manual_scroll_never_points_or_clicks(self):
        self.s.engine.held=True;self.s.native_down=True
        await self.s.command('head_scroll');await self.s.command('head_scroll')
        self.input.mouse_up.assert_called_once_with('left')
        await self.s.command('scroll_up')
        self.input.scroll.assert_called_once_with(0,2,scroll_speed=1,invert=False)
        self.input.click.assert_not_called();self.input.set_physical_cursor_pos.assert_not_called()
        self.assertTrue(self.s.snapshot()['head_scroll'])
        await self.s.command('scroll_done');self.assertFalse(self.s.engine.head_scroll)
        with self.assertRaises(ValueError):await self.s.command('scroll_up')

    async def test_practice_scroll_never_calls_native_or_overlay(self):
        self.s.state='practicing';self.s.owns_input=False;self.s.overlay=Mock()
        await self.s.command('head_scroll');await self.s.command('scroll_down')
        self.input.scroll.assert_not_called();self.s.overlay.update.assert_not_called()
        self.s.overlay.callback.assert_not_called()

    async def test_mode_and_lifecycle_guards(self):
        for mode in ('hand','combined'):
            self.s.profile['mode']=mode
            with self.assertRaises(ValueError):await self.s.command('head_scroll')
        self.s.profile['mode']='head';self.s.state='paused'
        with self.assertRaises(ValueError):await self.s.command('head_scroll')
        self.s.state='active';self.s.calibrated=False
        with self.assertRaises(ValueError):await self.s.command('head_scroll')

    async def test_pause_stop_practice_and_loss_clear_scroll(self):
        for action in ('pause','stop','practice'):
            self.s.worker=Mock();self.s.state='active';self.s.calibrated=True;self.s.owns_input=True
            await self.s.command('head_scroll');await self.s.command(action)
            self.assertFalse(self.s.engine.head_scroll,action)
        self.s.worker=Mock();self.s.state='active';self.s.calibrated=True;self.s.owns_input=True
        await self.s.command('head_scroll');self.s.observe({'seq':1,'timestamp':1.},now=1.)
        self.assertEqual(self.s.state,'tracking_lost');self.assertFalse(self.s.engine.head_scroll)

    async def test_observed_scrolling_preserves_cursor_and_takeover_pauses(self):
        await self.s.command('head_scroll')
        target=next(r for r in regions(self.s.display,active=True,scrolling=True) if r['action']=='scroll_down')
        x=(target['rect'][0]+target['rect'][2])/2;y=(target['rect'][1]+target['rect'][3])/2
        for i in range(12):
            frame=face(1+i*.1,(x-.5)*36,(y-.5)*36);frame['seq']=i
            self.s.observe(frame,now=frame['timestamp'])
        self.assertTrue(self.input.scroll.called)
        self.input.set_physical_cursor_pos.assert_not_called()
        self.input.get_physical_cursor_pos.return_value=(800,400)
        frame=face(2.3);frame['seq']=20;self.s.observe(frame,now=2.3)
        self.assertEqual(self.s.state,'paused');self.assertFalse(self.s.engine.head_scroll)

    async def test_monitor_change_and_watchdog_cancel_scroll(self):
        await self.s.command('head_scroll');self.s.last_frame=1.;self.s.watchdog(now=1.251)
        self.assertFalse(self.s.engine.head_scroll)
        self.s.state='active';await self.s.command('head_scroll')
        self.input.monitor_matches.return_value=False
        frame=face(2.);frame['seq']=1;self.s.observe(frame,now=2.)
        self.assertFalse(self.s.engine.head_scroll);self.assertIsNone(self.s.display)

    def test_scroll_dock_shares_centers_and_fits_small_practice_stage(self):
        display={'rect':{'x':-1920,'y':-200,'width':1920,'height':1080}}
        spec=layout(display,active=True,head=True,scrolling=True)
        hit={r['action']:r['rect'] for r in regions(display,active=True,scrolling=True)}
        for t in spec['targets']:
            self.assertGreaterEqual(t['w'],44);self.assertGreaterEqual(t['h'],44)
            x=(spec['x']+t['x']+t['w']/2+1920)/1919
            y=(spec['y']+t['y']+t['h']/2+200)/1079
            r=hit[t['action']];self.assertTrue(r[0]<=x<=r[2] and r[1]<=y<=r[3])
        for r in practice_regions((160,160),scrolling=True):
            self.assertTrue(all(0<=v<=1 for v in r['rect']))
