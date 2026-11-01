"""Opt-in Windows lifecycle test using the real installed launcher and a fake host.

Does not start a TouchHelm server or open a camera. Requires .NET Framework csc.
"""
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    root = Path(__file__).resolve().parents[1]
    compiler = Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenMutexW.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_wchar_p]
    api.OpenMutexW.restype = ctypes.c_void_p
    api.CloseHandle.argtypes = [ctypes.c_void_p]

    def mutex_exists():
        handle = api.OpenMutexW(0x00100000, False, 'Local\\TouchHelm.Desktop')
        if handle:
            api.CloseHandle(handle)
        return bool(handle)

    assert not mutex_exists(), 'Exit the installed TouchHelm app before this check'
    with tempfile.TemporaryDirectory(prefix='TouchHelmLauncher-') as folder:
        stage = Path(folder)
        (stage/'runtime').mkdir()
        (stage/'app').mkdir()
        (stage/'installed.json').write_text('{}')
        fake = stage/'FakeHost.cs'
        fake.write_text('''using System;using System.IO;using System.Threading;
class FakeHost {static void Main(string[] args) {
 string root=Path.GetDirectoryName(Path.GetDirectoryName(typeof(FakeHost).Assembly.Location));
 if(Environment.CommandLine.Contains("portable_setup.py")){
 File.WriteAllText(Path.Combine(root,"preparing"),"");Thread.Sleep(900);return;}
 File.WriteAllText(Path.Combine(root,"started"),"");Thread.Sleep(3500);
 File.WriteAllText(Path.Combine(root,"finished"),"");}}''')
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        subprocess.run([str(compiler), '/nologo', '/target:winexe',
            '/out:'+str(stage/'runtime/python.exe'), str(fake)], check=True, creationflags=flags)
        (stage/'runtime/pythonw.exe').write_bytes((stage/'runtime/python.exe').read_bytes())
        generated = stage/'Launcher.cs'
        generated.write_text((root/'packaging/PortableLauncher.cs').read_text()
            .replace('@@PAYLOAD_HASH@@', '').replace('@@PAYLOAD_LENGTH@@', '0'))
        subprocess.run([str(compiler), '/nologo', '/define:INSTALLED', '/target:winexe',
            '/out:'+str(stage/'TouchHelm.exe'), '/r:System.IO.Compression.dll',
            '/r:System.IO.Compression.FileSystem.dll', '/r:System.Windows.Forms.dll',
            '/r:System.Drawing.dll', '/r:System.Web.Extensions.dll', str(generated)],
            check=True, creationflags=flags)
        process = subprocess.Popen([str(stage/'TouchHelm.exe')], creationflags=flags)
        try:
            deadline = time.monotonic()+8
            while not (stage/'preparing').exists() and time.monotonic()<deadline:
                time.sleep(.05)
            assert mutex_exists(), 'First-launch preparation is running without its uninstall guard'
            while not (stage/'started').exists() and time.monotonic()<deadline:
                time.sleep(.05)
            assert (stage/'started').exists(), 'Fixture host did not start'
            assert mutex_exists(), 'Installed host is running without its uninstall guard'
            assert process.poll() is None, 'Launcher detached and released its lifecycle handle'
        finally:
            deadline = time.monotonic()+8
            while not (stage/'finished').exists() and time.monotonic()<deadline:
                time.sleep(.05)
            process.wait(timeout=5)
        assert not mutex_exists(), 'Guard was not released after the host exited'
    print('Installed launcher guards preparation and host lifetime: PASS')


if __name__ == '__main__':
    main()
