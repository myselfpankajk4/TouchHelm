"""Opt-in installed build check: no network/package commands permitted.

Run with the installed runtime/python.exe, not a developer Python.
"""
import argparse
import ctypes
import json
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root/'app'))
    from portable_setup import ComponentSetup
    setup = ComponentSetup(args.root, args.data)
    with patch('portable_setup.urllib.request.urlopen', side_effect=AssertionError('Unexpected download')), \
         patch.object(setup, 'command', side_effect=AssertionError('Unexpected package command')):
        setup.ensure_browser()
    # Import the actual acceleration extension, not only DXcam's Python facade.
    # This catches dependencies that import-only feature detection can miss.
    import dxcam.processor._numpy_kernels
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    api.GetModuleHandleW.restype = ctypes.c_void_p
    api.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong]
    handle = api.GetModuleHandleW('vcomp140.dll')
    assert handle, 'DXcam OpenMP runtime did not load'
    location = ctypes.create_unicode_buffer(32768)
    assert api.GetModuleFileNameW(handle, location, len(location))
    result = {'bundled_python': Path(sys.executable).absolute().is_relative_to(args.root),
              'browser_ready_without_downloads': True,
              'screen_audio_bundled': (args.root/'runtime/Lib/site-packages/aiortc').is_dir(),
              'camera_bundled': (args.root/'camera/Lib/site-packages/mediapipe').is_dir(),
              'openmp_loaded_from_app': Path(location.value).samefile(args.root/'runtime/vcomp140.dll')}
    args.report.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    assert all(result.values())


if __name__ == '__main__':
    main()
