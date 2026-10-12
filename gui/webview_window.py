"""Owned EdgeChromium desktop shell. Native bridge never lives on the LAN app."""
import asyncio
import base64
from collections import deque
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import io
import json
import mimetypes
from pathlib import Path
import platform
import secrets
import threading
from urllib.parse import unquote, urlsplit
import webbrowser

import qrcode

from server.build_version import get_build_id
from server.secure_pairing import private_storage_root, protect_user_path
from server.tailscale_pairing import HELP_URLS

ROOT = Path(__file__).resolve().parents[1]
GUI_WEB = ROOT / 'gui' / 'web'
THEMES = {'bloom', 'resonance', 'companion', 'clay', 'glass', 'soft', 'ink'}


def preview_state():
    """Explicitly synthetic desktop fixture; no native queries, keys or listeners."""
    url = 'http://192.168.1.25:8765/'
    output = io.BytesIO(); qrcode.make(url).save(output, format='PNG')
    trusted_output = io.BytesIO(); qrcode.make('https://sample-pc.example.ts.net:8443/').save(trusted_output, format='PNG')
    return {'preview': True, 'config': {'mouse_sensitivity': 1.3, 'mouse_acceleration': 1.25,
        'scroll_speed': 1.0, 'invert_scroll': False, 'require_pin': True, 'laser_color': 'blue'},
        'pin_code': '5678', 'devices': [{'device': 'Android phone', 'ip': '192.168.1.40', 'authenticated': True, 'ping': 12},
                                      {'device': 'Tablet', 'ip': '192.168.1.41', 'authenticated': False, 'ping': 0}],
        'activity': ['[10:40:12] Android phone: Connected', '[10:40:15] Android phone: Pointer moved'],
        'pairing': {'http_url': url, 'https_url': None, 'secure_ready': False,
                    'qr': 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode(),
                    'certificate': {}, 'setup_url': url,
                    'preview_trusted_qr':'data:image/png;base64,'+base64.b64encode(trusted_output.getvalue()).decode(),
                    'tailscale':{'state':'not_installed','ready':False,'url':None,'message':'Preview: install Tailscale on Windows and Android, then sign in to the same tailnet.'}},
        'preferences': {'theme': 'glass', 'appearance': 'dark', 'motion': 'system', 'contrast': 'system','effects':'rich','connection_mode':'http'},
        'diagnostics': {'engine': 'EdgeChromium / WebView2', 'python': 'Preview', 'build': 'Sample build',
                        'source': 'Sample workspace', 'host': '192.168.1.25', 'http_port': 8765,
                        'https_port': 8766, 'certificate_trust': 'Manual installation only'}}


def render_preview_html(asset_base='/preview/desktop/'):
    source = (GUI_WEB / 'index.html').read_text(encoding='utf-8')
    fixture = json.dumps(preview_state()).replace('<', '\\u003c')
    return source.replace('__DESKTOP_TOKEN__', 'preview-disabled').replace('__DESKTOP_ASSET_BASE__', asset_base).replace(
        '</head>', f'<script>window.__TOUCHHELM_DESKTOP_PREVIEW__={fixture};</script></head>')


class DesktopAssetServer:
    """Only approved GUI/theme/image files; no APIs, private paths or directories."""
    def __init__(self, token):
        self.token = token
        self.server = None
        self.thread = None
        self.url = None

    def resolve(self, request_path):
        path = unquote(urlsplit(request_path).path)
        prefix = f'/desktop/{self.token}/'
        if not path.startswith(prefix): return None
        relative = path[len(prefix):]
        if not relative or any(part in ('', '.', '..') for part in relative.split('/')) or '\\' in relative:
            return None
        if relative in ('index.html', 'desktop.css', 'desktop.js'):
            return GUI_WEB / relative
        if relative in ('themes.js', 'themes.css', 'theme-effects.js', 'theme-effects.css'):
            return ROOT / 'web' / relative
        if relative.startswith(('themes/', 'assets/', 'icons/')) and Path(relative).suffix.lower() in ('.css', '.svg', '.png', '.webp', '.jpg', '.woff2'):
            candidate = (ROOT / 'web' / relative).resolve()
            if candidate.is_relative_to(ROOT / 'web'):
                return candidate
        return None

    def start(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                expected_host = f'127.0.0.1:{owner.server.server_port}'
                if self.headers.get('Host') != expected_host:
                    self.send_error(403); return
                path = owner.resolve(self.path)
                if path is None or not path.is_file():
                    self.send_error(404); return
                data = path.read_bytes()
                if path.name == 'index.html':
                    data = data.replace(b'__DESKTOP_TOKEN__', owner.token.encode()).replace(
                        b'__DESKTOP_ASSET_BASE__', f'/desktop/{owner.token}/'.encode())
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
                self.end_headers(); self.wfile.write(data)
            def log_message(self, *args): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='TouchHelm desktop assets')
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/desktop/{self.token}/index.html'
        return self.url

    def close(self):
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.server = None
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2); self.thread = None


class DesktopAPI:
    def __init__(self, app): self._app = app

    def _authorize(self, token):
        app = self._app
        if (app._closing or not isinstance(token, str) or not token.isascii()
                or not hmac.compare_digest(token, app.token) or app.window is None):
            raise PermissionError('This native command belongs to the TouchHelm desktop window.')
        current = app.window.get_current_url()
        if not isinstance(current, str) or current.split('#', 1)[0] != app.owned_url:
            raise PermissionError('Native commands are unavailable outside the owned desktop page.')

    def get_state(self, token):
        self._authorize(token)
        return self._app.snapshot()

    def save_settings(self, token, settings):
        self._authorize(token)
        allowed = {'mouse_sensitivity', 'mouse_acceleration', 'scroll_speed', 'invert_scroll',
                   'require_pin', 'pin_code', 'laser_color', 'haptics_enabled', 'server_name', 'remote_enabled'}
        if not isinstance(settings, dict) or not settings or not set(settings) <= allowed:
            return {'success': False, 'error': 'Choose valid desktop settings. Port changes require a restart.'}
        app = self._app
        with app._settings_lock:
            try:
                changed_pin = any(key in settings and settings[key] != app.config.get(key)
                                  for key in ('require_pin', 'pin_code'))
                app.config.update(settings)
            except Exception as error:
                return {'success': False, 'error': str(error)}
            try:
                if app.server_loop is not None and not app.server_loop.is_closed():
                    if changed_pin:
                        app._submit(app.server.invalidate_auth_sessions())
                    else:
                        app._submit(app.server.remote_settings_changed())
                return {'success': True, 'config': app.config.public_data()}
            except Exception as error:
                return {'success': True, 'config': app.config.public_data(),
                        'warning': f'Settings saved, but connected phones could not be updated: {error}. Restart the host before continuing.'}

    def save_preferences(self, token, preferences):
        self._authorize(token)
        if (not isinstance(preferences, dict) or set(preferences) - {'theme', 'appearance', 'motion', 'contrast','effects','connection_mode'}
                or preferences.get('theme') not in THEMES
                or preferences.get('appearance') not in ('light', 'dark', 'system')
                or preferences.get('motion') not in ('full', 'reduced', 'system')
                or preferences.get('contrast') not in ('standard', 'increased', 'system')
                or preferences.get('effects','rich') not in ('rich','calm','off')
                or preferences.get('connection_mode','http') not in ('http','local_ca','tailscale')):
            return {'success': False, 'error': 'Choose valid appearance preferences.'}
        try:
            with self._app._settings_lock:
                self._app._save_preferences(preferences)
            return {'success': True}
        except Exception as error:
            return {'success': False, 'error': str(error)}

    def request_https(self, token, enabled=True):
        self._authorize(token)
        if type(enabled) is not bool:
            return {'success': False, 'error': 'Secure pairing must be enabled or disabled.'}
        app = self._app
        previous = app.config.get('https_enabled', False)
        with app._settings_lock:
            try:
                app.config.set('https_enabled', enabled)
                action = app.server.enable_https if enabled else app.server.disable_https
                app._submit(action())
                return {'success': True, 'pairing': app._pairing()}
            except Exception as error:
                app.config.set('https_enabled', previous)
                return {'success': False, 'error': str(error)}

    def open_phone(self, token, secure=False):
        self._authorize(token)
        if type(secure) is not bool: raise ValueError('Invalid pairing mode')
        url = self._app.phone_url(secure)
        webbrowser.open(url)
        return {'success': True}

    def open_pairing(self, token, mode):
        self._authorize(token)
        pairing=self._app._pairing()
        key={'http':'http_url','local_ca':'https_url','tailscale':'tailscale_url'}.get(mode)
        if not key or not pairing.get(key):return {'success':False,'error':'This connection is not ready. Complete setup or refresh its status.'}
        webbrowser.open(pairing[key]);return {'success':True}

    def refresh_tailscale(self, token):
        self._authorize(token)
        try:
            status=self._app._submit(self._app.server.refresh_tailscale(True))
            return {'success':True,'tailscale':status,'pairing':self._app._pairing()}
        except Exception as error:return {'success':False,'error':str(error)}

    def request_tailscale(self, token, enabled=True):
        self._authorize(token)
        if type(enabled) is not bool:return {'success':False,'error':'Choose enable or disable.'}
        app=self._app
        with app._settings_lock:
            try:
                if enabled and not app.config.get('require_pin'):
                    app.config.update({'require_pin':True,'pin_code':f'{secrets.randbelow(10000):04d}'})
                    app._submit(app.server.invalidate_auth_sessions())
                app._submit(app.server.enable_tailscale() if enabled else app.server.disable_tailscale())
                pairing=app._pairing()
                if enabled and not pairing['tailscale']['ready']:raise RuntimeError(pairing['tailscale']['message'])
                return {'success':True,'pairing':pairing}
            except Exception as error:return {'success':False,'error':str(error)}

    def open_tailscale_help(self, token, page):
        self._authorize(token)
        if page not in HELP_URLS:return {'success':False,'error':'Unknown setup step.'}
        webbrowser.open(HELP_URLS[page]);return {'success':True}

    def minimize(self, token):
        self._authorize(token)
        self._app.minimize()

    def stop_remote(self, token):
        self._authorize(token)
        try:
            self._app._submit(self._app.server.stop_remote())
            return {'success': True}
        except Exception as error:
            return {'success': False, 'error': str(error)}

    def open_casting_settings(self, token):
        self._authorize(token)
        import os
        os.startfile('ms-settings:project')
        return {'success':True}

    def close(self, token):
        self._authorize(token)
        self._app.request_close()


class WebViewDesktopApp:
    def __init__(self, config, server_instance, server_loop, *, primary_ip='127.0.0.1',
                 build_id='', on_exit=None, preference_path=None):
        self.config, self.server, self.server_loop = config, server_instance, server_loop
        self.primary_ip, self.build_id, self.on_exit = primary_ip, build_id, on_exit
        self.token = secrets.token_urlsafe(32)
        self.api = DesktopAPI(self)
        self.window, self.owned_url, self.tray_icon = None, None, None
        self.asset_server = DesktopAssetServer(self.token)
        self._closing = False
        self._settings_lock, self._state_lock = threading.RLock(), threading.RLock()
        self._activity, self._devices = deque(maxlen=1000), []
        self._qr_cache = {}
        self.preference_path = Path(preference_path) if preference_path is not None else private_storage_root() / 'desktop-preferences.json'

    def _submit(self, coroutine):
        if self.server_loop is None or self.server_loop.is_closed() or not self.server_loop.is_running():
            coroutine.close()
            raise RuntimeError('The host is stopping. Restart TouchHelm before changing secure pairing.')
        future = asyncio.run_coroutine_threadsafe(coroutine, self.server_loop)
        try:
            return future.result(timeout=25)
        except TimeoutError:
            future.cancel()
            raise RuntimeError('The host did not respond in time. Check Diagnostics and retry.')

    def _preferences(self):
        try:
            preferences = json.loads(self.preference_path.read_text(encoding='utf-8'))
            return preferences if isinstance(preferences, dict) else {}
        except (OSError, ValueError):
            return {'theme': self.config.get('theme', 'glass'), 'appearance': 'system', 'motion': 'system', 'contrast': 'system'}

    def _save_preferences(self, preferences):
        import os
        import tempfile
        self.preference_path.parent.mkdir(parents=True, exist_ok=True)
        protect_user_path(self.preference_path.parent)
        descriptor, temporary = tempfile.mkstemp(dir=self.preference_path.parent, suffix='.tmp')
        try:
            protect_user_path(Path(temporary))
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                descriptor = None; json.dump(preferences, stream)
            os.replace(temporary, self.preference_path)
            protect_user_path(self.preference_path)
        finally:
            if descriptor is not None: os.close(descriptor)
            if os.path.exists(temporary): os.unlink(temporary)

    def phone_url(self, secure=False):
        if secure and not getattr(self.server, 'https_site', None):
            raise RuntimeError('Enable secure pairing first.')
        host = f'[{self.primary_ip}]' if ':' in self.primary_ip else self.primary_ip
        port = self.config.get('https_port', 8766) if secure else self.config.get('port', 8765)
        return f'{"https" if secure else "http"}://{host}:{port}/?build={get_build_id()}'

    def _qr(self, url):
        if url not in self._qr_cache:
            output = io.BytesIO(); qrcode.make(url).save(output, format='PNG')
            if len(self._qr_cache) >= 4: self._qr_cache.clear()
            self._qr_cache[url] = 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()
        return self._qr_cache[url]

    def _pairing(self):
        ready = bool(getattr(self.server, 'https_site', None))
        info = {}
        manager = getattr(self.server, 'secure_pairing', None)
        if manager is not None:
            try:
                candidate = manager.public_info()
                if isinstance(candidate, dict): info = candidate
            except (OSError, RuntimeError): pass
        http_url = self.phone_url(False)
        secure_url = self.phone_url(True) if ready else None
        tailscale=getattr(self.server,'tailscale_status',None)
        if not isinstance(tailscale,dict):tailscale={'state':'unchecked','ready':False,'url':None,'message':'Check Tailscale to begin private HTTPS setup.'}
        tailscale_url=tailscale.get('url') if tailscale.get('ready') else None
        return {'http_url': http_url, 'https_url': secure_url, 'secure_ready': ready,
                'qr': self._qr(secure_url or http_url), 'qr_http': self._qr(http_url),
                'qr_https': self._qr(secure_url) if secure_url else None, 'certificate': info,
                'setup_url': http_url, 'tailscale':tailscale,'tailscale_url':tailscale_url,
                'qr_tailscale':self._qr(tailscale_url) if tailscale_url else None}

    def snapshot(self):
        with self._state_lock:
            devices, activity = copy.deepcopy(self._devices), list(self._activity)
        return {'config': self.config.public_data(), 'pin_code': self.config.get('pin_code', '')
                    if self.config.get('require_pin', False) else '',
                'devices': devices, 'activity': activity, 'pairing': self._pairing(),
                'remote': self.server.remote.snapshot(),
                'preferences': self._preferences(),
                'diagnostics': {'engine': 'EdgeChromium / WebView2', 'python': platform.python_version(),
                    'build': self.build_id, 'source': str(ROOT), 'host': self.primary_ip,
                    'http_port': self.config.get('port', 8765), 'https_port': self.config.get('https_port', 8766),
                    'native_input': 'Windows controller', 'certificate_trust': 'Manual installation only'}}

    def log_event(self, event_str):
        with self._state_lock: self._activity.append(str(event_str))

    def update_clients(self, clients):
        with self._state_lock: self._devices = copy.deepcopy(clients)

    def restore(self):
        if self.window and not self._closing:
            self.window.show(); self.window.restore()

    def restore_from_tray(self, *args): self.restore()

    def minimize(self):
        if self.tray_icon and self.tray_icon.visible:
            self.window.hide()
        else:
            self.window.minimize()

    def _start_tray(self):
        if self._closing or self.tray_icon is not None: return
        import pystray
        from PIL import Image
        def fail(error):
            icon, self.tray_icon = self.tray_icon, None
            if icon:
                try: icon.stop()
                except Exception: pass
            if not self._closing: self.restore()
            self.log_event(f'System tray unavailable: {error}')
        try:
            icon = pystray.Icon('TouchHelm', Image.open(ROOT / 'assets' / 'touchhelm.png').copy(),
                'TouchHelm', menu=pystray.Menu(pystray.MenuItem('Open TouchHelm', self.restore_from_tray, default=True),
                                            pystray.MenuItem('Stop remote session', lambda *args: self._submit(self.server.stop_remote())),
                                            pystray.MenuItem(lambda item:'Remote: '+self.server.remote.state, None, enabled=False),
                                            pystray.MenuItem('Exit', lambda *args: self.request_close())))
            self.tray_icon = icon
            def worker():
                try: icon.run(setup=lambda ready: setattr(ready, 'visible', True))
                except Exception as error: fail(error)
            threading.Thread(target=worker, daemon=True, name='TouchHelm tray').start()
        except Exception as error: fail(error)

    def request_close(self):
        if self.window: self.window.destroy()
        else: self._closing = True

    def run(self):
        if self._closing: return
        import webview
        webview.settings['ALLOW_FILE_URLS'] = False
        webview.settings['ALLOW_DOWNLOADS'] = False
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
        self.owned_url = self.asset_server.start()
        try:
            self.window = webview.create_window('TouchHelm', self.owned_url, js_api=self.api,
                width=1120, height=800, min_size=(820, 620), background_color='#111722', text_select=True)
            self.window.events.loaded += lambda: self._start_tray()
            self.window.events.closed += self._window_closed
            webview.start(gui='edgechromium', debug=False, private_mode=True,
                          icon=str(ROOT / 'assets' / 'touchhelm.ico'))
        finally:
            self.close()

    def _window_closed(self):
        self._closing = True
        if self.on_exit: self.on_exit()

    def close(self):
        self._closing = True
        icon, self.tray_icon = self.tray_icon, None
        if icon:
            try: icon.stop()
            except Exception: pass
        self.asset_server.close()
