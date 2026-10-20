"""Portable builds must be self-contained without importing the builder's state."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PortableTests(unittest.TestCase):
    def test_bundle_keeps_logical_path_under_windows_appdata_redirection(self):
        from server.portable import bundle_root
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {'TOUCHHELM_PORTABLE_ROOT': folder}), \
                 patch.object(Path, 'resolve', return_value=Path('unexpected-physical-cache')):
                self.assertEqual(bundle_root(), Path(folder).absolute())

    def test_portable_startup_reports_nonzero_application_exit(self):
        import portable_bootstrap
        from io import StringIO
        import sys
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(portable_bootstrap, 'prepare', return_value=(Path(folder), Path(folder))), \
                 patch('builtins.open', return_value=StringIO()), \
                 patch.dict(sys.modules, {'main': type('App', (), {'main': staticmethod(lambda: 1)})}), \
                 patch.object(portable_bootstrap, 'show_error') as error:
                self.assertEqual(portable_bootstrap.main(), 1)
                error.assert_called_once()

    def test_portable_prepare_failure_is_visible(self):
        import portable_bootstrap
        from io import StringIO
        with patch.object(portable_bootstrap, 'prepare', side_effect=PermissionError('owned fixture')), \
             patch('sys.stderr', StringIO()), \
             patch.object(portable_bootstrap, 'show_error') as error:
            self.assertEqual(portable_bootstrap.main(), 1)
            error.assert_called_once()

    def test_source_config_stays_in_checkout(self):
        from server.portable import config_path
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config_path(Path('owned')), Path('owned/config.json'))

    def test_portable_config_survives_version_changes(self):
        from server.portable import config_path
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {'TOUCHHELM_PORTABLE_ROOT': folder + '/v1', 'LOCALAPPDATA': folder}):
                self.assertEqual(config_path(Path('app')), Path(folder)/'TouchHelm/config.json')

    def test_new_portable_config_requires_a_fresh_pin(self):
        from server.config import ConfigManager
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {'TOUCHHELM_PORTABLE_ROOT': folder}):
                config = ConfigManager(str(Path(folder)/'config.json'))
            self.assertTrue(config.get('require_pin'))
            self.assertEqual(len(config.get('pin_code')), 4)

    def test_bundled_camera_runtime_checks_models_without_setup_marker(self):
        from server.aircontrol.setup import AirControlSetup
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'camera').mkdir(); (root/'camera/python.exe').touch()
            models = root/'app/assets/aircontrol'; models.mkdir(parents=True)
            (models/'owned.task').write_bytes(b'owned')
            (models/'manifest.json').write_text(json.dumps({'owned.task': {'sha256': hashlib.sha256(b'owned').hexdigest()}}))
            with patch.dict(os.environ, {'TOUCHHELM_PORTABLE_ROOT': folder}):
                setup = AirControlSetup(root/'data')
                self.assertTrue(setup.snapshot()['ready'])
                self.assertEqual(setup.python, root/'camera/python.exe')
                (models/'owned.task').write_bytes(b'damaged')
                self.assertFalse(setup._ready())

    def test_damaged_portable_camera_never_tries_pip(self):
        from server.aircontrol.setup import AirControlSetup
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {'TOUCHHELM_PORTABLE_ROOT': folder}):
                setup = AirControlSetup(Path(folder)/'data')
                with patch.object(setup, '_run') as run:
                    setup.start()
                    if setup.thread: setup.thread.join(2)
                run.assert_not_called()
                self.assertEqual(setup.snapshot()['state'], 'unavailable')
                self.assertIn('download', setup.snapshot()['message'].lower())
