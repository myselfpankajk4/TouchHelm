"""App-local OpenMP provider from a pinned, Microsoft-signed redistributable.

Extraction only: the Microsoft installer is never executed on the build host or
tester's PC. DXcam's native numpy kernels import VCOMP140.DLL by its normal name.
"""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import urllib.request

import build_portable as base

URL = ('https://download.visualstudio.microsoft.com/download/pr/'
    'ebdab8e5-1d7b-4d9f-a11b-cbb1720c3b12/'
    '843068991DAAA1F73AD9F6239BCE4D0F6A07A51F18C37EA2A867E9BECA71295C/VC_redist.x64.exe')
REDIST_SHA = '843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c'
DLL_SHA = '95d4ce4a6802d1e18b5e0e1722cc30ea72ca7e033f83828f05c0b7b993fe7cbf'


def verify_microsoft(path):
    quoted = str(path).replace("'", "''")
    script = ("Import-Module ($PSHOME+'\\Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1'); "
        "$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath '"+quoted+"'; "
        "if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)'){exit 1}")
    shell = Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command', script], check=True)


def ensure_openmp(cache):
    cache = Path(cache)
    dll = cache/'vcomp140.dll'
    if not dll.is_file() or base.sha(dll) != DLL_SHA:
        source = cache/'vc_redist.x64.exe'
        if not source.is_file() or base.sha(source) != REDIST_SHA:
            temporary = cache/'vc_redist.x64.download'
            urllib.request.urlretrieve(URL, temporary)
            if base.sha(temporary) != REDIST_SHA:
                raise RuntimeError('Microsoft C++ redistributable hash mismatch')
            temporary.replace(source)
        verify_microsoft(source)
        data = source.read_bytes()
        # This exact, pinned WiX bundle has two attached cabinets. Validate each
        # cabinet header rather than trusting incidental MSCF strings in its PE.
        cabinets = []
        offset = 0
        while True:
            offset = data.find(b'MSCF', offset)
            if offset < 0:
                break
            if offset+36 <= len(data):
                size = struct.unpack_from('<I', data, offset+8)[0]
                if data[offset+4:offset+8] == b'\0'*4 and data[offset+24:offset+26] == b'\x03\x01' and 36 < size <= len(data)-offset:
                    cabinets.append(data[offset:offset+size])
            offset += 4
        if len(cabinets) != 2:
            raise RuntimeError('Unexpected Microsoft redistributable layout')
        with tempfile.TemporaryDirectory(prefix='openmp-', dir=cache) as folder:
            folder = Path(folder)
            cabinet = folder/'payload.cab'
            cabinet.write_bytes(cabinets[1])
            expand = Path(os.environ['WINDIR'])/'System32/expand.exe'
            subprocess.run([str(expand), '-F:a4', str(cabinet), str(folder)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run([str(expand), '-F:vcomp140.dll_amd64', str(folder/'a4'), str(folder)], check=True, stdout=subprocess.DEVNULL)
            extracted = folder/'vcomp140.dll_amd64'
            if base.sha(extracted) != DLL_SHA:
                raise RuntimeError('Microsoft OpenMP DLL hash mismatch')
            shutil.copy2(extracted, dll)
    verify_microsoft(dll)
    return dll, {'version': '14.51.36247.0', 'source': URL, 'source_sha256': REDIST_SHA,
                 'file': 'runtime/vcomp140.dll', 'sha256': DLL_SHA, 'microsoft_signature_valid': True}
