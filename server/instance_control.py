"""Per-user named mutex and authenticated loopback activation/restart IPC."""
import ctypes
from ctypes import wintypes
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import tempfile
import threading
import time

from .secure_pairing import private_storage_root, protect_user_path


def source_build_id(root):
    """Source identity includes native Python changes, not just browser assets."""
    root = Path(root)
    files = [root / name for name in ('main.py', 'run.bat', 'requirements.txt', 'requirements-remote.txt')]
    suffixes = {'.py', '.js', '.css', '.html', '.json', '.svg', '.ps1', '.cs',
                '.ico', '.png', '.webp', '.jpg', '.jpeg', '.woff2', '.woff', '.ttf', '.otf'}
    for folder in ('server', 'gui', 'web', 'assets'):
        files.extend(path for path in (root / folder).rglob('*')
            if path.is_file() and path.suffix.lower() in suffixes
            and '__pycache__' not in path.parts
            and not path.relative_to(root).as_posix().startswith('assets/theme/review/')
            and not (folder == 'assets' and path.suffix.lower() == '.json'))
    digest = hashlib.sha256()
    for path in sorted(set(files)):
        if path.exists():
            digest.update(path.relative_to(root).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()[:32]


class WindowsMutex:
    def __init__(self):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.api.CreateMutexW.restype = wintypes.HANDLE
        self.api.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.api.ReleaseMutex.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL

    def create(self, name):
        ctypes.set_last_error(0)
        handle = self.api.CreateMutexW(None, True, name)
        error = ctypes.get_last_error()
        if not handle:
            raise OSError(error, 'Unable to create the TouchHelm instance mutex')
        return handle, error == 183

    def release(self, handle):
        self.api.ReleaseMutex(handle)

    def close(self, handle):
        self.api.CloseHandle(handle)


class InstanceController:
    def __init__(self, build_id, *, source_root=None, storage_dir=None, mutex=None,
                 protector=protect_user_path):
        self.build_id = build_id
        self.source_root = Path(source_root or Path(__file__).resolve().parents[1]).resolve()
        self.storage_dir = Path(storage_dir) if storage_dir is not None else private_storage_root() / 'instance'
        self.metadata_path = self.storage_dir / 'instance.json'
        self.token = secrets.token_urlsafe(32)
        username = f'{os.environ.get("USERDOMAIN", "")}\\{getpass.getuser()}'
        self.mutex_name = 'Local\\TouchHelm-' + hashlib.sha256(username.casefold().encode()).hexdigest()[:24]
        self._mutex = mutex
        self._handle = None
        self._protector = protector
        self._server = None
        self._thread = None
        self._lock = threading.RLock()
        self._restart_requested = False
        self._closing = False
        self.on_restore = lambda: None
        self.on_stop = lambda: None

    def acquire(self):
        if self._handle is not None:
            return True
        if self._mutex is None:
            if os.name != 'nt':
                raise RuntimeError('TouchHelm instance control requires Windows')
            self._mutex = WindowsMutex()
        handle, existed = self._mutex.create(self.mutex_name)
        if existed:
            self._mutex.close(handle)
            return False
        self._handle = handle
        return True

    def _process_request(self, data):
        if not isinstance(data, dict) or not isinstance(data.get('token'), str) or not data['token'].isascii() or not hmac.compare_digest(data['token'], self.token):
            return {'success': False, 'error': 'Unauthorized instance request'}
        build = data.get('build')
        if not isinstance(build, str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,64}', build):
            return {'success': False, 'error': 'Invalid source build'}
        with self._lock:
            if self._handle is None or self._closing:
                return {'success': False, 'error': 'Instance is no longer active'}
            if build == self.build_id and not self._restart_requested:
                self.on_restore()
                return {'success': True, 'action': 'restored'}
            if not self._restart_requested:
                self._restart_requested = True
                self.on_stop()
            return {'success': True, 'action': 'restarting'}

    def start(self, on_restore, on_stop):
        if self._handle is None or self._closing:
            raise RuntimeError('Only the owning instance may open IPC')
        self.on_restore, self.on_stop = on_restore, on_stop
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(2)
                try:
                    raw = self.rfile.readline(8193)
                    if len(raw) > 8192:
                        return
                    response = owner._process_request(json.loads(raw))
                    self.wfile.write((json.dumps(response) + '\n').encode())
                except (ValueError, UnicodeError, OSError):
                    return

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._protector(self.storage_dir)
        self._server = Server(('127.0.0.1', 0), Handler)
        metadata = {'protocol': 1, 'port': self._server.server_address[1], 'token': self.token,
                    'build': self.build_id, 'source_root': str(self.source_root)}
        descriptor, temporary = tempfile.mkstemp(dir=self.storage_dir, suffix='.tmp')
        try:
            self._protector(Path(temporary))
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                descriptor = None
                json.dump(metadata, stream)
            os.replace(temporary, self.metadata_path)
            self._protector(self.metadata_path)
        except Exception:
            self._server.server_close()
            self._server = None
            raise
        finally:
            if descriptor is not None: os.close(descriptor)
            if os.path.exists(temporary): os.unlink(temporary)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True,
                                        name='TouchHelm instance IPC')
        self._thread.start()

    def handoff(self, timeout=10):
        """Activate an owned host, or await its graceful release before taking over."""
        deadline = time.monotonic() + timeout
        response = None
        while time.monotonic() < deadline:
            # A previous owner may exit, or another launcher may win the race.
            # Re-check both ownership and the current authenticated IPC record.
            if self.acquire():
                return 'acquired'
            try:
                metadata = json.loads(self.metadata_path.read_text(encoding='utf-8'))
                port, token = metadata.get('port'), metadata.get('token')
                if metadata.get('protocol') != 1 or type(port) is not int or not 1 <= port <= 65535 or not isinstance(token, str) or len(token) < 32:
                    raise ValueError('Invalid local instance record')
                with socket.create_connection(('127.0.0.1', port), timeout=1) as channel:
                    channel.settimeout(2)
                    channel.sendall((json.dumps({'token': token, 'build': self.build_id}) + '\n').encode())
                    with channel.makefile('rb') as stream:
                        raw = stream.readline(8193)
                    response = json.loads(raw) if len(raw) <= 8192 else None
                if not isinstance(response, dict) or not response.get('success'):
                    return 'unavailable'
                if response.get('action') == 'restored':
                    return 'restored'
                if response.get('action') != 'restarting':
                    return 'unavailable'
                time.sleep(.1)
            except (OSError, ValueError):
                # Startup may own the mutex before its authenticated IPC is ready.
                time.sleep(.1)
        return 'unavailable'

    def close(self):
        with self._lock:
            self._closing = True
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
            self._thread = None
        with self._lock:
            if self._handle is None:
                return
            try:
                if json.loads(self.metadata_path.read_text(encoding='utf-8')).get('token') == self.token:
                    self.metadata_path.unlink()
            except (OSError, ValueError):
                pass
            handle, self._handle = self._handle, None
            self._mutex.release(handle)
            self._mutex.close(handle)
