import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from server.wireless_display import WirelessDisplaySetup, progress_percent
from server.config import ConfigManager

class WirelessDisplayTests(unittest.TestCase):
    def test_progress_uses_reported_percent_not_invented_completion(self):
        self.assertIsNone(progress_percent('Starting DISM...'))
        self.assertEqual(progress_percent('[=== 17.2% ===]\r[=== 82.0% ===]'),82)
        self.assertLess(progress_percent('100.0%'),100)

    def test_install_request_is_bounded_and_reports_uac_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=WirelessDisplaySetup(Path(folder),launcher=Mock(side_effect=PermissionError('Cancelled')))
            setup.install()
            setup.thread.join(2)
            self.assertEqual(setup.snapshot()['state'],'permission_required')
            self.assertEqual(setup.snapshot()['progress'],None)

    def test_existing_feature_does_not_reinstall(self):
        with tempfile.TemporaryDirectory() as folder:
            launcher=Mock();setup=WirelessDisplaySetup(Path(folder),launcher=launcher)
            setup.state={'state':'installed','progress':100,'message':'Ready'}
            setup.install();launcher.assert_not_called()

    def test_generated_password_is_unique_valid_and_legacy_pin_still_works(self):
        with tempfile.TemporaryDirectory() as folder:
            a=ConfigManager(str(Path(folder)/'a.json'));b=ConfigManager(str(Path(folder)/'b.json'))
            self.assertNotEqual(a.get('pin_code'),b.get('pin_code'))
            self.assertGreaterEqual(len(a.get('pin_code')),12)
            self.assertTrue(a._valid_pin(a.get('pin_code')))
            self.assertTrue(a._valid_pin('5678'))
            a.save();self.assertEqual(ConfigManager(a.file_path).get('pin_code'),a.get('pin_code'))
