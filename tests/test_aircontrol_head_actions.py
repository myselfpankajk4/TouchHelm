"""Head-only actions; deterministic observations, no webcam or Windows input."""
import math
import tempfile
import unittest
from pathlib import Path
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile, validate_profile, ProfileStore


def face(t, yaw=0., pitch=0., smile=0.):
    return {'timestamp':t,'face':{'tracked':True,'count':1,'yaw':yaw,'pitch':pitch,
        'expressions':{'eyeBlinkLeft':0.,'eyeBlinkRight':0.,'mouthSmileLeft':smile,
            'mouthSmileRight':smile,'browInnerUp':0.}}}


class HeadActionsTests(unittest.TestCase):
    def engine(self,**settings):
        p=default_profile(mode='head');p.update(settings)
        return GestureEngine(p)

    def test_fresh_profiles_default_to_head_but_explicit_saved_hand_is_kept(self):
        self.assertEqual(default_profile()['mode'],'head')
        with tempfile.TemporaryDirectory() as folder:
            store=ProfileStore(Path(folder)/'profile.json')
            self.assertEqual(store.read()['mode'],'head')
            store.save(default_profile(mode='hand'))
            self.assertEqual(store.read()['mode'],'hand')

    def test_right_and_double_dwell_fire_once_then_return_to_left_click(self):
        for action in ('right_click','double_click'):
            e=self.engine();e.select_dwell(action)
            e.step(face(0))
            events=e.step(face(.95))
            self.assertEqual([x['action'] for x in events if x['kind']=='action'],[action])
            self.assertEqual(e.dwell_action,'left_click')
            self.assertFalse(any(x['kind']=='action' for x in e.step(face(2))))

    def test_dwell_drag_holds_while_moving_and_drops_once_after_settling(self):
        e=self.engine(smoothing=0,head_stability=0);e.select_dwell('drag')
        events=[]
        for t,yaw in [(0,0),(.95,0),(1.05,5),(1.2,5),(1.4,5),(2.35,5),(2.5,5)]:
            events+=e.step(face(t,yaw))
        self.assertEqual([x['action'] for x in events if x['kind']=='button'],['down','up'])
        self.assertFalse(e.held);self.assertEqual(e.dwell_action,'left_click')
        self.assertTrue(any(x['kind']=='pointer' and x['x']>.6 for x in events))

    def test_lost_face_releases_latched_drag_and_clears_selection(self):
        e=self.engine();e.select_dwell('drag');e.step(face(0));e.step(face(.95))
        self.assertTrue(e.held)
        self.assertEqual(e.step({'timestamp':1.05}),[{'kind':'button','action':'up','button':'left'}])
        self.assertEqual(e.dwell_action,'left_click')

    def test_calibrated_expression_can_hold_drag_and_release_without_dwell_click(self):
        p=default_profile(mode='head');p.update(expressions_calibrated=True,calibrated_expressions=['smile'])
        p['bindings']['pinch_index']='none';p['bindings']['smile']='left_drag'
        e=GestureEngine(validate_profile(p));events=[]
        for t,s in [(0,0),(.1,.9),(.55,.9),(.65,.9),(.8,0),(1.9,0)]:events+=e.step(face(t,smile=s))
        self.assertEqual([x['action'] for x in events if x['kind']=='button'],['down','up'])
        self.assertFalse(any(x['kind']=='action' for x in events))

    def test_head_hud_selection_is_not_injected_as_a_pc_click(self):
        e=self.engine();e.hud_regions=[{'action':'dwell_drag','rect':[.4,.4,.6,.6]}]
        e.step(face(0));events=e.step(face(.95))
        self.assertEqual([x['action'] for x in events if x['kind']=='hud_action'],['dwell_drag'])
        self.assertFalse(any(x['kind'] in ('button','action') for x in events))

    def test_pixel_stabilization_holds_tiny_jitter_but_tracks_deliberate_motion(self):
        for width,height in [(1920,1080),(3840,2160)]:
            e=self.engine(smoothing=0);e.profile['_monitor_scale']=(width,height)
            e.step(face(0));origin=e.point
            for i in range(1,12):e.step(face(i/10,yaw=math.sin(i)*3*36/width))
            self.assertEqual(e.point,origin)
            e.step(face(1.3,yaw=5))
            self.assertGreater((e.point[0]-origin[0])*width,100)

    def test_face_click_confirmation_keeps_pre_expression_target(self):
        p=default_profile(mode='head');p.update(smoothing=0,head_stability=0,expressions_calibrated=True,calibrated_expressions=['smile'])
        p['bindings']['smile']='left_click';e=GestureEngine(p)
        e.step(face(0));e.step(face(.1,yaw=.7,smile=.9));events=e.step(face(.55,yaw=1,smile=.9))
        self.assertAlmostEqual(e.point[0],.5)
        self.assertIn({'kind':'action','action':'left_click'},events)

    def test_deliberate_head_move_reaches_ninety_percent_within_quarter_second(self):
        for fps in (10,15,30):
            e=self.engine()
            for i in range(fps):e.step(face(i/fps))
            for i in range(1,int(fps*.25)+1):e.step(face(1+i/fps,yaw=5))
            self.assertGreaterEqual((e.point[0]-.5)/(5/36),.9,f'{fps} fps remains too sluggish')

    def test_explicit_dwell_selection_enables_session_dwell_without_changing_saved_profile(self):
        p=default_profile(mode='head');p.update(dwell=False,expressions_calibrated=True,calibrated_expressions=['smile'])
        p['bindings']['smile']='left_click';e=GestureEngine(p);e.select_dwell('right_click')
        e.step(face(0));events=e.step(face(1))
        self.assertIn({'kind':'action','action':'right_click'},events)
        self.assertFalse(p['dwell'])

    def test_stabilization_does_not_make_monitor_edges_unreachable(self):
        e=self.engine(smoothing=0)
        e.step(face(0))
        e.step(face(.1,yaw=40,pitch=-40))
        self.assertEqual(e.point,(1.,0.))

    def test_hud_action_cannot_repeat_after_pause_or_release_reset_until_pointer_leaves(self):
        e=self.engine(smoothing=0,head_stability=0);e.hud_regions=[{'action':'pause','rect':[.4,.4,.6,.6]}]
        e.step(face(0));self.assertIn({'kind':'hud_action','action':'pause'},e.step(face(1)))
        e.reset()
        e.step(face(1.1));events=e.step(face(2.2))
        self.assertFalse(any(x['kind']=='hud_action' for x in events))
        e.step(face(2.3,yaw=10));e.step(face(2.4));events=e.step(face(3.4))
        self.assertIn({'kind':'hud_action','action':'pause'},events)

    def test_expression_drag_release_consumes_dwell_at_the_drop_destination(self):
        p=default_profile(mode='head');p.update(smoothing=0,head_stability=0,expressions_calibrated=True,calibrated_expressions=['smile'])
        p['bindings']['pinch_index']='none';p['bindings']['smile']='left_drag';e=GestureEngine(p);events=[]
        for t,yaw,smile in [(0,0,0),(.1,0,.9),(.55,0,.9),(.65,8,.9),(.8,8,0),(1.1,8,0),(1.5,8,0),(2.5,8,0)]:
            events+=e.step(face(t,yaw,smile=smile))
        self.assertEqual([x['action'] for x in events if x['kind']=='button'],['down','up'])
        self.assertFalse(any(x['kind']=='action' for x in events),'Releasing a facial drag must not trigger another click at the destination')
