"""
TouchHelm - Windows Native Input Controller
High-precision, sub-millisecond mouse and keyboard simulation via Win32 User32 APIs.
"""

import ctypes
from ctypes import wintypes
import time
import math
import subprocess
import threading

from .osd_overlay import OSDOverlay

user32 = ctypes.windll.user32

# Win32 Mouse Flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000

# Win32 Keyboard Flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

# Win32 Virtual Key Codes
VK_MAP = {
    "backspace": 0x08, "back": 0x08,
    "tab": 0x09,
    "clear": 0x0C,
    "enter": 0x0D, "return": 0x0D,
    "numpadenter": 0x0D, "numpad_enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B, "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "pgdn": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "select": 0x29,
    "print": 0x2A,
    "execute": 0x2B,
    "printscreen": 0x2C, "prtsc": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E, "del": 0x2E,
    "help": 0x2F,
    "win": 0x5B, "windows": 0x5B, "lwin": 0x5B,
    "rwin": 0x5C,
    "apps": 0x5D,
    "sleep": 0x5F,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69,
    "multiply": 0x6A,
    "add": 0x6B,
    "separator": 0x6C,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "f13": 0x7C, "f14": 0x7D, "f15": 0x7E, "f16": 0x7F,
    "f17": 0x80, "f18": 0x81, "f19": 0x82, "f20": 0x83,
    "f21": 0x84, "f22": 0x85, "f23": 0x86, "f24": 0x87,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "lshift": 0xA0, "shiftleft": 0xA0,
    "rshift": 0xA1, "shiftright": 0xA1,
    "lctrl": 0xA2, "controlleft": 0xA2,
    "rctrl": 0xA3, "controlright": 0xA3,
    "lalt": 0xA4, "altleft": 0xA4,
    "ralt": 0xA5, "altright": 0xA5,
    "numpadmultiply": 0x6A, "numpadadd": 0x6B,
    "numpadsubtract": 0x6D, "numpaddecimal": 0x6E, "numpaddivide": 0x6F,
    # Physical OEM keys; the active Windows keyboard layout determines the glyph.
    "semicolon": 0xBA, ";": 0xBA, "oem_1": 0xBA,
    "equal": 0xBB, "=": 0xBB, "oem_plus": 0xBB,
    "comma": 0xBC, ",": 0xBC,
    "minus": 0xBD, "-": 0xBD,
    "period": 0xBE, ".": 0xBE,
    "slash": 0xBF, "/": 0xBF, "oem_2": 0xBF,
    "backquote": 0xC0, "`": 0xC0, "oem_3": 0xC0,
    "bracketleft": 0xDB, "[": 0xDB, "oem_4": 0xDB,
    "backslash": 0xDC, "\\": 0xDC, "oem_5": 0xDC,
    "bracketright": 0xDD, "]": 0xDD, "oem_6": 0xDD,
    "quote": 0xDE, "'": 0xDE, "oem_7": 0xDE,
    "intlbackslash": 0xE2, "oem_102": 0xE2,
    "volume_mute": 0xAD, "mute": 0xAD,
    "volume_down": 0xAE, "volumedown": 0xAE,
    "volume_up": 0xAF, "volumeup": 0xAF,
    "media_next": 0xB0, "nexttrack": 0xB0,
    "media_prev": 0xB1, "prevtrack": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3, "playpause": 0xB3,
    "browser_back": 0xA6,
    "browser_forward": 0xA7,
    "browser_refresh": 0xA8,
    "browser_home": 0xAC,
}

# Win32 Structures for SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t)
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class INPUT_I(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("i", INPUT_I)
    ]

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


# COM GUID structure and Win32 COM helpers
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8)
    ]

ole32 = ctypes.oledll.ole32

def _parse_guid(guid_str: str) -> GUID:
    g = GUID()
    ole32.CLSIDFromString(wintypes.LPCWSTR(guid_str), ctypes.byref(g))
    return g

CLSID_MMDeviceEnumerator = _parse_guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
IID_IMMDeviceEnumerator = _parse_guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
IID_IAudioEndpointVolume = _parse_guid("{5CDF2C82-841E-4546-9722-0CF74078229A}")


class WindowsAudioController:
    """
    Direct Windows Core Audio COM Controller.
    Queries and controls real Windows Master Audio Volume (0-100%) and Mute state
    with zero external third-party dependencies.
    """

    def __init__(self):
        self._cached_vol = None
        self._cached_mute = None
        try:
            v, m = self.get_volume_info()
            self._cached_vol = v
            self._cached_mute = m
        except Exception:
            pass

    @staticmethod
    def _get_endpoint_volume():
        pEnumerator = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator),
            None,
            1,  # CLSCTX_INPROC_SERVER
            ctypes.byref(IID_IMMDeviceEnumerator),
            ctypes.byref(pEnumerator)
        )
        if hr != 0 or not pEnumerator:
            return None, None, None

        enum_vtable = ctypes.cast(pEnumerator, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        GetDefaultAudioEndpoint = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
        )(enum_vtable[4])
        ReleaseEnum = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(enum_vtable[2])

        pDevice = ctypes.c_void_p()
        hr = GetDefaultAudioEndpoint(pEnumerator, 0, 0, ctypes.byref(pDevice))  # eRender=0, eConsole=0
        ReleaseEnum(pEnumerator)
        if hr != 0 or not pDevice:
            return None, None, None

        dev_vtable = ctypes.cast(pDevice, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        Activate = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )(dev_vtable[3])
        ReleaseDev = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(dev_vtable[2])

        pVolume = ctypes.c_void_p()
        hr = Activate(pDevice, ctypes.byref(IID_IAudioEndpointVolume), 1, None, ctypes.byref(pVolume))
        ReleaseDev(pDevice)
        if hr != 0 or not pVolume:
            return None, None, None

        vol_vtable = ctypes.cast(pVolume, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ReleaseVol = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vol_vtable[2])
        return pVolume, vol_vtable, ReleaseVol

    def _unknown(self):
        self._cached_vol = self._cached_mute = None
        return None, None

    def _read_endpoint(self, endpoint, vtable):
        get_level = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_float))(vtable[9])
        get_mute = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                                     ctypes.POINTER(wintypes.BOOL))(vtable[15])
        level, muted = ctypes.c_float(), wintypes.BOOL()
        level_ok = get_level(endpoint, ctypes.byref(level)) == 0
        mute_ok = get_mute(endpoint, ctypes.byref(muted)) == 0
        self._cached_vol = (max(0, min(100, round(level.value * 100)))
                            if level_ok and math.isfinite(level.value) else None)
        self._cached_mute = bool(muted.value) if mute_ok else None
        return self._cached_vol, self._cached_mute

    def get_volume_info(self) -> tuple:
        """Observed (percent, mute); a missing/failed field is None."""
        hr_init = ole32.CoInitialize(None)
        try:
            endpoint, vtable, release = self._get_endpoint_volume()
            if not endpoint:
                return self._unknown()
            try:
                return self._read_endpoint(endpoint, vtable)
            finally:
                release(endpoint)
        except Exception:
            return self._unknown()
        finally:
            if hr_init in (0, 1):
                ole32.CoUninitialize()

    def set_volume(self, percent: int) -> tuple:
        """Request an absolute level and return measured readback only."""
        percent = max(0, min(100, int(percent)))
        hr_init = ole32.CoInitialize(None)
        try:
            endpoint, vtable, release = self._get_endpoint_volume()
            if not endpoint:
                return self._unknown()
            try:
                setter = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                    ctypes.c_float, ctypes.c_void_p)(vtable[7])
                if setter(endpoint, percent / 100.0, None) != 0:
                    return self._unknown()
                if percent > 0:
                    # Setting a positive level explicitly unmutes without
                    # relying on a stale cached mute observation.
                    unmute = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                        wintypes.BOOL, ctypes.c_void_p)(vtable[14])
                    unmute(endpoint, wintypes.BOOL(False), None)
                return self._read_endpoint(endpoint, vtable)
            finally:
                release(endpoint)
        except Exception:
            return self._unknown()
        finally:
            if hr_init in (0, 1):
                ole32.CoUninitialize()

    def toggle_mute(self) -> tuple:
        _, muted = self.get_volume_info()
        if muted is None:
            return self._unknown()
        return self.set_mute(not muted)

    def set_mute(self, is_muted: bool) -> tuple:
        hr_init = ole32.CoInitialize(None)
        try:
            endpoint, vtable, release = self._get_endpoint_volume()
            if not endpoint:
                return self._unknown()
            try:
                setter = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                    wintypes.BOOL, ctypes.c_void_p)(vtable[14])
                if setter(endpoint, wintypes.BOOL(bool(is_muted)), None) != 0:
                    return self._unknown()
                return self._read_endpoint(endpoint, vtable)
            finally:
                release(endpoint)
        except Exception:
            return self._unknown()
        finally:
            if hr_init in (0, 1):
                ole32.CoUninitialize()
    def change_volume(self, delta: int) -> tuple:
        """Adjusts volume by delta percent."""
        cur_vol, cur_mute = self.get_volume_info()
        if cur_vol is None:
            return None, cur_mute
        new_vol = max(0, min(100, cur_vol + delta))
        if delta > 0 and cur_mute:
            self.set_mute(False)
        return self.set_volume(new_vol)


class WindowsBrightnessController:
    """
    Windows Display Brightness Controller.
    Queries and controls monitor brightness via Windows WMI (WmiMonitorBrightness)
    with Dxva2 fallback for external desktop monitors.
    Thread-safe with background coalescing worker and silent execution (no flashing console windows).
    """

    def __init__(self):
        self._current_level = None
        self._target_level = None
        self._available = False
        self._generation = 0
        self.on_readback = None
        self._lock = threading.Lock()
        self._has_work = threading.Event()
        self._stopping = threading.Event()
        self._worker_thread = threading.Thread(target=self._apply_worker, daemon=True)
        self._worker_thread.start()
        self._query_initial_brightness()

    def _query_initial_brightness(self):
        self.refresh_brightness()

    @property
    def available(self):
        with self._lock:
            return self._available

    def refresh_brightness(self, expected_generation=None):
        """Bounded actual readback; never return an intended target as observed."""
        observed = None
        # 1. Query WMI via powershell with CREATE_NO_WINDOW
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness).CurrentBrightness"],
                capture_output=True, text=True, timeout=2,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            val = res.stdout.strip()
            if res.returncode == 0 and val.isdigit() and 0 <= int(val) <= 100:
                observed = int(val)
        except Exception:
            pass

        # 2. Fallback to Dxva2 for external desktop monitors
        if observed is None:
            observed = self._query_dxva2_brightness()
        with self._lock:
            if expected_generation is not None and expected_generation != self._generation:
                return None
            self._current_level = observed
            if observed is not None:
                self._available = True
        return observed

    def _query_dxva2_brightness(self):
        try:
            dxva2 = ctypes.windll.dxva2
            hmon = user32.MonitorFromPoint(POINT(0, 0), 1)
            count = wintypes.DWORD()
            if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(count)) and count.value > 0:
                class PHYSICAL_MONITOR(ctypes.Structure):
                    _fields_ = [('hPhysicalMonitor', wintypes.HANDLE), ('szDesc', wintypes.WCHAR * 128)]
                mons = (PHYSICAL_MONITOR * count.value)()
                if dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, count.value, mons):
                    mini = wintypes.DWORD()
                    cur = wintypes.DWORD()
                    maxi = wintypes.DWORD()
                    ok = dxva2.GetMonitorBrightness(mons[0].hPhysicalMonitor, ctypes.byref(mini), ctypes.byref(cur), ctypes.byref(maxi))
                    dxva2.DestroyPhysicalMonitors(count.value, mons)
                    if ok and maxi.value > mini.value:
                        pct = round(((cur.value - mini.value) / (maxi.value - mini.value)) * 100)
                        return max(0, min(100, pct))
        except Exception:
            pass
        return None

    def _apply_dxva2_brightness(self, target_percent: int):
        try:
            dxva2 = ctypes.windll.dxva2
            hmon = user32.MonitorFromPoint(POINT(0, 0), 1)
            count = wintypes.DWORD()
            if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(count)) and count.value > 0:
                class PHYSICAL_MONITOR(ctypes.Structure):
                    _fields_ = [('hPhysicalMonitor', wintypes.HANDLE), ('szDesc', wintypes.WCHAR * 128)]
                mons = (PHYSICAL_MONITOR * count.value)()
                if dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, count.value, mons):
                    for i in range(count.value):
                        mini = wintypes.DWORD()
                        cur = wintypes.DWORD()
                        maxi = wintypes.DWORD()
                        if dxva2.GetMonitorBrightness(mons[i].hPhysicalMonitor, ctypes.byref(mini), ctypes.byref(cur), ctypes.byref(maxi)):
                            if maxi.value > mini.value:
                                val = round(mini.value + (target_percent / 100.0) * (maxi.value - mini.value))
                                dxva2.SetMonitorBrightness(mons[i].hPhysicalMonitor, val)
                    dxva2.DestroyPhysicalMonitors(count.value, mons)
        except Exception:
            pass

    def _apply_worker(self):
        while not self._stopping.is_set():
            self._has_work.wait()
            self._has_work.clear()
            if self._stopping.is_set():
                break
            with self._lock:
                target = self._target_level
                self._target_level = None
                generation = self._generation
            if target is None:
                continue

            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {target})"],
                    capture_output=True, timeout=3,
                    creationflags=0x08000000  # CREATE_NO_WINDOW
                )
            except Exception:
                pass

            # Also apply to Dxva2 monitors if available
            if self._stopping.is_set():
                break
            try:
                self._apply_dxva2_brightness(target)
            except Exception:
                pass
            observed = self.refresh_brightness(expected_generation=generation)
            if self._stopping.is_set():
                break
            if observed is not None and callable(self.on_readback):
                try:
                    self.on_readback(observed)
                except Exception:
                    pass

    def get_brightness(self):
        with self._lock:
            return self._current_level

    def set_brightness(self, level: int):
        level = max(0, min(100, int(level)))
        with self._lock:
            if self._stopping.is_set():
                return self._current_level
            self._generation += 1
            self._current_level = None
            self._target_level = level
            self._has_work.set()
        return None

    def change_brightness(self, delta: int):
        with self._lock:
            if self._stopping.is_set() or self._current_level is None:
                return self._current_level
            new_level = max(0, min(100, self._current_level + delta))
            self._generation += 1
            self._current_level = None
            self._target_level = new_level
            self._has_work.set()
            return None

    def close(self):
        """Cancel queued brightness changes and let an in-flight bounded query finish."""
        self._stopping.set()
        with self._lock:
            self._target_level = None
        self._has_work.set()
        if threading.current_thread() is not self._worker_thread:
            self._worker_thread.join(timeout=3.5)


class WindowsInputController:
    """Precision Windows Input Controller with acceleration and smooth handling."""

    def __init__(self):
        self.subpixel_x = 0.0
        self.subpixel_y = 0.0
        self.is_left_down = False
        self.is_right_down = False
        self.is_middle_down = False
        self.audio_ctrl = WindowsAudioController()
        self.brightness_ctrl = WindowsBrightnessController()
        self.osd = OSDOverlay()
        self._closed = False
        self.ensure_input_desktop()

    def ensure_input_desktop(self):
        """Attaches calling thread to active interactive Windows desktop."""
        try:
            h_input = user32.OpenInputDesktop(0, False, 0x01FF)
            if not h_input:
                h_input = user32.OpenInputDesktop(0, False, 0x0001)
            if h_input:
                user32.SetThreadDesktop(h_input)
                user32.CloseDesktop(h_input)
        except Exception:
            pass

    def get_screen_size(self):
        """Returns (width, height) of primary screen."""
        self.ensure_input_desktop()
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        return w, h

    def get_cursor_pos(self):
        """Returns (x, y) coordinates of cursor."""
        self.ensure_input_desktop()
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def set_cursor_pos(self, x: int, y: int):
        """Sets cursor position directly."""
        self.ensure_input_desktop()
        user32.SetCursorPos(int(x), int(y))

    def set_physical_cursor_pos(self, x: int, y: int):
        """Map capture pixels without caller DPI virtualization."""
        self.ensure_input_desktop()
        if not user32.SetPhysicalCursorPos(int(x), int(y)):
            raise RuntimeError('Windows could not move the pointer in the active desktop.')

    def get_physical_cursor_pos(self):
        self.ensure_input_desktop()
        point=POINT()
        if not user32.GetPhysicalCursorPos(ctypes.byref(point)):
            raise RuntimeError('Windows could not read the active desktop pointer.')
        return point.x,point.y

    def monitor_matches(self,display):
        """Read physical monitor geometry without going through slow COM providers."""
        class RECT(ctypes.Structure):
            _fields_=[('left',ctypes.c_long),('top',ctypes.c_long),('right',ctypes.c_long),('bottom',ctypes.c_long)]
        class INFO(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('monitor',RECT),('work',RECT),('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]
        callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HANDLE,wintypes.HDC,ctypes.POINTER(RECT),wintypes.LPARAM)
        api=user32;api.GetMonitorInfoW.argtypes=(wintypes.HANDLE,ctypes.POINTER(INFO))
        previous=None
        try:
            api.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
            previous=api.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
            found=[]
            @callback_type
            def visit(handle,dc,rect,param):
                info=INFO();info.size=ctypes.sizeof(INFO)
                if api.GetMonitorInfoW(handle,ctypes.byref(info)) and info.device==display.get('id'):
                    r=info.monitor
                    found.append({'x':r.left,'y':r.top,'width':r.right-r.left,'height':r.bottom-r.top})
                return True
            api.EnumDisplayMonitors(None,None,visit,0)
            return bool(found and found[0]==display.get('rect'))
        finally:
            if previous:api.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))

    def move_rel(self, dx: float, dy: float, sensitivity: float = 1.0, acceleration: float = 1.0):
        """
        Relative mouse movement with sub-pixel accumulator and acceleration curve.
        """
        self.ensure_input_desktop()
        raw_dist = math.hypot(dx, dy)
        if raw_dist > 0:
            accel_factor = 1.0 + (raw_dist * 0.04 * (acceleration - 1.0)) if acceleration > 1.0 else 1.0
            total_dx = dx * sensitivity * accel_factor + self.subpixel_x
            total_dy = dy * sensitivity * accel_factor + self.subpixel_y

            int_dx = int(total_dx)
            int_dy = int(total_dy)

            self.subpixel_x = total_dx - int_dx
            self.subpixel_y = total_dy - int_dy

            if int_dx != 0 or int_dy != 0:
                pt_before = POINT()
                user32.GetCursorPos(ctypes.byref(pt_before))
                user32.mouse_event(MOUSEEVENTF_MOVE, int_dx, int_dy, 0, 0)
                pt_after = POINT()
                user32.GetCursorPos(ctypes.byref(pt_after))
                # Fallback to SetCursorPos if mouse_event did not register
                if pt_after.x == pt_before.x and pt_after.y == pt_before.y:
                    user32.SetCursorPos(pt_before.x + int_dx, pt_before.y + int_dy)

    def mouse_down(self, button: str = "left"):
        """Press down mouse button."""
        self.ensure_input_desktop()
        btn = button.lower()
        if btn == "left":
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.is_left_down = True
        elif btn == "right":
            user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            self.is_right_down = True
        elif btn == "middle":
            user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
            self.is_middle_down = True

    def mouse_up(self, button: str = "left"):
        """Release mouse button."""
        self.ensure_input_desktop()
        btn = button.lower()
        if btn == "left":
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.is_left_down = False
        elif btn == "right":
            user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            self.is_right_down = False
        elif btn == "middle":
            user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
            self.is_middle_down = False

    def click(self, button: str = "left"):
        """Quick click mouse button."""
        self.ensure_input_desktop()
        self.mouse_down(button)
        time.sleep(0.02)
        self.mouse_up(button)

    def double_click(self, button: str = "left"):
        """Double click mouse button."""
        self.click(button)
        time.sleep(0.06)
        self.click(button)

    def scroll(self, dx: float = 0.0, dy: float = 0.0, scroll_speed: float = 1.0, invert: bool = False):
        """
        Scroll wheel simulation.
        dy > 0: scroll up, dy < 0: scroll down.
        """
        self.ensure_input_desktop()
        inv = -1.0 if invert else 1.0
        if dy != 0:
            clicks = int(dy * scroll_speed * 15.0 * inv)
            if clicks != 0:
                user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, clicks, 0)
        if dx != 0:
            clicks_h = int(dx * scroll_speed * 15.0 * inv)
            if clicks_h != 0:
                user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, clicks_h, 0)

    def _get_vk(self, key: str):
        """Resolves key string to virtual key code."""
        key_lower = key.lower()
        if key_lower in VK_MAP:
            return VK_MAP[key_lower]
        if len(key) == 1:
            ch = key.upper()
            if "A" <= ch <= "Z" or "0" <= ch <= "9":
                return ord(ch)
        return None

    def _is_extended_key(self, vk: int, key: str = "") -> bool:
        # Numpad Enter shares VK_RETURN with the main Enter but has an E0 prefix.
        return key.lower() in ("numpadenter", "numpad_enter") or vk in (
            0x5B, 0x5C, 0x5D, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
            0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x6F, 0x90, 0xA3, 0xA5,
            0xA6, 0xA7, 0xA8, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3)

    def key_down(self, key: str):
        """Press down a virtual key."""
        self.ensure_input_desktop()
        vk = self._get_vk(key)
        if vk:
            flags = KEYEVENTF_EXTENDEDKEY if self._is_extended_key(vk, key) else 0
            user32.keybd_event(vk, 0, flags, 0)

    def key_up(self, key: str):
        """Release a virtual key."""
        self.ensure_input_desktop()
        vk = self._get_vk(key)
        if vk:
            flags = (KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP) if self._is_extended_key(vk, key) else KEYEVENTF_KEYUP
            user32.keybd_event(vk, 0, flags, 0)

    def key_tap(self, key: str):
        """Tap a virtual key."""
        self.ensure_input_desktop()
        vk = self._get_vk(key)
        if vk:
            flags = KEYEVENTF_EXTENDEDKEY if self._is_extended_key(vk, key) else 0
            try:
                user32.keybd_event(vk, 0, flags, 0)
                time.sleep(0.015)
            finally:user32.keybd_event(vk, 0, flags | KEYEVENTF_KEYUP, 0)

    def hotkey(self, *keys):
        """Presses keys in sequence, then releases in reverse."""
        self.ensure_input_desktop()
        vk_list = []
        release_error=None
        try:
            for k in keys:
                vk = self._get_vk(k)
                if vk:
                    flags = KEYEVENTF_EXTENDEDKEY if self._is_extended_key(vk, k) else 0
                    vk_list.append((vk, flags))
                    user32.keybd_event(vk, 0, flags, 0)
                    time.sleep(0.01)
            time.sleep(0.02)
        finally:
            # Cleanup must not sleep or abandon the remaining modifiers when a
            # shortcut is interrupted or one native release fails.
            for vk, flags in reversed(vk_list):
                try:user32.keybd_event(vk, 0, flags | KEYEVENTF_KEYUP, 0)
                except Exception as error:release_error=error
        if release_error:raise release_error

    def type_unicode_char(self, char: str):
        """Types a single unicode character via SendInput."""
        self.ensure_input_desktop()
        encoded = char.encode("utf-16-le", errors="surrogatepass")
        for offset in range(0, len(encoded), 2):
            self._type_unicode_unit(int.from_bytes(encoded[offset:offset + 2], "little"))

    def _type_unicode_unit(self, code: int):
        # Key down
        inp_down = INPUT()
        inp_down.type = INPUT_KEYBOARD
        inp_down.i.ki.wVk = 0
        inp_down.i.ki.wScan = code
        inp_down.i.ki.dwFlags = KEYEVENTF_UNICODE
        inp_down.i.ki.time = 0
        inp_down.i.ki.dwExtraInfo = 0

        # Key up
        inp_up = INPUT()
        inp_up.type = INPUT_KEYBOARD
        inp_up.i.ki.wVk = 0
        inp_up.i.ki.wScan = code
        inp_up.i.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inp_up.i.ki.time = 0
        inp_up.i.ki.dwExtraInfo = 0

        arr = (INPUT * 2)(inp_down, inp_up)
        user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))

    def type_text(self, text: str, newline_mode='enter'):
        """Types string with full unicode support."""
        for ch in text:
            if ch == "\n":
                if newline_mode == 'shift_enter':
                    self.hotkey('shift','enter')
                else:
                    self.key_tap("enter")
            elif ch == "\t":
                self.key_tap("tab")
            else:
                self.type_unicode_char(ch)

    def zoom(self,delta):
        """Ctrl-wheel while preserving an already-held physical Control key."""
        self.ensure_input_desktop()
        held=bool(user32.GetAsyncKeyState(0x11)&0x8000)
        if not held:self.key_down('ctrl')
        try:user32.mouse_event(MOUSEEVENTF_WHEEL,0,0,int(max(-10,min(10,delta))*120),0)
        finally:
            if not held:self.key_up('ctrl')

    def presentation_action(self, action: str):
        """
        Executes presentation control actions.
        Compatible with PowerPoint, Google Slides, Keynote, PDF viewers, Prezi.
        """
        act = action.lower()
        if act in ("next", "slide_next"):
            # Right arrow advances slides in PowerPoint/Google Slides/PDF
            self.key_tap("right")
        elif act in ("prev", "previous", "slide_prev"):
            # Left arrow goes back
            self.key_tap("left")
        elif act in ("start", "slide_start"):
            # F5 starts presentation from beginning
            self.key_tap("f5")
        elif act in ("start_current", "slide_current", "current"):
            # Shift + F5 starts from current slide
            self.hotkey("shift", "f5")
        elif act in ("end", "slide_end", "exit"):
            # Escape ends presentation
            self.key_tap("esc")
        elif act in ("black", "slide_black"):
            # 'B' toggles black screen in PowerPoint/Keynote
            self.type_unicode_char("b")
        elif act in ("white", "slide_white"):
            # 'W' toggles white screen
            self.type_unicode_char("w")

    # -------------------------------------------------------------------------
    # Audio Volume & Display Brightness Control
    # -------------------------------------------------------------------------
    def get_volume(self) -> tuple:
        """Returns (volume_percent, is_muted)."""
        return self.audio_ctrl.get_volume_info()

    def set_volume(self, percent: int) -> tuple:
        """Sets Windows master volume (0-100) and returns (new_volume, is_muted)."""
        state = self.audio_ctrl.set_volume(percent)
        if state[0] is not None and state[1] is not None:
            self.osd.show("volume", state[0], muted=state[1])
        return state

    def toggle_mute(self) -> tuple:
        """Toggles Windows master mute and returns (volume, is_muted)."""
        return self._native_volume_key("volume_mute")

    def set_mute(self, is_muted: bool) -> tuple:
        """Sets Windows master mute and returns (volume, is_muted)."""
        state = self.audio_ctrl.set_mute(is_muted)
        if state[0] is not None and state[1] is not None:
            self.osd.show("volume", state[0], muted=state[1])
        return state

    def change_volume(self, delta: int) -> tuple:
        """Changes Windows master volume by delta and returns (volume, is_muted)."""
        if delta in (-2, 2):
            return self._native_volume_key("volume_up" if delta > 0 else "volume_down")
        state = self.audio_ctrl.change_volume(delta)
        if state[0] is not None and state[1] is not None:
            self.osd.show("volume", state[0], muted=state[1])
        return state

    def _native_volume_key(self, key: str) -> tuple:
        before = self.audio_ctrl.get_volume_info()
        self.key_tap(key)
        state = before
        # Windows handles the media key asynchronously. Bound both elapsed time
        # and query count, including the unchanged-at-min/max case.
        deadline = time.monotonic() + 0.12
        for _ in range(7):
            state = self.audio_ctrl.get_volume_info()
            if state != before or time.monotonic() >= deadline:
                break
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
        return state

    def get_brightness(self) -> int:
        """Returns current display brightness percentage (0-100)."""
        return self.brightness_ctrl.get_brightness()

    def set_brightness(self, level: int) -> int:
        """Queue a target; display feedback only after actual worker readback."""
        self.brightness_ctrl.on_readback = self._brightness_observed
        actual = self.brightness_ctrl.set_brightness(level)
        if actual is not None:
            self.osd.show("brightness", actual)
        return actual

    def change_brightness(self, delta: int) -> int:
        """Change from a known measured level; unknown readback stays unknown."""
        self.brightness_ctrl.on_readback = self._brightness_observed
        actual = self.brightness_ctrl.change_brightness(delta)
        if actual is not None:
            self.osd.show("brightness", actual)
        return actual

    def _brightness_observed(self, actual):
        if actual is not None and not self._closed:
            self.osd.show("brightness", actual)

    def close(self):
        """Close only feedback/brightness resources owned by this controller."""
        if self._closed:
            return
        self._closed = True
        try:
            self.osd.close()
        finally:
            self.brightness_ctrl.close()

    def media_action(self, action: str):
        """Executes multimedia key actions."""
        act = action.lower()
        if act in ("vol_up", "volume_up", "volumeup"):
            return self.change_volume(2)
        elif act in ("vol_down", "volume_down", "volumedown"):
            return self.change_volume(-2)
        elif act in ("mute", "volume_mute", "volumemute"):
            return self.toggle_mute()
        elif act in ("play_pause", "playpause", "play"):
            self.key_tap("media_play_pause")
        elif act in ("next", "nexttrack", "media_next"):
            self.key_tap("media_next")
        elif act in ("prev", "previous", "prevtrack", "media_prev"):
            self.key_tap("media_prev")
        elif act in ("stop", "media_stop"):
            self.key_tap("media_stop")

    def windows_shortcut(self, shortcut: str):
        """Executes Windows desktop productivity shortcuts."""
        sc = shortcut.lower()
        if sc in ("start", "start_menu", "win", "windows"):
            self.key_tap("win")
        elif sc == "desktop":
            self.hotkey("win", "d")
        elif sc == "task_view":
            self.hotkey("win", "tab")
        elif sc == "app_switch":
            self.hotkey("alt", "tab")
        elif sc == "lock":
            self.hotkey("win", "l")
        elif sc == "close":
            self.hotkey("alt", "f4")
        elif sc == "search":
            self.hotkey("win", "s")
        elif sc == "screenshot":
            self.hotkey("win", "shift", "s")
        elif sc == "file_explorer":
            self.hotkey("win", "e")
        elif sc == "settings":
            self.hotkey("win", "i")
        elif sc == "copy":
            self.hotkey("ctrl", "c")
        elif sc == "paste":
            self.hotkey("ctrl", "v")
        elif sc == "cut":
            self.hotkey("ctrl", "x")
        elif sc == "undo":
            self.hotkey("ctrl", "z")
        elif sc == "redo":
            self.hotkey("ctrl", "y")
        elif sc == "save":
            self.hotkey("ctrl", "s")
        elif sc == "select_all":
            self.hotkey("ctrl", "a")
