"""Deterministic camera observations; no webcam or native input."""
import unittest
from server.aircontrol.engine import GestureEngine, physical_point
from server.aircontrol.profiles import default_profile, validate_profile

def observation(t, *, pose='Pointing_Up', pinch=1, middle=1, x=.5, y=.5, face=False):
    value={'timestamp':t,'hand':{'x':x,'y':y,'confidence':.95,'pose':pose,
        'pinch_index':pinch,'pinch_middle':middle,'index_extended':True},'hands_count':1}
    if face:value['face']={'yaw':0,'pitch':0,'confidence':.95,'count':1,'expressions':{}}
    return value

class GestureEngineTests(unittest.TestCase):
    def setUp(self):self.engine=GestureEngine(default_profile())

    def test_index_drag_does_not_raise_the_other_pinch_threshold(self):
        self.engine.step(observation(0,pinch=.15,middle=.33))
        self.engine.step(observation(.11,pinch=.15,middle=.33))
        events=self.engine.step(observation(.2,pinch=.2,middle=.33))
        self.assertTrue(self.engine.held)
        self.assertFalse(any(e.get('action')=='up' for e in events))

    def test_finger_curl_does_not_move_the_click_target_but_held_drag_moves(self):
        profile=default_profile();profile['smoothing']=0
        engine=GestureEngine(profile)
        engine.step(observation(0,x=.5))
        engine.step(observation(.1,x=.43,pinch=.15))
        self.assertAlmostEqual(engine.point[0],.5)
        events=engine.step(observation(.21,x=.42,pinch=.15))
        self.assertTrue(any(e.get('action')=='down' for e in events))
        self.assertAlmostEqual(engine.point[0],.5)
        engine.step(observation(.3,x=.49,pinch=.15))
        self.assertAlmostEqual(engine.point[0],.6)

    def test_unassigned_pose_does_not_freeze_pointer_movement(self):
        events=self.engine.step(observation(0,pose='Thumb_Up'))
        self.assertTrue(any(e['kind']=='pointer' for e in events))

    def test_head_dwell_tolerates_small_high_frequency_pose_jitter(self):
        for size in ((1920,1080),(3840,2160)):
            with self.subTest(display=size):
                self.engine=GestureEngine(default_profile(mode='head'));self.engine.profile['_monitor_scale']=size
                clicks=[]
                for i in range(40):
                    frame=observation(i/15,face=True)
                    frame['face']['yaw']=0 if i==0 else (.65 if i%2 else -.65)
                    clicks.extend(e for e in self.engine.step(frame) if e.get('action')=='left_click')
                self.assertEqual(len(clicks),1)

    def test_unassigned_smile_does_not_block_head_dwell(self):
        profile=default_profile(mode='head');profile['expressions_calibrated']=True;profile['calibrated_expressions']=['smile']
        self.engine=GestureEngine(profile)
        for i in range(2):
            frame=observation(i,face=True);frame['face']['expressions']={'mouthSmileLeft':.9,'mouthSmileRight':.9}
            events=self.engine.step(frame)
        self.assertTrue(any(e.get('action')=='left_click' for e in events))

    def test_expression_click_cannot_be_followed_by_a_duplicate_dwell_click(self):
        profile=default_profile(mode='head');profile['expressions_calibrated']=True;profile['calibrated_expressions']=['smile'];profile['bindings']['smile']='left_click'
        engine=GestureEngine(profile);actions=[]
        for t,smile in [(0,0),(.1,.9),(.6,.9),(.7,0),(1,0),(1.7,0),(2,0)]:
            frame=observation(t,face=True);frame['face']['expressions']={'mouthSmileLeft':smile,'mouthSmileRight':smile}
            actions.extend(e for e in engine.step(frame) if e.get('action')=='left_click')
        self.assertEqual(len(actions),1)

    def test_pinch_debounces_holds_drag_and_releases_once(self):
        self.engine.step(observation(0,pinch=.15))
        events=self.engine.step(observation(.11,pinch=.15))
        self.assertEqual([e['action'] for e in events if e['kind']=='button'],['down'])
        self.assertFalse(any(e['kind']=='button' for e in self.engine.step(observation(.2,pinch=.15,x=.7))))
        events=self.engine.step(observation(.3,pinch=.8))
        self.assertEqual([e['action'] for e in events if e['kind']=='button'],['up'])

    def test_real_pinch_can_click_with_a_curled_index_finger(self):
        first=observation(0,pinch=.1);first['hand']['index_extended']=False
        second=observation(.11,pinch=.1);second['hand']['index_extended']=False
        self.engine.step(first)
        self.assertTrue(any(e.get('action')=='down' for e in self.engine.step(second)))

    def test_geometric_pinch_is_not_hidden_by_open_palm_classifier_label(self):
        self.engine.step(observation(0,pose='Open_Palm',pinch=.1))
        events=self.engine.step(observation(.11,pose='Open_Palm',pinch=.1))
        self.assertTrue(any(e.get('action')=='down' for e in events))

    def test_open_palm_steers_normally_and_only_resumes_while_paused(self):
        events=self.engine.step(observation(0,pose='Open_Palm'))
        self.assertTrue(any(e['kind']=='pointer' for e in events))
        self.engine.step(observation(.1,pose='Open_Palm'),paused=True)
        events=self.engine.step(observation(.91,pose='Open_Palm'),paused=True)
        self.assertTrue(any(e.get('action')=='resume' for e in events))

    def test_conflicting_pinches_cannot_click(self):
        self.engine.step(observation(0,pinch=.1,middle=.1))
        events=self.engine.step(observation(.2,pinch=.1,middle=.1))
        self.assertFalse(any(e['kind'] in ('button','action') for e in events))

    def test_loss_releases_owned_button(self):
        self.engine.step(observation(0,pinch=.1));self.engine.step(observation(.11,pinch=.1))
        events=self.engine.step({'timestamp':.2})
        self.assertIn({'kind':'button','action':'up','button':'left'},events)
        self.assertTrue(self.engine.lost)

    def test_scroll_lock_does_not_also_move_or_click(self):
        self.engine.step(observation(0,pose='Victory'))
        self.engine.step(observation(.21,pose='Victory'))
        events=self.engine.step(observation(.3,pose='Victory',y=.7))
        self.assertTrue(any(e['kind']=='scroll' for e in events))
        self.assertFalse(any(e['kind'] in ('pointer','button') for e in events))

    def test_fist_never_looks_like_a_pinch(self):
        self.engine.step(observation(0,pose='Closed_Fist',pinch=.1))
        events=self.engine.step(observation(.61,pose='Closed_Fist',pinch=.1))
        self.assertIn({'kind':'action','action':'pause'},events)
        self.assertFalse(any(e['kind']=='button' and e['action']=='down' for e in events))

    def test_head_dwell_fires_once_until_pointer_leaves(self):
        self.engine=GestureEngine(default_profile(mode='head'))
        self.engine.step(observation(0,face=True))
        events=self.engine.step(observation(.91,face=True))
        self.assertEqual([e['action'] for e in events if e['kind']=='action'],['left_click'])
        self.assertFalse(any(e['kind']=='action' for e in self.engine.step(observation(2,face=True))))

    def test_combined_requires_both_sources_and_does_not_use_hand_pointer(self):
        self.engine=GestureEngine(default_profile(mode='combined'))
        events=self.engine.step(observation(0,x=.9,face=True))
        point=next(e for e in events if e['kind']=='pointer')
        self.assertAlmostEqual(point['x'],.5)
        self.assertFalse(any(e['kind']=='pointer' for e in self.engine.step(observation(.1))))

    def test_normal_blink_is_not_an_action(self):
        self.engine=GestureEngine(default_profile(mode='head'))
        frame=observation(0,face=True);frame['face']['expressions']={'eyeBlinkLeft':1,'eyeBlinkRight':1}
        self.assertFalse(any(e['kind']=='action' for e in self.engine.step(frame)))

    def test_coordinates_respect_negative_monitor_origin(self):
        rect={'x':-1920,'y':-200,'width':1920,'height':1080}
        self.assertEqual(physical_point(rect,0,0),(-1920,-200))
        self.assertEqual(physical_point(rect,1,1),(-1,879))

    def test_profiles_reject_unsafe_actions_and_missing_pause(self):
        for action in ('shell:format','left_drag'):
            profile=default_profile();profile['bindings']['closed_fist']=action
            with self.assertRaises(ValueError):validate_profile(profile)
        profile=default_profile();profile['bindings']['closed_fist']='none'
        with self.assertRaises(ValueError):validate_profile(profile)

    def test_reset_releases_drag_and_clears_dwell(self):
        self.engine.step(observation(0,pinch=.1));self.engine.step(observation(.11,pinch=.1))
        self.assertEqual(self.engine.reset(),[{'kind':'button','action':'up','button':'left'}])

    def test_conflict_requires_release_before_a_single_pinch_can_fire(self):
        self.engine.step(observation(0,pinch=.1,middle=.1))
        self.engine.step(observation(.2,pinch=.1,middle=.5))
        events=self.engine.step(observation(.4,pinch=.1,middle=.5))
        self.assertFalse(any(e['kind']=='button' for e in events))

    def test_scroll_cannot_turn_into_a_click_without_a_neutral_release(self):
        self.engine.step(observation(0,pose='Victory'))
        self.engine.step(observation(.21,pose='Victory'))
        self.engine.step(observation(.3,pinch=.1))
        events=self.engine.step(observation(.5,pinch=.1))
        self.assertFalse(any(e['kind'] in ('button','action') for e in events))
        self.engine.step(observation(.6))
        self.engine.step(observation(.7,pinch=.1))
        self.assertTrue(any(e.get('action')=='down' for e in self.engine.step(observation(.81,pinch=.1))))
