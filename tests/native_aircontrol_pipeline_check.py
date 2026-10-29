"""Opt-in real inference/IPC check with a public still image, never a webcam.

Unlike the model check, this runs the production camera worker, its stdout pipe,
the service loop and enable transition. Only VideoCapture and native input are
replaced. No camera, desktop clicks, keys or real cursor movement are used.
"""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def replay():
    import cv2
    from server.aircontrol import worker
    image = cv2.imread(str(ROOT / '.tmp/aircontrol-reference/pointing_up.jpg'))
    if image is None:
        raise RuntimeError('Run native_aircontrol_model_check.py --download-reference first')

    class ReferenceCapture:
        def __init__(self, *args): self.stopped = False; self.started = False
        def isOpened(self): return True
        def set(self, *args):
            if self.started:
                raise RuntimeError('Camera properties changed while the capture thread was reading')
            return True
        def read(self):
            self.started = True
            time.sleep(1 / 30)
            return (not self.stopped, image.copy())
        def release(self): self.stopped = True

    cv2.VideoCapture = ReferenceCapture
    original_models = worker.models
    def slow_models(*args):
        hand, face = original_models(*args)
        class SlowHand:
            def recognize_for_video(self, *values):
                time.sleep(.06)  # Exercise the real adaptive-rate branch.
                return hand.recognize_for_video(*values)
            def close(self): hand.close()
        return SlowHand() if hand else None, face
    worker.models = slow_models
    sys.argv.remove('--replay')
    worker.main()


async def check():
    from server.aircontrol.service import AirControlService
    from server.aircontrol.setup import AirControlSetup
    from server.private_storage import private_storage_root
    setup = AirControlSetup(private_storage_root() / 'aircontrol')
    assert setup.snapshot()['ready'], 'Set up the isolated AirControl runtime first'
    native = Mock()
    native.get_physical_cursor_pos.side_effect = lambda: tuple(native.set_physical_cursor_pos.call_args.args)
    displays = AsyncMock(return_value={'displays': [{'id': 'reference', 'primary': True,
        'rect': {'x': 0, 'y': 0, 'width': 1920, 'height': 1080}}]})
    real_popen = subprocess.Popen

    def launch(args, **kwargs):
        if len(args) > 2 and Path(args[2]).name == 'worker.py':
            args = [args[0], args[1], str(Path(__file__).resolve()), '--replay', *args[3:]]
        return real_popen(args, **kwargs)

    with tempfile.TemporaryDirectory() as folder, patch('server.aircontrol.process.subprocess.Popen', side_effect=launch):
        service = AirControlService(native, displays, folder=folder, setup=setup,desktop_available=lambda:True)
        try:
            await service.command('start')
            deadline = time.monotonic() + 25
            while service.stable_frames < 20 and time.monotonic() < deadline:
                await asyncio.sleep(.05)
            assert service.stable_frames >= 20, service.snapshot()['message']
            # This check verifies transport and control activation; physical
            # calibration/pinch accuracy is covered separately, not fabricated.
            service.calibrated = True
            service.state = 'practicing'
            service.practice_frames = 15
            service.practice_actions = 1
            await service.command('enable')
            await asyncio.sleep(1)
            assert service.state == 'active', service.message
            assert native.set_physical_cursor_pos.call_count >= 10, 'Accepted observations did not reach native input'
            print(json.dumps({'inference_pipe_activation': 'passed', 'pointer_proposals': native.set_physical_cursor_pos.call_count,
                'measured_updates_fps': service.snapshot()['metrics']['fps'], 'camera_opened': False, 'native_input': 'mocked'}))
        finally:
            await service.close()


if __name__ == '__main__':
    if '--replay' in sys.argv:
        replay()
    else:
        asyncio.run(check())
