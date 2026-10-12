"""Compact, click-through, per-pixel-alpha Windows laser overlay."""
import ctypes
from ctypes import wintypes
from functools import lru_cache
import json
import math
import os
import queue
import subprocess
import sys
import threading

from PIL import Image


COLOR_PRESETS = {
    'red': ((255, 68, 102), (255, 0, 51)),
    'green': ((68, 255, 136), (0, 238, 68)),
    'blue': ((51, 187, 255), (0, 136, 255)),
    'amber': ((255, 187, 51), (255, 136, 0)),
}
SPRITE_SIZE = 64


@lru_cache(maxsize=4)
def glow_sprite(color_name):
    outer, middle = COLOR_PRESETS.get(color_name, COLOR_PRESETS['red'])
    image = Image.new('RGBA', (SPRITE_SIZE, SPRITE_SIZE))
    pixels = image.load()
    for y in range(SPRITE_SIZE):
        for x in range(SPRITE_SIZE):
            radius = math.hypot(x - 31.5, y - 31.5)
            if radius <= 4:
                pixels[x, y] = (255, 255, 255, 255)
            elif radius <= 10:
                fraction = (radius - 4) / 6
                pixels[x, y] = (*(round(255 * (1 - fraction) + c * fraction) for c in middle),
                                round(245 - 35 * fraction))
            elif radius < 29:
                fraction = (radius - 10) / 19
                pixels[x, y] = (*(round(middle[i] * (1 - fraction) + outer[i] * fraction)
                                  for i in range(3)), round(130 * (1 - fraction) ** 2))
    return image


def laser_geometry(norm_x, norm_y, rect, size=SPRITE_SIZE):
    x = rect['x'] + round(max(0., min(1., float(norm_x))) * rect['width']) - size // 2
    y = rect['y'] + round(max(0., min(1., float(norm_y))) * rect['height']) - size // 2
    return x, y, size


class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [('cx', ctypes.c_long), ('cy', ctypes.c_long)]


class BLEND(ctypes.Structure):
    _fields_ = [('op', ctypes.c_byte), ('flags', ctypes.c_byte),
                ('constant_alpha', ctypes.c_byte), ('alpha_format', ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('width', ctypes.c_long),
                ('height', ctypes.c_long), ('planes', wintypes.WORD),
                ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
                ('image_size', wintypes.DWORD), ('xppm', ctypes.c_long),
                ('yppm', ctypes.c_long), ('colors', wintypes.DWORD),
                ('important', wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('header', BITMAPINFOHEADER), ('colors', wintypes.DWORD * 3)]


def _signature(dll, name, result, *args):
    method = getattr(dll, name)
    method.restype, method.argtypes = result, list(args)
    return method


def _premultiplied_bgra(image):
    pixels = bytearray(image.tobytes())
    for offset in range(0, len(pixels), 4):
        red, green, blue, alpha = pixels[offset:offset + 4]
        pixels[offset:offset + 4] = bytes((blue * alpha // 255, green * alpha // 255,
                                          red * alpha // 255, alpha))
    return bytes(pixels)


class LaserOverlayApp:
    """A 64px layered popup whose four color DIBs stay cached until exit."""
    def __init__(self, color_name='red'):
        self.api, self.gdi, self.kernel = (ctypes.windll.user32, ctypes.windll.gdi32,
                                           ctypes.windll.kernel32)
        try:
            self.api.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            self.api.SetProcessDPIAware()
        self._configure()
        self.color_name = color_name if color_name in COLOR_PRESETS else 'red'
        self.display_rect = None
        self.is_active = False
        self._bitmaps = {}
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [('style', wintypes.UINT), ('proc', proc_type),
                        ('cls_extra', ctypes.c_int), ('wnd_extra', ctypes.c_int),
                        ('instance', wintypes.HINSTANCE), ('icon', wintypes.HICON),
                        ('cursor', wintypes.HANDLE), ('background', wintypes.HBRUSH),
                        ('menu', wintypes.LPCWSTR), ('name', wintypes.LPCWSTR)]

        @proc_type
        def window_proc(hwnd, message, wparam, lparam):
            if message == 0x0021:  # WM_MOUSEACTIVATE
                return 3  # MA_NOACTIVATE
            if message == 0x0084:  # WM_NCHITTEST
                return -1  # HTTRANSPARENT
            return self.api.DefWindowProcW(hwnd, message, wparam, lparam)

        self._window_proc = window_proc
        self._class = WNDCLASS()
        self._class.proc = window_proc
        self._class.instance = self.kernel.GetModuleHandleW(None)
        self._class.name = f'TouchHelmLaser{os.getpid()}'
        self.api.RegisterClassW(ctypes.byref(self._class))
        # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE, initially hidden.
        self.hwnd = self.api.CreateWindowExW(0x080800A8, self._class.name,
            'TouchHelm laser', 0x80000000, 0, 0, SPRITE_SIZE, SPRITE_SIZE,
            None, None, self._class.instance, None)
        if not self.hwnd:
            raise OSError('Could not create laser overlay window')

    def _configure(self):
        api, gdi, kernel = self.api, self.gdi, self.kernel
        _signature(kernel, 'GetModuleHandleW', wintypes.HMODULE, wintypes.LPCWSTR)
        _signature(api, 'DefWindowProcW', ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                   wintypes.WPARAM, wintypes.LPARAM)
        _signature(api, 'RegisterClassW', wintypes.ATOM, ctypes.c_void_p)
        _signature(api, 'CreateWindowExW', wintypes.HWND, wintypes.DWORD, wintypes.LPCWSTR,
                   wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                   ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                   wintypes.HINSTANCE, ctypes.c_void_p)
        _signature(api, 'UpdateLayeredWindow', wintypes.BOOL, wintypes.HWND, wintypes.HDC,
                   ctypes.POINTER(POINT), ctypes.POINTER(SIZE), wintypes.HDC,
                   ctypes.POINTER(POINT), wintypes.DWORD, ctypes.POINTER(BLEND), wintypes.DWORD)
        _signature(api, 'GetDC', wintypes.HDC, wintypes.HWND)
        _signature(api, 'ReleaseDC', ctypes.c_int, wintypes.HWND, wintypes.HDC)
        _signature(api, 'ShowWindow', wintypes.BOOL, wintypes.HWND, ctypes.c_int)
        _signature(api, 'DestroyWindow', wintypes.BOOL, wintypes.HWND)
        _signature(api, 'PeekMessageW', wintypes.BOOL, ctypes.POINTER(wintypes.MSG),
                   wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT)
        _signature(api, 'TranslateMessage', wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
        _signature(api, 'DispatchMessageW', ctypes.c_ssize_t, ctypes.POINTER(wintypes.MSG))
        _signature(gdi, 'CreateCompatibleDC', wintypes.HDC, wintypes.HDC)
        _signature(gdi, 'CreateDIBSection', wintypes.HBITMAP, wintypes.HDC,
                   ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
        _signature(gdi, 'SelectObject', wintypes.HANDLE, wintypes.HDC, wintypes.HANDLE)
        _signature(gdi, 'DeleteObject', wintypes.BOOL, wintypes.HANDLE)
        _signature(gdi, 'DeleteDC', wintypes.BOOL, wintypes.HDC)

    def _bitmap(self, color):
        if color in self._bitmaps:
            return self._bitmaps[color]
        info = BITMAPINFO()
        info.header.size = ctypes.sizeof(BITMAPINFOHEADER)
        info.header.width, info.header.height = SPRITE_SIZE, -SPRITE_SIZE
        info.header.planes, info.header.bits = 1, 32
        bits = ctypes.c_void_p()
        dc = self.gdi.CreateCompatibleDC(None)
        bitmap = self.gdi.CreateDIBSection(dc, ctypes.byref(info), 0,
                                           ctypes.byref(bits), None, 0)
        if not bitmap or not bits.value:
            self.gdi.DeleteDC(dc)
            raise OSError('Could not prepare laser bitmap')
        ctypes.memmove(bits, _premultiplied_bgra(glow_sprite(color)), SPRITE_SIZE ** 2 * 4)
        previous = self.gdi.SelectObject(dc, bitmap)
        self._bitmaps[color] = (dc, bitmap, previous)
        return self._bitmaps[color]

    def set_color(self, color_name):
        if color_name in COLOR_PRESETS:
            self.color_name = color_name

    def set_display(self, rect):
        if not isinstance(rect, dict):
            return
        values = [rect.get(key) for key in ('x', 'y', 'width', 'height')]
        if any(type(value) is not int for value in values):
            return
        if values[2] <= 0 or values[3] <= 0 or values[2] > 40000 or values[3] > 40000:
            return
        self.display_rect = dict(zip(('x', 'y', 'width', 'height'), values))

    def update_position(self, norm_x, norm_y, active=True):
        if not active:
            self.hide()
            return
        if self.display_rect is None:
            self.set_display({'x': 0, 'y': 0, 'width': self.api.GetSystemMetrics(0),
                              'height': self.api.GetSystemMetrics(1)})
        try:
            if not math.isfinite(float(norm_x)) or not math.isfinite(float(norm_y)):
                return
            x, y, size = laser_geometry(norm_x, norm_y, self.display_rect)
        except (TypeError, ValueError):
            return
        dc, _, _ = self._bitmap(self.color_name)
        position, dimensions, source = POINT(x, y), SIZE(size, size), POINT(0, 0)
        blend = BLEND(0, 0, 255, 1)
        screen = self.api.GetDC(None)
        try:
            updated = self.api.UpdateLayeredWindow(self.hwnd, screen,
                ctypes.byref(position), ctypes.byref(dimensions), dc,
                ctypes.byref(source), 0, ctypes.byref(blend), 2)
        finally:
            self.api.ReleaseDC(None, screen)
        if updated:
            self.api.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
            self.is_active = True

    def hide(self):
        self.api.ShowWindow(self.hwnd, 0)
        self.is_active = False

    def pump_messages(self):
        message = wintypes.MSG()
        while self.api.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            self.api.TranslateMessage(ctypes.byref(message))
            self.api.DispatchMessageW(ctypes.byref(message))

    def close(self):
        if self.hwnd:
            self.api.DestroyWindow(self.hwnd)
            self.hwnd = None
        for dc, bitmap, previous in self._bitmaps.values():
            self.gdi.SelectObject(dc, previous)
            self.gdi.DeleteObject(bitmap)
            self.gdi.DeleteDC(dc)
        self._bitmaps.clear()


def run_overlay_process():
    app = LaserOverlayApp()
    commands = queue.Queue(maxsize=1)
    disconnected = threading.Event()

    def read_commands():
        try:
            for line in sys.stdin:
                try:
                    command = json.loads(line)
                    if not isinstance(command, dict):
                        continue
                    if commands.full():
                        commands.get_nowait()
                    commands.put_nowait(command)
                except (ValueError, queue.Empty, queue.Full):
                    continue
        finally:
            disconnected.set()

    threading.Thread(target=read_commands, daemon=True).start()
    try:
        while not disconnected.is_set() or not commands.empty():
            try:
                command = commands.get(timeout=.01)
            except queue.Empty:
                app.pump_messages()
                continue
            name = command.get('cmd')
            if name == 'quit':
                break
            if name == 'update':
                if command.get('display_rect'):
                    app.set_display(command['display_rect'])
                app.update_position(command.get('x', .5), command.get('y', .5),
                                    command.get('active', True))
            elif name == 'color':
                app.set_color(command.get('color'))
            elif name == 'hide':
                app.hide()
            app.pump_messages()
    finally:
        app.close()


class LaserOverlayClient:
    """Existing JSON command interface to an owned, lazy helper process."""
    def __init__(self):
        self.proc = None
        self._is_enabled = False
        self.color = 'red'

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        try:
            self.proc = subprocess.Popen([sys.executable, '-u', '-m', 'server.laser_overlay'],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                text=True, bufsize=1,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                creationflags=subprocess.CREATE_NO_WINDOW)
            self._is_enabled = True
            self.set_color(self.color)
        except OSError:
            self.proc = None
            self._is_enabled = False

    def _send(self, command):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(json.dumps(command) + '\n')
                self.proc.stdin.flush()
            except (OSError, ValueError):
                pass

    def update(self, x, y, active=True, display_rect=None):
        if not self.proc or self.proc.poll() is not None:
            if active:
                self.start()
            else:
                return
        command = {'cmd': 'update', 'x': x, 'y': y, 'active': active}
        if display_rect is not None:
            command['display_rect'] = display_rect
        self._send(command)

    def set_color(self, color):
        if color in COLOR_PRESETS:
            self.color = color
            self._send({'cmd': 'color', 'color': color})

    def hide(self):
        self._send({'cmd': 'hide'})

    def stop(self):
        process, self.proc = self.proc, None
        self._is_enabled = False
        if process is None:
            return
        try:
            if process.poll() is None:
                process.stdin.write(json.dumps({'cmd': 'quit'}) + '\n')
                process.stdin.flush()
            process.wait(timeout=.5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            try:
                process.terminate()
                process.wait(timeout=.5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=.5)


if __name__ == '__main__':
    run_overlay_process()
