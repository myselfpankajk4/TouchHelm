import unittest
from aircontrol_replay import run_replay
from server.aircontrol.engine import GestureEngine


class ReplayTests(unittest.TestCase):
    def test_stationary_motion_has_zero_jitter_and_one_dwell_action(self):
        r=run_replay(engine_factory=GestureEngine,fps=15,size=(1920,1080),scenario='stationary')
        self.assertEqual(r['jitter_rms_px'],0.)
        self.assertEqual(r['actions'],['left_click'])

    def test_loss_releases_drag_on_the_first_invalid_observation(self):
        r=run_replay(engine_factory=GestureEngine,fps=10,size=(1920,1080),scenario='loss')
        self.assertEqual(r['button_downs'],1);self.assertEqual(r['button_ups'],1)
        self.assertEqual(r['release_delay_samples'],0)

    def test_conflict_never_clicks_and_edges_remain_reachable(self):
        r=run_replay(engine_factory=GestureEngine,fps=15,size=(3840,2160),scenario='conflict')
        self.assertEqual(r['actions'],[]);self.assertEqual(r['button_downs'],0)
        edges=run_replay(engine_factory=GestureEngine,fps=15,size=(3840,2160),scenario='edges')
        self.assertTrue(edges['edges_reachable'])

    def test_step_response_is_measured_at_each_delivery_rate(self):
        for fps in (10,15,30):
            r=run_replay(engine_factory=GestureEngine,fps=fps,size=(1920,1080),scenario='step')
            self.assertIsNotNone(r['step_90_ms']);self.assertLessEqual(r['step_90_ms'],250)
