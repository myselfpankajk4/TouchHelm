from collections import deque
import json
import unittest
from server.aircontrol.metrics import SessionMetrics


class MetricsTests(unittest.TestCase):
    def test_stopped_session_duration_does_not_keep_growing(self):
        m=SessionMetrics();m.reset(10.);m.stop(15.)
        self.assertEqual(m.snapshot(100.)['duration_seconds'],5.)
    def test_empty_windows_are_unknown_and_percentiles_use_real_finite_samples(self):
        m=SessionMetrics();m.reset(10.)
        self.assertIsNone(m.snapshot(10.)['median_latency_ms'])
        self.assertIsNone(m.snapshot(10.)['p95_latency_ms'])
        for n in range(1,101):m.record_latency(n)
        for n in (True,-1,float('nan'),float('inf')):m.record_latency(n)
        s=m.snapshot(11.)
        self.assertEqual(s['median_latency_ms'],50.5);self.assertEqual(s['p95_latency_ms'],95)
        self.assertEqual(s['latency_sample_count'],100)

    def test_shared_deque_stays_bounded_and_reset_preserves_its_identity(self):
        samples=deque(maxlen=600);m=SessionMetrics(samples)
        for n in range(601):m.record_latency(n)
        self.assertEqual(len(samples),600);self.assertEqual(samples[0],1)
        m.reset(1.);self.assertEqual(len(samples),0)

    def test_tracking_interruptions_are_transitions_not_lost_frame_counts(self):
        m=SessionMetrics();m.reset(0.)
        for at,tracked in [(0,False),(1,True),(2,False),(3,False),(4,True),(5,False)]:
            m.observe(at=at,tracked=tracked,capture_fps=15,inference_ms=10,frame_age_ms=20)
        self.assertEqual(m.snapshot(5.)['tracking_interruptions'],2)
        m.observe(at=4.,tracked=True,capture_fps=float('nan'))
        self.assertEqual(m.snapshot(5.)['capture_fps'],15)

    def test_report_allowlist_drops_hostile_and_nonfinite_data(self):
        m=SessionMetrics();m.reset(0.);m.record_latency(15.)
        record={'name':'click','elapsed_ms':200,'misses':1,'successes':3,
                'window_title':'private','landmarks':[[.1,.2]],'path':'C:/private'}
        report=m.report(at=2.,mode='head',display_size=[1920,1080],results=[record]*101,build_id='a'*32)
        self.assertEqual(set(report),{'version','build','mode','display_size','duration_seconds','metrics','exercises'})
        self.assertEqual(len(report['exercises']),100)
        self.assertEqual(set(report['exercises'][0]),{'name','elapsed_ms','misses','successes'})
        self.assertNotIn('private',json.dumps(report));json.dumps(report,allow_nan=False)
        report=m.report(at=2.,mode='head',display_size=[1920,1080],results=[],build_id='C:/private')
        self.assertEqual(report['build'],'')
