import math
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock,Mock
from server.aircontrol.glide import CursorGlide
from server.aircontrol.service import AirControlService


class Clock:
    def __init__(self):self.now=100.
    def __call__(self):return self.now


def make(**options):
    clock=Clock();writes=[]
    glide=CursorGlide(lambda x,y:writes.append((x,y)),clock=clock,**options)
    return glide,clock,writes


def run_sweep(glide,clock,*,fps,speed,seconds,tick=.01):
    """Camera frames arrive every 1/fps; Windows is written every ``tick`` seconds."""
    positions=[];frame=0;next_frame=clock.now;end=clock.now+seconds;start=clock.now
    while clock.now<end:
        if clock.now>=next_frame-1e-9:
            glide.retarget((int(round(100+speed*(next_frame-start))),500));next_frame+=1/fps
        glide.tick();positions.append((clock.now-start,glide.last[0]))
        clock.now+=tick
    return positions


class CursorGlideTests(unittest.TestCase):
    def test_without_a_running_glide_every_point_is_written_immediately(self):
        glide,clock,writes=make()
        glide.retarget((10,20));glide.retarget((300,400))
        self.assertEqual(writes,[(10,20),(300,400)]);self.assertEqual(glide.last,(300,400))
        self.assertIsNone(glide.tick())

    def test_first_point_jumps_then_later_points_glide_in_small_steps(self):
        glide,clock,writes=make();glide.start(threaded=False)
        glide.retarget((100,100));self.assertEqual(writes,[(100,100)])
        clock.now+=.1;glide.retarget((200,100));self.assertEqual(writes,[(100,100)])
        for _ in range(10):
            clock.now+=.01;glide.tick()
        xs=[x for x,_ in writes]
        self.assertGreater(len(xs),6);self.assertEqual(xs,sorted(xs));self.assertEqual(xs[-1],200)
        self.assertTrue(all(b-a<=20 for a,b in zip(xs,xs[1:])))
        self.assertLessEqual(max(xs),200)
        glide.close()

    def test_no_overshoot_or_extrapolation_after_reaching_the_target(self):
        glide,clock,writes=make();glide.start(threaded=False)
        glide.retarget((0,0));clock.now+=.1;glide.retarget((50,-30))
        for _ in range(40):
            clock.now+=.01;glide.tick()
        self.assertEqual(glide.last,(50,-30));self.assertEqual(writes[-1],(50,-30))
        count=len(writes);clock.now+=1;self.assertIsNone(glide.tick());self.assertEqual(len(writes),count)

    def test_ninety_percent_step_response_stays_within_250_ms(self):
        for fps in (4,6,8,10,12,15,30):
            with self.subTest(fps=fps):
                glide,clock,writes=make();glide.start(threaded=False)
                period=1/fps
                for i in range(5):
                    glide.retarget((100,100));clock.now+=period
                glide.retarget((100,100));start=clock.now
                glide.retarget((1100,100));reached=None
                for _ in range(100):
                    clock.now+=.01;glide.tick()
                    if glide.last[0]>=1000 and reached is None:reached=clock.now-start
                self.assertIsNotNone(reached);self.assertLessEqual(reached,.25)
                glide.close()

    def test_steady_sweep_moves_evenly_instead_of_in_one_step_per_frame(self):
        glide,clock,writes=make();glide.start(threaded=False)
        positions=run_sweep(glide,clock,fps=10,speed=1000,seconds=2)
        steady=[x for t,x in positions if t>=.6]
        steps=[b-a for a,b in zip(steady,steady[1:])]
        self.assertGreater(min(steps),5);self.assertLessEqual(max(steps),14)
        self.assertGreaterEqual(len({x for x in steady}),len(steady)-2)
        engine_step=1000/10
        self.assertLess(max(steps),engine_step/5)

    def test_cursor_trails_a_steady_sweep_by_about_one_frame_interval(self):
        glide,clock,writes=make();glide.start(threaded=False)
        positions=run_sweep(glide,clock,fps=10,speed=1000,seconds=2)
        for t,x in positions:
            if t<.6:continue
            lag=(100+1000*t-x)/1000
            self.assertLess(lag,.19);self.assertGreater(lag,-.01)

    def test_halt_stops_writes_and_forgets_the_point(self):
        glide,clock,writes=make();glide.start(threaded=False)
        glide.retarget((0,0));clock.now+=.1;glide.retarget((100,0));clock.now+=.02;glide.tick()
        count=len(writes);glide.halt()
        clock.now+=1;self.assertIsNone(glide.tick());self.assertIsNone(glide.settle())
        self.assertEqual(len(writes),count);self.assertIsNone(glide.last)
        glide.retarget((500,500));self.assertEqual(writes[-1],(500,500))

    def test_settle_lands_on_the_engine_point_immediately(self):
        glide,clock,writes=make();glide.start(threaded=False)
        glide.retarget((0,0));clock.now+=.1;glide.retarget((100,40));clock.now+=.02;glide.tick()
        self.assertNotEqual(glide.last,(100,40))
        self.assertEqual(glide.settle(),(100,40));self.assertEqual(writes[-1],(100,40))
        clock.now+=1;self.assertIsNone(glide.tick())

    def test_retarget_mid_glide_continues_from_the_current_position(self):
        glide,clock,writes=make();glide.start(threaded=False)
        glide.retarget((0,0));clock.now+=.1;glide.retarget((100,0));clock.now+=.05;glide.tick()
        middle=glide.last[0];self.assertTrue(0<middle<100)
        glide.retarget((300,0));clock.now+=.01;glide.tick()
        self.assertGreaterEqual(glide.last[0],middle);self.assertLess(glide.last[0],200)

    def test_physical_mouse_movement_stops_the_glide_instead_of_fighting_it(self):
        glide,clock,writes=make(probe=lambda:(900,900))
        glide.start(threaded=False);glide.set_last((0,0))
        glide.retarget((100,0));clock.now+=.1;glide.retarget((200,0))
        count=len(writes);clock.now+=.05
        self.assertIsNone(glide.tick());self.assertTrue(glide.taken_over);self.assertEqual(len(writes),count)
        self.assertTrue(glide.diverged(12))
        glide.halt();self.assertFalse(glide.taken_over)

    def test_close_leaves_nothing_to_write(self):
        glide,clock,writes=make();glide.start(threaded=False)
        glide.retarget((0,0));clock.now+=.1;glide.retarget((100,0))
        glide.close();clock.now+=1
        self.assertIsNone(glide.tick());self.assertIsNone(glide.last);self.assertFalse(glide.running)


class CursorGlideThreadTests(unittest.TestCase):
    def test_thread_writes_intermediate_steps_and_stops_on_close(self):
        writes=[];glide=CursorGlide(lambda x,y:writes.append((x,y,time.monotonic())))
        glide.start();self.assertTrue(glide.running)
        glide.retarget((0,0));time.sleep(.1);glide.retarget((300,0));time.sleep(.3)
        self.assertEqual(glide.last,(300,0));self.assertGreater(len(writes),8)
        glide.close()
        count=len(writes);time.sleep(.1);self.assertEqual(len(writes),count)
        self.assertFalse([t for t in threading.enumerate() if t.name=='aircontrol-cursor-glide' and t.is_alive()])

    def test_halt_from_another_thread_means_no_write_after_it_returns(self):
        writes=[];glide=CursorGlide(lambda x,y:writes.append(time.monotonic()))
        glide.start();glide.retarget((0,0));time.sleep(.05);glide.retarget((2000,0));time.sleep(.04)
        glide.halt();stamp=time.monotonic();time.sleep(.15)
        self.assertFalse([t for t in writes if t>stamp]);glide.close()

    def test_write_failure_is_reported_and_stops_the_thread(self):
        def write(x,y):
            if x>0:raise RuntimeError('desktop locked')
        glide=CursorGlide(write);glide.start()
        glide.retarget((0,0));time.sleep(.05);glide.retarget((500,0));time.sleep(.3)
        self.assertIsInstance(glide.error,RuntimeError);glide.close()


class ServiceGlideTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.input=Mock();self.input.get_physical_cursor_pos.return_value=(0,0)
        self.service=AirControlService(self.input,AsyncMock(return_value={'displays':[]}),folder=Path(self.folder.name),desktop_available=lambda:True)
        s=self.service;s.worker=Mock();s.state='active';s.owns_input=True;s.calibrated=True
        s.display={'id':'m','rect':{'x':0,'y':0,'width':1000,'height':800}}
        self.clock=Clock();s.glide._clock=self.clock;s.glide.start(threaded=False)
        self.input.get_physical_cursor_pos.side_effect=lambda:s.glide.last or (0,0)
        self.events=[];s.engine.lost=False;s.engine.step=lambda frame,paused=False:list(self.events)
        self.seq=0;self.stamp=time.monotonic()

    async def asyncTearDown(self):
        await self.service.close();self.folder.cleanup()

    def frame(self):
        self.seq+=1;self.stamp+=.1;self.clock.now+=.1
        self.service.observe({'timestamp':self.stamp,'seq':self.seq,'hand':{'confidence':1,'x':.5,'y':.5}},now=self.stamp)

    def pointer(self,x,y):self.events[:]=[{'kind':'pointer','x':x,'y':y}]

    async def test_pointer_events_glide_instead_of_stepping(self):
        self.pointer(.1,.5);self.frame()
        self.input.set_physical_cursor_pos.assert_called_once_with(100,400)
        self.pointer(.5,.5);self.frame()
        self.assertEqual(self.input.set_physical_cursor_pos.call_count,1)
        self.service.glide.tick(self.clock.now+.05)
        self.assertEqual(self.input.set_physical_cursor_pos.call_count,2)
        x=self.input.set_physical_cursor_pos.call_args.args[0];self.assertTrue(100<x<500)
        self.assertEqual(self.service.state,'active')

    async def test_click_lands_on_the_engine_point_not_the_trailing_cursor(self):
        order=Mock();order.attach_mock(self.input.set_physical_cursor_pos,'move');order.attach_mock(self.input.mouse_down,'down')
        order.attach_mock(self.input.mouse_up,'up')
        self.pointer(.1,.5);self.frame()
        self.events[:]=[{'kind':'pointer','x':.5,'y':.5},{'kind':'button','action':'down','button':'left'}];self.frame()
        names=[c[0] for c in order.mock_calls];self.assertEqual(names[-2:],['move','down'])
        self.assertEqual(order.mock_calls[-2].args,(500,400));self.assertEqual(self.service.last_point,(500,400))
        self.assertTrue(self.service.native_down)
        self.events[:]=[{'kind':'pointer','x':.8,'y':.5},{'kind':'button','action':'up','button':'left'}];self.frame()
        names=[c[0] for c in order.mock_calls];self.assertEqual(names[-2:],['move','up'])
        self.assertEqual(order.mock_calls[-2].args,(799,400));self.assertFalse(self.service.native_down)

    async def test_drag_moves_while_held_and_drops_at_the_engine_point(self):
        self.pointer(.1,.5);self.frame()
        self.events[:]=[{'kind':'button','action':'down','button':'left'}];self.frame()
        self.pointer(.6,.5);self.frame()
        self.service.glide.tick(self.clock.now+.04)
        moved=self.input.set_physical_cursor_pos.call_args.args[0];self.assertTrue(100<moved<600)
        self.assertTrue(self.service.native_down);self.input.mouse_up.assert_not_called()

    async def test_action_click_is_sent_after_settling(self):
        calls=[]
        self.input.set_physical_cursor_pos.side_effect=lambda x,y:calls.append(('move',x,y))
        self.input.click.side_effect=lambda b:calls.append(('click',b))
        self.pointer(.1,.5);self.frame()
        self.events[:]=[{'kind':'pointer','x':.7,'y':.2},{'kind':'action','action':'left_click'}];self.frame()
        self.assertEqual(calls[-2:],[('move',699,160),('click','left')])

    async def test_pause_and_tracking_loss_stop_the_glide_at_once(self):
        self.pointer(.1,.5);self.frame();self.pointer(.9,.5);self.frame()
        count=self.input.set_physical_cursor_pos.call_count
        self.service.pause('Tracking lost.','tracking_lost')
        self.assertIsNone(self.service.last_point);self.assertIsNone(self.service.glide.tick(self.clock.now+1))
        self.assertEqual(self.input.set_physical_cursor_pos.call_count,count)

    async def test_stop_closes_the_glide(self):
        self.pointer(.1,.5);self.frame();self.pointer(.9,.5);self.frame()
        count=self.input.set_physical_cursor_pos.call_count
        await self.service.command('stop')
        self.assertFalse(self.service.glide.running);self.assertIsNone(self.service.glide.tick(self.clock.now+1))
        self.assertEqual(self.input.set_physical_cursor_pos.call_count,count)

    async def test_glide_takeover_and_write_failure_pause_through_the_loop_check(self):
        self.pointer(.1,.5);self.frame();self.pointer(.9,.5);self.frame()
        self.input.get_physical_cursor_pos.side_effect=lambda:(900,700)
        self.service.glide.tick(self.clock.now+.02)
        self.service._check_glide();self.assertEqual(self.service.state,'paused')
        self.assertIn('Physical mouse',self.service.message)
        self.service.state='active';self.service.glide.error=RuntimeError('boom')
        self.service._check_glide();self.assertEqual(self.service.state,'tracking_lost')
        self.assertIn('RuntimeError',self.service.last_error)

    async def test_physical_mouse_takeover_still_pauses_on_the_next_frame(self):
        self.pointer(.1,.5);self.frame()
        self.input.get_physical_cursor_pos.side_effect=lambda:(900,700)
        self.pointer(.2,.5);self.frame()
        self.assertEqual(self.service.state,'paused')

    async def test_real_loop_runs_a_thread_and_cleans_up(self):
        s=self.service;s.glide.close();s.glide._clock=time.monotonic
        s.worker=Mock();s.worker.latest.return_value=None;s.started=time.monotonic();s.last_frame=time.monotonic()
        import asyncio
        s.task=asyncio.create_task(s._loop());await asyncio.sleep(.1)
        self.assertTrue(s.glide.running)
        await s._stop()
        self.assertFalse(s.glide.running)
        self.assertFalse([t for t in threading.enumerate() if t.name=='aircontrol-cursor-glide' and t.is_alive()])


if __name__=='__main__':unittest.main()
