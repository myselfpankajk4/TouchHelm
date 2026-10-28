"""Cursor accuracy at the moment of a click: pointer choice, anchor lookback and migration."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import aircontrol_accuracy_benchmark as bench
from server.aircontrol import engine as engine_module
from server.aircontrol.profiles import TUNING, default_profile, upgrade_profile, validate_profile
from server.aircontrol.worker import hand_state
from types import SimpleNamespace as Item

def state(points):
    result=Item(hand_landmarks=[points],handedness=[[Item(category_name='Right',score=.95)]],gestures=[[]])
    return hand_state(result,'auto',None)[0]

class PointerChoiceTests(unittest.TestCase):
    def test_pointer_is_the_knuckle_centre_not_a_pinching_fingertip(self):
        points=bench.landmarks(.5,.5,1.)
        expected=(sum(points[i].x for i in (5,9,13,17))/4,sum(points[i].y for i in (5,9,13,17))/4)
        s=state(points)
        self.assertAlmostEqual(s['x'],expected[0],places=9);self.assertAlmostEqual(s['y'],expected[1],places=9)

    def test_closing_a_pinch_does_not_move_the_pointer(self):
        open_hand=state(bench.landmarks(.5,.5,1.));closed=state(bench.landmarks(.5,.5,0.))
        self.assertEqual((open_hand['x'],open_hand['y']),(closed['x'],closed['y']))
        self.assertLess(closed['pinch_index'],.1);self.assertGreater(open_hand['pinch_index'],.8)

class ClickAccuracyTests(unittest.TestCase):
    def test_click_lands_within_a_small_target_where_the_fingertip_pointer_missed_it(self):
        for fps in (15,30):
            with self.subTest(fps=fps):
                old=[bench.pinch_click(pointer='fingertip',lookback=0.,fps=fps,seed=s) for s in range(1,7)]
                new=[bench.pinch_click(fps=fps,seed=s) for s in range(1,7)]
                self.assertGreater(min(old),40.)
                self.assertLess(max(new),14.)

    def test_click_while_the_hand_is_still_moving_lands_near_where_it_was_aimed(self):
        for fps in (15,30):
            with self.subTest(fps=fps):
                new=[bench.pinch_click(fps=fps,seed=s,velocity=(.12,0.)) for s in range(1,7)]
                self.assertLess(max(new),30.)

    def test_smile_click_is_pinned_before_the_face_pulls_the_head_pose(self):
        # Assumed pose shifts (degrees) while a smile builds; the real size varies per face.
        for shift in (3,6):
            with self.subTest(shift=shift):
                old=[bench.head_smile_click(lookback=0.,seed=s,pose_shift=shift) for s in range(1,7)]
                new=[bench.head_smile_click(seed=s,pose_shift=shift) for s in range(1,7)]
                self.assertGreater(min(old),20.)
                self.assertLess(max(new),30.)
                self.assertLess(sum(new),sum(old)/4)

    def test_lookback_never_reaches_further_back_than_it_is_configured(self):
        self.assertLessEqual(engine_module.HAND_LOOKBACK,.25)
        self.assertLessEqual(engine_module.HEAD_LOOKBACK,.35)

class MigrationTests(unittest.TestCase):
    def test_saved_hand_bounds_measured_on_a_fingertip_are_reset_once(self):
        profile=default_profile(mode='hand');profile['calibration']['hand_bounds']=[.3,.2,.8,.6]
        upgraded=validate_profile(upgrade_profile(profile,TUNING-1))
        self.assertEqual(upgraded['calibration']['hand_bounds'],default_profile()['calibration']['hand_bounds'])
        kept=validate_profile(upgrade_profile(profile,TUNING))
        self.assertEqual(kept['calibration']['hand_bounds'],[.3,.2,.8,.6])

if __name__=='__main__':unittest.main()
