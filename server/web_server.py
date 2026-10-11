"""
TouchHelm - Async Web & WebSocket Server
Handles HTTP static serving (PWA client) and real-time low-latency WebSocket communication.
"""

import os
import json
import time
import asyncio
import math
import hmac
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
        self._service_tasks = {}
        self._native_action_lock = asyncio.Lock()

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
        try:
            if kind == 'get_desktop_state':
                reply = {'type': 'desktop_state', **await self.desktop_services.snapshot()}
            elif kind == 'get_apps':
                reply = {'type': 'apps_sync', 'apps': await self.desktop_services.list_apps()}
            elif kind == 'get_media_library':
                reply = {'type': 'media_library', **await self.desktop_services.list_media()}
            else:
                if kind == 'launch_app':
                    result = await self.desktop_services.launch_app(data.get('app_id', ''))
                elif kind == 'play_media':
                    result = await self.desktop_services.media_command('play',
                        session_id=data.get('session_id', ''), item_id=data.get('item_id', ''))
                elif kind == 'presentation':
                    action = data.get('action', '')
                    if action not in ('next', 'prev', 'start', 'start_current', 'end', 'black', 'white'):
                        result = {'success': False, 'handled': True, 'message': 'Unsupported presentation action.'}
                    else:
                        result = await self.desktop_services.presentation_command(action)
                        if not result.get('handled'):
                            await self._native_call('presentation_action', action)
                            result = {'success': True, 'message': 'Presentation key sent to the active app.'}
                else:
                    action = data.get('action', '')
                    result = await self.desktop_services.media_command(action, session_id=data.get('session_id', ''))
                    if not result.get('handled') and not data.get('session_id'):
                        await self._native_call('media_action', action)
                        result = {'success': True, 'message': 'Media key sent to the active player.'}
                reply = {'type': 'command_result', 'command': kind,
                         'success': bool(result.get('success')), 'message': result.get('message', '')}
            if client.authenticated and client.ws in self.clients and not client.ws.closed:
                await client.ws.send_json(reply)
        except asyncio.CancelledError:
            raise
        except Exception:
            if client.authenticated and not client.ws.closed:
                with suppress(ConnectionError, RuntimeError):
                    await client.ws.send_json({'type': 'command_result', 'command': kind,
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
        clients = list(self.clients.items())
        authorized = not self.config.get("require_pin", False)
        # Revoke every session before yielding to a socket. One disconnected
        # device must not leave the remaining clients authorized with an old PIN.
        for _, client in clients:
            client.authenticated = authorized
        for _, client in clients:
            self._cancel_desktop_requests(client)
            self._release_client_input(client)
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
        return isinstance(pin, str) and pin.isascii() and hmac.compare_digest(pin, self.config.get("pin_code", ""))

    async def _send_auth_success(self, client):
        vol, muted = self.input_ctrl.get_volume()
        await client.ws.send_json({"type": "auth_res", "success": True,
                                   "message": "Connected", "volume": vol, "muted": muted,
                                   "brightness": self.input_ctrl.get_brightness(),
                                   "config": self.config.public_data()})

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
                          "volume": ("level",), "brightness": ("level",)}
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
                         "brightness": ("action",), "laser": ("color",)}
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
        vol, muted = self.input_ctrl.get_volume()
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
                if "port" in data:
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
                            self._cancel_desktop_requests(client)
                            self._release_client_input(client)
                            client.authenticated = False
                            await ws.send_json({"type": "auth_res", "success": False, "message": "Invalid PIN"})
                            self._notify_client_change()
                            continue
                        client.authenticated = True
                        await self._send_auth_success(client)
                        self._log_event(f"Connected as {client.device_name}", client.remote_ip)
                        self._notify_client_change()
                        continue

                    if not client.authenticated:
                        continue

                    desktop_query = msg_type in ('get_desktop_state', 'get_apps', 'launch_app',
                                                  'get_media_library', 'play_media', 'presentation')
                    media_query = msg_type == 'media' and data.get('action') in (
                        'play_pause', 'playpause', 'play', 'pause', 'next', 'prev', 'previous', 'stop', 'nexttrack', 'prevtrack')
                    if desktop_query or media_query:
                        await self._queue_desktop_request(client, data)
                        continue

                    # Update device name if passed in general packets
                    if "device_name" in data and client.device_name == "Unknown Device":
                        client.device_name = str(data["device_name"])[:40]
                        self._notify_client_change()

                    # System status queries
                    if msg_type == "get_volume":
                        cur_vol, cur_muted = self.input_ctrl.get_volume()
                        await ws.send_json({"type": "volume_sync", "volume": cur_vol, "muted": cur_muted})
                        continue

                    elif msg_type == "get_brightness":
                        cur_bright = self.input_ctrl.get_brightness()
                        await ws.send_json({"type": "brightness_sync", "level": cur_bright})
                        continue

                    elif msg_type == "get_system_status":
                        cur_vol, cur_muted = self.input_ctrl.get_volume()
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
                        self.input_ctrl.type_text(txt)
                        self._log_event(f"Typed text ({len(txt)} chars)", client.device_name)

                    elif msg_type == "hotkey":
                        keys = data.get("keys", [])
                        if keys:
                            self.input_ctrl.hotkey(*keys)
                            self._log_event(f"Hotkey: {'+'.join(keys)}", client.device_name)

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
                        self.laser_client.update(norm_x, norm_y, active)

                    elif msg_type == "laser_hide":
                        self.laser_client.hide()

                elif msg.type == web.WSMsgType.ERROR:
                    pass

        finally:
            self._cancel_desktop_requests(client)
            self._release_client_input(client)
            self.laser_client.hide()
            if ws in self.clients:
                del self.clients[ws]
                self._notify_client_change()
                self._log_event("Device disconnected", client.device_name)

        return ws

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
        self.app = web.Application()
        self.app.on_response_prepare.append(self._no_cache_headers)
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get('/index.html', self.handle_index)
        self.app.router.add_get('/sw.js', self.handle_worker)
        self.app.router.add_get('/api/version', self.handle_version)
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
        self.volume_monitor_task = asyncio.create_task(self._volume_monitor_loop())
        self.desktop_monitor_task = asyncio.create_task(self._desktop_monitor_loop())
        print(f"TouchHelm Server listening on port {port}")

    async def stop(self):
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
