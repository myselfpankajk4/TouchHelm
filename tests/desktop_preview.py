"""Capture real Tk widgets in a transparent preview; no tray/network/input."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui.app_window import TouchHelmDesktopApp
from server.config import ConfigManager


def capture_client(root, target):
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetParent.restype = wintypes.HWND
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                               ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
    rectangle = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rectangle))
    width, height = rectangle.right, rectangle.bottom
    dc = user32.GetDC(hwnd)
    memory = gdi32.CreateCompatibleDC(dc)
    bitmap = gdi32.CreateCompatibleBitmap(dc, width, height)
    previous = gdi32.SelectObject(memory, bitmap)

    class BitmapHeader(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                    ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("image_size", wintypes.DWORD), ("x_density", wintypes.LONG), ("y_density", wintypes.LONG),
                    ("colors", wintypes.DWORD), ("important_colors", wintypes.DWORD)]

    try:
        if not user32.PrintWindow(hwnd, memory, 3):
            raise RuntimeError("PrintWindow could not render the offscreen Tk client")
        info = BitmapHeader(ctypes.sizeof(BitmapHeader), width, -height, 1, 32, 0, width * height * 4)
        buffer = ctypes.create_string_buffer(width * height * 4)
        if not gdi32.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(info), 0):
            raise RuntimeError("GetDIBits could not read the rendered Tk client")
        Image.frombytes("RGB", (width, height), buffer.raw, "raw", "BGRX").save(target)
    finally:
        gdi32.SelectObject(memory, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(hwnd, dc)


def main():
    destination = ROOT / "tests" / "artifacts"
    destination.mkdir(exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    # Place the client beyond the complete virtual desktop; it never appears
    # on any monitor and the override-redirect window has no taskbar entry.
    user32 = ctypes.windll.user32
    root.attributes("-alpha", 0.0)
    root.attributes("-disabled", True)
    right = user32.GetSystemMetrics(76) + user32.GetSystemMetrics(78) + 200
    top = user32.GetSystemMetrics(77) + 200
    root.overrideredirect(True)
    root.geometry(f"880x700+{right}+{top}")
    try:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as folder:
            config = ConfigManager(str(Path(folder) / "config.json"))
            config.update({"require_pin": True, "pin_code": "5678"})
            with patch.object(TouchHelmDesktopApp, "_init_tray_icon"), patch(
                "gui.app_window.get_local_ip_addresses", return_value=["192.168.1.25"]
            ):
                app = TouchHelmDesktopApp(root, config)
            root.geometry(f"880x700+{right}+{top}")
            root.deiconify()
            # A transparent window on a real display allows Windows to paint
            # child widgets; the offscreen render alone may omit their DCs.
            # Keep it click-through, non-activating and absent from the taskbar.
            user32.GetParent.restype = wintypes.HWND
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
            hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
            extended = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, extended | 0x20 | 0x80 | 0x08000000)
            root.geometry("880x700+20+20")
            app.update_clients([
                {"ip": "192.168.1.40", "device": "Android Phone", "connected_at": 1,
                 "authenticated": True, "ping": 12, "packets": 18},
                {"ip": "192.168.1.41", "device": "Pixel 9", "connected_at": 2,
                 "authenticated": False, "ping": 0, "packets": 0},
            ])
            app.log_event("[15:20:10] Android Phone: Device connected")
            app.log_event("[15:20:11] Android Phone: Connected as Android Phone")
            app.log_event("[15:20:14] Android Phone: Click (left)")
            app._refresh_settings()
            app._refresh_devices()
            app._flush_activity()
            root.update_idletasks()
            root.update()
            capture_client(root, destination / "desktop-connection.png")
            app.notebook.select(app.tab_settings)
            root.update_idletasks()
            root.update()
            capture_client(root, destination / "desktop-settings.png")
            root.geometry("820x620+20+20")
            app.notebook.select(app.tab_status)
            root.update_idletasks()
            root.update()
            assert app.lbl_pin_display.winfo_height() >= app.lbl_pin_display.winfo_reqheight(), "Security status clipped"
            capture_client(root, destination / "desktop-connection-minimum.png")
            app.notebook.select(app.tab_settings)
            root.update_idletasks()
            root.update()
            app.settings_canvas.yview_moveto(1.0)
            root.update_idletasks()
            root.update()
            capture_client(root, destination / "desktop-settings-minimum.png")
            app.scale_sens.event_generate("<FocusIn>")
            root.update_idletasks()
            root.update()
            assert app.scale_sens.winfo_rooty() >= app.settings_canvas.winfo_rooty(), "Keyboard focus leaves Pointer speed offscreen"
            assert app.scale_sens.winfo_rooty() + app.scale_sens.winfo_height() <= app.settings_canvas.winfo_rooty() + app.settings_canvas.winfo_height(), "Focused control is clipped"
            print(json.dumps({"size": [root.winfo_width(), root.winfo_height()],
                              "settings_viewport": app.settings_canvas.winfo_width(),
                              "settings_content": app.settings_canvas.itemcget(app._settings_window, "width"),
                              "device_rows": len(app.devices_tree.get_children()),
                              "pairing_security": [app.pin_info_frame.winfo_y(), app.pin_info_frame.winfo_height(),
                                                   app.pin_info_frame.master.winfo_height()],
                              "security_label": [app.lbl_pin_display.winfo_y(), app.lbl_pin_display.winfo_height()],
                              "images": ["desktop-connection.png", "desktop-settings.png",
                                         "desktop-connection-minimum.png", "desktop-settings-minimum.png"]}))
            app._closing = True
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
