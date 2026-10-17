import unittest
from server.aircontrol.filters import OneEuro

class FilterTests(unittest.TestCase):
    def test_fresh_samples_reject_nonfinite_or_repeated_times(self):
        f=OneEuro();f.step(.5,0)
        with self.assertRaises(ValueError):f.step(.6,0)
        with self.assertRaises(ValueError):f.step(float('nan'),1)
    def test_reset_or_long_gap_does_not_replay_old_motion(self):
        f=OneEuro();f.step(.1,0)
        self.assertEqual(f.step(.8,1),.8)
        f.reset();self.assertEqual(f.step(.3,2),.3)
    def test_large_intentional_motion_does_not_take_many_frames(self):
        f=OneEuro(minimum=1.,beta=6.);f.step(.1,0)
        values=[f.step(.9,i/30) for i in range(1,5)]
        self.assertGreater(values[-1],.85)
