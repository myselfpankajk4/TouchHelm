"""Hand pointer steadiness: a held finger must not make the cursor shake."""
import math
import random
import statistics
import unittest
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile, validate_profile

SIZE=(1920,1080)

def hand(t,x,y,*,pinch=1.):
    return {'timestamp':t,'hand':{'tracked':True,'x':x,'y':y,'pinch_index':pinch,'pinch_middle':1.,'pose':''}}

def engine(**changes):
    profile=default_profile(mode='hand');profile.update(changes)
    result=GestureEngine(profile);result.profile['_monitor_scale']=SIZE
    return result

def held_finger(e,*,fps=12,sigma=.004,seconds=6,seed=3):
    random.seed(seed);points=[]
    for i in range(fps*seconds):
        t=i/fps
        e.step(hand(t,.5+random.gauss(0,sigma),.5+random.gauss(0,sigma)))
        if t>=2:points.append((e.point[0]*SIZE[0],e.point[1]*SIZE[1]))
    cx=statistics.mean(p[0] for p in points);cy=statistics.mean(p[1] for p in points)
    deviations=[math.hypot(p[0]-cx,p[1]-cy) for p in points]
    return math.sqrt(statistics.mean(d*d for d in deviations)),max(deviations)

class HandSteadinessTests(unittest.TestCase):
    def test_default_profile_holds_a_noisy_finger_inside_a_small_target(self):
        # Raw landmark noise of this size is about 15.5 px RMS on a 1080p screen
        # (2D, after the hand-bounds mapping). Average several seeds so one lucky
        # or unlucky random walk cannot decide the result.
        raw=.004*math.sqrt(2)/.7*SIZE[0]
        for fps in (10,15,30):
            with self.subTest(fps=fps):
                runs=[held_finger(engine(),fps=fps,seed=seed,seconds=14) for seed in range(1,9)]
                self.assertLess(statistics.mean(r for r,_ in runs),raw/3.)
                self.assertLess(max(p for _,p in runs),raw*.9)

    def test_quick_setup_range_is_not_shakier_than_the_default_range(self):
        # Quick setup maps only a 0.5 x 0.4 slice of the camera to the screen,
        # which magnifies landmark noise unless the filter compensates.
        def mean_rms(bounds):
            runs=[]
            for seed in range(1,9):
                e=engine();e.profile['calibration']['hand_bounds']=bounds
                runs.append(held_finger(e,fps=15,seed=seed,seconds=14)[0])
            return statistics.mean(runs)
        self.assertLess(mean_rms([.25,.3,.75,.7]),mean_rms([.15,.15,.85,.85])*1.6)

    def test_quick_setup_range_still_follows_deliberate_movement(self):
        e=engine();e.profile['calibration']['hand_bounds']=[.25,.3,.75,.7];fps=12
        for i in range(fps*2):e.step(hand(i/fps,.5,.5))
        start=e.point[0];reached=None
        for i in range(fps*2,fps*5):
            t=i/fps;e.step(hand(t,.6,.5))
            if reached is None and e.point[0]-start>=.9*.1/.5:reached=t-2
        self.assertIsNotNone(reached)
        self.assertLess(reached,.5)

    def test_deliberate_movement_still_follows_quickly(self):
        e=engine();fps=12
        for i in range(fps*2):e.step(hand(i/fps,.5,.5))
        start=e.point[0]
        reached=None
        for i in range(fps*2,fps*5):
            t=i/fps;e.step(hand(t,.65,.5))
            if reached is None and (e.point[0]-start)>=.9*(.65-.5)/.7:reached=t-2
        self.assertIsNotNone(reached)
        self.assertLess(reached,.5)

    def test_slow_drift_is_not_swallowed_by_the_hold(self):
        e=engine();fps=15
        for i in range(fps*2):e.step(hand(i/fps,.5,.5))
        before=e.point[0]
        for i in range(fps*2,fps*6):
            e.step(hand(i/fps,.5+(i/fps-2)*.04,.5))
        # 0.16 of the comfortable area moved; most of it must reach the screen.
        self.assertGreater((e.point[0]-before)*SIZE[0],.16/.7*SIZE[0]*.8)

    def test_hold_can_be_turned_off_without_disabling_filtering(self):
        steady=held_finger(engine(hand_stability=6.))[1]
        loose=held_finger(engine(hand_stability=0.))[1]
        self.assertGreater(loose,steady)

    def test_smoothing_off_is_raw_pointer(self):
        e=engine(smoothing=0)
        e.step(hand(0,.5,.5));e.step(hand(.1,.52,.5))
        raw=(.52-.15)/.7
        self.assertAlmostEqual(e.point[0],raw,places=6)

    def test_stability_is_validated_and_old_profiles_receive_the_default(self):
        profile=default_profile(mode='hand');del profile['hand_stability']
        self.assertEqual(validate_profile(profile)['hand_stability'],6.)
        for bad in (-1,17,float('nan'),'6'):
            profile=default_profile(mode='hand');profile['hand_stability']=bad
            with self.assertRaises(ValueError):validate_profile(profile)

    def test_pinch_release_does_not_jump_the_pointer(self):
        e=engine();fps=15
        for i in range(fps*2):e.step(hand(i/fps,.5,.5))
        for i in range(fps*2,fps*3):e.step(hand(i/fps,.5,.5,pinch=.1))
        held=e.point
        e.step(hand(3.0+1/fps,.5,.5))
        e.step(hand(3.0+2/fps,.5,.5))
        self.assertLess(math.hypot((e.point[0]-held[0])*SIZE[0],(e.point[1]-held[1])*SIZE[1]),2.)

if __name__=='__main__':unittest.main()
