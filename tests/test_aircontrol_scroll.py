"""Head-scroll proposals use no camera, native input, or timer."""
import unittest
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile
from test_aircontrol_head_actions import face


class HeadScrollTests(unittest.TestCase):
    def engine(self):
        profile=default_profile(mode='head');profile.update(smoothing=0,head_stability=0)
        engine=GestureEngine(profile)
        engine.set_head_scroll(True)
        engine.hud_regions=[{'action':'scroll_up','rect':[.4,.4,.6,.6]},
                            {'action':'scroll_down','rect':[.7,.4,.9,.6]}]
        return engine

    def test_scroll_waits_for_dwell_and_repeats_at_most_every_150_ms(self):
        e=self.engine();events=[]
        for t in [0,.2,.4,.6,.8]:events+=e.step(face(t))
        self.assertFalse(events)
        self.assertEqual(e.step(face(.9)),[{'kind':'scroll','dy':2}])
        self.assertEqual(e.step(face(1.)),[])
        self.assertEqual(e.step(face(1.051)),[{'kind':'scroll','dy':2}])

    def test_departure_direction_change_and_long_gap_start_a_fresh_dwell(self):
        e=self.engine();e.step(face(0));e.step(face(.9))
        self.assertEqual(e.step(face(1.,yaw=-10)),[])
        self.assertEqual(e.step(face(1.1,yaw=10)),[])
        self.assertEqual(e.step(face(1.3,yaw=10)),[])
        for t in [1.5,1.7,1.9]:self.assertEqual(e.step(face(t,yaw=10)),[])
        self.assertEqual(e.step(face(2.01,yaw=10)),[{'kind':'scroll','dy':-2}])
        self.assertEqual(e.step(face(3.,yaw=10)),[])

    def test_loss_releases_mode_and_never_injects_click_or_pointer_while_scrolling(self):
        e=self.engine();e.held=True
        self.assertEqual(e.set_head_scroll(True),[{'kind':'button','action':'up','button':'left'}])
        events=[]
        for i in range(25):events+=e.step(face(i/10,smile=.9))
        self.assertTrue(all(x['kind']=='scroll' for x in events))
        e.step({'timestamp':3.});self.assertFalse(e.head_scroll)

    def test_hand_and_combined_cannot_enter_head_scroll(self):
        for mode in ('hand','combined'):
            with self.assertRaises(ValueError):GestureEngine(default_profile(mode=mode)).set_head_scroll(True)

    def test_held_expression_cannot_fire_on_exit_until_relaxed(self):
        e=self.engine();e.profile.update(expressions_calibrated=True,calibrated_expressions=['smile'])
        e.profile['bindings']['smile']='left_click';e.hud_regions=[]
        e.step(face(0,smile=.9));e.set_head_scroll(False)
        events=[]
        for t in [.1,.3,.5,.7,.9,1.1]:events+=e.step(face(t,smile=.9))
        self.assertFalse(any(x.get('action')=='left_click' for x in events))
        e.step(face(1.2));e.step(face(1.3,smile=.9))
        self.assertIn({'kind':'action','action':'left_click'},e.step(face(1.8,smile=.9)))
