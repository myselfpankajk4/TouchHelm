"""Hardware readback regressions: all COM, WMI, DDC, keys and OSD mocked."""
import ctypes
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server import windows_input as native


class AudioReadbackTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(native.ole32,'CoInitialize',return_value=0),
                        patch.object(native.ole32,'CoUninitialize')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.audio = native.WindowsAudioController.__new__(native.WindowsAudioController)
        self.audio._cached_vol = 50
        self.audio._cached_mute = False

    def test_missing_endpoint_is_unknown_and_setters_never_fabricate_requested_state(self):
        with patch.object(self.audio,'_get_endpoint_volume',return_value=(None,None,None)):
            self.assertEqual(self.audio.get_volume_info(),(None,None))
            self.assertEqual(self.audio.set_volume(80),(None,None))
            self.assertEqual(self.audio.set_mute(True),(None,None))
            self.assertEqual(self.audio.toggle_mute(),(None,None))

    def test_failed_getter_hresult_does_not_use_zero_initialized_output(self):
        functions={9:Mock(return_value=-1),15:Mock(return_value=-1)}
        with patch.object(self.audio,'_get_endpoint_volume',return_value=(1,functions,Mock())), \
             patch.object(native.ctypes,'WINFUNCTYPE',side_effect=lambda *args:lambda function:function):
            self.assertEqual(self.audio.get_volume_info(),(None,None))

    def test_successful_getters_and_setter_use_actual_values(self):
        def level(endpoint,value):
            value._obj.value=.63
            return 0
        def muted(endpoint,value):
            value._obj.value=True
            return 0
        functions={7:Mock(return_value=0),14:Mock(return_value=0),9:level,15:muted}
        release=Mock()
        with patch.object(self.audio,'_get_endpoint_volume',return_value=(1,functions,release)), \
             patch.object(native.ctypes,'WINFUNCTYPE',side_effect=lambda *args:lambda function:function):
            self.assertEqual(self.audio.get_volume_info(),(63,True))
            self.assertEqual(self.audio.set_volume(80),(63,True))
        self.assertEqual(release.call_count,2)

    def test_failed_setter_does_not_return_requested_value(self):
        functions={7:Mock(return_value=-1),14:Mock(return_value=-1),9:Mock(return_value=-1),15:Mock(return_value=-1)}
        with patch.object(self.audio,'_get_endpoint_volume',return_value=(1,functions,Mock())), \
             patch.object(native.ctypes,'WINFUNCTYPE',side_effect=lambda *args:lambda function:function):
            self.assertEqual(self.audio.set_volume(80),(None,None))

    def test_relative_volume_unknown_does_not_guess_baseline(self):
        with patch.object(self.audio,'get_volume_info',return_value=(None,None)), \
             patch.object(self.audio,'set_volume') as setter:
            self.assertEqual(self.audio.change_volume(5),(None,None))
            setter.assert_not_called()


class BrightnessReadbackTests(unittest.TestCase):
    def setUp(self):
        with patch.object(native.threading,'Thread'), \
             patch.object(native.WindowsBrightnessController,'_query_initial_brightness'):
            self.brightness=native.WindowsBrightnessController()
        self.addCleanup(self.brightness.close)

    def test_unavailable_initial_and_pending_values_are_unknown(self):
        self.assertIsNone(self.brightness.get_brightness())
        self.assertIsNone(self.brightness.set_brightness(72))
        self.assertIsNone(self.brightness.get_brightness())
        self.assertEqual(self.brightness._target_level,72)

    def test_unknown_relative_brightness_does_not_enqueue_guessed_level(self):
        self.assertIsNone(self.brightness.change_brightness(-10))
        self.assertIsNone(self.brightness._target_level)

    def test_failed_refresh_clears_stale_observation(self):
        self.brightness._current_level=70
        with patch.object(native.subprocess,'run',return_value=SimpleNamespace(stdout='',returncode=1)), \
             patch.object(self.brightness,'_query_dxva2_brightness',return_value=None):
            self.assertIsNone(self.brightness.refresh_brightness())
        self.assertIsNone(self.brightness.get_brightness())

    def test_valid_zero_readback_is_known_and_channel_available(self):
        with patch.object(native.subprocess,'run',return_value=SimpleNamespace(stdout='0',returncode=0)):
            self.assertEqual(self.brightness.refresh_brightness(),0)
        self.assertEqual(self.brightness.get_brightness(),0)
        self.assertTrue(self.brightness.available)

    def test_worker_updates_only_measured_value_after_applying_target(self):
        self.brightness.set_brightness(72)
        def observed(expected_generation=None):
            with self.brightness._lock:
                self.brightness._current_level=69
            self.brightness._stopping.set()
            return 69
        with patch.object(native.subprocess,'run') as wmi, \
             patch.object(self.brightness,'_apply_dxva2_brightness') as ddc, \
             patch.object(self.brightness,'refresh_brightness',side_effect=observed) as refresh:
            self.brightness._apply_worker()
        refresh.assert_called_once()
        self.assertEqual(self.brightness.get_brightness(),69)
        self.assertIsNone(self.brightness._target_level)
        wmi.assert_called_once()
        ddc.assert_called_once_with(72)

    def test_obsolete_readback_cannot_publish_over_newer_brightness_request(self):
        self.brightness.set_brightness(72)
        generation=self.brightness._generation
        def delayed(*args,**kwargs):
            self.brightness.set_brightness(85)
            return SimpleNamespace(stdout='70',returncode=0)
        with patch.object(native.subprocess,'run',side_effect=delayed):
            self.assertIsNone(self.brightness.refresh_brightness(expected_generation=generation))
        self.assertIsNone(self.brightness.get_brightness())
        self.assertEqual(self.brightness._target_level,85)

    def test_completed_worker_emits_actual_indicator_callback(self):
        self.brightness.set_brightness(72)
        completed=Mock(side_effect=lambda _:self.brightness._stopping.set())
        self.brightness.on_readback=completed
        def observed(expected_generation=None):
            with self.brightness._lock:
                self.brightness._current_level=69
            return 69
        with patch.object(native.subprocess,'run'), \
             patch.object(self.brightness,'_apply_dxva2_brightness'), \
             patch.object(self.brightness,'refresh_brightness',side_effect=observed):
            self.brightness._apply_worker()
        completed.assert_called_once_with(69)


class ReadbackFacadeTests(unittest.TestCase):
    def test_unknown_readback_never_starts_indicator(self):
        controller=native.WindowsInputController.__new__(native.WindowsInputController)
        controller.audio_ctrl=Mock()
        controller.audio_ctrl.set_volume.return_value=(None,None)
        controller.audio_ctrl.set_mute.return_value=(None,None)
        controller.audio_ctrl.change_volume.return_value=(None,None)
        controller.brightness_ctrl=Mock()
        controller.brightness_ctrl.set_brightness.return_value=None
        controller.brightness_ctrl.change_brightness.return_value=None
        controller.osd=Mock()
        self.assertEqual(controller.set_volume(50),(None,None))
        self.assertEqual(controller.set_mute(True),(None,None))
        self.assertEqual(controller.change_volume(5),(None,None))
        self.assertIsNone(controller.set_brightness(60))
        self.assertIsNone(controller.change_brightness(-5))
        controller.osd.show.assert_not_called()
