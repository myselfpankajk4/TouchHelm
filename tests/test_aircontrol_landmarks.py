"""Synthetic Tasks results exercise landmark conversion without SDK/camera imports."""
from types import SimpleNamespace as Item
import unittest
from server.aircontrol.worker import hand_state,face_state

def hand(x=.3):
    points=[Item(x=x+i*.01,y=.5) for i in range(21)]
    points[4]=Item(x=points[8].x,y=points[8].y)
    return points

class LandmarkTests(unittest.TestCase):
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
