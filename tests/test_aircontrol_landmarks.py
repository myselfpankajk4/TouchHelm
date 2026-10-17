"""Synthetic Tasks results exercise landmark conversion without SDK/camera imports."""
from types import SimpleNamespace as Item
import unittest
from server.aircontrol.worker import hand_state,face_state

def hand(x=.3):
    points=[Item(x=x+i*.01,y=.5) for i in range(21)]
    points[4]=Item(x=points[8].x,y=points[8].y)
    return points

class LandmarkTests(unittest.TestCase):
    def test_handedness_uncertainty_does_not_mean_tracking_loss(self):
        from server.aircontrol.engine import GestureEngine
        from server.aircontrol.profiles import default_profile
        result=Item(hand_landmarks=[hand()],handedness=[[Item(category_name='Right',score=.53)]],
            gestures=[[Item(category_name='None',score=.57)]])
        state,_,_=hand_state(result,'auto',None)
        engine=GestureEngine(default_profile())
        events=engine.step({'timestamp':1,'hand':state})
        self.assertFalse(engine.lost)
        self.assertTrue(any(e['kind']=='pointer' for e in events))

    def test_weak_or_unknown_pose_is_not_accepted_as_a_supported_gesture(self):
        result=Item(hand_landmarks=[hand()],handedness=[[Item(category_name='Right',score=.99)]],
            gestures=[[Item(category_name='Open_Palm',score=.61)]])
        state,_,_=hand_state(result,'auto',None)
        self.assertEqual(state['pose'],'')

    def test_index_pinch_is_normalized_by_palm_and_keeps_native_landmarks(self):
        result=Item(hand_landmarks=[hand()],handedness=[[Item(category_name='Right',score=.99)]],
            gestures=[[Item(category_name='Pointing_Up',score=.9)]])
        state,center,points=hand_state(result,'right',None)
        self.assertEqual(state['pinch_index'],0);self.assertTrue(state['index_extended'])
        self.assertEqual(len(points),21);self.assertEqual(state['gesture_confidence'],.9)
        self.assertAlmostEqual(state['x'],.38)

    def test_same_hand_binding_does_not_jump_to_a_distant_person(self):
        result=Item(hand_landmarks=[hand(.7)],handedness=[[Item(category_name='Right',score=.99)]],gestures=[[]])
        state,center,points=hand_state(result,'auto',(.1,.5))
        self.assertIsNone(state);self.assertEqual(center,(.1,.5));self.assertEqual(points,[])

    def test_hand_preference_excludes_opposite_hand(self):
        result=Item(hand_landmarks=[hand()],handedness=[[Item(category_name='Left',score=.99)]],gestures=[[]])
        self.assertIsNone(hand_state(result,'right',None)[0])

    def test_ambiguous_faces_have_no_pose_or_expression_output(self):
        self.assertEqual(face_state(Item(face_landmarks=[[],[]])),(None,[]))

    def test_neutral_face_matrix_and_expression_scores_are_converted(self):
        class Matrix:
            def __getitem__(self,index):return 1 if index==(2,2) else 0
        result=Item(face_landmarks=[[Item(x=.5,y=.5) for _ in range(478)]],
            facial_transformation_matrixes=[Matrix()],face_blendshapes=[[Item(category_name='mouthSmileLeft',score=.8)]])
        state,points=face_state(result)
        self.assertEqual((state['yaw'],state['pitch']),(0,0))
        self.assertEqual(state['expressions']['mouthSmileLeft'],.8);self.assertEqual(len(points),12)

    def test_mirrored_face_keeps_winks_on_the_subjects_same_side(self):
        class Matrix:
            def __getitem__(self,index):return 1 if index==(2,2) else 0
        result=Item(face_landmarks=[[Item(x=.5,y=.5) for _ in range(478)]],
            facial_transformation_matrixes=[Matrix()],face_blendshapes=[[
                Item(category_name='eyeBlinkLeft',score=.9),Item(category_name='eyeBlinkRight',score=.1)]])
        state,_=face_state(result,mirrored=True)
        self.assertEqual(state['expressions']['eyeBlinkRight'],.9)
        self.assertEqual(state['expressions']['eyeBlinkLeft'],.1)

    def test_pinches_use_image_aspect_not_distorted_normalized_distances(self):
        points=hand();points[4]=Item(x=points[8].x,y=points[8].y+.03)
        result=Item(hand_landmarks=[points],handedness=[[Item(category_name='Right',score=.99)]],gestures=[[]])
        square=hand_state(result,'auto',None,image_size=(480,480))[0]
        wide=hand_state(result,'auto',None,image_size=(640,480))[0]
        self.assertAlmostEqual(wide['pinch_index'],square['pinch_index']*.75)
