"""Instance control tests replace named mutex and IPC effects."""
import importlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class InstanceControlTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('server.instance_control')
        self.folder = tempfile.TemporaryDirectory(dir=ROOT / 'tests')
        self.addCleanup(self.folder.cleanup)
        self.mutex = Mock()
        self.mutex.create.return_value = (123, False)
        self.instance = self.module.InstanceController('build-a', storage_dir=self.folder.name,
            source_root=ROOT, mutex=self.mutex, protector=Mock())
        self.instance.on_restore, self.instance.on_stop = Mock(), Mock()

    def test_secondary_does_not_own_or_release_other_instances_mutex(self):
        self.mutex.create.return_value = (123, True)
        self.assertFalse(self.instance.acquire())
        self.mutex.close.assert_called_once_with(123)
        self.instance.close()
        self.mutex.release.assert_not_called()

    def test_matching_build_restores_without_stopping(self):
        self.assertTrue(self.instance.acquire())
        response = self.instance._process_request({'token': self.instance.token, 'build': 'build-a'})
        self.assertEqual(response['action'], 'restored')
        self.instance.on_restore.assert_called_once_with()
        self.instance.on_stop.assert_not_called()

    def test_changed_source_build_requests_graceful_stop_once(self):
        self.instance.acquire()
        request = {'token': self.instance.token, 'build': 'build-b'}
        self.assertEqual(self.instance._process_request(request)['action'], 'restarting')
        self.instance._process_request(request)
        self.instance.on_stop.assert_called_once_with()
        self.instance.on_restore.assert_not_called()

    def test_missing_or_forged_token_cannot_restore_or_stop(self):
        self.instance.acquire()
        for token in (None, [], 'wrong', '', '😀'):
            response = self.instance._process_request({'token': token, 'build': 'build-b'})
            self.assertFalse(response['success'])
        self.instance.on_restore.assert_not_called()
        self.instance.on_stop.assert_not_called()

    def test_close_releases_owned_mutex_once_and_keeps_new_owner_metadata(self):
        self.instance.acquire()
        self.instance.metadata_path.write_text(json.dumps({'token': 'new-owner'}))
        self.instance.close(); self.instance.close()
        self.mutex.release.assert_called_once_with(123)
        self.mutex.close.assert_called_once_with(123)
        self.assertTrue(self.instance.metadata_path.exists())

    def test_native_source_change_changes_build_without_docs_noise(self):
        root = Path(self.folder.name)
        (root / 'server').mkdir()
        (root / 'main.py').write_text('one')
        before = self.module.source_build_id(root)
        (root / 'notes.md').write_text('unrelated')
        self.assertEqual(self.module.source_build_id(root), before)
        (root / 'server' / 'windows_input.py').write_text('new native code')
        self.assertNotEqual(self.module.source_build_id(root), before)

    def test_two_simultaneous_restart_requests_stop_only_once(self):
        self.instance.acquire()
        gate = threading.Barrier(3)
        replies = []
        def request():
            gate.wait()
            replies.append(self.instance._process_request({'token': self.instance.token, 'build': 'build-b'}))
        workers = [threading.Thread(target=request) for _ in range(2)]
        for worker in workers: worker.start()
        gate.wait()
        for worker in workers: worker.join(timeout=2)
        self.assertEqual(len(replies), 2)
        self.assertTrue(all(reply['action'] == 'restarting' for reply in replies))
        self.instance.on_stop.assert_called_once_with()

    def test_shutdown_rejects_requests_before_releasing_owned_resources(self):
        self.instance.acquire()
        replies = []
        server = Mock()
        server.shutdown.side_effect = lambda: replies.append(self.instance._process_request(
            {'token': self.instance.token, 'build': 'build-b'}))
        self.instance._server = server
        self.instance.close()
        self.assertFalse(replies[0]['success'])
        self.instance.on_stop.assert_not_called()

    def test_losing_restart_launcher_restores_the_new_matching_owner(self):
        self.instance.metadata_path.write_text(json.dumps({'protocol': 1, 'port': 55555, 'token': 'a' * 43}))
        channels = []
        for action in ('restarting', 'restored'):
            channel = MagicMock()
            channel.__enter__.return_value = channel
            channel.makefile.return_value = io.BytesIO(json.dumps({'success': True, 'action': action}).encode())
            channels.append(channel)
        with patch.object(self.instance, 'acquire', return_value=False), patch.object(
            self.module.socket, 'create_connection', side_effect=channels
        ), patch.object(self.module.time, 'sleep'):
            self.assertEqual(self.instance.handoff(timeout=.02), 'restored')

    def test_runtime_native_helper_and_artwork_change_build_but_qa_captures_do_not(self):
        root = Path(self.folder.name)
        (root / 'server').mkdir()
        (root / 'assets/theme/review').mkdir(parents=True)
        (root / 'web/assets').mkdir(parents=True)
        before = self.module.source_build_id(root)
        (root / 'assets/theme/review/screenshot.png').write_bytes(b'qa only')
        self.assertEqual(self.module.source_build_id(root), before)
        for relative in ('server/desktop_native.cs', 'assets/touchhelm.ico',
                         'assets/touchhelm.png', 'assets/theme/background.webp', 'web/assets/interface.woff2'):
            (root / relative).write_bytes(b'first runtime content')
            updated = self.module.source_build_id(root)
            self.assertNotEqual(updated, before, relative)
            (root / relative).write_bytes(b'updated runtime content')
            before = self.module.source_build_id(root)
            self.assertNotEqual(before, updated, relative)


if __name__ == '__main__':
    unittest.main()
