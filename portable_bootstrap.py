"""Entrypoint for the embedded runtime; also provides a camera-free build probe."""
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback


def prepare():
    root = Path(__file__).absolute().parent.parent
    if not (root/'runtime/python.exe').is_file():
        raise RuntimeError('Launch the portable TouchHelm EXE to use this entrypoint.')
    os.environ['TOUCHHELM_PORTABLE_ROOT'] = str(root)
    compact=(root/'compact.json').is_file()
    system_browser=compact or (root/'installed.json').is_file()
    if system_browser:os.environ.pop('WEBVIEW2_BROWSER_EXECUTABLE_FOLDER',None)
    else:os.environ['WEBVIEW2_BROWSER_EXECUTABLE_FOLDER'] = str(root/'webview2')
    os.environ['PYTHONUTF8'] = '1'
    os.environ.pop('PYTHONHOME', None)
    os.environ.pop('PYTHONPATH', None)
    os.environ['TCL_LIBRARY'] = str(root/'runtime/tcl/tcl8.6')
    os.environ['TK_LIBRARY'] = str(root/'runtime/tcl/tk8.6')
    from server.portable import config_path
    data = config_path(Path(__file__).parent).parent
    if compact:
        from portable_setup import component_directory
        component=component_directory(root,data)
        if not (component/'ready').is_file():raise RuntimeError('Open the compact EXE to finish first-run preparation.')
        os.environ['TOUCHHELM_COMPONENT_ROOT']=str(component)
        sys.path.insert(0,str(component/'remote/site'))
    else:os.environ.pop('TOUCHHELM_COMPONENT_ROOT',None)
    import webview
    # pywebview's Windows backend detection checks this setting before it ever
    # creates WebView2; the Microsoft environment variable alone is insufficient.
    webview.settings['WEBVIEW2_RUNTIME_PATH'] = None if system_browser else str(root/'webview2')
    from server.secure_pairing import protect_user_path
    protect_user_path(data)
    return root, data


def self_test(root, data):
    """Imports only: no camera, capture, input injection, host singleton or PIN log."""
    import argparse
    import importlib
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    report = {'ok': False, 'python': sys.version.split()[0], 'bundled_python':
              Path(sys.executable).absolute().is_relative_to(root), 'checks': {}}
    exit_code = 1
    try:
        for name in ('aiohttp', 'websockets', 'PIL', 'qrcode', 'pystray', 'cryptography',
                     'webview', 'clr', 'aiortc', 'av', 'dxcam', 'pyaudiowpatch', 'cv2',
                     'tkinter', 'server.web_server', 'gui.webview_window'):
            importlib.import_module(name)
            report['checks'][name] = True
        from server.aircontrol.setup import AirControlSetup
        setup = AirControlSetup(data/'aircontrol')
        if not setup.snapshot()['ready']: raise RuntimeError('Bundled camera integrity check failed')
        camera = subprocess.run([str(setup.python), str(root/'app/server/aircontrol/worker.py'),
            '--check', '--models', str(setup.models)], capture_output=True, text=True,
            timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        if camera.returncode:
            raise RuntimeError(f'Bundled camera worker failed ({camera.returncode}): '+
                               (camera.stdout+camera.stderr)[-1500:])
        report['checks']['camera_models'] = True
        # Force Fixed Version WebView2 and execute JS inside its actual renderer.
        import webview
        import winreg
        real_open = winreg.OpenKey
        def without_installed_webview(key, sub_key, *args, **kwargs):
            if 'edgeupdate' in str(sub_key).lower():
                raise FileNotFoundError('Installed WebView2 deliberately hidden for portable verification')
            return real_open(key, sub_key, *args, **kwargs)
        system_browser=(root/'compact.json').is_file() or (root/'installed.json').is_file()
        if not system_browser:winreg.OpenKey = without_installed_webview
        window = webview.create_window('TouchHelm portable verification',
            html='<html><body>TouchHelm runtime check</body></html>', hidden=True)
        def probe():
            try:
                report['checks']['webview2_javascript'] = window.evaluate_js('6 * 7') == 42
            except Exception as error:
                report['renderer_error'] = str(error)
            finally:
                window.destroy()
        webview.start(probe, gui='edgechromium', private_mode=True)
        from webview.platforms import winforms
        if system_browser:
            report['checks']['system_webview2'] = bool(winforms.is_chromium and not webview.settings['WEBVIEW2_RUNTIME_PATH'])
        else:
            report['checks']['fixed_runtime_without_installed_webview'] = bool(
                winforms.is_chromium and webview.settings['WEBVIEW2_RUNTIME_PATH'] == str(root/'webview2'))
        winreg.OpenKey = real_open
        # A real Tk window proves the fallback's Tcl/Tk DLLs also relocate.
        import tkinter
        tk = tkinter.Tk(); tk.withdraw(); tk.update(); tk.destroy()
        report['checks']['tk_window'] = True
        report['ok'] = report['bundled_python'] and all(report['checks'].values())
        exit_code = 0 if report['ok'] else 1
    except Exception:
        report['error'] = traceback.format_exc()
    Path(args.report).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return exit_code


def show_error():
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,
        'TouchHelm could not start. Check Windows security notifications and try a fresh download. '
        'If diagnostics were created, they are in LocalAppData\\TouchHelm\\desktop.log.', 'TouchHelm', 0x10)


def main():
    stream = None
    previous = sys.stdout, sys.stderr
    try:
        root, data = prepare()
        if '--self-test' in sys.argv:
            return self_test(root, data)
        # pythonw has no console. Keep diagnostics in the protected user directory.
        stream = open(data/'desktop.log', 'w', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = stream
        import main as application
        result = application.main()
        if result not in (None, 0):
            show_error()
            return int(result)
    except Exception:
        if sys.stderr is not None: traceback.print_exc()
        show_error()
        return 1
    finally:
        sys.stdout, sys.stderr = previous
        if stream is not None: stream.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
