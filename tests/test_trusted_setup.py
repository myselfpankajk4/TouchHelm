import unittest
import asyncio
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch
from server.config import ConfigManager
from server.trusted_setup import TrustedPairingSetup

class TrustedSetupTests(unittest.TestCase):
    def test_ready_setup_enables_access_preserves_theme_and_saves_trusted_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            config=ConfigManager(str(Path(folder)/'config.json'))
            tail=Mock();tail.inspect.side_effect=[{'state':'setup_required'},{'state':'ready','ready':True}]
            server=SimpleNamespace(tailscale=tail,invalidate_auth_sessions=AsyncMock(),enable_tailscale=AsyncMock(),remote_settings_changed=AsyncMock())
            app=SimpleNamespace(config=config,server=server,_settings_lock=threading.RLock(),_submit=asyncio.run,_preferences=lambda:{'theme':'bloom'},_save_preferences=Mock())
            installer=Mock();setup=TrustedPairingSetup(app,find_cli=lambda:'tailscale.exe',run=installer)
            with patch('server.remote_media.capabilities',return_value={'audio':True,'video':True}):
                setup.start();setup.thread.join(2)
            self.assertEqual(setup.snapshot()['state'],'ready')
            self.assertTrue(config.get('require_pin'));self.assertTrue(config.get('remote_enabled'))
            self.assertEqual(len(config.get('pin_code')),4)
            app._save_preferences.assert_called_once_with({'theme':'bloom','connection_mode':'tailscale'})
            server.invalidate_auth_sessions.assert_awaited_once();installer.assert_not_called()

    def test_missing_installer_reports_actionable_state(self):
        app=Mock();setup=TrustedPairingSetup(app,find_cli=lambda:None,find_winget=lambda:None)
        setup.start();setup.thread.join(2)
        self.assertEqual(setup.snapshot()['state'],'unavailable')
        app.server.enable_tailscale.assert_not_called()

    def test_signed_out_pc_stays_login_required_without_claiming_trust(self):
        app=Mock();app.server.tailscale.inspect.return_value={'state':'login_required','message':'Sign in first'}
        setup=TrustedPairingSetup(app,find_cli=lambda:'tailscale.exe')
        setup.start();setup.thread.join(2)
        self.assertEqual(setup.snapshot()['state'],'login_required')
        app.server.enable_tailscale.assert_not_called()

