"""Build identity and HTTP cache policy without desktop side effects."""
import importlib
from pathlib import Path
import tempfile
import unittest


class BuildVersionTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('server.build_version')
        except ImportError:
            self.fail('Build version module is missing')

    def test_saved_asset_change_changes_build_identity(self):
        version = self.module()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'index.html').write_text('<html>one</html>')
            (root / 'app.js').write_text('first')
            initial = version.get_build_id(root)
            self.assertEqual(version.get_build_id(root), initial)
            (root / 'app.js').write_text('new contents')
            self.assertNotEqual(version.get_build_id(root), initial)

    def test_version_is_derived_from_contents_not_directory_location(self):
        version = self.module()
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for folder in (first, second):
                (Path(folder) / 'app.js').write_text('same source')
            self.assertEqual(version.get_build_id(Path(first)), version.get_build_id(Path(second)))

    def test_rendered_page_has_versioned_assets_and_matching_meta(self):
        version = self.module()
        html = '<meta name="touchhelm-build" content="__TOUCHHELM_BUILD__"><script src="app.js?v=__TOUCHHELM_BUILD__"></script>'
        rendered = version.render_versioned(html, 'abc123')
        self.assertIn('content="abc123"', rendered)
        self.assertIn('app.js?v=abc123', rendered)
        self.assertNotIn('__TOUCHHELM_BUILD__', rendered)
