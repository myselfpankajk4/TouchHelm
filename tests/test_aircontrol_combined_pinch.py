"""Combined mode: a pinch click must land where the pointer was when it began."""
import unittest
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile

def frame(t,yaw,pinch):
    return {'timestamp':t,'hand':{'tracked':True,'x':.5,'y':.5,'pinch_index':pinch,'pinch_middle':1.,'pose':''},
            'face':{'tracked':True,'count':1,'yaw':yaw,'pitch':0.,'expressions':{}}}

class CombinedPinchTests(unittest.TestCase):
    def engine(self,binding):
        profile=default_profile(mode='combined');profile['bindings']['pinch_index']=binding
        engine=GestureEngine(profile);engine.profile['_monitor_scale']=(1920,1080)
        for i in range(30):engine.step(frame(i/15,0.,1.))
        return engine

    def test_head_drift_during_a_pinch_click_does_not_move_the_target(self):
        e=self.engine('left_click');before=e.point;pointer_x=[]
        for i in range(30,45):
            events=e.step(frame(i/15,1.5*(i-30)/15,.1))
            pointer_x+=[x['x'] for x in events if x['kind']=='pointer']
        self.assertTrue(pointer_x)
        self.assertTrue(all(abs(x-before[0])*1920<1. for x in pointer_x))

    def test_pointer_resumes_from_the_click_point_after_release(self):
        e=self.engine('left_click');before=e.point
        for i in range(30,40):e.step(frame(i/15,.6,.1))
        for i in range(40,55):e.step(frame(i/15,.6,1.))
        # Head stayed 0.6 degrees off; the pointer may follow, but not jump.
        self.assertLess(abs(e.point[0]-before[0])*1920,40.)

    def test_drag_still_follows_the_head_after_it_starts(self):
        e=self.engine('left_drag');before=e.point;down=False
        for i in range(30,60):
            down|=any(x['kind']=='button' and x['action']=='down' for x in e.step(frame(i/15,3*(i-30)/15,.1)))
        self.assertTrue(down)
        self.assertGreater(abs(e.point[0]-before[0])*1920,30.)

if __name__=='__main__':unittest.main()
