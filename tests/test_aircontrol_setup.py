import hashlib
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
from server.aircontrol.setup import AirControlSetup, checked_model
from server.aircontrol.profiles import ProfileStore,default_profile

class AirSetupTests(unittest.TestCase):
    def test_model_checksum_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model.task';path.write_bytes(b'owned fixture')
            self.assertTrue(checked_model(path,hashlib.sha256(b'owned fixture').hexdigest()))
            self.assertFalse(checked_model(path,'0'*64))

    def test_constructor_does_not_install_or_start_camera(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=AirControlSetup(Path(folder)/'runtime')
            self.assertEqual(setup.snapshot()['state'],'setup_required')
            self.assertFalse((Path(folder)/'runtime').exists())

    def test_cancel_is_visible_and_never_reports_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=AirControlSetup(Path(folder)/'runtime');setup.cancel()
            self.assertFalse(setup.snapshot()['ready'])

    def test_named_profiles_keep_their_saved_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ProfileStore(Path(folder)/'profiles.json')
            first=default_profile('everyday');first['sensitivity']=1.7;store.save(first)
            store.save(default_profile('presenter'))
            self.assertEqual(store.all()['everyday']['sensitivity'],1.7)
            self.assertEqual(store.read()['name'],'presenter')

    def test_unsupported_python_reports_actionable_error_without_installing(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=AirControlSetup(Path(folder)/'air')
            with patch('server.aircontrol.setup.sys.version_info',(3,12,0)):
                setup._install()
            self.assertEqual(setup.snapshot()['state'],'unavailable')
            self.assertIn('Python 3.13',setup.snapshot()['message'])
            self.assertFalse(setup.folder.exists())
