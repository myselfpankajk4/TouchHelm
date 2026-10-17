import hashlib
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
from server.aircontrol.setup import AirControlSetup, checked_model
from server.aircontrol.profiles import ProfileStore,default_profile

class AirSetupTests(unittest.TestCase):
    def test_runtime_subprocess_uses_resolved_physical_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            logical=Path(folder)/'logical';physical=Path(folder)/'redirected'
            with patch.object(Path,'resolve',return_value=physical):
                setup=AirControlSetup(logical)
            self.assertEqual(setup.folder,physical)
            self.assertEqual(setup.python,physical/'runtime/Scripts/python.exe')
            self.assertEqual(setup.models,physical/'models')

    def test_failed_command_reports_its_stage_and_actual_error(self):
        from unittest.mock import Mock
        from io import BytesIO
        with tempfile.TemporaryDirectory() as folder:
            setup=AirControlSetup(folder)
            process=Mock(stdout=BytesIO(b'failed to locate pyvenv.cfg: missing file\n'),returncode=106)
            process.poll.return_value=106
            with patch('server.aircontrol.setup.subprocess.Popen',return_value=process):
                with self.assertRaisesRegex(RuntimeError,'pyvenv.cfg'):
                    setup._run(['python','-m','pip'],10,stage='Installing camera packages')

    def test_new_directory_is_resolved_again_before_creating_venv(self):
        with tempfile.TemporaryDirectory() as folder:
            logical=Path(folder)/'logical';physical=Path(folder)/'physical';physical.mkdir()
            with patch.object(Path,'resolve',side_effect=[logical,physical]):
                setup=AirControlSetup(logical)
                with patch('server.secure_pairing.protect_user_path'),patch.object(setup,'_run',side_effect=RuntimeError('test boundary')) as run:
                    setup._install()
            self.assertEqual(run.call_args.args[0][-1],str(physical/'runtime'))
            self.assertEqual(setup.python,physical/'runtime/Scripts/python.exe')

    def test_installer_errors_do_not_expose_package_source_credentials(self):
        from unittest.mock import Mock
        from io import BytesIO
        with tempfile.TemporaryDirectory() as folder:
            setup=AirControlSetup(folder)
            process=Mock(stdout=BytesIO(b'ERROR: Failed download https://user:secret@example.invalid/wheel?token=private\n'),returncode=1)
            process.poll.return_value=1
            with patch('server.aircontrol.setup.subprocess.Popen',return_value=process):
                with self.assertRaises(RuntimeError) as error:setup._run(['python'],10,stage='Installing camera packages')
            self.assertIn('Installing camera packages',str(error.exception))
            self.assertNotIn('secret',str(error.exception));self.assertNotIn('private',str(error.exception))

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
