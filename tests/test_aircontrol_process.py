"""Worker EOF is observable even when a last frame was buffered."""
import unittest
import io
import time
from pathlib import Path
from unittest.mock import Mock,patch
from server.aircontrol.process import CameraWorker

class CameraPipeTests(unittest.TestCase):
    def test_fast_exit_does_not_discard_the_workers_explicit_error(self):
        worker=CameraWorker(Mock(python=Path('python.exe'),models=Path('models')))
        process=Mock();process.poll.return_value=1
        process.stdout=io.StringIO('{"type":"error","message":"Camera frame conversion failed"}\n')
        process.stderr=io.StringIO('')
        with patch('server.aircontrol.process.subprocess.Popen',return_value=process):worker.start({})
        deadline=time.monotonic()+1
        item=None
        while time.monotonic()<deadline:
            item=worker.latest()
            if item and 'conversion' in item.get('message',''):break
            time.sleep(.005)
        self.assertIn('conversion',item.get('message',''))

    def test_native_crash_includes_exit_code_and_bounded_stderr(self):
        worker=CameraWorker(Mock(python=Path('python.exe'),models=Path('models')))
        process=Mock();process.poll.return_value=-1073741819
        process.stdout=io.StringIO('');process.stderr=io.StringIO('Native capture failed: unsupported format\n')
        with patch('server.aircontrol.process.subprocess.Popen',return_value=process):worker.start({})
        deadline=time.monotonic()+1
        item=None
        while time.monotonic()<deadline:
            item=worker.latest()
            if item and 'unsupported' in item.get('message',''):break
            time.sleep(.005)
        self.assertIn('-1073741819',item.get('message',''))
        self.assertIn('unsupported format',item.get('message',''))
        self.assertLess(len(item['message']),500)

    def test_process_exit_after_buffered_frame_is_reported(self):
        worker=CameraWorker(Mock());worker.process=Mock()
        worker.process.poll.return_value=1
        worker.queue.put_nowait({'type':'observation','seq':1})
        self.assertEqual(worker.latest()['type'],'observation')
        self.assertEqual(worker.latest()['type'],'error')
