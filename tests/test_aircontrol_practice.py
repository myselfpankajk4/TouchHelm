import unittest
from server.aircontrol.practice import PracticeSession


class PracticeTests(unittest.TestCase):
    def practice(self,name='click'):
        p=PracticeSession();p.set_viewport(640,480);p.start(name,0.);return p

    def test_click_targets_score_only_inside_and_finish_once(self):
        p=self.practice();click=[{'kind':'action','action':'left_click'}]
        p.consume(click,(.1,.1),.1);self.assertEqual(p.snapshot(.1)['misses'],1)
        for t,point in [(1.,(.25,.5)),(2.,(.75,.5)),(3.,(.5,.25))]:p.consume(click,point,t)
        self.assertEqual(p.snapshot(3.)['successes'],3)
        self.assertEqual(p.snapshot(3.)['status'],'complete')
        p.consume(click,(.5,.25),4.)
        self.assertEqual(len(p.snapshot(4.)['results']),1)

    def test_drag_must_start_inside_and_drop_inside_destination(self):
        p=self.practice('drag');down=[{'kind':'button','action':'down','button':'left'}]
        up=[{'kind':'button','action':'up','button':'left'}]
        p.consume(down,(.25,.5),1.);p.consume(up,(.5,.5),2.)
        self.assertEqual(p.snapshot(2.)['misses'],1)
        p.consume(down,(.25,.5),3.);p.consume(up,(.75,.5),4.)
        self.assertEqual(p.snapshot(4.)['status'],'complete')

    def test_short_stationary_hand_tap_completes_click(self):
        p=self.practice();p.consume([{'kind':'button','action':'down','button':'left'}],(.25,.5),.1)
        p.consume([{'kind':'button','action':'up','button':'left'}],(.25,.5),.3)
        self.assertEqual(p.snapshot(.3)['accepted_clicks'],1)

    def test_resize_revision_does_not_count_a_miss_and_stale_revision_is_ignored(self):
        p=self.practice('drag');p.consume([{'kind':'button','action':'down','button':'left'}],(.25,.5),.1)
        p.set_viewport(320,240,revision=1)
        p.set_viewport(640,480,revision=0)
        self.assertEqual(p.snapshot(.2)['viewport_revision'],1)
        p.consume([{'kind':'button','action':'up','button':'left'}],(.75,.5),.3)
        self.assertEqual(p.snapshot(.3)['misses'],0)
        with self.assertRaises(ValueError):p.set_viewport(400,300,revision=1)

    def test_pause_excludes_time_and_requires_explicit_resume(self):
        p=self.practice();p.interrupt(1.)
        p.consume([{'kind':'action','action':'left_click'}],(.25,.5),5.)
        self.assertEqual(p.snapshot(5.)['successes'],0)
        self.assertEqual(p.snapshot(5.)['elapsed_ms'],1000)
        p.resume(6.);self.assertEqual(p.snapshot(7.)['elapsed_ms'],2000)

    def test_scroll_uses_only_scroll_events_and_bounds_history(self):
        p=self.practice('scroll');p.consume([{'kind':'pointer','x':1,'y':1}],(1,1),.1)
        self.assertEqual(p.snapshot(.1)['document_position'],0)
        for i in range(10):p.consume([{'kind':'scroll','dy':-2}],(.5,.5),i+1.)
        self.assertEqual(p.snapshot(10.)['status'],'complete')
        for i in range(101):
            p.start('scroll',20.+i*2);p.consume([{'kind':'scroll','dy':-20}],(.5,.5),21.+i*2)
        self.assertEqual(len(p.snapshot(230.)['results']),100)

    def test_viewport_and_observations_reject_invalid_values(self):
        p=self.practice()
        for value in (True,159,8193,float('nan')):
            with self.assertRaises(ValueError):p.set_viewport(value,480,revision=1)
        with self.assertRaises(ValueError):p.start('shell',1.)
        p.consume([{'kind':'action','action':'left_click'}],(float('nan'),.5),1.)
        self.assertEqual(p.snapshot(1.)['successes'],0)
