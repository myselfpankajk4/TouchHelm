"""Asynchronous, bounded Windows context providers; remote callers use catalog IDs."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import math
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

from .asset_store import AssetStore


ROOT = Path(__file__).resolve().parents[1]
MAX_MEDIA_ITEMS = 200


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
                total=None, slide_title='', message=message, capabilities={}, display=None)


def _media(message='No active Windows media session is available.'):
    return dict(available=False, session_id='', app='', title='', artist='', album='',
                genre=[], track=None, album_tracks=None, artwork_id=None,
                status='unavailable', position=None, duration=None, min_seek=None, max_seek=None,
                playback_rate=None, shuffle=None, repeat=None, updated_at=time.time(),
                capabilities={key: False for key in
                              ('play', 'pause', 'play_pause', 'next', 'prev', 'stop', 'seek', 'shuffle', 'repeat', 'rate')},
                message=message, sessions=[])


class DesktopServices:
    def __init__(self, *, bridge=None, usage_file=None, media_dirs=None, timeout=4.0, assets=None):
        self.timeout = timeout
        self._bridge = bridge if bridge is not None else PersistentPowerShellBridge(timeout)
        self._usage_file = Path(usage_file) if usage_file is not None else ROOT / '.touchhelm_usage.json'
        self.assets = assets if assets is not None else AssetStore()
        self._legacy_usage = ROOT / '.phonepad_usage.json' if usage_file is None else None
        self._usage = None
        self._pinned = set()
        self._usage_lock = threading.Lock()
        self._apps = {}
        self._apps_at = 0.
        self._media_catalog = {}
        self._sessions = {}
        self._current_session = ''
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
        return await asyncio.to_thread(self._normalize_assets, result)

    def _normalize_assets(self, value):
        if isinstance(value, list):
            return [self._normalize_assets(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key in ('artwork_data', 'icon_data', 'preview_data'):
                target = 'icon_id' if key == 'icon_data' else 'artwork_id'
                result[target] = None
                if isinstance(item, str) and len(item) <= 6 * 1024 * 1024:
                    try:
                        result[target] = self.assets.put(base64.b64decode(item, validate=True))
                    except ValueError:
                        pass
            else:
                if key in ('artwork_id', 'icon_id') and key in result:
                    continue
                result[key] = self._normalize_assets(item)
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
                source = self._usage_file
                if not source.exists() and self._legacy_usage and self._legacy_usage.exists():
                    source = self._legacy_usage
                if source.stat().st_size > 128 * 1024:
                    raise ValueError('Usage history exceeds its size limit')
                saved = json.loads(source.read_text(encoding='utf-8'))
                if not isinstance(saved, dict):
                    raise ValueError('Usage history must be an object')
                counts = saved.get('launches', saved)
                if not isinstance(counts, dict):
                    counts = {}
                self._usage = {key: value for key, value in counts.items()
                               if isinstance(key, str) and type(value) is int and value >= 0}
                pins = saved.get('pinned', [])
                self._pinned = {key for key in pins if isinstance(key, str)} if isinstance(pins, list) else set()
            except (OSError, ValueError, AttributeError):
                self._usage = {}

    async def list_apps(self):
        if self._closed:
            return []
        try:
            result = await self._call('apps')
            if result.get('icons_pending'):
                try:
                    result = await self._call('apps')
                except Exception:
                    pass  # Keep the valid first-pass catalog if icons time out.
            self._apps = {app['id']: {'id': app['id'], 'name': app['name'],
                                     'running': bool(app.get('windows')), 'icon_id': app.get('icon_id'),
                                     'windows': [{'id': window['id'], 'title': str(window.get('title', ''))}
                                                 for window in app.get('windows', []) if isinstance(window, dict)
                                                 and isinstance(window.get('id'), str)]}
                          for app in result.get('apps', [])
                          if isinstance(app, dict) and isinstance(app.get('id'), str)
                          and isinstance(app.get('name'), str) and app['id'] and app['name']}
            self._apps_at = time.monotonic()
            await asyncio.wait_for(asyncio.to_thread(self._load_usage), self.timeout)
        except Exception:
            # Existing catalog entries remain valid if Windows temporarily fails.
            if not self._apps:
                return []
        apps = [dict(app, launches=(self._usage or {}).get(app['id'], 0), pinned=app['id'] in self._pinned)
                for app in self._apps.values()]
        return sorted(apps, key=lambda app: (not app['pinned'], not app['running'], -app['launches'], app['name'].casefold(), app['id']))

    def _save_usage(self):
        self._usage_file.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=self._usage_file.parent, suffix='.tmp')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump({'version': 2, 'launches': self._usage, 'pinned': sorted(self._pinned)}, stream, indent=2)
            os.replace(temporary, self._usage_file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _record_launch(self, app_id):
        self._load_usage()
        with self._usage_lock:
            self._usage[app_id] = self._usage.get(app_id, 0) + 1
            self._save_usage()

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

    async def list_media(self):
        native = {'sessions': [], 'items': [], 'playlist_supported': False,
                  'playlist_message': 'Windows media sessions do not expose a player queue.'}
        if self._closed:
            return dict(native, playlist_message='Windows providers are closed')
        try:
            native.update(await self._call('media_library'))
        except Exception as error:
            native['playlist_message'] = str(error)
        self._current_session = native.get('current', {}).get('session_id', '')
        self._sessions = {session.get('id', session.get('session_id')): session
                          for session in native.get('sessions', []) if isinstance(session, dict)
                          and isinstance(session.get('id', session.get('session_id')), str)}
        catalog = {item['id']: dict(item) for item in native.get('items', [])
                   if isinstance(item, dict) and isinstance(item.get('id'), str)
                   and item.get('kind') == 'queue'}
        if not native.get('playlist_supported'):
            catalog = {}
        self._media_catalog = dict(list(catalog.items())[:MAX_MEDIA_ITEMS])
        items = [{key: item.get(key, '') for key in ('id', 'title', 'subtitle', 'kind')}
                 for item in list(catalog.values())[:MAX_MEDIA_ITEMS]]
        message = str(native.get('playlist_message', ''))
        return {'sessions': list(self._sessions.values()), 'items': items,
                'playlist_supported': bool(native.get('playlist_supported')), 'playlist_message': message.strip()}

    async def media_command(self, action, session_id='', item_id='', value=None):
        aliases = {'playpause': 'play_pause', 'previous': 'prev', 'nexttrack': 'next', 'prevtrack': 'prev'}
        if not isinstance(action, str):
            return {'success': False, 'message': 'Unsupported media action.', 'handled': False}
        action = aliases.get(action, action)
        if action not in ('play_pause', 'play', 'pause', 'next', 'prev', 'stop', 'seek', 'shuffle', 'repeat', 'rate'):
            return {'success': False, 'message': 'Unsupported media action.', 'handled': False}
        if not isinstance(session_id, str) or not isinstance(item_id, str):
            return {'success': False, 'message': 'Choose a valid player or media item.', 'handled': True}
        advanced = action in ('seek', 'shuffle', 'repeat', 'rate')
        valid = (action == 'seek' and type(value) in (int, float) and math.isfinite(value) and value >= 0 or
                 action == 'shuffle' and type(value) is bool or
                 action == 'repeat' and value in ('none', 'track', 'list') or
                 action == 'rate' and type(value) in (int, float) and math.isfinite(value) and .25 <= value <= 4)
        if advanced and not valid:
            return {'success': False, 'message': 'Choose a valid media value.', 'handled': True}
        try:
            if item_id:
                item = self._media_catalog.get(item_id)
                if item is None or action != 'play':
                    return {'success': False, 'message': 'Refresh the media list and choose an item.', 'handled': True}
                payload = {'kind': item['kind'], 'item_id': item_id}
                result = await self._call('media_play', payload)
            else:
                if advanced or session_id:
                    await self.list_media()
                    if not session_id:
                        session_id = self._current_session
                    if session_id not in self._sessions:
                        return {'success': False, 'message': 'This player is no longer available.', 'handled': True}
                    session = self._sessions[session_id]
                    capabilities = session.get('capabilities', {})
                    if not capabilities.get(action, False):
                        return {'success': False, 'message': 'This player does not support that action.', 'handled': True}
                    if action == 'seek':
                        low, high = session.get('min_seek'), session.get('max_seek')
                        if type(low) not in (int, float) or type(high) not in (int, float) or not low <= value <= high:
                            return {'success': False, 'message': 'Seek is outside the current player timeline.', 'handled': True}
                payload = {'action': action, 'session_id': session_id}
                if advanced:
                    payload['value'] = value
                result = await self._call('media_command', payload)
            return {'success': bool(result.get('success')), 'message': str(result.get('message', 'Media action unavailable.')),
                    'handled': bool(result.get('handled', False))}
        except Exception as error:
            return {'success': False, 'message': str(error), 'handled': bool(session_id or item_id)}

    async def presentation_command(self, action, slide=None):
        aliases = {'slide_next': 'next', 'previous': 'prev', 'slide_prev': 'prev',
                   'slide_start': 'start', 'slide_current': 'start_current', 'current': 'start_current',
                   'slide_end': 'end', 'exit': 'end', 'slide_black': 'black', 'slide_white': 'white'}
        if not isinstance(action, str):
            return {'success': False, 'message': 'Unsupported presentation action.', 'handled': False}
        action = aliases.get(action, action)
        if action not in ('next', 'prev', 'start', 'start_current', 'end', 'black', 'white', 'goto'):
            return {'success': False, 'message': 'Unsupported presentation action.', 'handled': False}
        if action == 'goto' and (type(slide) is not int or not 1 <= slide <= 10000):
            return {'success': False, 'message': 'Choose a valid slide.', 'handled': True}
        try:
            payload = {'action': action}
            if action == 'goto':
                payload['slide'] = slide
            result = await self._call('presentation_command', payload)
            return {'success': bool(result.get('success')), 'message': str(result.get('message', '')),
                    'handled': bool(result.get('handled', False))}
        except Exception as error:
            return {'success': False, 'message': str(error), 'handled': True}

    async def presentation_details(self):
        try:
            return await self._call('presentation_details')
        except Exception as error:
            return dict(available=False, current=None, next=None, notes='', slides=[],
                        capabilities={}, message=str(error))

    async def displays(self):
        try:
            return await self._call('displays')
        except Exception as error:
            return dict(displays=[], selected_id=None, message=str(error))

    def _pin(self, app_id, pinned):
        self._load_usage()
        with self._usage_lock:
            previous = set(self._pinned)
            if pinned:
                self._pinned.add(app_id)
            else:
                self._pinned.discard(app_id)
            try:
                self._save_usage()
            except Exception:
                self._pinned = previous
                raise

    async def app_action(self, app_id, action, window_id=''):
        if not isinstance(app_id, str) or not isinstance(window_id, str) or action not in ('focus', 'pin', 'unpin', 'details'):
            return dict(success=False, message='Choose a valid app action.')
        if not self._apps or time.monotonic() - self._apps_at > 30:
            await self.list_apps()
        app = self._apps.get(app_id)
        if app is None:
            return dict(success=False, message='Refresh Apps and choose a registered app.')
        try:
            if action in ('pin', 'unpin'):
                await asyncio.to_thread(self._pin, app_id, action == 'pin')
                return dict(success=True, message='App pinned.' if action == 'pin' else 'App unpinned.')
            if action == 'details':
                return dict(success=True, message='', details=dict(app, pinned=app_id in self._pinned,
                                                                   launches=(self._usage or {}).get(app_id, 0)))
            windows = app.get('windows', [])
            if not window_id and len(windows) == 1:
                window_id = windows[0]['id']
            if not any(window['id'] == window_id for window in windows):
                return dict(success=False, message='Refresh Apps and choose an available window.')
            return await self._call('app_action', {'app_id': app_id, 'action': 'focus', 'window_id': window_id})
        except Exception as error:
            return dict(success=False, message=str(error))

    async def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            await asyncio.wait_for(asyncio.to_thread(self._bridge.close), min(self.timeout, 1.))
        except Exception:
            pass
