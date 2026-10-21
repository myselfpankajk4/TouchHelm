import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class CompactSetupTests(unittest.TestCase):
    def test_ready_marker_does_not_hide_a_missing_native_camera_dll(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder);camera=setup.component/'camera'
            for name in ('python.exe','Lib/site-packages/mediapipe/__init__.py','Lib/site-packages/cv2/__init__.py'):
                path=camera/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'owned')
            (camera/'ready').write_text(setup.identity)
            (camera/'.native-files.json').write_text(json.dumps({'python313.dll':100}))
            self.assertFalse(setup.feature_ready('camera'))

    def test_cancelling_certificate_verification_terminates_its_child(self):
        from portable_setup import SetupCancelled
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder);process=MagicMock(returncode=0);process.poll.return_value=None
            process.__enter__.return_value=process;process.communicate.return_value=(b'',b'')
            with patch.object(setup,'check_cancel',side_effect=[None,SetupCancelled()]), \
                 patch('portable_setup.subprocess.Popen',return_value=process):
                with self.assertRaises(SetupCancelled):setup.verify_microsoft(Path(folder)/'installer.exe')
            process.terminate.assert_called_once()

    def test_network_failure_explains_connectivity_instead_of_manual_pip_advice(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder);setup.component.mkdir(parents=True)
            process=Mock(returncode=1);process.poll.return_value=1
            def failed_command(*args,**kwargs):
                kwargs['stdout'].write(b'NameResolutionError: download server could not resolve\nConsider using the --user option\n')
                kwargs['stdout'].flush();return process
            with patch('portable_setup.subprocess.Popen',side_effect=failed_command):
                with self.assertRaisesRegex(RuntimeError,'internet|download server'):
                    setup.command(['owned-fixture'])

    def test_retry_cleans_abandoned_generated_folders_and_preserves_unrelated_data(self):
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder);setup.component.mkdir(parents=True)
            abandoned=setup.component/('.camera-'+'a'*32);abandoned.mkdir();(abandoned/'partial').touch()
            notes=setup.component/'.camera-notes';notes.mkdir();(notes/'keep').touch()
            with patch.object(setup,'locked',return_value=nullcontext()),patch.object(setup,'ensure_webview'), \
                 patch.object(setup,'ensure_models'),patch.object(setup,'ensure_remote'),patch.object(setup,'ensure_camera'):
                setup.ensure()
            self.assertFalse(abandoned.exists());self.assertTrue((notes/'keep').exists())

    def test_failed_prepare_removes_its_temporary_files_but_preserves_other_data(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder); setup.component.mkdir(parents=True)
            saved=setup.component/'owned.txt';saved.write_text('keep')
            with patch.object(setup,'install_packages',side_effect=RuntimeError('download interrupted')):
                with self.assertRaisesRegex(RuntimeError,'interrupted'):setup.ensure_remote()
            self.assertEqual(list(setup.component.glob('.remote-*')),[])
            self.assertEqual(saved.read_text(),'keep')

    def test_missing_browser_is_installed_silently_only_after_signature_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder)
            with patch.object(setup,'webview_available',side_effect=[False,True]), \
                 patch.object(setup,'download') as download,patch.object(setup,'verify_microsoft') as signature, \
                 patch.object(setup,'command') as command:
                setup.ensure_webview()
            download.assert_called_once();signature.assert_called_once()
            self.assertEqual(command.call_args.args[0][1:],['/silent','/install'])

    def fixture(self, folder):
        from portable_setup import ComponentSetup
        root=Path(folder)/'bundle'; data=Path(folder)/'data'
        (root/'app/assets/aircontrol').mkdir(parents=True)
        (root/'runtime').mkdir()
        (root/'runtime/python.exe').write_bytes(b'owned python fixture')
        (root/'app/requirements-aircontrol.txt').write_text('camera==1 --hash=sha256:'+'a'*64)
        (root/'app/requirements-remote-portable.txt').write_text('remote==1 --hash=sha256:'+'b'*64)
        (root/'app/assets/aircontrol/manifest.json').write_text(json.dumps({'model.task':
            {'sha256':hashlib.sha256(b'owned model').hexdigest(),'bytes':11,'url':'https://example.invalid/model'}}))
        (root/'compact.json').write_text(json.dumps({'schema':1,'seed_files':['python.exe']}))
        return ComponentSetup(root,data,protector=lambda p:None)

    def test_component_identity_tracks_dependency_and_model_changes_not_ui_version(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder); original=setup.identity
            (setup.root/'app/requirements-remote-portable.txt').write_text('different dependency')
            changed=self.fixture_identity(setup)
            self.assertNotEqual(changed,original)

    def fixture_identity(self,setup):
        from portable_setup import ComponentSetup
        return ComponentSetup(setup.root,setup.data,protector=lambda p:None).identity

    def test_seed_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder); setup.manifest['seed_files']=['../private.txt']
            with self.assertRaisesRegex(ValueError,'seed'):
                setup.seed_camera(setup.component/'camera')

    def test_cancelled_setup_does_not_run_any_command(self):
        from portable_setup import SetupCancelled
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder); cancel=Path(folder)/'cancel'; cancel.touch(); setup.cancel_file=cancel
            with patch.object(setup,'command') as command:
                with self.assertRaises(SetupCancelled):setup.ensure()
                command.assert_not_called()

    def test_download_checks_sha256_before_publishing(self):
        from io import BytesIO
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder); target=Path(folder)/'download.task'
            with patch('portable_setup.urllib.request.urlopen',return_value=BytesIO(b'bad model')):
                with self.assertRaisesRegex(RuntimeError,'integrity'):
                    setup.download('https://example.invalid/model',target,'0'*64,9)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(folder).glob('*.partial-*')),[])

    def test_remote_pip_is_hash_locked_and_ignores_global_pip_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder)
            with patch.object(setup,'command') as command:
                setup.install_packages(Path(folder)/'site',setup.root/'app/requirements-remote-portable.txt')
            args=command.call_args.args[0]
            for value in ('--isolated','--require-hashes','--only-binary=:all:','--no-input'):
                self.assertIn(value,args)

    def test_existing_webview_is_reused_without_downloading(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder)
            with patch.object(setup,'webview_available',return_value=True),patch.object(setup,'download') as download:
                setup.ensure_webview()
                download.assert_not_called()

    def test_untrusted_webview_bootstrapper_is_never_executed(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder)
            with patch.object(setup,'webview_available',return_value=False), \
                 patch.object(setup,'download'),patch.object(setup,'verify_microsoft',side_effect=RuntimeError('signature rejected')), \
                 patch.object(setup,'command') as command:
                with self.assertRaisesRegex(RuntimeError,'signature'):
                    setup.ensure_webview()
                command.assert_not_called()
