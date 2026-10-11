"""Owned, lazy desktop feedback. Importing this module creates no window."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


class OSDOverlay:
    """Send transient feedback to a separate, non-activating native window."""

    def __init__(self):
        self._process = None
        self._closed = False
        self._lock = threading.Lock()

    def show(self, kind: str, value: int, muted: bool = False):
        if kind not in ("volume", "brightness"):
            return
        message = json.dumps({"kind": kind, "value": max(0, min(100, int(value))),
                              "muted": bool(muted)}) + "\n"
        with self._lock:
            if self._closed:
                return
            try:
                if self._process is not None and self._process.poll() is not None:
                    self._process.stdin.close()
                    self._process.wait()
                    self._process = None
                if self._process is None:
                    self._process = subprocess.Popen(
                        [sys.executable, "-u", str(Path(__file__).resolve())],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, text=True,
                        creationflags=0x08000000)  # CREATE_NO_WINDOW
                self._process.stdin.write(message)
                self._process.stdin.flush()
            except (OSError, ValueError):
                # Feedback must never prevent an otherwise valid input action.
                self._dispose_process()

    def _dispose_process(self):
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()  # EOF requests a graceful exit.
            process.wait(timeout=0.5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            try:
                process.terminate()
                process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=0.5)
                except (OSError, subprocess.TimeoutExpired):
                    pass

    def close(self):
        with self._lock:
            self._closed = True
            self._dispose_process()


def _show_without_activation(api, hwnd, x, y, width, height):
    # NOACTIVATE also applies to later updates of an already visible indicator.
    api.SetWindowPos(hwnd, -1, x, y, width, height, 0x0010 | 0x0040)
    api.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE


def _run_helper():
    """Win32-only child: no taskbar item, focus changes, or input interception."""
    api = ctypes.windll.user32
    gdi = ctypes.windll.gdi32
    kernel = ctypes.windll.kernel32
    pointer = ctypes.c_ssize_t
    proc_type = ctypes.WINFUNCTYPE(pointer, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASS(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", proc_type),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL),
                    ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL),
                    ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

    # Explicit pointer-sized signatures prevent 64-bit HWND/HDC truncation.
    def signature(dll, name, result, *args):
        function = getattr(dll, name)
        function.restype, function.argtypes = result, list(args)
        return function

    signature(kernel, "GetModuleHandleW", wintypes.HMODULE, wintypes.LPCWSTR)
    signature(api, "DefWindowProcW", pointer, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    signature(api, "RegisterClassW", wintypes.ATOM, ctypes.POINTER(WNDCLASS))
    signature(api, "CreateWindowExW", wintypes.HWND, wintypes.DWORD, wintypes.LPCWSTR,
              wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
              ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p)
    signature(api, "SetWindowPos", wintypes.BOOL, wintypes.HWND, wintypes.HWND,
              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
    signature(api, "ShowWindow", wintypes.BOOL, wintypes.HWND, ctypes.c_int)
    signature(api, "SetLayeredWindowAttributes", wintypes.BOOL, wintypes.HWND,
              wintypes.DWORD, wintypes.BYTE, wintypes.DWORD)
    signature(api, "BeginPaint", wintypes.HDC, wintypes.HWND, ctypes.POINTER(PAINTSTRUCT))
    signature(api, "EndPaint", wintypes.BOOL, wintypes.HWND, ctypes.POINTER(PAINTSTRUCT))
    signature(api, "FillRect", ctypes.c_int, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH)
    signature(api, "DrawTextW", ctypes.c_int, wintypes.HDC, wintypes.LPCWSTR,
              ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT)
    signature(api, "InvalidateRect", wintypes.BOOL, wintypes.HWND, ctypes.c_void_p, wintypes.BOOL)
    signature(api, "PeekMessageW", wintypes.BOOL, ctypes.POINTER(wintypes.MSG), wintypes.HWND,
              wintypes.UINT, wintypes.UINT, wintypes.UINT)
    signature(api, "TranslateMessage", wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
    signature(api, "DispatchMessageW", pointer, ctypes.POINTER(wintypes.MSG))
    signature(api, "DestroyWindow", wintypes.BOOL, wintypes.HWND)
    signature(gdi, "CreateSolidBrush", wintypes.HBRUSH, wintypes.DWORD)
    signature(gdi, "DeleteObject", wintypes.BOOL, wintypes.HANDLE)
    signature(gdi, "SelectObject", wintypes.HANDLE, wintypes.HDC, wintypes.HANDLE)
    signature(gdi, "GetStockObject", wintypes.HANDLE, ctypes.c_int)
    signature(gdi, "SetTextColor", wintypes.DWORD, wintypes.HDC, wintypes.DWORD)
    signature(gdi, "SetBkMode", ctypes.c_int, wintypes.HDC, ctypes.c_int)

    updates = queue.Queue(maxsize=1)
    disconnected = threading.Event()

    def read_updates():
        try:
            for line in sys.stdin:
                try:
                    state = json.loads(line)
                    if state.get("kind") not in ("volume", "brightness"):
                        continue
                    state["value"] = max(0, min(100, int(state["value"])))
                    if updates.full():
                        updates.get_nowait()
                    updates.put_nowait(state)
                except (ValueError, TypeError, AttributeError, queue.Empty, queue.Full):
                    continue
        finally:
            disconnected.set()

    brushes = [gdi.CreateSolidBrush(color) for color in (0x29231D, 0x4D4338, 0xF1B580)]
    state = {"kind": "volume", "value": 0, "muted": False}
    width, height = 300, 86

    @proc_type
    def window_proc(hwnd, message, wparam, lparam):
        if message == 0x0021:  # WM_MOUSEACTIVATE: defensive no-focus handling
            return 3  # MA_NOACTIVATE
        if message == 0x0084:  # WM_NCHITTEST: let clicks pass through
            return -1  # HTTRANSPARENT
        if message == 0x000F:  # WM_PAINT
            paint = PAINTSTRUCT()
            dc = api.BeginPaint(hwnd, ctypes.byref(paint))
            old_font = gdi.SelectObject(dc, gdi.GetStockObject(17))  # DEFAULT_GUI_FONT
            api.FillRect(dc, ctypes.byref(wintypes.RECT(0, 0, width, height)), brushes[0])
            gdi.SetTextColor(dc, 0xF6F2ED)
            gdi.SetBkMode(dc, 1)  # TRANSPARENT
            title = "Volume" if state["kind"] == "volume" else "Brightness"
            value = "Muted" if state["kind"] == "volume" and state.get("muted") else f'{state["value"]}%'
            api.DrawTextW(dc, f"TouchHelm   {title}", -1,
                          ctypes.byref(wintypes.RECT(20, 15, 235, 42)), 0x24)
            api.DrawTextW(dc, value, -1, ctypes.byref(wintypes.RECT(225, 15, 280, 42)), 0x26)
            api.FillRect(dc, ctypes.byref(wintypes.RECT(20, 54, 280, 62)), brushes[1])
            api.FillRect(dc, ctypes.byref(wintypes.RECT(20, 54, 20 + round(260 * state["value"] / 100), 62)), brushes[2])
            gdi.SelectObject(dc, old_font)
            api.EndPaint(hwnd, ctypes.byref(paint))
            return 0
        return api.DefWindowProcW(hwnd, message, wparam, lparam)

    instance = kernel.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = window_proc, instance, "TouchHelmFeedback"
    api.RegisterClassW(ctypes.byref(wc))
    # LAYERED + TRANSPARENT passes clicks through to other applications.
    # TOPMOST | TRANSPARENT | TOOLWINDOW | LAYERED | NOACTIVATE; hidden WS_POPUP.
    hwnd = api.CreateWindowExW(0x080800A8, wc.lpszClassName, "TouchHelm", 0x80000000,
                              0, 0, width, height, None, None, instance, None)
    if not hwnd:
        for brush in brushes:
            gdi.DeleteObject(brush)
        return
    api.SetLayeredWindowAttributes(hwnd, 0, 255, 0x02)  # LWA_ALPHA, opaque paint
    threading.Thread(target=read_updates, daemon=True).start()
    expires, visible = 0.0, False
    try:
        while not disconnected.is_set():
            try:
                state = updates.get_nowait()
                work = wintypes.RECT()
                api.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
                x = work.left + max(0, (work.right - work.left - width) // 2)
                y = max(work.top, work.bottom - height - 36)
                _show_without_activation(api, hwnd, x, y, width, height)
                api.InvalidateRect(hwnd, None, False)
                expires, visible = time.monotonic() + 1.5, True
            except queue.Empty:
                pass
            if visible and time.monotonic() >= expires:
                api.ShowWindow(hwnd, 0)
                visible = False
            message = wintypes.MSG()
            while api.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                api.TranslateMessage(ctypes.byref(message))
                api.DispatchMessageW(ctypes.byref(message))
            time.sleep(0.02)
    finally:
        api.DestroyWindow(hwnd)
        for brush in brushes:
            gdi.DeleteObject(brush)


if __name__ == "__main__":
    _run_helper()
