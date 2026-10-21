"""An installed build must never fall back to downloading Python packages."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_compact_setup


class InstalledDistributionTests(unittest.TestCase):
    def test_installed_setup_cannot_accidentally_select_full_download_mode(self):
        import portable_setup
        with tempfile.TemporaryDirectory() as folder:
            fixture = test_compact_setup.CompactSetupTests().fixture(folder)
            (fixture.root/'compact.json').rename(fixture.root/'installed.json')
            with patch.object(portable_setup, '__file__', str(fixture.root/'app/portable_setup.py')), \
                 patch.dict(os.environ, {'LOCALAPPDATA': str(fixture.data)}), \
                 patch('sys.argv', ['setup', '--progress', str(Path(folder)/'progress.json'),
                                    '--cancel', str(Path(folder)/'cancel')]), \
                 patch.object(portable_setup.ComponentSetup, 'ensure',
                              side_effect=AssertionError('Installed app must never run pip')), \
                 patch.object(portable_setup.ComponentSetup, 'ensure_browser') as browser:
                self.assertEqual(portable_setup.main(), 0)
            browser.assert_called_once()

    def test_installed_setup_only_prepares_browser_never_camera_or_packages(self):
        from portable_setup import ComponentSetup
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as folder:
            fixture = test_compact_setup.CompactSetupTests().fixture(folder)
            (fixture.root/'compact.json').rename(fixture.root/'installed.json')
            setup = ComponentSetup(fixture.root, fixture.data, protector=lambda p: None)
            with patch.object(setup, 'locked', return_value=nullcontext()), \
                 patch.object(setup, 'ensure_webview') as browser, \
                 patch.object(setup, 'install_packages', side_effect=AssertionError('No pip on client')), \
                 patch.object(setup, 'download', side_effect=AssertionError('No feature download')):
                setup.ensure_browser()
            browser.assert_called_once()
            self.assertFalse((setup.component/'ready').exists())

    def test_installed_startup_uses_bundled_features_and_system_webview(self):
        import portable_bootstrap
        import types
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'app').mkdir()
            (root/'runtime').mkdir()
            (root/'runtime/python.exe').touch()
            (root/'installed.json').write_text(json.dumps({'schema': 1}))
            webview = types.SimpleNamespace(settings={})
            with patch.object(portable_bootstrap, '__file__', str(root/'app/portable_bootstrap.py')), \
                 patch.dict(os.environ, {'LOCALAPPDATA': str(root/'profile'),
                     'PYTHONHOME': 'invalid', 'PYTHONPATH': 'invalid',
                     'TOUCHHELM_COMPONENT_ROOT': 'stale-compact-components',
                     'WEBVIEW2_BROWSER_EXECUTABLE_FOLDER': 'stale-offline-browser'}), \
                 patch.dict('sys.modules', {'webview': webview}), \
                 patch('server.secure_pairing.protect_user_path'):
                actual, _ = portable_bootstrap.prepare()
                self.assertEqual(actual, root)
                self.assertIsNone(webview.settings['WEBVIEW2_RUNTIME_PATH'])
                for name in ('PYTHONHOME', 'PYTHONPATH', 'TOUCHHELM_COMPONENT_ROOT',
                             'WEBVIEW2_BROWSER_EXECUTABLE_FOLDER'):
                    self.assertNotIn(name, os.environ)


if __name__ == '__main__':
    unittest.main()
