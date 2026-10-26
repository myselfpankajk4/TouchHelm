"""Owned, temporary browser relay. Importing this module opens no network path.

The launcher is opt-in. Public authentication/routes belong to the caller; this
manager only owns the helper and short-lived pairing/session capabilities.
"""
import asyncio
import hashlib
import hmac
import inspect
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

from .portable import bundle_root

VERSION = '2026.10.3'
URL = f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-windows-amd64.exe'
HASH = '76b2805253d0d6ffacb092a7acfbee99e7af6917835c0c5410e23f3ef5052da2'
LICENSE_URL = f'https://raw.githubusercontent.com/cloudflare/cloudflared/{VERSION}/LICENSE'
LINK_TTL = 30 * 60
TICKET_TTL = 120
MAX_SESSIONS = 8
MAX_HELPER_BYTES = 96 * 1024 * 1024
_SECRET = re.compile(r'[A-Za-z0-9_-]{43}\Z')
_ASSIGNED_URL = re.compile(r'https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com(?=[\s|"<>]|$)')


class BrowserLinkError(RuntimeError):
    """Safe for user-visible error reporting: never contains helper output."""


def _private_root():
    from .secure_pairing import private_storage_root
    return private_storage_root()/'browser-link'


def _valid_helper(path):
    try:
        with Path(path).open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == HASH
    except OSError:
        return False


def _download(url, target):
    deadline = time.monotonic() + 90
    received = 0
    request = urllib.request.Request(url, headers={'User-Agent': 'TouchHelm-Browser-Link/' + VERSION})
    with urllib.request.urlopen(request, timeout=15) as source, Path(target).open('xb') as output:
        while True:
            if time.monotonic() >= deadline:
                raise BrowserLinkError('Browser helper download timed out. Check internet access and retry.')
            block = source.read(256 * 1024)
            if not block:
                break
            received += len(block)
            if received > MAX_HELPER_BYTES:
                raise BrowserLinkError('Browser helper download exceeded its size limit.')
            output.write(block)


def ensure_helper(*, cache_dir=None, downloader=None, protector=None):
    """Return a hash-verified bundled/cache helper; never run an installer.

    Optional seams permit offline packaging tests. A downloader writes only its
    supplied temporary target; its result is independently hash checked here.
    """
    bundle = bundle_root()
    if bundle is not None:
        bundled = bundle/'cloudflared/cloudflared.exe'
        if _valid_helper(bundled):
            return bundled
    cache = Path(cache_dir) if cache_dir is not None else _private_root()/'helper'/VERSION
    temporary = cache/('.download-' + uuid.uuid4().hex)
    try:
        cache.mkdir(parents=True, exist_ok=True)
        if protector is None:
            from .secure_pairing import protect_user_path
            protector = protect_user_path
        protector(cache)
        target = cache/'cloudflared.exe'
        if _valid_helper(target):
            return target
        (downloader or _download)(URL, temporary)
        if not _valid_helper(temporary):
            raise BrowserLinkError('Browser helper failed its integrity check. Retry the official download.')
        temporary.replace(target)
        return target
    except BrowserLinkError:
        raise
    except Exception:
        raise BrowserLinkError('Browser helper could not be prepared. Check internet access and Windows security notifications.') from None
    finally:
        temporary.unlink(missing_ok=True)


def _backend(value):
    try:
        if not isinstance(value, str) or any(char.isspace() for char in value):
            raise ValueError()
        parsed = urllib.parse.urlsplit(value)
        host = ipaddress.ip_address(parsed.hostname)
        if (parsed.scheme != 'http' or not host.is_loopback or parsed.username is not None
                or parsed.password is not None or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment or parsed.port is None or not 1 <= parsed.port <= 65535):
            raise ValueError()
        return f'http://{"["+str(host)+"]" if host.version == 6 else host}:{parsed.port}'
    except (ValueError, TypeError, AttributeError):
        raise BrowserLinkError('Browser link requires a dedicated loopback HTTP listener.') from None


def _environment(home):
    # Flags have many environment aliases. Construct an allowlist instead of
    # inheriting account tokens, proxy settings, logging destinations or ingress.
    keep = {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'COMSPEC', 'PATH', 'PATHEXT',
            'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE', 'PROCESSOR_IDENTIFIER'}
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    env.update(HOME=str(home), USERPROFILE=str(home), CFDPATH=str(home),
               APPDATA=str(home), LOCALAPPDATA=str(home), TEMP=str(home), TMP=str(home))
    return env


class BrowserLinkManager:
    def __init__(self, on_stopped=None, *, executable=None, clock=time.monotonic,
                 process_factory=None, helper_resolver=None, work_root=None,
                 startup_timeout=45, monitor_interval=.25):
        self.on_stopped = on_stopped
        self.executable = Path(executable) if executable is not None else None
        self.clock = clock
        self._factory = process_factory or asyncio.create_subprocess_exec
        self._helper_resolver = helper_resolver or ensure_helper
        self._work_root = Path(work_root) if work_root is not None else _private_root()/'runs'
        self._startup_timeout = startup_timeout
        self._monitor_interval = monitor_interval
        self._start_lock, self._stop_lock = asyncio.Lock(), asyncio.Lock()
        self._process = self._reader = self._monitor = self._workdir = None
        self._generation = 0
        self._active_link = False
        self._state, self._message = 'stopped', 'Browser link is off.'
        self._origin = self._candidate = None
        self._announced = self._registered = False
        self._deadline = self._ticket = None
        self._ticket_deadline = 0
        self._sessions = {}
        self._ready_event = asyncio.Event()

    def _revoke(self):
        self._ticket = None
        self._ticket_deadline = 0
        self._sessions.clear()

    def _ready(self):
        if self._deadline is not None and self.clock() >= self._deadline:
            self._revoke()
            self._state, self._message = 'stopped', 'Browser link expired. Create a new link on the PC.'
        alive = self._process is not None and self._process.returncode is None
        if not alive:
            self._revoke()
        return self._state == 'ready' and alive

    def snapshot(self):
        ready = self._ready()
        ticket = self._ticket if ready and self.clock() < self._ticket_deadline else None
        return {'state': self._state, 'ready': ready,
                'origin': self._origin if ready else None,
                'pairing_url': f'{self._origin}/#browser-link={ticket}' if ticket else None,
                'message': self._message,
                'expires_in': max(0, int(self._deadline-self.clock())) if ready else 0}

    def rotate_ticket(self):
        if self._ready():
            self._ticket = secrets.token_urlsafe(32)
            self._ticket_deadline = min(self.clock()+TICKET_TTL, self._deadline)
        return self.snapshot()

    def exchange(self, token):
        if (not self._ready() or not isinstance(token, str) or not _SECRET.fullmatch(token)
                or not self._ticket or self.clock() >= self._ticket_deadline
                or not hmac.compare_digest(token, self._ticket)):
            return None
        now = self.clock()
        self._sessions = {key: expires for key, expires in self._sessions.items() if expires > now}
        if len(self._sessions) >= MAX_SESSIONS:
            return None
        session = secrets.token_urlsafe(32)
        self._sessions[session] = self._deadline
        self.rotate_ticket()
        return session

    def valid_session(self, raw):
        return bool(self._ready() and isinstance(raw, str) and _SECRET.fullmatch(raw)
                    and self._sessions.get(raw, 0) > self.clock())

    async def start(self, backend_url):
        backend = _backend(backend_url)
        async with self._start_lock:
            if self._active_link or self._process is not None:
                await self.stop('Replaced by a new browser link.')
                if self._process is not None:
                    raise BrowserLinkError('The previous browser helper could not stop. Exit TouchHelm and retry.')
            self._generation += 1
            generation = self._generation
            self._active_link = True
            self._state, self._message = 'preparing', 'Preparing the verified browser helper…'
            self._origin = self._candidate = self._deadline = None
            self._announced = self._registered = False
            self._revoke()
            self._ready_event = asyncio.Event()
            try:
                helper = self.executable or await asyncio.to_thread(self._helper_resolver)
                if not _valid_helper(helper):
                    raise BrowserLinkError('Browser helper failed its integrity check. Download the current TouchHelm build.')
                if generation != self._generation:
                    raise BrowserLinkError('Browser link startup was stopped.')
                self._work_root.mkdir(parents=True, exist_ok=True)
                self._workdir = self._work_root/('link-' + uuid.uuid4().hex)
                self._workdir.mkdir()
                # Restrict production runs. Test roots inherit their owned temp ACL.
                if self._work_root == _private_root()/'runs':
                    from .secure_pairing import protect_user_path
                    protect_user_path(self._work_root)
                config = self._workdir/'empty.yml'
                config.write_text('{}\n', encoding='utf-8')
                args = [str(helper), 'tunnel', '--config', str(config), '--no-autoupdate',
                        '--protocol', 'http2', '--metrics', '127.0.0.1:0',
                        '--management-diagnostics=false', '--loglevel', 'info', '--output', 'json',
                        '--url', backend]
                self._state, self._message = 'starting', 'Connecting the temporary HTTPS browser link…'
                process = await self._factory(*args, cwd=self._workdir, env=_environment(self._workdir),
                    stdin=subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT, limit=8192,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if generation != self._generation:
                    await self._terminate(process)
                    raise BrowserLinkError('Browser link startup was stopped.')
                self._process = process
                self._reader = asyncio.create_task(self._read_output(generation))
                self._monitor = asyncio.create_task(self._watch(generation))
                await asyncio.wait_for(self._ready_event.wait(), self._startup_timeout)
                if not self._ready():
                    raise BrowserLinkError('Browser link could not start. Check internet access and retry.')
                return self.snapshot()
            except asyncio.CancelledError:
                if generation == self._generation:
                    await self.stop('Browser link startup cancelled.')
                raise
            except Exception:
                if generation == self._generation:
                    await self._shutdown('error', 'Browser link could not start. Check internet access and Windows security notifications.')
                raise BrowserLinkError('Browser link could not start. Check internet access and retry.') from None

    async def _read_output(self, generation):
        try:
            while generation == self._generation:
                line = await self._process.stdout.readline()
                if not line:
                    break
                if len(line) > 8192:
                    raise ValueError('Oversized helper line')
                text = line.decode('utf-8', errors='replace').strip()
                try:
                    record = json.loads(text)
                    if isinstance(record, dict):
                        text = str(record.get('message', record.get('msg', '')))
                except ValueError:
                    pass
                if 'Your quick Tunnel has been created!' in text:
                    self._announced = True
                if self._announced and self._candidate is None:
                    match = _ASSIGNED_URL.search(text)
                    if match:
                        self._candidate = match.group(0)
                if text.startswith('Registered tunnel connection'):
                    self._registered = True
                if self._candidate and self._registered and self._state == 'starting':
                    self._origin = self._candidate
                    self._deadline = self.clock()+LINK_TTL
                    self._state, self._message = 'ready', 'Temporary browser link ready. Internet is required throughout this session.'
                    self.rotate_ticket()
                    self._ready_event.set()
            if generation == self._generation:
                await self._shutdown('error', 'Browser link disconnected. Create a new link on the PC.')
        except asyncio.CancelledError:
            raise
        except Exception:
            if generation == self._generation:
                await self._shutdown('error', 'Browser helper stopped. Create a new link on the PC.')

    async def _watch(self, generation):
        while generation == self._generation:
            await asyncio.sleep(self._monitor_interval)
            if generation != self._generation:
                return
            if self._process.returncode is not None:
                await self._shutdown('error', 'Browser link disconnected. Create a new link on the PC.')
                return
            if self._deadline is not None and self.clock() >= self._deadline:
                await self._shutdown('stopped', 'Browser link expired. Create a new link on the PC.')
                return

    @staticmethod
    async def _terminate(process):
        if process is None or process.returncode is not None:
            return True
        try:
            process.terminate()
        except ProcessLookupError:
            return True
        except OSError:
            try:
                process.kill()
            except ProcessLookupError:
                return True
            except OSError:
                return False
        try:
            await asyncio.wait_for(process.wait(), 5)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                return True
            except OSError:
                return False
            try:
                await asyncio.wait_for(process.wait(), 3)
            except (asyncio.TimeoutError, OSError):
                return False
        return True

    async def stop(self, reason='Browser link is off.'):
        await self._shutdown('stopped', str(reason)[:180])

    async def _shutdown(self, state, message):
        notify = False
        async with self._stop_lock:
            if not self._active_link and self._process is None:
                return
            notify, self._active_link = self._active_link, False
            self._generation += 1
            self._state, self._message = state, message
            self._origin = self._candidate = self._deadline = None
            self._revoke()
            self._ready_event.set()
            current = asyncio.current_task()
            tasks = [task for task in (self._reader, self._monitor) if task is not None and task is not current]
            self._reader = self._monitor = None
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            process, self._process = self._process, None
            try:
                if not await self._terminate(process):
                    self._process = process
                    self._state, self._message = 'error', 'The browser helper could not stop. Exit TouchHelm and retry.'
            finally:
                folder, self._workdir = self._workdir, None
                if folder is not None and folder.exists():
                    # Only our generated immediate child may be removed.
                    if (folder.parent == self._work_root and re.fullmatch(r'link-[0-9a-f]{32}', folder.name)
                            and folder.resolve().parent == self._work_root.resolve()):
                        try:
                            shutil.rmtree(folder)
                        except OSError:
                            pass
        if notify and self.on_stopped is not None:
            try:
                result = self.on_stopped()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                # Revocation is already complete. Never expose callback details.
                pass
