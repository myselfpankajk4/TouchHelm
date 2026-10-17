import unittest
from server.aircontrol.expressions import levels,measure,learn,recognize
from server.aircontrol.profiles import default_profile,validate_profile

def face(smile=.1,left=.1,right=.1,brow=.1):
    return {'count':1,'expressions':{'mouthSmileLeft':smile,'mouthSmileRight':smile,
        'eyeBlinkLeft':left,'eyeBlinkRight':right,'browInnerUp':brow}}

class ExpressionTests(unittest.TestCase):
    def test_simultaneous_assigned_expressions_cancel_instead_of_picking_an_action(self):
        profile=default_profile(mode='head');profile.update(expressions_calibrated=True,calibrated_expressions=['smile','wink_left'])
        profile['bindings'].update(smile='left_click',wink_left='right_click')
        self.assertEqual(recognize(face(smile=.9,left=.9),profile,''),'conflict')
    def test_personal_smile_below_old_fixed_threshold_can_be_calibrated(self):
        neutral=levels(face());active=levels(face(smile=.45))
        threshold=learn(neutral,active,'smile')
        profile=default_profile(mode='head');profile.update(expressions_calibrated=True,calibrated_expressions=['smile'],expression_thresholds={'smile':threshold})
        profile['bindings']['smile']='left_click'
        profile=validate_profile(profile)
        self.assertEqual(recognize(face(smile=.4),profile,''),'smile')
        self.assertEqual(recognize(face(smile=.25),profile,'smile'),'smile')
        self.assertEqual(recognize(face(),profile,'smile'),'')

    def test_noise_or_bilateral_blink_cannot_be_learned_as_a_wink(self):
        neutral=levels(face())
        with self.assertRaises(ValueError):learn(neutral,levels(face(smile=.15)),'smile')
        with self.assertRaises(ValueError):learn(neutral,levels(face(left=.8,right=.8)),'wink_left')

    def test_measure_requires_a_stable_current_sequence_with_real_channels(self):
        frames=[{'timestamp':i/15,'face':face()} for i in range(8)]
        self.assertAlmostEqual(measure(frames)['smile'],.1)
        with self.assertRaises(ValueError):measure(frames[:3])
        with self.assertRaises(ValueError):measure([{'timestamp':i/15,'face':{'count':1,'expressions':{}}} for i in range(8)])

    def test_normal_blink_does_not_trigger_a_calibrated_wink(self):
        neutral=levels(face());threshold=learn(neutral,levels(face(left=.65)),'wink_left')
        profile=default_profile(mode='head');profile.update(expressions_calibrated=True,calibrated_expressions=['wink_left'],expression_thresholds={'wink_left':threshold})
        profile['bindings']['wink_left']='left_click'
        self.assertEqual(recognize(face(left=.9,right=.9),profile,''),'')

    def test_legacy_profiles_migrate_without_losing_calibrated_bindings(self):
        profile=default_profile();profile.pop('expression_thresholds',None)
        self.assertEqual(validate_profile(profile)['expression_thresholds'],{})
