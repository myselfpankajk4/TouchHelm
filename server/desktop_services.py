"""Asynchronous, bounded Windows context providers; remote callers use catalog IDs."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
MAX_MEDIA_ITEMS = 200
MEDIA_EXTENSIONS = {'.mp3', '.wav', '.flac', '.wma', '.aac', '.m4a', '.ogg',
                    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v', '.webm'}


class ProviderRequestCancelled(RuntimeError):
    pass


class PersistentPowerShellBridge:
    """One hidden, lazy JSON-lines helper. Timeouts discard the affected process."""
    def __init__(self, timeout=4.0):
        self.timeout = timeout
        self._lock = threading.Lock()
        self._proc = None
        self._responses = None
        self._sequence = 0
        self._closed = False

    def _start(self):
        if self._closed:
            raise RuntimeError('Windows providers are closed')
        if os.name != 'nt':
            raise RuntimeError('Windows desktop providers are unavailable on this platform')
        self._proc = subprocess.Popen(
            ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
             '-ExecutionPolicy', 'Bypass', '-File', str(Path(__file__).with_name('desktop_bridge.ps1'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW, cwd=str(ROOT))
        responses = self._responses = queue.Queue()
        process = self._proc

        def read_lines():
            try:
                for line in process.stdout:
                    try:
                        responses.put(json.loads(line))
                    except (ValueError, RecursionError):
                        continue
            finally:
                responses.put(None)

        threading.Thread(target=read_lines, name='TouchHelm desktop bridge', daemon=True).start()

    def _terminate(self):
        process, self._proc = self._proc, None
        self._responses = None
        if process is None:
            return
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            pass
        for stream in (process.stdin, process.stdout):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass

    def request(self, command, payload=None, *, cancelled=None):
        started = time.monotonic()
        if not self._lock.acquire(timeout=self.timeout):
            raise TimeoutError('Windows provider is busy; try again')
        try:
            if cancelled is not None and cancelled.is_set():
                raise ProviderRequestCancelled('Desktop command was cancelled')
            if self._closed:
                raise RuntimeError('Windows providers are closed')
            if self._proc is None or self._proc.poll() is not None:
                self._terminate()
                self._start()
            self._sequence += 1
            request_id = self._sequence
            if cancelled is not None and cancelled.is_set():
                raise ProviderRequestCancelled('Desktop command was cancelled')
            self._proc.stdin.write(json.dumps({'id': request_id, 'command': command,
                                               'payload': payload or {}}, ensure_ascii=True) + '\n')
            self._proc.stdin.flush()
            while True:
                remaining = self.timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('Windows provider timed out')
                try:
                    response = self._responses.get(timeout=remaining)
                except queue.Empty as error:
                    raise TimeoutError('Windows provider timed out') from error
                if response is None:
                    raise RuntimeError('Windows provider exited unexpectedly')
                if not isinstance(response, dict) or response.get('id') != request_id:
                    continue
                if 'error' in response:
                    raise RuntimeError(str(response['error']))
                return response.get('result', {})
        except ProviderRequestCancelled:
            # A queued cancellation owns no active helper request; keep the
            # healthy process used by other clients alive.
            raise
        except Exception:
            self._terminate()
            raise
        finally:
            self._lock.release()

    def close(self):
        self._closed = True
        # Killing a blocked provider also wakes its waiting reader/request.
        self._terminate()


def _presentation(message='No supported presentation context is available.'):
    return dict(available=False, app='', title='', active=False, slide=None,
                total=None, slide_title='', message=message)


def _media(message='No active Windows media session is available.'):
    return dict(available=False, session_id='', app='', title='', artist='', album='',
                status='unavailable', position=None, duration=None, message=message, sessions=[])


def _default_media_dirs():
    directories = [Path.home() / 'Music', Path.home() / 'Videos']
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                for name in ('My Music', 'My Video'):
                    try:
                        value = os.path.expandvars(winreg.QueryValueEx(key, name)[0])
                        directories.append(Path(value))
                    except OSError:
                        pass
        except OSError:
            pass
    return list(dict.fromkeys(directories))


class DesktopServices:
    def __init__(self, *, bridge=None, usage_file=None, media_dirs=None, timeout=4.0):
        self.timeout = timeout
        self._bridge = bridge if bridge is not None else PersistentPowerShellBridge(timeout)
        self._usage_file = Path(usage_file) if usage_file is not None else ROOT / '.touchhelm_usage.json'
        self._media_dirs = media_dirs
        self._usage = None
        self._usage_lock = threading.Lock()
        self._apps = {}
        self._apps_at = 0.
        self._media_catalog = {}
        self._sessions = {}
        self._closed = False

    async def _call(self, command, payload=None):
        if self._closed:
            raise RuntimeError('Windows providers are closed')
        cancelled = threading.Event()
        try:
            result = await asyncio.wait_for(asyncio.to_thread(self._bridge.request, command, payload,
                                                             cancelled=cancelled), self.timeout + .1)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except asyncio.TimeoutError as error:
            cancelled.set()
            raise TimeoutError('Windows provider timed out') from error
        if not isinstance(result, dict):
            raise RuntimeError('Windows provider returned an invalid response')
        return result

    async def snapshot(self):
        try:
            state = await self._call('snapshot')
            presentation, media = _presentation(), _media()
            presentation.update({k: v for k, v in state.get('presentation', {}).items() if k in presentation})
            media.update({k: v for k, v in state.get('media', {}).items() if k in media})
            return {'presentation': presentation, 'media': media}
        except Exception as error:
            message = str(error) or 'Windows provider timed out'
            return {'presentation': _presentation(message), 'media': _media(message)}

    def _load_usage(self):
        if self._usage is not None:
            return
        with self._usage_lock:
            if self._usage is not None:
                return
            try:
                if self._usage_file.stat().st_size > 128 * 1024:
                    raise ValueError('Usage history exceeds its size limit')
                saved = json.loads(self._usage_file.read_text(encoding='utf-8'))
                self._usage = {key: value for key, value in saved.items()
                               if isinstance(key, str) and type(value) is int and value >= 0}
            except (OSError, ValueError, AttributeError):
                self._usage = {}

    async def list_apps(self):
        if self._closed:
            return []
        try:
            result = await self._call('apps')
            self._apps = {app['id']: {'id': app['id'], 'name': app['name'], 'running': bool(app.get('running', False))}
                          for app in result.get('apps', [])
                          if isinstance(app, dict) and isinstance(app.get('id'), str)
                          and isinstance(app.get('name'), str) and app['id'] and app['name']}
            self._apps_at = time.monotonic()
            await asyncio.wait_for(asyncio.to_thread(self._load_usage), self.timeout)
        except Exception:
            # Existing catalog entries remain valid if Windows temporarily fails.
            if not self._apps:
                return []
        apps = [dict(app, launches=(self._usage or {}).get(app['id'], 0)) for app in self._apps.values()]
        return sorted(apps, key=lambda app: (not app['running'], -app['launches'], app['name'].casefold(), app['id']))

    def _record_launch(self, app_id):
        self._load_usage()
        with self._usage_lock:
            self._usage[app_id] = self._usage.get(app_id, 0) + 1
            self._usage_file.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(dir=self._usage_file.parent, suffix='.tmp')
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                    json.dump(self._usage, stream, indent=2)
                os.replace(temporary, self._usage_file)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    async def launch_app(self, app_id):
        if not isinstance(app_id, str) or not app_id or len(app_id) > 512 or self._closed:
            return {'success': False, 'message': 'Choose an app from the Windows catalog.'}
        if not self._apps or time.monotonic() - self._apps_at > 30:
            await self.list_apps()
        if app_id not in self._apps:
            return {'success': False, 'message': 'This app is not in the current Windows catalog. Refresh Apps.'}
        try:
            result = await self._call('launch_app', {'app_id': app_id})
            if result.get('success'):
                try:
                    await asyncio.wait_for(asyncio.to_thread(self._record_launch, app_id), self.timeout)
                except Exception:
                    return {'success': True, 'message': 'App requested; launch history could not be saved.'}
            return {'success': bool(result.get('success')), 'message': str(result.get('message', 'App request failed.'))}
        except Exception as error:
            return {'success': False, 'message': str(error)}

    def _scan_media(self):
        result = {}
        deadline = time.monotonic() + min(self.timeout, 2.)
        folders = self._media_dirs if self._media_dirs is not None else _default_media_dirs()
        visited = 0
        for directory in folders:
            directory = Path(directory).absolute()
            if str(directory).startswith('\\\\'):
                continue
            for folder, subdirs, files in os.walk(directory, followlinks=False):
                visited += 1
                subdirs[:] = sorted(name for name in subdirs
                                    if not os.path.islink(os.path.join(folder, name))
                                    and not getattr(os.path, 'isjunction', lambda _: False)(os.path.join(folder, name)))
                if len(Path(folder).relative_to(directory).parts) >= 5:
                    subdirs.clear()
                for name in sorted(files, key=str.casefold):
                    if time.monotonic() > deadline or len(result) >= MAX_MEDIA_ITEMS or visited > 500:
                        return result
                    path = Path(folder) / name
                    if path.suffix.lower() not in MEDIA_EXTENSIONS or path.is_symlink():
                        continue
                    identifier = 'local:' + hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:24]
                    result[identifier] = {'id': identifier, 'title': path.stem,
                                          'subtitle': str(path.parent.name), 'kind': 'local', 'path': str(path)}
        return result

    async def list_media(self):
        native = {'sessions': [], 'items': [], 'playlist_supported': False,
                  'playlist_message': 'Windows media sessions do not expose a player queue.'}
        if self._closed:
            return dict(native, playlist_message='Windows providers are closed')
        try:
            native.update(await self._call('media_library'))
        except Exception as error:
            native['playlist_message'] = str(error)
        try:
            local = await asyncio.wait_for(asyncio.to_thread(self._scan_media), self.timeout)
        except Exception:
            local = {}
        self._sessions = {session.get('id', session.get('session_id')): session
                          for session in native.get('sessions', []) if isinstance(session, dict)
                          and isinstance(session.get('id', session.get('session_id')), str)}
        catalog = {item['id']: dict(item) for item in native.get('items', [])
                   if isinstance(item, dict) and isinstance(item.get('id'), str)
                   and item.get('kind') == 'queue'}
        for identifier, session in self._sessions.items():
            item_id = 'session:' + identifier
            catalog[item_id] = {'id': item_id, 'title': session.get('title') or session.get('app', 'Current player'),
                                'subtitle': session.get('artist') or session.get('app', ''),
                                'kind': 'session', 'session_id': identifier}
        catalog.update(local)
        self._media_catalog = catalog
        items = [{key: item.get(key, '') for key in ('id', 'title', 'subtitle', 'kind')}
                 for item in list(catalog.values())[:MAX_MEDIA_ITEMS]]
        message = str(native.get('playlist_message', ''))
        if not native.get('playlist_supported'):
            message += ' Current sessions and local Music/Videos files are shown when available.'
        return {'sessions': list(self._sessions.values()), 'items': items,
                'playlist_supported': bool(native.get('playlist_supported')), 'playlist_message': message.strip()}

    async def media_command(self, action, session_id='', item_id=''):
        aliases = {'playpause': 'play_pause', 'previous': 'prev', 'nexttrack': 'next', 'prevtrack': 'prev'}
        if not isinstance(action, str):
            return {'success': False, 'message': 'Unsupported media action.', 'handled': False}
        action = aliases.get(action, action)
        if action not in ('play_pause', 'play', 'pause', 'next', 'prev', 'stop'):
            return {'success': False, 'message': 'Unsupported media action.', 'handled': False}
        if not isinstance(session_id, str) or not isinstance(item_id, str):
            return {'success': False, 'message': 'Choose a valid player or media item.', 'handled': True}
        try:
            if item_id:
                item = self._media_catalog.get(item_id)
                if item is None or action != 'play':
                    return {'success': False, 'message': 'Refresh the media list and choose an item.', 'handled': True}
                payload = {'kind': item['kind'], 'item_id': item_id}
                if item['kind'] == 'local':
                    payload['path'] = item['path']
                elif item['kind'] == 'session':
                    payload['session_id'] = item['session_id']
                result = await self._call('media_play', payload)
            else:
                if session_id and session_id not in self._sessions:
                    await self.list_media()
                    if session_id not in self._sessions:
                        return {'success': False, 'message': 'This player is no longer available.', 'handled': True}
                result = await self._call('media_command', {'action': action, 'session_id': session_id})
            return {'success': bool(result.get('success')), 'message': str(result.get('message', 'Media action unavailable.')),
                    'handled': bool(result.get('handled', False))}
        except Exception as error:
            return {'success': False, 'message': str(error), 'handled': bool(session_id or item_id)}

    async def presentation_command(self, action):
        aliases = {'slide_next': 'next', 'previous': 'prev', 'slide_prev': 'prev',
                   'slide_start': 'start', 'slide_current': 'start_current', 'current': 'start_current',
                   'slide_end': 'end', 'exit': 'end', 'slide_black': 'black', 'slide_white': 'white'}
        if not isinstance(action, str):
            return {'success': False, 'message': 'Unsupported presentation action.', 'handled': False}
        action = aliases.get(action, action)
        if action not in ('next', 'prev', 'start', 'start_current', 'end', 'black', 'white'):
            return {'success': False, 'message': 'Unsupported presentation action.', 'handled': False}
        try:
            result = await self._call('presentation_command', {'action': action})
            return {'success': bool(result.get('success')), 'message': str(result.get('message', '')),
                    'handled': bool(result.get('handled', False))}
        except Exception as error:
            return {'success': False, 'message': str(error), 'handled': False}

    async def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            await asyncio.wait_for(asyncio.to_thread(self._bridge.close), min(self.timeout, 1.))
        except Exception:
            pass
