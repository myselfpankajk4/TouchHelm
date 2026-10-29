"""Head & Face mode: a held head pose must stay put, and deliberate moves must still track.

Measured with synthetic Gaussian yaw/pitch noise (no camera). Thresholds are relative
to the raw mapped noise so they hold across the head_range and sensitivity settings.
"""
import math
import random
import json
import statistics
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server.aircontrol.engine import GestureEngine,VERTICAL_GAIN
from server.aircontrol.profiles import ProfileStore, default_profile

SIZE=(1920,1080)


def face(t,yaw=0.,pitch=0.,smile=0.):
    return {'timestamp':t,'face':{'tracked':True,'count':1,'yaw':yaw,'pitch':pitch,
        'expressions':{'eyeBlinkLeft':0.,'eyeBlinkRight':0.,'mouthSmileLeft':smile,
            'mouthSmileRight':smile,'browInnerUp':0.}}}


def engine(**changes):
    profile=default_profile(mode='head');profile.update(changes)
    e=GestureEngine(profile);e.profile['_monitor_scale']=SIZE
    return e


def held_pose(fps,seed,sigma=.3,seconds=14,**changes):
    e=engine(**changes);random.seed(seed);points=[]
    for i in range(fps*seconds):
        t=i/fps;e.step(face(t,random.gauss(0,sigma),random.gauss(0,sigma)))
        if t>=2:points.append((e.point[0]*SIZE[0],e.point[1]*SIZE[1]))
    cx=statistics.mean(p[0] for p in points);cy=statistics.mean(p[1] for p in points)
    distances=[math.hypot(p[0]-cx,p[1]-cy) for p in points]
    return math.sqrt(statistics.mean(d*d for d in distances)),max(distances)


class HeadSteadinessTests(unittest.TestCase):
    def measure(self,fps,sigma=.3,**changes):
        runs=[held_pose(fps,seed,sigma,**changes) for seed in range(1,9)]
        span=changes.get('head_range',18)*2/changes.get('sensitivity',1.)
        raw=sigma*math.sqrt(1+VERTICAL_GAIN**2)/span*SIZE[0]
        return statistics.mean(r for r,_ in runs)/raw,max(p for _,p in runs)/raw

    def test_held_pose_is_far_steadier_than_the_raw_pose(self):
        for fps in (10,15,30):
            rms,peak=self.measure(fps)
            self.assertLess(rms,.2,f'{fps} fps rms ratio')
            self.assertLess(peak,.5,f'{fps} fps peak ratio')

    def test_narrow_head_range_and_high_sensitivity_are_steadied_in_proportion(self):
        for changes in ({'head_range':9},{'sensitivity':2.},{'head_range':30}):
            for fps in (10,15):
                rms,peak=self.measure(fps,**changes)
                self.assertLess(rms,.2,f'{changes} {fps} fps rms ratio')
                self.assertLess(peak,.5,f'{changes} {fps} fps peak ratio')

    def test_deliberate_move_still_reaches_ninety_percent_within_a_quarter_second(self):
        for fps in (10,15,30):
            e=engine()
            for i in range(fps*2):e.step(face(i/fps))
            start=e.point[0]
            for i in range(1,int(fps*.25)+1):e.step(face(2+i/fps,yaw=5))
            self.assertGreaterEqual((e.point[0]-start)/(5/36),.9,f'{fps} fps')

    def test_slow_drift_is_followed_not_swallowed_by_the_hold(self):
        e=engine()
        for i in range(30):e.step(face(i/15))
        for i in range(30,105):
            t=i/15;e.step(face(t,.6*(t-2)))
        lag=(.5+.6*3/36-e.point[0])*SIZE[0]
        self.assertLess(lag,45.)

    def test_pointer_does_not_jump_when_an_expression_click_ends_after_head_drift(self):
        profile=dict(expressions_calibrated=True,calibrated_expressions=['smile'])
        e=engine(**profile);e.profile['bindings']['smile']='left_click'
        for i in range(30):e.step(face(i/15))
        for i in range(30,50):e.step(face(i/15,2.*(i-30)/20,smile=.95))
        before=e.point[0]*SIZE[0];xs=[before]
        for i in range(50,80):
            events=e.step(face(i/15,2.))
            xs+=[x['x']*SIZE[0] for x in events if x['kind']=='pointer']
        steps=[abs(b-a) for a,b in zip(xs,xs[1:])]
        self.assertLess(max(steps),25.,'release must glide, not jump')

    def test_default_hold_is_larger_than_the_old_four_pixels_and_inside_the_dwell_radius(self):
        profile=default_profile(mode='head')
        self.assertGreaterEqual(profile['head_stability'],8)
        self.assertLess(profile['head_stability'],profile['dwell_radius'])


class HeadEdgeReachTests(unittest.TestCase):
    """Screen edges, corners and the title-bar buttons must be reachable and holdable with less head travel."""
    def point_at(self,yaw,pitch,fps=15,sigma=0.):
        e=engine();rng=random.Random(3)
        for i in range(fps*4):e.step(face(i/fps,yaw+rng.gauss(0,sigma),pitch+rng.gauss(0,sigma)))
        return e.point[0],e.point[1]

    def test_middle_of_the_screen_is_unchanged(self):
        x,y=self.point_at(6.,0.)
        self.assertAlmostEqual(x,.5+6/36,delta=.005)
        self.assertAlmostEqual(y,.5,delta=.005)

    def test_edges_are_reached_with_less_rotation_than_the_old_linear_mapping(self):
        x,_=self.point_at(15.5,0.);_,y=self.point_at(0.,12.5)
        self.assertGreaterEqual(x,.995);self.assertGreaterEqual(y,.995)
        x,_=self.point_at(-15.5,0.);_,y=self.point_at(0.,-12.5)
        self.assertLessEqual(x,.005);self.assertLessEqual(y,.005)

    def test_corner_is_pinned_and_turning_further_changes_nothing(self):
        for yaw,pitch in ((15.5,12.5),(25.,20.),(40.,35.)):
            x,y=self.point_at(yaw,pitch);self.assertGreaterEqual(x,.999);self.assertGreaterEqual(y,.999)

    def test_mapping_is_continuous_monotonic_and_never_more_than_double_speed(self):
        engine_=engine();step=.002;previous=None
        for axis in (0,1):
            previous=None
            for i in range(-300,301):
                mapped,gain=engine_._reach(i*step,axis)
                self.assertLessEqual(abs(mapped),.5)
                if previous is not None:
                    self.assertGreaterEqual(mapped,previous[0]-1e-9,'monotonic')
                    self.assertLessEqual(abs(gain-previous[1]),.02,'gain has no jumps')
                    slope=(mapped-previous[0])/step
                    self.assertLessEqual(slope,(2.+.01)*(1.25 if axis else 1.),'speed is bounded')
                previous=(mapped,gain)

    def test_holding_near_an_edge_is_as_steady_as_holding_in_the_middle(self):
        for fps in (10,15):
            for yaw,pitch in ((12.,0.),(14.,0.),(0.,10.),(14.,11.5),(20.,20.)):
                runs=[]
                for seed in range(1,5):
                    e=engine();rng=random.Random(seed);points=[]
                    for i in range(fps*12):
                        t=i/fps;e.step(face(t,yaw+rng.gauss(0,.3),pitch+rng.gauss(0,.3)))
                        if t>=3:points.append((e.point[0]*SIZE[0],e.point[1]*SIZE[1]))
                    cx=statistics.mean(q[0] for q in points);cy=statistics.mean(q[1] for q in points)
                    distances=[math.hypot(q[0]-cx,q[1]-cy) for q in points]
                    runs.append((math.sqrt(statistics.mean(d*d for d in distances)),max(distances)))
                self.assertLess(statistics.mean(r for r,_ in runs),4.,f'{fps} fps {yaw},{pitch} rms')
                self.assertLess(max(p for _,p in runs),22.,f'{fps} fps {yaw},{pitch} peak')

    def test_deliberate_move_toward_an_edge_is_still_quick(self):
        fps=15;e=engine()
        for i in range(fps*2):e.step(face(i/fps,10.,0.))
        start=e.point[0]
        for i in range(1,int(fps*.25)+1):e.step(face(2+i/fps,15.,0.))
        self.assertGreaterEqual((e.point[0]-start)/(1.-start),.85)


def glitchy_pose(fps,seed,sigma,spike,seconds=14):
    """Held head whose tracking sometimes returns a wrong pose for a single frame."""
    r=random.Random(seed);e=engine();points=[]
    for i in range(fps*seconds):
        t=i/fps;yaw,pitch=r.gauss(0,sigma),r.gauss(0,sigma)
        if r.random()<spike:pitch+=r.choice((-1,1))*r.uniform(1.5,3.)
        if r.random()<spike:yaw+=r.choice((-1,1))*r.uniform(1.5,3.)
        e.step(face(t,yaw,pitch))
        if t>=2:points.append((e.point[0]*SIZE[0],e.point[1]*SIZE[1]))
    cx=statistics.mean(p[0] for p in points);cy=statistics.mean(p[1] for p in points)
    return math.sqrt(statistics.mean((p[0]-cx)**2+(p[1]-cy)**2 for p in points))


class HeadGlitchTests(unittest.TestCase):
    def test_single_frame_tracking_glitches_barely_move_the_cursor(self):
        for fps in (10,15,30):
            rms=statistics.mean(glitchy_pose(fps,seed,.3,.03) for seed in range(1,9))
            self.assertLess(rms,16.,f'{fps} fps rms px (about 30 px without glitch rejection)')

    def test_one_wrong_frame_is_dropped_and_the_cursor_does_not_flinch(self):
        for fps in (10,15,30):
            e=engine()
            for i in range(fps*2):e.step(face(i/fps))
            start=e.point[0]*SIZE[0];worst=0.
            for i in range(fps*2,fps*4):
                yaw=4. if i==fps*3 else 0.
                e.step(face(i/fps,yaw=yaw,pitch=-yaw/2))
                worst=max(worst,abs(e.point[0]*SIZE[0]-start))
            self.assertLess(worst,3.,f'{fps} fps')

    def test_noisier_tracking_is_held_within_the_widened_stillness_zone(self):
        for fps in (10,15,30):
            rms=statistics.mean(held_pose(fps,seed,sigma=.5)[0] for seed in range(1,9))
            self.assertLess(rms,8.5,f'{fps} fps rms px (about 9 px without the adaptive hold)')

    def test_widened_hold_stays_inside_the_dwell_radius(self):
        e=engine();e.jitter=500.
        widened=e._noisy_radius((.5,.5),SIZE,8.,1.,dwell_cap=22.)
        self.assertGreater(widened,8.)
        self.assertLess(widened,22.)
        self.assertEqual(e._noisy_radius((.5,.5),SIZE,0.,2.,dwell_cap=22.),0.,'a zero hold stays off')


class HeadSweepSmoothnessTests(unittest.TestCase):
    def sweep_steps(self,fps,speed):
        e=engine();xs=[]
        for i in range(fps*5):
            t=i/fps;yaw=-16. if t<2 else -16+speed*(t-2) if t<2+30/speed else 14.
            e.step(face(t,yaw));xs.append(e.point[0]*SIZE[0])
        steps=[b-a for a,b in zip(xs,xs[1:])]
        return steps[int(fps*2.4):max(int(fps*(2+30/speed-.2)),int(fps*2.4)+3)]

    def test_a_fast_continuous_sweep_moves_every_frame_instead_of_stopping_and_jumping(self):
        # Over 1.5 degrees per frame used to be judged a glitch every frame: hold, replay, hold...
        for fps,speed in ((10,20),(10,30),(15,30),(15,20),(30,30)):
            steps=self.sweep_steps(fps,speed)
            self.assertGreater(min(steps),.5*statistics.mean(steps),f'{fps} fps at {speed} deg/s stalls')
            self.assertLess(max(steps),1.5*statistics.mean(steps),f'{fps} fps at {speed} deg/s lurches')

    def test_a_glitch_in_the_middle_of_a_fast_sweep_is_still_rejected(self):
        e=engine();xs=[]
        for i in range(14):
            t=i/10;yaw=-16+20*t
            if i==8:yaw+=6.
            e.step(face(t,yaw));xs.append(e.point[0]*SIZE[0])
        steps=[b-a for a,b in zip(xs,xs[1:])][3:]
        self.assertLess(max(steps),2.2*statistics.median(steps),'the wrong frame must not throw the cursor ahead')


class SavedProfileMigrationTests(unittest.TestCase):
    def write(self,folder,data):
        path=Path(folder)/'profile.json';path.write_text(json.dumps(data),encoding='utf-8');return ProfileStore(path)

    def test_profile_saved_with_the_old_default_picks_up_the_new_hold(self):
        old=default_profile(mode='head');old['head_stability']=4.;old['smoothing']=.5
        with tempfile.TemporaryDirectory() as folder:
            store=self.write(folder,{'version':1,'active':'everyday','profiles':{'everyday':old}})
            profile=store.read()
            self.assertEqual(profile['head_stability'],8.)
            self.assertEqual(profile['smoothing'],.5,'other saved choices are kept')

    def test_legacy_single_profile_file_is_upgraded_too(self):
        old=default_profile(mode='head');old['head_stability']=4
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.write(folder,old).read()['head_stability'],8.)

    def test_a_choice_saved_after_the_upgrade_is_never_overridden(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ProfileStore(Path(folder)/'profile.json')
            profile=default_profile(mode='head');profile['head_stability']=4.
            with patch('server.private_storage.protect_user_path'):store.save(profile)
            self.assertEqual(ProfileStore(store.path).read()['head_stability'],4.)

    def test_other_old_values_are_not_touched(self):
        old=default_profile(mode='head');old['head_stability']=0.
        with tempfile.TemporaryDirectory() as folder:
            store=self.write(folder,{'version':1,'active':'everyday','profiles':{'everyday':old}})
            self.assertEqual(store.read()['head_stability'],0.)


if __name__=='__main__':unittest.main()
