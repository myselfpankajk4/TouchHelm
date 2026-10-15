"""
TouchHelm - Async Web & WebSocket Server
Handles HTTP static serving (PWA client) and real-time low-latency WebSocket communication.
"""

import os
import json
import secrets
from pathlib import Path
import time
import asyncio
import math
import hmac
from urllib.parse import urlsplit
from contextlib import suppress
from aiohttp import web

from server.windows_input import WindowsInputController, VK_MAP
from server.laser_overlay import LaserOverlayClient
from server.config import ConfigManager
from server.discovery import get_local_ip_addresses
from server.desktop_services import DesktopServices
from server.build_version import get_build_id, render_versioned

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


class ConnectedClient:
    def __init__(self, ws, remote_ip: str):
        self.ws = ws
        self.remote_ip = remote_ip
        self.device_name = "Unknown Device"
        self.connected_at = time.time()
        self.authenticated = False
        self.last_ping_rtt = 0.0
        self.packet_count = 0
        self.held_buttons = set()
        self.held_keys = set()
        self.text_field_id = ''
        self.text_revision = ''


class TouchHelmServer:
    def __init__(self, config: ConfigManager, on_event=None, on_client_change=None):
        self.config = config
        self.on_event = on_event
        self.on_client_change = on_client_change

        self.input_ctrl = WindowsInputController()
        self.laser_client = LaserOverlayClient()
        self.clients = {}  # ws -> ConnectedClient
        self.app = None
        self.runner = None
        self.site = None
        self.volume_monitor_task = None
        self.desktop_monitor_task = None
        self.desktop_services = DesktopServices()
        self.secure_pairing = None
        self.https_site = None
        from server.tailscale_pairing import TailscalePairingManager
        self.tailscale = TailscalePairingManager(config)
        self.tailscale_site = None
        self.tailscale_origin = None
        self.tailscale_status = {'state':'unchecked','ready':False,'url':None,'message':'Check Tailscale from the desktop.'}
        self._handoffs = {}
        self._pin_failures = []
        self._pin_blocked_until = 0.
        self._displays = {}
        self._service_tasks = {}
        self._native_action_lock = asyncio.Lock()
        from server.remote_service import RemoteService
        from server.remote_media import MediaWorker, capabilities
        self.remote = RemoteService(config, self.desktop_services.displays, MediaWorker,
            self._release_client_input, self.input_ctrl, capabilities=capabilities,
            notify=self._remote_state_changed, before_control=self._remote_acquire_input)
        self._remote_tasks = {}
        from server.text_sync import FocusedTextService
        self.text_service = FocusedTextService()
        self._text_tasks = {}

    async def _text_request(self, client, data):
        def allowed():
            return (client.authenticated and not client.ws.closed and
                    self.clients.get(client.ws) is client and self.config.get('require_pin')
                    and not self.remote.blocks_input(client))
        state = {'available':False,'message':'Enable a host PIN to sync focused PC text.'}
        if allowed():
            if data['action']=='write':
                if (not client.text_field_id or data.get('field_id')!=client.text_field_id
                        or data.get('revision')!=client.text_revision):
                    state={'available':False,'message':'PC field changed. Review the PC text before sending.'}
                else:
                    async with self._native_action_lock:
                        if allowed():state=await self.text_service.request(data)
            else:
                state=await self.text_service.request(data)
        if not client.authenticated or client.ws.closed or self.clients.get(client.ws) is not client:return
        # A revoked PIN must not expose a result that arrived after revocation.
        if not self.config.get('require_pin'):
            state={'available':False,'message':'Enable a host PIN in desktop Settings to sync focused PC text.'}
        elif self.remote.blocks_input(client):
            state={'available':False,'message':'Another phone owns Remote control. PC text sync is paused.'}
        client.text_field_id=state.get('field_id','') if state.get('available') else ''
        client.text_revision=state.get('revision','') if state.get('available') else ''
        with suppress(ConnectionError,RuntimeError):
            await client.ws.send_json({'type':'text_state','request_id':data.get('request_id',0),**state})

    def _cancel_text_request(self, client):
        task=self._text_tasks.pop(client.ws,None)
        if task and not task.done():task.cancel()
        client.text_field_id=client.text_revision=''

    def _remote_state_changed(self, state):
        owner = self.remote.owner
        async def send():
            for client in list(self.clients.values()):
                if client.authenticated and not client.ws.closed:
                    if state.get('type')=='remote_cursor' and client is not owner:continue
                    # A session token is delivered only to its owning websocket.
                    value = state if client is owner else dict(state, session_id='', revision='')
                    with suppress(ConnectionError, RuntimeError):
                        await client.ws.send_json(value)
        asyncio.create_task(send())

    def _remote_acquire_input(self):
        for client in list(self.clients.values()):
            self._cancel_text_request(client)
            self._release_client_input(client)
        self.laser_client.hide()

    async def _remote_request(self, client, data, secure):
        result = await self.remote.request(client, data, secure)
        if client.authenticated and not client.ws.closed:
            with suppress(ConnectionError, RuntimeError): await client.ws.send_json(result)

    async def stop_remote(self):
        await self.remote.stop('Stopped from the desktop.')

    async def remote_settings_changed(self):
        if not self.config.get('remote_enabled') or not self.config.get('require_pin'):
            await self.remote.stop('Remote screen access disabled on the desktop.')
        await self.broadcast({'type':'config_sync','config':self.config.public_data()})

    async def _native_call(self, name, *args):
        async with self._native_action_lock:
            return await asyncio.to_thread(getattr(self.input_ctrl, name), *args)

    async def _desktop_monitor_loop(self):
        previous = None
        while True:
            await asyncio.sleep(1)
            if not any(client.authenticated for client in self.clients.values()):
                continue
            try:
                state = await self.desktop_services.snapshot()
                encoded = json.dumps(state, sort_keys=True)
                if encoded != previous:
                    previous = encoded
                    await self.broadcast({'type': 'desktop_state', **state})
            except asyncio.CancelledError:
                raise
            except Exception:
                continue

    async def _desktop_request(self, client, data):
        if not client.authenticated or client.ws not in self.clients or client.ws.closed:
            return
        kind = data['type']
        if self.remote.blocks_input(client) and kind not in ('get_desktop_state','get_apps','get_media_library','get_presentation_details','get_displays'):
            return
        try:
            if kind == 'get_desktop_state':
                reply = {'type': 'desktop_state', **await self.desktop_services.snapshot()}
            elif kind == 'get_apps':
                reply = {'type': 'apps_sync', 'apps': await self.desktop_services.list_apps()}
            elif kind == 'get_media_library':
                reply = {'type': 'media_library', **await self.desktop_services.list_media()}
            elif kind == 'get_presentation_details':
                reply = {'type':'presentation_details', **await self.desktop_services.presentation_details()}
            elif kind == 'get_displays':
                displays=await self.desktop_services.displays()
                self._displays={display['id']:display for display in displays.get('displays',[]) if isinstance(display,dict) and isinstance(display.get('id'),str)}
                reply={'type':'displays',**displays}
            else:
                if kind == 'launch_app':
                    result = await self.desktop_services.launch_app(data.get('app_id', ''))
                elif kind == 'app_action':
                    result = await self.desktop_services.app_action(data.get('app_id',''),data.get('action',''),data.get('window_id',''))
                elif kind == 'play_media':
                    result = await self.desktop_services.media_command('play',
                        session_id=data.get('session_id', ''), item_id=data.get('item_id', ''))
                elif kind == 'presentation':
                    action = data.get('action', '')
                    if action not in ('next', 'prev', 'start', 'start_current', 'end', 'black', 'white','goto'):
                        result = {'success': False, 'handled': True, 'message': 'Unsupported presentation action.'}
                    else:
                        result = await self.desktop_services.presentation_command(action,slide=data.get('slide')) if action=='goto' else await self.desktop_services.presentation_command(action)
                        if not result.get('handled'):
                            await self._native_call('presentation_action', action)
                            result = {'success': True, 'message': 'Presentation key sent to the active app.'}
                else:
                    action = data.get('action', '')
                    kwargs={'session_id':data.get('session_id','')}
                    if 'value' in data: kwargs['value']=data['value']
                    result = await self.desktop_services.media_command(action, **kwargs)
                    if action in ('play_pause','play','pause','next','prev','stop') and not result.get('handled') and not data.get('session_id'):
                        await self._native_call('media_action', action)
                        result = {'success': True, 'message': 'Media key sent to the active player.'}
                reply = {'type': 'command_result', 'command': kind,
                         'success': bool(result.get('success')), 'message': result.get('message', '')}
                if kind=='app_action':
                    reply.update({key:data.get(key,'') for key in ('action','app_id','window_id')})
                    for key in ('requested','confirmed'):
                        if type(result.get(key)) is bool:reply[key]=result[key]
                if isinstance(result.get('details'),dict):reply['details']=result['details']
            if client.authenticated and client.ws in self.clients and not client.ws.closed:
                await client.ws.send_json(reply)
        except asyncio.CancelledError:
            raise
        except Exception:
            if client.authenticated and not client.ws.closed:
                with suppress(ConnectionError, RuntimeError):
                    await client.ws.send_json({'type': 'command_result', 'command': kind,
                        **({key:data.get(key,'') for key in ('action','app_id','window_id')} if kind=='app_action' else {}),
                        'success': False, 'message': 'Windows could not complete this request. Try again.'})

    async def _queue_desktop_request(self, client, data):
        kind = data['type']
        owned = [value for value in self._service_tasks.values() if value[0] is client]
        if kind.startswith('get_') and any(value[1] == kind for value in owned):
            return
        if len(owned) >= 8:
            # Reply in the socket handler rather than spawning another task:
            # commands must not leave the phone waiting indefinitely, and a
            # burst of requests must not create an unbounded reply queue.
            if client.authenticated and client.ws in self.clients and not client.ws.closed:
                with suppress(ConnectionError, RuntimeError):
                    await client.ws.send_json({'type': 'command_result', 'command': kind,
                        **({key:data.get(key,'') for key in ('action','app_id','window_id')} if kind=='app_action' else {}),
                        'success': False, 'message': 'The PC is busy. Wait a moment and try again.'})
            return
        task = asyncio.create_task(self._desktop_request(client, data))
        self._service_tasks[task] = (client, kind)
        task.add_done_callback(lambda completed: self._service_tasks.pop(completed, None))

    def _cancel_desktop_requests(self, client):
        for task, (owner, _) in list(self._service_tasks.items()):
            if owner is client:
                task.cancel()

    async def broadcast(self, msg: dict):
        """Broadcasts a JSON message to all currently connected WebSocket clients."""
        text = json.dumps(msg)
        for ws, client in list(self.clients.items()):
            try:
                if client.authenticated and not ws.closed:
                    await ws.send_str(text)
            except Exception:
                pass

    async def _volume_monitor_loop(self):
        """Monitors Windows master volume and broadcasts updates when changed externally."""
        try:
            last_vol, last_mute = await self._native_call('get_volume')
        except Exception:
            last_vol, last_mute = None, None
        last_brightness = self.input_ctrl.get_brightness()
        while True:
            try:
                await asyncio.sleep(0.5)
                if not self.clients:
                    continue
                vol, muted = await self._native_call('get_volume')
                if vol != last_vol or muted != last_mute:
                    last_vol = vol
                    last_mute = muted
                    await self.broadcast({"type": "volume_sync", "volume": vol, "muted": muted})
                brightness = self.input_ctrl.get_brightness()
                if brightness != last_brightness:
                    last_brightness = brightness
                    await self.broadcast({'type':'brightness_sync','level':brightness})
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def _log_event(self, action: str, client_name: str = "Client"):
        msg = f"[{time.strftime('%H:%M:%S')}] {client_name}: {action}"
        print(msg)
        if self.on_event:
            try:
                self.on_event(msg)
            except Exception:
                pass

    def _notify_client_change(self):
        if self.on_client_change:
            try:
                client_list = [
                    {
                        "ip": c.remote_ip,
                        "device": c.device_name,
                        "connected_at": c.connected_at,
                        "authenticated": c.authenticated,
                        "ping": round(c.last_ping_rtt, 1),
                        "packets": c.packet_count
                    }
                    for c in self.clients.values()
                ]
                self.on_client_change(client_list)
            except Exception:
                pass

    async def invalidate_auth_sessions(self):
        """Release held input and apply changes to the configured PIN immediately."""
        self._pin_failures.clear()
        self._pin_blocked_until = 0.
        clients = list(self.clients.items())
        authorized = not self.config.get("require_pin", False)
        # Revoke every session before yielding to a socket. One disconnected
        # device must not leave the remaining clients authorized with an old PIN.
        for _, client in clients:
            client.authenticated = authorized
        await self.remote.stop('Pairing changed. Authenticate again to start Remote.')
        for _, client in clients:
            self._cancel_text_request(client)
            self._cancel_desktop_requests(client)
            self._release_client_input(client)
        self.laser_client.hide()
        for ws, client in clients:
            if not ws.closed:
                try:
                    if client.authenticated:
                        await self._send_auth_success(client)
                    else:
                        await ws.send_json({"type": "auth_required"})
                except (ConnectionError, RuntimeError):
                    continue
        self._notify_client_change()

    def _pin_matches(self, pin):
        # Global rather than per-IP: private Serve peers share a loopback proxy.
        now = time.monotonic()
        if now < self._pin_blocked_until:
            return False
        self._pin_failures = [stamp for stamp in self._pin_failures if now-stamp < 60]
        matches = isinstance(pin, str) and pin.isascii() and hmac.compare_digest(pin, self.config.get("pin_code", ""))
        if matches:
            return True
        # Missing credentials are discovery, not a submitted PIN guess.
        if pin not in (None, ''):
            self._pin_failures.append(now)
            if len(self._pin_failures) >= 8:
                self._pin_blocked_until = now+60
                self._pin_failures.clear()
        return False

    async def _send_auth_success(self, client):
        vol, muted = await self._native_call('get_volume')
        if not client.authenticated or client.ws.closed:
            return False
        await client.ws.send_json({"type": "auth_res", "success": True,
                                   "message": "Connected", "volume": vol, "muted": muted,
                                   "brightness": self.input_ctrl.get_brightness(),
                                   "config": self.config.public_data()})
        return True

    def _release_client_input(self, client):
        for button in list(client.held_buttons):
            client.held_buttons.remove(button)
            if not any(button in c.held_buttons for c in self.clients.values()):
                self.input_ctrl.mouse_up(button)
        for key in list(client.held_keys):
            client.held_keys.remove(key)
            if not any(key in c.held_keys for c in self.clients.values()):
                self.input_ctrl.key_up(key)

    @staticmethod
    def _valid_packet(data):
        if not isinstance(data, dict) or not isinstance(data.get("type"), str):
            return False
        kind = data["type"]
        numeric_fields = {"ping": ("t",), "move": ("dx", "dy"),
                          "scroll": ("dx", "dy"), "laser": ("x", "y"),
                          "volume": ("level",), "brightness": ("level",),"zoom":("delta",),"presentation":("slide",)}
        for field in numeric_fields.get(kind, ()):
            if field in data:
                value = data[field]
                limit = 10 ** 15 if kind == "ping" else 10000
                if type(value) not in (int, float) or abs(value) > limit or not math.isfinite(value):
                    return False
        string_fields = {"auth": ("device_name", "pin"), "key": ("key",),
                         "keydown": ("key",), "keyup": ("key",), "text": ("text",),
                         "presentation": ("action",), "media": ("action", "session_id"),
                         "launch_app": ("app_id",), "play_media": ("item_id", "session_id"),
                         "shortcut": ("name",), "volume": ("action",),
                         "brightness": ("action",), "laser": ("color","display_id"),"app_action":("app_id","action","window_id")}
        for field in string_fields.get(kind, ()):
            if field in data:
                if not isinstance(data[field], str):
                    return False
                if field in ('app_id', 'item_id', 'session_id') and len(data[field]) > 1024:
                    return False
        if kind in ("click", "dblclick", "double_click", "mousedown", "mouseup"):
            if data.get("button", "left") not in ("left", "right", "middle"):
                return False
        if kind == "hotkey":
            keys = data.get("keys", [])
            if not isinstance(keys, list) or len(keys) > 16 or not all(isinstance(k, str) for k in keys):
                return False
        if kind == "laser":
            if "active" in data and type(data["active"]) is not bool:
                return False
            if data.get("color", "red") not in ("red", "green", "blue", "amber"):
                return False
        if kind == "text" and len(data.get("text", "")) > 10000:
            return False
        if kind=='text' and data.get('newline_mode','enter') not in ('enter','shift_enter'):return False
        if kind=='text_sync':
            if data.get('action') not in ('read','write'):return False
            if type(data.get('request_id',0)) is not int or not 0<=data.get('request_id',0)<=2**53:return False
            if data.get('newline_mode','shift_enter') not in ('enter','shift_enter'):return False
            if data['action']=='write' and (not isinstance(data.get('text'),str) or len(data['text'])>10000):return False
            for key in ('field_id','revision'):
                if key in data and (not isinstance(data[key],str) or len(data[key])>128):return False
        if kind=='zoom' and ('delta' not in data or abs(data['delta'])>10):return False
        if kind=='keydown' and 'repeat' in data and type(data['repeat']) is not bool:return False
        if kind=='media' and data.get('action') in ('seek','rate','shuffle','repeat'):
            action,value=data['action'],data.get('value')
            if action=='shuffle' and type(value) is not bool:return False
            if action=='repeat' and value not in ('none','track','list'):return False
            if action in ('seek','rate'):
                if type(value) not in (int,float) or not math.isfinite(value):return False
                if action=='seek' and value<0:return False
                if action=='rate' and not .25<=value<=4:return False
        return True

    @staticmethod
    def _canonical_key(key):
        lowered = key.lower()
        if lowered in ('numpadenter', 'numpad_enter'):
            return 'numpadenter'
        vk = VK_MAP.get(lowered)
        if vk is not None:
            return next(name for name, code in VK_MAP.items() if code == vk)
        if len(lowered) == 1 and lowered.isascii() and lowered.isalnum():
            return lowered
        return None

    async def handle_info(self, request):
        """API info route returning PC details and configuration."""
        w, h = self.input_ctrl.get_screen_size()
        ips = get_local_ip_addresses()
        vol, muted = await self._native_call('get_volume')
        bright = self.input_ctrl.get_brightness()
        return web.json_response({
            "service": "touchhelm",
            "version": "1.0.0",
            "server_name": self.config.get("server_name"),
            "ips": ips,
            "port": self.config.get("port"),
            "screen_width": w,
            "screen_height": h,
            "volume": vol,
            "muted": muted,
            "brightness": bright,
            "require_pin": self.config.get("require_pin", False),
            "mouse_sensitivity": self.config.get("mouse_sensitivity", 1.3),
            "mouse_acceleration": self.config.get("mouse_acceleration", 1.25),
            "scroll_speed": self.config.get("scroll_speed", 1.0),
            "invert_scroll": self.config.get("invert_scroll", False),
            "laser_color": self.config.get("laser_color", "red"),
            "theme": self.config.get("theme", "cyber")
        }, headers={"Access-Control-Allow-Origin": "*"})

    async def handle_config(self, request):
        """API route to get or update settings."""
        headers = {"Access-Control-Allow-Origin": "*",
                   "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                   "Access-Control-Allow-Headers": "Content-Type, X-TouchHelm-Pin"}
        if request.method == "OPTIONS":
            return web.Response(status=204, headers=headers)
        if request.method not in ("GET", "POST"):
            return web.Response(status=405, headers=headers)
        if self.config.get("require_pin", False) and not self._pin_matches(request.headers.get("X-TouchHelm-Pin")):
            return web.json_response({"success": False, "error": "PIN required"}, status=401, headers=headers)
        if request.method == "POST":
            try:
                data = await request.json()
                if not isinstance(data, dict):
                    raise ValueError("Settings must be an object")
                if any(key in data for key in ('port','https_port','https_enabled','tailscale_enabled','tailscale_owned_host','remote_enabled')):
                    raise ValueError("Changing the port requires a server restart")
                pin_setting_changed = any(k in data and self.config.get(k) != data[k]
                                          for k in ("require_pin", "pin_code"))
                self.config.update(data)
                if pin_setting_changed:
                    await self.invalidate_auth_sessions()
                else:
                    await self.broadcast({"type": "config_sync", "config": self.config.public_data()})
                return web.json_response({"success": True, "config": self.config.public_data()}, headers=headers)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)}, status=400, headers=headers)
        return web.json_response(self.config.public_data(), headers=headers)

    async def handle_ws(self, request):
        ws = web.WebSocketResponse(heartbeat=15.0)
        await ws.prepare(request)

        remote_ip = request.remote or "unknown"
        client = ConnectedClient(ws, remote_ip)
        client.remote_secure = self.request_origin(request).startswith('https://')
        self.clients[ws] = client
        self._notify_client_change()
        self._log_event("Device connected", remote_ip)

        try:
            client.authenticated = not self.config.get("require_pin", False)
            if client.authenticated:
                await self._send_auth_success(client)
            else:
                await ws.send_json({"type": "auth_required"})
            self._notify_client_change()
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except (ValueError, RecursionError):
                        continue

                    if not self._valid_packet(data):
                        continue

                    client.packet_count += 1
                    msg_type = data.get("type")

                    # Handle ping immediately
                    if msg_type == "ping":
                        send_t = data.get("t", 0)
                        now_ms = time.time() * 1000
                        if send_t:
                            client.last_ping_rtt = max(0.5, now_ms - send_t)
                        await ws.send_json({"type": "pong", "t": send_t, "server_t": now_ms})
                        continue

                    # Handle handshake / device info
                    if msg_type == "auth":
                        client.device_name = str(data.get("device_name", "TouchHelm Client"))[:40]
                        authorized = not self.config.get("require_pin", False) or self._pin_matches(data.get("pin"))
                        if not authorized:
                            self._cancel_text_request(client)
                            if self.remote.owner is client: await self.remote.stop('Authentication revoked.')
                            self._cancel_desktop_requests(client)
                            self._release_client_input(client)
                            self.laser_client.hide()
                            client.authenticated = False
                            message = "Too many PIN attempts. Wait 60 seconds and retry." if time.monotonic() < self._pin_blocked_until else "Invalid PIN"
                            await ws.send_json({"type": "auth_res", "success": False, "message": message})
                            self._notify_client_change()
                            continue
                        client.authenticated = True
                        if await self._send_auth_success(client):
                            self._log_event(f"Connected as {client.device_name}", client.remote_ip)
                        self._notify_client_change()
                        continue

                    if not client.authenticated:
                        continue

                    if msg_type.startswith('remote_') and msg_type != 'remote_input':
                        previous = self._remote_tasks.get(ws)
                        if msg_type in ('remote_stop', 'remote_pause'):
                            if previous and not previous.done(): previous.cancel()
                            await self._remote_request(client, data, client.remote_secure)
                        elif previous and not previous.done():
                            await ws.send_json({'type':'remote_result','success':False,'message':'Remote request is still running.'})
                        else:
                            task=asyncio.create_task(self._remote_request(client,data,client.remote_secure))
                            self._remote_tasks[ws]=task
                        continue
                    if msg_type == 'remote_input':
                        if not self.remote.accept_input(client,data):
                            await ws.send_json({'type':'remote_result','success':False,'message':'Remote input is paused, stale, or view-only.'})
                            continue
                        command=data.get('command')
                        if not isinstance(command,dict) or not self._valid_packet(command): continue
                        kind=command.get('type')
                        if kind=='absolute':
                            point=self.remote.point(client,dict(data,x=command.get('x'),y=command.get('y')))
                            if point:
                                try:self.input_ctrl.set_physical_cursor_pos(*point)
                                except RuntimeError as error:
                                    await ws.send_json({'type':'remote_result','success':False,'message':str(error)})
                            continue
                        if kind not in ('move','click','dblclick','mousedown','mouseup','scroll','key','keydown','keyup','text','hotkey','zoom'):continue
                        data=command;msg_type=kind
                    elif self.remote.blocks_input(client) and msg_type not in ('ping','get_desktop_state','get_apps','get_media_library','get_displays','get_volume','get_brightness','get_system_status','get_presentation_details'):
                        await ws.send_json({'type':'command_result','success':False,'message':'Another phone currently owns Remote control.'})
                        continue

                    desktop_query = msg_type in ('get_desktop_state', 'get_apps', 'launch_app',
                                                  'get_media_library', 'play_media', 'presentation','get_presentation_details','get_displays','app_action')
                    if msg_type=='text_sync':
                        previous=self._text_tasks.get(ws)
                        if not previous or previous.done():
                            self._text_tasks[ws]=asyncio.create_task(self._text_request(client,data))
                        else:
                            await ws.send_json({'type':'text_state','request_id':data.get('request_id',0),
                                'available':False,'message':'PC text provider is busy. Your draft is kept.'})
                        continue
                    media_query = msg_type == 'media' and data.get('action') in (
                        'play_pause', 'playpause', 'play', 'pause', 'next', 'prev', 'previous', 'stop', 'nexttrack', 'prevtrack',
                        'seek','shuffle','repeat','rate')
                    if desktop_query or media_query:
                        await self._queue_desktop_request(client, data)
                        continue

                    # Update device name if passed in general packets
                    if "device_name" in data and client.device_name == "Unknown Device":
                        client.device_name = str(data["device_name"])[:40]
                        self._notify_client_change()

                    # System status queries
                    if msg_type == "get_volume":
                        cur_vol, cur_muted = await self._native_call('get_volume')
                        await ws.send_json({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                        continue

                    elif msg_type == "get_brightness":
                        cur_bright = self.input_ctrl.get_brightness()
                        await ws.send_json({"type": "brightness_sync", "level": cur_bright})
                        continue

                    elif msg_type == "get_system_status":
                        cur_vol, cur_muted = await self._native_call('get_volume')
                        cur_bright = self.input_ctrl.get_brightness()
                        await ws.send_json({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                        await ws.send_json({"type": "brightness_sync", "level": cur_bright})
                        continue

                    elif msg_type == "volume":
                        if "level" in data:
                            v = int(data["level"])
                            cur_vol, cur_muted = await self._native_call('set_volume', v)
                            await self.broadcast({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                            self._log_event(f"Volume set to {cur_vol}%", client.device_name)
                        elif data.get("action") == "up":
                            cur_vol, cur_muted = await self._native_call('change_volume', 2)
                            await self.broadcast({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                            self._log_event(f"Volume up ({cur_vol}%)", client.device_name)
                        elif data.get("action") == "down":
                            cur_vol, cur_muted = await self._native_call('change_volume', -2)
                            await self.broadcast({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                            self._log_event(f"Volume down ({cur_vol}%)", client.device_name)
                        elif data.get("action") == "mute":
                            cur_vol, cur_muted = await self._native_call('toggle_mute')
                            await self.broadcast({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                            self._log_event(f"Volume mute toggled ({cur_muted})", client.device_name)
                        continue

                    elif msg_type == "brightness":
                        if "level" in data:
                            b = int(data["level"])
                            cur_bright = await self._native_call('set_brightness', b)
                            await self.broadcast({"type": "brightness_sync", "level": cur_bright})
                            self._log_event(f"Brightness set to {cur_bright}%", client.device_name)
                        elif data.get("action") == "up":
                            cur_bright = await self._native_call('change_brightness', 10)
                            await self.broadcast({"type": "brightness_sync", "level": cur_bright})
                            self._log_event(f"Brightness up ({cur_bright}%)", client.device_name)
                        elif data.get("action") == "down":
                            cur_bright = await self._native_call('change_brightness', -10)
                            await self.broadcast({"type": "brightness_sync", "level": cur_bright})
                            self._log_event(f"Brightness down ({cur_bright}%)", client.device_name)
                        continue

                    elif msg_type == "start_menu":
                        self.input_ctrl.key_tap("win")
                        self._log_event("Start Menu", client.device_name)
                        continue

                    # Process Control Packets:
                    sens = self.config.get("mouse_sensitivity", 1.3)
                    accel = self.config.get("mouse_acceleration", 1.25)
                    scroll_spd = self.config.get("scroll_speed", 1.0)
                    invert_sc = self.config.get("invert_scroll", False)

                    if msg_type == "move":
                        dx = float(data.get("dx", 0))
                        dy = float(data.get("dy", 0))
                        self.input_ctrl.move_rel(dx, dy, sensitivity=sens, acceleration=accel)

                    elif msg_type == "click":
                        btn = data.get("button", "left")
                        self.input_ctrl.click(btn)
                        self._log_event(f"Click ({btn})", client.device_name)

                    elif msg_type in ("dblclick", "double_click"):
                        btn = data.get("button", "left")
                        self.input_ctrl.double_click(btn)
                        self._log_event(f"Double Click ({btn})", client.device_name)

                    elif msg_type == "mousedown":
                        btn = data.get("button", "left")
                        if not any(btn in c.held_buttons for c in self.clients.values()):
                            self.input_ctrl.mouse_down(btn)
                        client.held_buttons.add(btn)

                    elif msg_type == "mouseup":
                        btn = data.get("button", "left")
                        if btn in client.held_buttons:
                            client.held_buttons.remove(btn)
                            if not any(btn in c.held_buttons for c in self.clients.values()):
                                self.input_ctrl.mouse_up(btn)

                    elif msg_type == "scroll":
                        dx = float(data.get("dx", 0))
                        dy = float(data.get("dy", 0))
                        self.input_ctrl.scroll(dx, dy, scroll_speed=scroll_spd, invert=invert_sc)

                    elif msg_type == "key":
                        k = data.get("key", "")
                        self.input_ctrl.key_tap(k)
                        self._log_event(f"Key tap: {k}", client.device_name)

                    elif msg_type == "keydown":
                        k = self._canonical_key(data.get("key", ""))
                        if data.get('repeat') and k in client.held_keys and k in ('backspace','delete','left','right','up','down','pageup','pagedown','home','end'):
                            self.input_ctrl.key_down(k)
                        if k:
                            if not any(k in c.held_keys for c in self.clients.values()):
                                self.input_ctrl.key_down(k)
                            client.held_keys.add(k)

                    elif msg_type == "keyup":
                        k = self._canonical_key(data.get("key", ""))
                        if k in client.held_keys:
                            client.held_keys.remove(k)
                            if not any(k in c.held_keys for c in self.clients.values()):
                                self.input_ctrl.key_up(k)

                    elif msg_type == "text":
                        txt = data.get("text", "")
                        if data.get('newline_mode')=='shift_enter':await self._native_call('type_text',txt,'shift_enter')
                        else:await self._native_call('type_text',txt)
                        self._log_event(f"Typed text ({len(txt)} chars)", client.device_name)

                    elif msg_type == "hotkey":
                        keys = data.get("keys", [])
                        if keys:
                            self.input_ctrl.hotkey(*keys)
                            self._log_event(f"Hotkey: {'+'.join(keys)}", client.device_name)
                    elif msg_type=='zoom':
                        await self._native_call('zoom',data['delta'])

                    elif msg_type == "presentation":
                        action = data.get("action", "")
                        self.input_ctrl.presentation_action(action)
                        self._log_event(f"Presentation: {action}", client.device_name)

                    elif msg_type == "media":
                        action = data.get("action", "")
                        if action in ("vol_up", "volume_up"):
                            cur_vol, cur_muted = await self._native_call('change_volume', 2)
                            await self.broadcast({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                            self._log_event(f"Media Volume Up ({cur_vol}%)", client.device_name)
                        elif action in ("vol_down", "volume_down"):
                            cur_vol, cur_muted = await self._native_call('change_volume', -2)
                            await self.broadcast({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                            self._log_event(f"Media Volume Down ({cur_vol}%)", client.device_name)
                        elif action in ("mute", "volume_mute"):
                            cur_vol, cur_muted = await self._native_call('toggle_mute')
                            await self.broadcast({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                            self._log_event(f"Media Mute Toggled ({cur_muted})", client.device_name)
                        else:
                            self.input_ctrl.media_action(action)
                            self._log_event(f"Media: {action}", client.device_name)

                    elif msg_type == "shortcut":
                        name = data.get("name", "")
                        self.input_ctrl.windows_shortcut(name)
                        self._log_event(f"Shortcut: {name}", client.device_name)

                    elif msg_type == "laser":
                        norm_x = max(0., min(1., float(data.get("x", 0.5))))
                        norm_y = max(0., min(1., float(data.get("y", 0.5))))
                        active = bool(data.get("active", True))
                        color = data.get("color", self.config.get("laser_color", "red"))
                        self.laser_client.set_color(color)
                        display=self._displays.get(data.get('display_id'))
                        if data.get('display_id') and display is None:continue
                        if display:self.laser_client.update(norm_x,norm_y,active,display.get('rect'))
                        else:self.laser_client.update(norm_x, norm_y, active)

                    elif msg_type == "laser_hide":
                        self.laser_client.hide()

                elif msg.type == web.WSMsgType.ERROR:
                    pass

        finally:
            self._cancel_text_request(client)
            task=self._remote_tasks.pop(ws,None)
            if task and not task.done():task.cancel()
            if self.remote.owner is client:await self.remote.stop('Phone disconnected.')
            self._cancel_desktop_requests(client)
            self._release_client_input(client)
            self.laser_client.hide()
            if ws in self.clients:
                del self.clients[ws]
                self._notify_client_change()
                self._log_event("Device disconnected", client.device_name)

        return ws

    def _http_authorized(self,request):
        return not self.config.get('require_pin',False) or self._pin_matches(request.headers.get('X-TouchHelm-Pin'))

    async def handle_asset(self,request):
        if not self._http_authorized(request):return web.Response(status=401)
        data=await asyncio.to_thread(self.desktop_services.assets.get,request.match_info['asset_id'])
        if data is None:return web.Response(status=404)
        return web.Response(body=data,content_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    async def handle_pairing(self,request):
        if not self._http_authorized(request):return web.Response(status=401)
        info={};certificate_available=False
        if self.secure_pairing:
            try:
                info=self.secure_pairing.public_info()
                certificate_available=True
            except (OSError,ValueError):
                info={'message':'The public pairing certificate is unavailable. Retry HTTPS setup on the desktop.'}
        return web.json_response(dict(info,enabled=bool(self.https_site),certificate_available=certificate_available,
                                      https_port=self.config.get('https_port',8766), https_url=self.local_https_origin(request)+'/' if self.https_site and self.local_https_origin(request) else None,
                                      tailscale={key:value for key,value in self.tailscale_status.items() if key != 'host'}))

    def local_https_origin(self, request):
        host = urlsplit(f'http://{request.host}').hostname
        if host not in get_local_ip_addresses()+['localhost','127.0.0.1','::1']: return None
        return f'https://{"["+host+"]" if ":" in host else host}:{self.config.get("https_port",8766)}'

    def _is_tailscale_request(self, request):
        local = request.transport.get_extra_info('sockname') if request.transport else None
        return bool(self.tailscale_origin and local and local[0]=='127.0.0.1' and local[1]==8767
                and request.remote=='127.0.0.1' and request.host==urlsplit(self.tailscale_origin).netloc)

    def request_origin(self, request):
        if self._is_tailscale_request(request):
            return self.tailscale_origin
        return f'{request.scheme}://{request.host}'

    @web.middleware
    async def _private_transport(self, request, handler):
        local = request.transport.get_extra_info('sockname') if request.transport else None
        if local and local[1]==8767:
            if (not self.tailscale_origin or self.request_origin(request)!=self.tailscale_origin
                    or not self.config.get('require_pin')): return web.Response(status=403)
        if request.headers.get('Origin') and request.headers['Origin'] != self.request_origin(request):
            return web.Response(status=403)
        return await handler(request)

    async def handle_certificate(self,request):
        if not self._http_authorized(request):return web.Response(status=401)
        if self.secure_pairing is None:return web.Response(status=404)
        try:
            data=self.secure_pairing.public_certificate_der()
        except (OSError,ValueError):
            return web.Response(status=404)
        return web.Response(body=data,content_type='application/x-x509-ca-cert',headers={'Content-Disposition':'attachment; filename="touchhelm-ca.crt"','Cache-Control':'no-store'})

    async def handle_handoff(self,request):
        if not self._http_authorized(request):return web.Response(status=401)
        if request.headers.get('Origin') and request.headers['Origin'] != self.request_origin(request):return web.Response(status=403)
        if request.method not in ('GET','POST'):
            return web.Response(status=405,headers={'Allow':'GET, POST'})
        now=time.monotonic()
        self._handoffs={key:value for key,value in self._handoffs.items() if value['expires']>now}
        if request.method=='GET':
            origin=self.request_origin(request)
            if not origin.startswith('https://'):return web.Response(status=400)
            if origin==self.tailscale_origin and not self._is_tailscale_request(request):return web.Response(status=403)
            if origin==self.tailscale_origin and not self._pin_matches(request.headers.get('X-TouchHelm-Pin')):return web.Response(status=401)
            value=self.consume_handoff(request.query.get('token',''),request.remote,origin)
            return web.json_response(value) if value is not None else web.Response(status=404)
        if not self.https_site and not self.tailscale_origin:return web.json_response({'error':'Enable HTTPS on the desktop first.'},status=409)
        try:
            data=await request.json()
            if not isinstance(data,dict) or not isinstance(data.get('draft',''),str) or len(data.get('draft',''))>10000:raise ValueError('Draft exceeds transfer limit')
            local_target=self.local_https_origin(request) if self.https_site else None
            target=data.get('target_origin') or local_target
            if not target or target not in (local_target,self.tailscale_origin):raise ValueError('Invalid destination')
            if target==self.tailscale_origin and not self._pin_matches(request.headers.get('X-TouchHelm-Pin')):return web.Response(status=401)
            baseline=data.get('live_baseline','')
            if not isinstance(baseline,str) or len(baseline)>10000:raise ValueError('Invalid baseline')
            allowed={'theme','appearance','motion','contrast','newline_mode','haptics','effects','live_typing','pc_text_sync'}
            preferences=data.get('preferences',{})
            if not isinstance(preferences,dict):raise ValueError('Invalid preferences')
            preferences={key:value for key,value in preferences.items() if key in allowed and type(value) in (str,bool) and len(str(value))<=32}
            if len(self._handoffs)>=32:raise ValueError('Too many pending transfers')
            token=secrets.token_urlsafe(32)
            self._handoffs[token]={'expires':now+60,'ip':request.remote,'target':target,'cross_transport':target==self.tailscale_origin,'data':{'draft':data.get('draft',''),'live_baseline':baseline,'preferences':preferences}}
            return web.json_response({'token':token,'target_origin':target,'expires_in':60})
        except (ValueError,TypeError):return web.Response(status=400)

    def consume_handoff(self,token,remote_ip,target_origin=None):
        value=self._handoffs.get(token)
        if not value or value['expires']<=time.monotonic():
            self._handoffs.pop(token,None);return None
        if target_origin is not None and value['target']!=target_origin:return None
        if value.get('cross_transport') and target_origin != value['target']:return None
        if not value.get('cross_transport') and value['ip']!=remote_ip:return None
        self._handoffs.pop(token,None)
        return value['data']

    async def refresh_tailscale(self, force=False):
        state=await asyncio.to_thread(self.tailscale.inspect,force)
        if state['ready'] and self.config.get('require_pin') and self.config.get('tailscale_enabled'):
            self.tailscale_origin=state['url'].rstrip('/')
            if not self.tailscale_site:
                try:
                    site=web.TCPSite(self.runner,'127.0.0.1',8767);await site.start();self.tailscale_site=site
                except Exception:
                    self.tailscale_origin=None
                    state=dict(state,ready=False,url=None,state='unavailable',message='The private backend could not start. Check port 8767 and restart TouchHelm.')
        else:
            await self.stop_tailscale_backend()
            if state['ready']:state=dict(state,ready=False,url=None,state='setup_required')
        self.tailscale_status=state
        return state

    async def enable_tailscale(self):
        state=await asyncio.to_thread(self.tailscale.inspect,True)
        if state['state'] not in ('setup_required','ready'):raise RuntimeError(state['message'])
        self.tailscale_origin=f'https://{state["host"]}:8443'
        try:
            if not self.tailscale_site:
                site=web.TCPSite(self.runner,'127.0.0.1',8767);await site.start();self.tailscale_site=site
            await asyncio.to_thread(self.tailscale.enable)
        except Exception:
            await self.stop_tailscale_backend();raise
        return await self.refresh_tailscale(True)

    async def disable_tailscale(self):
        await asyncio.to_thread(self.tailscale.disable)
        await self.stop_tailscale_backend()
        return await self.refresh_tailscale(True)

    async def stop_tailscale_backend(self):
        if self.tailscale_site:await self.tailscale_site.stop()
        self.tailscale_site=None;self.tailscale_origin=None;self._handoffs.clear()

    async def enable_https(self):
        if self.https_site:return
        from server.secure_pairing import SecurePairingManager
        from server.discovery import get_local_ip_addresses
        if self.secure_pairing is None:self.secure_pairing=SecurePairingManager()
        context=await asyncio.to_thread(self.secure_pairing.prepare,get_local_ip_addresses()+['localhost','127.0.0.1'])
        site=web.TCPSite(self.runner,'0.0.0.0',int(self.config.get('https_port',8766)),ssl_context=context)
        await site.start();self.https_site=site

    async def disable_https(self):
        if self.https_site:await self.https_site.stop()
        self.https_site=None;self._handoffs.clear()

    async def handle_desktop_preview(self,request):
        root=Path(__file__).resolve().parents[1]/'gui'/'web'
        relative=request.match_info.get('path','') or 'index.html'
        if relative=='index.html':
            from gui.webview_window import render_preview_html
            return web.Response(text=render_preview_html(),content_type='text/html')
        if relative.startswith(('themes/','icons/')) or relative in ('themes.js','themes.css','theme-effects.js','theme-effects.css'):
            root=Path(WEB_DIR)
        candidate=(root/relative).resolve()
        if not candidate.is_relative_to(root.resolve()) or candidate.suffix not in ('.html','.js','.css','.svg','.png','.webp'):return web.Response(status=404)
        if not candidate.is_file():return web.Response(status=404)
        # Static shell contains no privileged values; native bridge is absent.
        return web.FileResponse(candidate)

    async def handle_index(self, request):
        with open(os.path.join(WEB_DIR, 'index.html'), encoding='utf-8') as source:
            html = render_versioned(source.read(), get_build_id())
        return web.Response(text=html, content_type='text/html', headers={'Cache-Control': 'no-store'})

    async def handle_version(self, request):
        return web.json_response({'build': get_build_id()}, headers={
            'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*'})

    async def handle_worker(self, request):
        with open(os.path.join(WEB_DIR, 'sw.js'), encoding='utf-8') as source:
            worker = render_versioned(source.read(), get_build_id())
        return web.Response(text=worker, content_type='application/javascript', headers={'Cache-Control': 'no-store'})

    async def _no_cache_headers(self, request, response):
        response.headers['Cache-Control'] = 'no-store'

    async def start(self):
        self.app = web.Application(middlewares=[self._private_transport])
        self.app.on_response_prepare.append(self._no_cache_headers)
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get('/index.html', self.handle_index)
        self.app.router.add_get('/sw.js', self.handle_worker)
        self.app.router.add_get('/api/version', self.handle_version)
        self.app.router.add_get('/api/assets/{asset_id}',self.handle_asset)
        self.app.router.add_get('/api/pairing',self.handle_pairing)
        self.app.router.add_get('/api/pairing/certificate',self.handle_certificate)
        self.app.router.add_route('*','/api/pairing/handoff',self.handle_handoff)
        self.app.router.add_get('/preview/desktop/',self.handle_desktop_preview)
        self.app.router.add_get('/preview/desktop/{path:.*}',self.handle_desktop_preview)
        self.app.router.add_get("/api/info", self.handle_info)
        self.app.router.add_route("*", "/api/config", self.handle_config)
        self.app.router.add_get("/ws", self.handle_ws)

        # Static assets
        self.app.router.add_static("/", WEB_DIR, show_index=False)

        port = int(self.config.get("port", 8765))
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "0.0.0.0", port)
        await self.site.start()
        if self.config.get('https_enabled',False):await self.enable_https()
        if self.config.get('tailscale_enabled',False):await self.refresh_tailscale(True)
        self.volume_monitor_task = asyncio.create_task(self._volume_monitor_loop())
        self.desktop_monitor_task = asyncio.create_task(self._desktop_monitor_loop())
        print(f"TouchHelm Server listening on port {port}")

    async def stop(self):
        text_tasks=list(self._text_tasks.values())
        for task in text_tasks:task.cancel()
        if text_tasks:await asyncio.gather(*text_tasks,return_exceptions=True)
        self._text_tasks.clear()
        await self.text_service.close()
        for task in self._remote_tasks.values():task.cancel()
        await asyncio.gather(*self._remote_tasks.values(),return_exceptions=True)
        self._remote_tasks.clear()
        await self.remote.stop('Host stopped.')
        await self.stop_tailscale_backend()
        await self.disable_https()
        if self.desktop_monitor_task:
            self.desktop_monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.desktop_monitor_task
            self.desktop_monitor_task = None
        tasks = list(self._service_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._service_tasks.clear()
        if self.volume_monitor_task:
            self.volume_monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.volume_monitor_task
            self.volume_monitor_task = None
        for ws, client in list(self.clients.items()):
            self._release_client_input(client)
            await ws.close(code=1001, message=b"Server shutting down")
        self.clients.clear()
        self._notify_client_change()
        self.laser_client.stop()
        await self.desktop_services.close()
        await self._native_call('close')
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        self.site = None
