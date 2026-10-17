import unittest
from unittest.mock import Mock
from server.aircontrol.overlay import AirOverlay

class OverlayTests(unittest.TestCase):
    def test_paused_virtual_pointer_only_operates_resume_and_recenter(self):
        callback=Mock();overlay=AirOverlay(callback)
        display={'rect':{'x':-1920,'y':0,'width':1920,'height':1080}}
        # HUD is anchored 320 px from the selected monitor's right edge.
        def dwell(px,py):overlay.dwell(px/1919,py/1079,display)
        dwell(1600+40,930+95);callback.assert_called_once_with('resume')
        callback.reset_mock();dwell(1600+140,930+95);callback.assert_called_once_with('recenter')
        callback.reset_mock();dwell(1600+240,930+95);callback.assert_not_called()
