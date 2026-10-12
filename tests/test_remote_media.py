"""Provider lifecycle with capture and native audio mocked."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from server.remote_media import DesktopCapture


class CaptureTests(unittest.TestCase):
    def test_audio_output_format_stays_constant_across_device_changes(self):
        from server.remote_media import AudioNormalizer
        normalizer=AudioNormalizer()
        for rate,channels in ((48000,2),(44100,1),(48000,2),(96000,2)):
            result=normalizer.frame(bytes(rate//50*channels*2),rate,channels)
            self.assertEqual(result.sample_rate,48000)
            self.assertEqual(result.samples,960)
            self.assertEqual(result.layout.name,'stereo')

    def test_capture_config_uses_explicit_cpu_processor_and_identity(self):
        display={'id':'display-1','rect':{'x':-800,'y':0,'width':800,'height':600}}
        camera=Mock(width=800,height=600)
        dxcam=SimpleNamespace(__factory=SimpleNamespace(outputs=[[SimpleNamespace(desc=SimpleNamespace(DeviceName='display-1'))]]),create=Mock(return_value=camera))
        capture=DesktopCapture(display,'balanced')
        with patch.dict('sys.modules',{'dxcam':dxcam}):capture.open()
        self.assertEqual(dxcam.create.call_args.kwargs.get('processor_backend'),'numpy')
        capture.close();camera.release.assert_called_once()

    def test_lock_and_geometry_change_stop_before_returning_old_frame(self):
        display={'id':'display-1','rect':{'x':0,'y':0,'width':800,'height':600}}
        capture=DesktopCapture(display,'balanced');capture.camera=Mock(width=800,height=600);capture.dimensions=(800,600)
        capture.last_frame=object()
        with patch('server.remote_media.unlocked_desktop',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'locked'):capture.frame()
        capture.checked=0;capture.camera.width=900
        with patch('server.remote_media.unlocked_desktop',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'geometry'):capture.frame()

    def test_removed_monitor_stops_capture(self):
        capture=DesktopCapture({'id':'display-1','rect':{'x':0,'y':0,'width':800,'height':600}},'balanced')
        bounds=SimpleNamespace(left=0,top=0,right=800,bottom=600)
        output=SimpleNamespace(update_desc=Mock(),desc=SimpleNamespace(DesktopCoordinates=bounds,AttachedToDesktop=False))
        capture.camera=Mock(width=800,height=600,_output=output);capture.dimensions=(800,600)
        with patch('server.remote_media.unlocked_desktop',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'removed'):capture.frame()
