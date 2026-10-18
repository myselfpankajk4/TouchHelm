"""Desktop native bridge tests never create a webview, tray or real clipboard."""
import asyncio
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from server.config import ConfigManager

ROOT = Path(__file__).resolve().parents[1]


class WebViewShellTests(unittest.TestCase):
    def test_export_uses_running_host_build_instead_of_renderer_label(self):
        self.app.build_id='b'*32
        self.app._submit=Mock(return_value={'success':True,'report':{}})
        self.app.server.aircontrol.command=Mock(return_value=object())
        self.api.aircontrol(self.app.token,'export_report',{'build_id':'forged'})
        self.app.server.aircontrol.command.assert_called_once_with('export_report',{'build_id':'b'*32})

    def test_aircontrol_commands_and_frames_require_owned_desktop(self):
        self.app.window.get_current_url.return_value='https://attacker.invalid/'
        for method,args in ((self.api.aircontrol,('start',{})),(self.api.get_aircontrol_frame,())):
            with self.assertRaises(PermissionError):method(self.app.token,*args)
        self.app.server.aircontrol.command.assert_not_called()

    def test_wireless_install_and_password_commands_require_owned_desktop(self):
        self.app.wireless_display.install=Mock()
        self.app.window.get_current_url.return_value='https://attacker.invalid/'
        for method in (self.api.install_wireless_display,self.api.generate_password,self.api.prepare_trusted_pairing):
            with self.assertRaises(PermissionError):method(self.app.token)
        self.app.wireless_display.install.assert_not_called()

    def test_remote_enable_uses_generated_password_without_manual_pin_setup(self):
        result=self.api.save_settings(self.app.token,{'remote_enabled':True})
        self.assertTrue(result['success']);self.assertTrue(self.config.get('require_pin'))
        self.assertEqual(len(self.config.get('pin_code')),4)
        self.assertNotIn('pin_code',result['config'])

    def test_tailscale_commands_restricted_to_owned_desktop_window(self):
        self.assertTrue(hasattr(self.api,'request_tailscale'), 'Private Serve belongs to the native bridge')
        self.app.window.get_current_url.return_value='https://attacker.invalid/'
        for method,args in ((self.api.request_tailscale,(True,)),(self.api.refresh_tailscale,()),(self.api.open_tailscale_help,('windows',))):
            with self.assertRaises(PermissionError): method(self.app.token,*args)

    def setUp(self):
        self.module = importlib.import_module('gui.webview_window')
        self.folder = tempfile.TemporaryDirectory(dir=ROOT / 'tests')
        self.addCleanup(self.folder.cleanup)
        self.config = ConfigManager(str(Path(self.folder.name) / 'config.json'))
        self.app = self.module.WebViewDesktopApp(self.config, Mock(), None,
            primary_ip='192.168.1.12', build_id='build-a',
            preference_path=Path(self.folder.name) / 'preferences.json')
        self.app.owned_url = 'http://127.0.0.1:49123/desktop/secret/index.html'
        self.app.window = Mock()
        self.app.window.get_current_url.return_value = self.app.owned_url
        self.api = self.app.api

    def test_forged_token_cannot_mutate_settings_or_invoke_window(self):
        with self.assertRaises(PermissionError):
            self.api.save_settings('wrong', {'mouse_sensitivity': 2.5})
        with self.assertRaises(PermissionError):
            self.api.minimize('wrong')
        self.assertEqual(self.config.get('mouse_sensitivity'), 1.3)
        self.app.window.hide.assert_not_called()

    def test_bridge_refuses_external_or_other_local_pages_even_with_correct_token(self):
        for url in ('http://attacker.invalid/', 'http://127.0.0.1:49123/phone',
                    self.app.owned_url + '?redirect=evil'):
            self.app.window.get_current_url.return_value = url
            with self.assertRaises(PermissionError):
                self.api.get_state(self.app.token)

    def test_valid_settings_update_is_atomic_and_errors_are_returned(self):
        result = self.api.save_settings(self.app.token, {'scroll_speed': 1.8})
        self.assertTrue(result['success'])
        result = self.api.save_settings(self.app.token, {'scroll_speed': 1.2, 'mouse_sensitivity': 'fast'})
        self.assertFalse(result['success'])
        self.assertEqual(self.config.get('scroll_speed'), 1.8)

    def test_remote_bridge_cannot_inject_shell_commands_or_restart_port(self):
        for payload in ({'command': 'calc.exe'}, {'port': 9999}):
            self.assertFalse(self.api.save_settings(self.app.token, payload)['success'])

    def test_minimize_uses_taskbar_until_tray_is_ready(self):
        self.app.tray_icon = None
        self.api.minimize(self.app.token)
        self.app.window.minimize.assert_called_once_with()
        self.app.window.hide.assert_not_called()

    def test_phone_url_is_generated_internally_and_never_accepts_arbitrary_url(self):
        with patch.object(self.module.webbrowser, 'open') as opened:
            self.api.open_phone(self.app.token)
        self.assertTrue(opened.call_args.args[0].startswith('http://192.168.1.12:8765/'))

    def test_activity_log_is_bounded_and_client_values_are_copied(self):
        for number in range(1200): self.app.log_event(str(number))
        clients = [{'device': 'Phone', 'authenticated': False}]
        self.app.update_clients(clients)
        clients[0]['device'] = 'changed'
        state = self.api.get_state(self.app.token)
        self.assertEqual(len(state['activity']), 1000)
        self.assertEqual(state['devices'][0]['device'], 'Phone')

    def test_asset_resolver_cannot_expose_private_keys_or_traverse_files(self):
        server = self.module.DesktopAssetServer('secret')
        self.assertIsNone(server.resolve('/desktop/secret/../../server/windows_input.py'))
        self.assertIsNone(server.resolve('/desktop/secret/server.key'))
        self.assertIsNone(server.resolve('/desktop/wrong/index.html'))
        self.assertEqual(server.resolve('/desktop/secret/index.html'), ROOT / 'gui/web/index.html')
        self.assertEqual(server.resolve('/desktop/secret/aircontrol-view.js'), ROOT / 'gui/web/aircontrol-view.js')

    def test_desktop_preferences_use_shared_theme_values_and_persist(self):
        preferences = {'theme': 'ink', 'appearance': 'light', 'motion': 'reduced', 'contrast': 'increased'}
        with patch.object(self.module, 'protect_user_path'):
            result = self.api.save_preferences(self.app.token, preferences)
        self.assertTrue(result['success'])
        self.assertEqual(self.app._preferences(), preferences)

    def test_http_and_https_qr_codes_are_distinct_and_both_match_selected_addresses(self):
        self.app.server.https_site = object()
        pairing = self.app._pairing()
        self.assertIn('qr_http', pairing)
        self.assertIn('qr_https', pairing)
        self.assertNotEqual(pairing['qr_http'], pairing['qr_https'])

    def test_saved_settings_are_reported_truthfully_when_phone_sync_fails(self):
        self.app.server_loop = Mock()
        self.app.server_loop.is_closed.return_value = False
        self.app.server.broadcast = lambda message: asyncio.sleep(0)
        def unavailable(coroutine):
            coroutine.close()
            raise RuntimeError('Host stopped before phone notification')
        with patch.object(self.app, '_submit', side_effect=unavailable):
            result = self.api.save_settings(self.app.token, {'scroll_speed': 1.7})
        self.assertTrue(result['success'])
        self.assertIn('warning', result)
        self.assertEqual(self.config.get('scroll_speed'), 1.7)

    def test_failed_https_enable_restores_previous_setting(self):
        self.app.server.enable_https = lambda: asyncio.sleep(0)
        result = self.api.request_https(self.app.token, True)
        self.assertFalse(result['success'])
        self.assertFalse(self.config.get('https_enabled'))


if __name__ == '__main__':
    unittest.main()
