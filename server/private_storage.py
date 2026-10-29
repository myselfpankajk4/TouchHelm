"""Per-user private storage location and owner-only ACLs."""
import csv
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import subprocess


class PrivateStorageError(RuntimeError):
    pass


def private_storage_root():
    local = os.environ.get('LOCALAPPDATA')
    return Path(local) / 'TouchHelm' if local else Path.home() / '.touchhelm'


def protect_user_path(path):
    """Replace, rather than extend, the DACL: only the current user has access."""
    path = Path(path)
    if os.name != 'nt':
        path.chmod(0o700 if path.is_dir() else 0o600)
        return
    result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
        capture_output=True, text=True, timeout=3, check=True, creationflags=0x08000000)
    rows = list(csv.reader(result.stdout.splitlines()))
    sid = rows[0][-1].strip() if rows else ''
    if not re.fullmatch(r'S-1-\d+(?:-\d+)+', sid):
        raise PrivateStorageError('Windows could not identify the private folder owner.')
    api, kernel = ctypes.windll.advapi32, ctypes.windll.kernel32
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    api.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    api.SetFileSecurityW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f'D:P(A;OICI;FA;;;{sid})', 1, ctypes.byref(descriptor), None):
        raise PrivateStorageError('Windows could not create a private folder ACL.')
    try:
        if not api.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise PrivateStorageError('Windows could not protect the private folder.')
    finally:
        kernel.LocalFree(descriptor)
