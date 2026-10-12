"""
TouchHelm - Digital Laser Pointer & Spotlight Overlay
Creates a hardware-accelerated, transparent, click-through overlay
on Windows desktop to project laser pointer dots and presentation spotlights.
"""

import sys
import os
import json
import time
import ctypes
from ctypes import wintypes
import tkinter as tk

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080

COLOR_PRESETS = {
    "red": {"outer": "#ff4466", "mid": "#ff0033", "core": "#ffffff"},
    "green": {"outer": "#44ff88", "mid": "#00ee44", "core": "#ffffff"},
    "blue": {"outer": "#33bbff", "mid": "#0088ff", "core": "#ffffff"},
    "amber": {"outer": "#ffbb33", "mid": "#ff8800", "core": "#ffffff"},
}

class LaserOverlayApp:
    def __init__(self, color_name="red"):
        self.root = tk.Tk()
        self.root.title("TouchHelm Laser Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # Transparent background color key
        self.bg_color = "#000001"
        self.root.attributes("-transparentcolor", self.bg_color)
        self.root.config(bg=self.bg_color)

        # Screen dimensions
        self.sw = user32.GetSystemMetrics(0)
        self.sh = user32.GetSystemMetrics(1)
        self.root.geometry(f"{self.sw}x{self.sh}+0+0")

        self.canvas = tk.Canvas(
            self.root,
            width=self.sw,
            height=self.sh,
            bg=self.bg_color,
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill="both", expand=True)

        self.color_name = color_name
        self.is_active = False
        self.last_x = self.sw // 2
        self.last_y = self.sh // 2
        self.items = []

        # Make window click-through and toolwindow (hidden from taskbar)
        self._apply_click_through()

    def _apply_click_through(self):
        try:
            self.root.update_idletasks()
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW
            )
        except Exception as e:
            sys.stderr.write(f"Click-through setup error: {e}\n")

    def set_color(self, color_name: str):
        if color_name in COLOR_PRESETS:
            self.color_name = color_name

    def draw_laser(self, x: int, y: int):
        self.canvas.delete("laser")
        preset = COLOR_PRESETS.get(self.color_name, COLOR_PRESETS["red"])

        # Outer glow
        r_outer = 22
        self.canvas.create_oval(
            x - r_outer, y - r_outer, x + r_outer, y + r_outer,
            fill=preset["outer"], outline="", tags="laser"
        )

        # Mid beam
        r_mid = 13
        self.canvas.create_oval(
            x - r_mid, y - r_mid, x + r_mid, y + r_mid,
            fill=preset["mid"], outline="", tags="laser"
        )

        # Intense core
        r_core = 5
        self.canvas.create_oval(
            x - r_core, y - r_core, x + r_core, y + r_core,
            fill=preset["core"], outline="", tags="laser"
        )

    def update_position(self, norm_x: float, norm_y: float, active: bool = True):
        self.is_active = active
        if active:
            px = int(norm_x * self.sw)
            py = int(norm_y * self.sh)
            self.last_x = px
            self.last_y = py
            self.draw_laser(px, py)
        else:
            self.canvas.delete("laser")

    def set_display(self,rect):
        """Move the owned click-through window to a validated monitor rectangle."""
        if not isinstance(rect,dict):return
        values=[rect.get(key) for key in ('x','y','width','height')]
        if any(type(value) is not int for value in values):return
        x,y,width,height=values
        if width<=0 or height<=0 or width>40000 or height>40000:return
        if getattr(self,'display_rect',None)==tuple(values):return
        self.display_rect=tuple(values);self.sw=width;self.sh=height
        self.root.geometry(f'{width}x{height}')
        self.canvas.configure(width=width,height=height)
        self.root.update_idletasks()
        hwnd=user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        user32.SetWindowPos(hwnd,0,x,y,width,height,0x0010|0x0004)

    def hide(self):
        self.is_active = False
        self.canvas.delete("laser")

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


def run_overlay_process():
    """Reads JSON commands line-by-line from stdin via thread for responsiveness."""
    import threading
    app = LaserOverlayApp()

    def handle_command(data):
        cmd = data.get("cmd")
        if cmd == "quit":
            app.close()
            sys.exit(0)
        elif cmd == "update":
            if data.get('display_rect'):app.set_display(data['display_rect'])
            x = data.get("x", 0.5)
            y = data.get("y", 0.5)
            active = data.get("active", True)
            app.update_position(x, y, active)
        elif cmd == "color":
            app.set_color(data.get("color", "red"))
        elif cmd == "hide":
            app.hide()

    def stdin_worker():
        for line in sys.stdin:
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                app.root.after(0, handle_command, data)
            except Exception:
                pass

    t = threading.Thread(target=stdin_worker, daemon=True)
    t.start()
    app.root.mainloop()


class LaserOverlayClient:
    """Helper client used by the WebSocket server to control the overlay."""
    def __init__(self):
        self.proc = None
        self._is_enabled = False
        self.color = "red"

    def start(self):
        import subprocess
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "server.laser_overlay"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self._is_enabled = True
            self.set_color(self.color)
        except Exception as e:
            print(f"Failed to start laser overlay process: {e}")

    def update(self, x: float, y: float, active: bool = True, display_rect=None):
        if not self.proc or self.proc.poll() is not None:
            if active:
                self.start()
            else:
                return
        try:
            payload={"cmd":"update","x":x,"y":y,"active":active}
            if display_rect is not None:payload['display_rect']=display_rect
            msg = json.dumps(payload) + "\n"
            self.proc.stdin.write(msg)
            self.proc.stdin.flush()
        except Exception:
            pass

    def set_color(self, color: str):
        if color not in COLOR_PRESETS:
            return
        self.color = color
        if self.proc and self.proc.poll() is None:
            try:
                msg = json.dumps({"cmd": "color", "color": color}) + "\n"
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
            except Exception:
                pass

    def hide(self):
        if self.proc and self.proc.poll() is None:
            try:
                msg = json.dumps({"cmd": "hide"}) + "\n"
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
            except Exception:
                pass

    def stop(self):
        if self.proc:
            try:
                self.proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                self.proc.stdin.flush()
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None


if __name__ == "__main__":
    run_overlay_process()
