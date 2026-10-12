"""Native controls tests: all keyboard, audio and helper effects are replaced."""
import importlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch, call

from server import windows_input as native


class NativeControlsTests(unittest.TestCase):
    def test_multiline_chat_text_uses_shift_enter_without_app_submit(self):
        ctrl=native.WindowsInputController.__new__(native.WindowsInputController)
        ctrl.type_unicode_char=Mock();ctrl.key_tap=Mock();ctrl.hotkey=Mock()
        ctrl.type_text('one\ntwo', newline_mode='shift_enter')
        ctrl.hotkey.assert_called_once_with('shift','enter')
        ctrl.key_tap.assert_not_called()
        self.assertEqual(ctrl.type_unicode_char.call_count,6)

    def setUp(self):
        self.ctrl = native.WindowsInputController.__new__(native.WindowsInputController)
        self.ctrl.ensure_input_desktop = Mock()
        self.ctrl.audio_ctrl = Mock()
        self.ctrl.brightness_ctrl = Mock()
        self.ctrl.osd = Mock()
        self.ctrl._closed = False
        self.keys = patch.object(native.user32, "keybd_event").start()
        self.addCleanup(patch.stopall)
        patch.object(native.time, "sleep").start()

    def test_volume_step_uses_native_key_and_reads_changed_state(self):
        self.ctrl.audio_ctrl.get_volume_info.side_effect = [(50, False), (50, False), (52, False)]
        self.assertEqual(self.ctrl.change_volume(2), (52, False))
        self.keys.assert_has_calls([call(0xAF, 0, 1, 0), call(0xAF, 0, 3, 0)])
        self.ctrl.audio_ctrl.change_volume.assert_not_called()
        self.ctrl.osd.show.assert_not_called()

    def test_volume_down_uses_native_key(self):
        self.ctrl.audio_ctrl.get_volume_info.side_effect = [(50, False), (48, False)]
        self.assertEqual(self.ctrl.change_volume(-2), (48, False))
        self.assertEqual(self.keys.call_args_list, [call(0xAE, 0, 1, 0), call(0xAE, 0, 3, 0)])

    def test_mute_uses_native_key_and_actual_state(self):
        self.ctrl.audio_ctrl.get_volume_info.side_effect = [(50, False), (50, True)]
        self.assertEqual(self.ctrl.toggle_mute(), (50, True))
        self.assertEqual(self.keys.call_args_list, [call(0xAD, 0, 1, 0), call(0xAD, 0, 3, 0)])
        self.ctrl.audio_ctrl.toggle_mute.assert_not_called()

    def test_unresponsive_native_volume_poll_has_fixed_bound(self):
        self.ctrl.audio_ctrl.get_volume_info.return_value = (100, False)
        self.assertEqual(self.ctrl.change_volume(2), (100, False))
        self.assertLessEqual(self.ctrl.audio_ctrl.get_volume_info.call_count, 8)

    def test_absolute_volume_indicator_uses_actual_returned_level(self):
        self.ctrl.audio_ctrl.set_volume.return_value = (63, True)
        self.assertEqual(self.ctrl.set_volume(64), (63, True))
        self.ctrl.osd.show.assert_called_once_with("volume", 63, muted=True)
        self.keys.assert_not_called()

    def test_arbitrary_volume_delta_retains_exact_com_semantics(self):
        self.ctrl.audio_ctrl.change_volume.return_value = (55, False)
        self.assertEqual(self.ctrl.change_volume(5), (55, False))
        self.ctrl.audio_ctrl.change_volume.assert_called_once_with(5)
        self.ctrl.osd.show.assert_called_once_with("volume", 55, muted=False)

    def test_brightness_indicators_use_clamped_controller_results(self):
        self.ctrl.brightness_ctrl.set_brightness.return_value = 100
        self.ctrl.brightness_ctrl.change_brightness.return_value = 95
        self.assertEqual(self.ctrl.set_brightness(150), 100)
        self.assertEqual(self.ctrl.change_brightness(-5), 95)
        self.assertEqual(self.ctrl.osd.show.call_args_list,
                         [call("brightness", 100), call("brightness", 95)])

    def test_oem_punctuation_has_physical_virtual_keys(self):
        for name, symbol, vk in [("semicolon", ";", 0xBA), ("equal", "=", 0xBB),
            ("comma", ",", 0xBC), ("minus", "-", 0xBD), ("period", ".", 0xBE),
            ("slash", "/", 0xBF), ("backquote", "`", 0xC0),
            ("bracketleft", "[", 0xDB), ("backslash", "\\", 0xDC),
            ("bracketright", "]", 0xDD), ("quote", "'", 0xDE)]:
            with self.subTest(name=name):
                self.assertEqual(self.ctrl._get_vk(name), vk)
                self.assertEqual(self.ctrl._get_vk(symbol), vk)

    def test_all_function_and_native_numpad_keys(self):
        for number in range(1, 25):
            self.assertEqual(self.ctrl._get_vk(f"f{number}"), 0x6F + number)
        for number in range(10):
            self.assertEqual(self.ctrl._get_vk(f"numpad{number}"), 0x60 + number)
        for name, vk in [("numpadmultiply", 0x6A), ("numpadadd", 0x6B),
            ("numpadsubtract", 0x6D), ("numpaddecimal", 0x6E), ("numpaddivide", 0x6F)]:
            self.assertEqual(self.ctrl._get_vk(name), vk)

    def test_side_modifiers_and_numpad_enter_have_correct_flags(self):
        for key, vk, flags in [("lshift", 0xA0, 0), ("rshift", 0xA1, 0),
            ("lctrl", 0xA2, 0), ("rctrl", 0xA3, 1), ("lalt", 0xA4, 0),
            ("ralt", 0xA5, 1), ("enter", 0x0D, 0), ("numpadenter", 0x0D, 1),
            ("numpaddivide", 0x6F, 1), ("numlock", 0x90, 1)]:
            with self.subTest(key=key):
                self.keys.reset_mock()
                self.ctrl.key_down(key)
                self.ctrl.key_up(key)
                self.assertEqual(self.keys.call_args_list,
                                 [call(vk, 0, flags, 0), call(vk, 0, flags | 2, 0)])

    def test_numpad_enter_identity_survives_hotkey_press_and_release(self):
        self.ctrl.hotkey("rctrl", "numpadenter")
        self.assertEqual(self.keys.call_args_list, [call(0xA3, 0, 1, 0),
            call(0x0D, 0, 1, 0), call(0x0D, 0, 3, 0), call(0xA3, 0, 3, 0)])

    def test_close_owns_helpers_and_is_idempotent(self):
        self.ctrl.close()
        self.ctrl.close()
        self.ctrl.osd.close.assert_called_once_with()
        self.ctrl.brightness_ctrl.close.assert_called_once_with()

    def test_controller_construction_cannot_start_indicator(self):
        with patch.object(native, "WindowsAudioController"), \
                patch.object(native, "WindowsBrightnessController"), \
                patch.object(native.WindowsInputController, "ensure_input_desktop"), \
                patch("server.osd_overlay.subprocess.Popen") as popen:
            controller = native.WindowsInputController()
            controller.close()
            popen.assert_not_called()

    def test_brightness_close_cancels_pending_native_work(self):
        with patch.object(native.WindowsBrightnessController, "_query_initial_brightness"), \
                patch.object(native.threading, "Thread") as thread, \
                patch.object(native.subprocess, "run") as run:
            brightness = native.WindowsBrightnessController()
            brightness.set_brightness(72)
            brightness.close()
            brightness._apply_worker()
            self.assertIsNone(brightness.set_brightness(50))
            self.assertIsNone(brightness.change_brightness(-10))
            thread.return_value.join.assert_called_once_with(timeout=3.5)
            run.assert_not_called()


class IndicatorOwnershipTests(unittest.TestCase):
    def test_native_child_creates_hidden_nonactivating_window_and_cleans_up(self):
        overlay = importlib.import_module("server.osd_overlay")
        api, gdi, kernel = Mock(), Mock(), Mock()
        api.CreateWindowExW.return_value = 123
        kernel.GetModuleHandleW.return_value = 1
        gdi.CreateSolidBrush.side_effect = [11, 12, 13]
        # EOF ends the helper immediately. Every DLL call and thread is mocked.
        def fake_thread(*, target, daemon):
            return SimpleNamespace(start=target)
        with patch.object(overlay.ctypes, "windll", SimpleNamespace(
                user32=api, gdi32=gdi, kernel32=kernel)), \
                patch.object(overlay.threading, "Thread", side_effect=fake_thread), \
                patch.object(overlay.sys, "stdin", io.StringIO("")):
            overlay._run_helper()
        arguments = api.CreateWindowExW.call_args.args
        self.assertEqual(arguments[0] & 0x08000000, 0x08000000)  # NOACTIVATE
        self.assertEqual(arguments[0] & 0x80, 0x80)  # TOOLWINDOW
        self.assertEqual(arguments[0] & 0x80000, 0x80000)  # LAYERED: cross-process click-through
        self.assertEqual(arguments[3] & 0x10000000, 0)  # no WS_VISIBLE
        api.ShowWindow.assert_not_called()
        api.SetLayeredWindowAttributes.assert_called_once_with(123, 0, 255, 2)
        api.DestroyWindow.assert_called_once_with(123)
        self.assertEqual(gdi.DeleteObject.call_args_list, [call(11), call(12), call(13)])

    def test_native_show_preserves_focus_on_first_and_subsequent_updates(self):
        overlay = importlib.import_module("server.osd_overlay")
        api = Mock()
        for _ in range(2):
            overlay._show_without_activation(api, 123, 40, 60, 300, 86)
        self.assertEqual(api.SetWindowPos.call_args_list,
                         [call(123, -1, 40, 60, 300, 86, 0x50)] * 2)
        self.assertEqual(api.ShowWindow.call_args_list, [call(123, 4)] * 2)
        api.SetForegroundWindow.assert_not_called()
        api.SetFocus.assert_not_called()

    def test_helper_starts_lazily_and_sends_json_without_console(self):
        overlay = importlib.import_module("server.osd_overlay")
        process = Mock()
        process.poll.return_value = None
        process.stdin = io.StringIO()
        with patch.object(overlay.subprocess, "Popen", return_value=process) as popen:
            indicator = overlay.OSDOverlay()
            popen.assert_not_called()
            indicator.show("volume", 73, muted=True)
            self.assertEqual(json.loads(process.stdin.getvalue()),
                             {"kind": "volume", "value": 73, "muted": True})
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000000)
            indicator.close()
            process.wait.assert_called_once()
            indicator.show("brightness", 30)
            self.assertEqual(popen.call_count, 1)

    def test_stuck_owned_helper_is_terminated_and_reaped(self):
        overlay = importlib.import_module("server.osd_overlay")
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [overlay.subprocess.TimeoutExpired("osd", .5), None]
        with patch.object(overlay.subprocess, "Popen", return_value=process):
            indicator = overlay.OSDOverlay()
            indicator.show("brightness", 30)
            indicator.close()
            process.terminate.assert_called_once()
            self.assertEqual(process.wait.call_count, 2)

    def test_failed_helper_launch_does_not_break_input_action(self):
        overlay = importlib.import_module("server.osd_overlay")
        with patch.object(overlay.subprocess, "Popen", side_effect=OSError("unavailable")):
            indicator = overlay.OSDOverlay()
            indicator.show("volume", 64)
            indicator.close()

    def test_helper_that_ignores_termination_is_killed_and_reaped(self):
        overlay = importlib.import_module("server.osd_overlay")
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [overlay.subprocess.TimeoutExpired("osd", .5),
                                   overlay.subprocess.TimeoutExpired("osd", .5), None]
        with patch.object(overlay.subprocess, "Popen", return_value=process):
            indicator = overlay.OSDOverlay()
            indicator.show("brightness", 30)
            indicator.close()
            process.kill.assert_called_once()
            self.assertEqual(process.wait.call_count, 3)


if __name__ == "__main__":
    unittest.main()
