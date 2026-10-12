"""Provider lifecycle with capture and native audio mocked."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from server.remote_media import DesktopCapture


class CaptureTests(unittest.TestCase):
    def test_encoding_budget_improves_detail_and_keeps_congestion_feedback(self):
        from server.remote_media import configure_video_encoding
        from aiortc.codecs import h264, vpx
        for quality, expected in [('clear',6000000),('detail',10000000),('saver',1200000)]:
            configure_video_encoding(quality)
            encoder=h264.H264Encoder()
            self.assertEqual(encoder.target_bitrate,expected)
            encoder.target_bitrate=250000
            self.assertLessEqual(encoder.target_bitrate,500000)
        self.assertGreaterEqual(vpx.MAX_BITRATE,10000000)
    def test_dxcam_030_managed_com_objects_are_released_once(self):
        from server.remote_media import release_dxgi_duplicator, release_stage_surface
        class Pointer:
            def Release(self):raise AssertionError('comtypes already owns Release on destruction')
        duplicator=SimpleNamespace(duplicator=Pointer(),texture=Pointer(),release_frame=Mock())
        stage=SimpleNamespace(texture=Pointer(),interface=Pointer(),width=10,height=10)
        release_dxgi_duplicator(duplicator);release_stage_surface(stage)
        duplicator.release_frame.assert_called_once()
        self.assertIsNone(duplicator.duplicator);self.assertIsNone(duplicator.texture)
        self.assertIsNone(stage.texture);self.assertIsNone(stage.interface)

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
