"""Worker EOF is observable even when a last frame was buffered."""
import unittest
from unittest.mock import Mock
from server.aircontrol.process import CameraWorker

class CameraPipeTests(unittest.TestCase):
    def test_process_exit_after_buffered_frame_is_reported(self):
        worker=CameraWorker(Mock());worker.process=Mock()
        worker.process.poll.return_value=1
        worker.queue.put_nowait({'type':'observation','seq':1})
        self.assertEqual(worker.latest()['type'],'observation')
        self.assertEqual(worker.latest()['type'],'error')
