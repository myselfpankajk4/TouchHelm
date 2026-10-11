"""
TouchHelm - Windows Desktop GUI & Control Panel with System Tray Support
Modern Windows 11 styled interface displaying pairing QR code,
connected Android devices, live activity stream, and sensitivity settings.
"""

import sys
import time
import socket
import webbrowser
import threading
import queue
import asyncio
import tkinter as tk
from tkinter import ttk
import qrcode
import pystray
from PIL import Image, ImageDraw

from server.config import ConfigManager
from server.discovery import get_local_ip_addresses
from server.build_version import get_build_id

# Colors (Windows 11 Fluent Dark)
BG_DARK = "#111722"
BG_CARD = "#192230"
BG_CARD_ALT = "#202d3e"
BORDER_COLOR = "#3b4b62"
ACCENT_BLUE = "#86b7fb"
ACCENT_GREEN = "#8ed5ae"
ACCENT_RED = "#f85149"
TEXT_PRIMARY = "#f0f6fc"
TEXT_SECONDARY = "#b5c1d2"
TEXT_MUTED = TEXT_SECONDARY


# Monkey patch pystray Win32 notification handler to support both single-click and double-click
try:
    import pystray._win32
    from pystray._util import win32 as pystray_win32
    _orig_win32_on_notify = pystray._win32.Icon._on_notify

    def _safe_win32_on_notify(self, wparam, lparam):
        # 0x0202 is WM_LBUTTONUP, 0x0203 is WM_LBUTTONDBLCLK
        if lparam in (pystray_win32.WM_LBUTTONUP, 0x0203):
            self()
        else:
            _orig_win32_on_notify(self, wparam, lparam)

    pystray._win32.Icon._on_notify = _safe_win32_on_notify
except Exception:
    pass


def create_tray_image():
    """Generates a high-contrast 64x64 icon for the system tray in RGB mode.
    Ensures crisp visibility on both dark and light Windows taskbars/trays."""
    img = Image.new("RGB", (64, 64), color=(14, 165, 233))  # Vibrant Sky Blue
    d = ImageDraw.Draw(img)
    # Inner contrast card
    d.rounded_rectangle([4, 4, 59, 59], radius=12, fill=(15, 23, 42), outline=(255, 255, 255), width=2)
    # Trackpad surface
    d.rounded_rectangle([12, 10, 51, 53], radius=6, fill=(30, 41, 59), outline=(56, 189, 248), width=2)
    # Center touch divider lines
    d.line([32, 12, 32, 28], fill=(56, 189, 248), width=2)
    d.line([14, 28, 49, 28], fill=(56, 189, 248), width=2)
    # Vibrant Lime touch point
    d.ellipse([25, 34, 38, 47], fill=(74, 222, 128))
    return img



class TouchHelmDesktopApp:
    def __init__(self, root: tk.Tk, config: ConfigManager, server_instance=None, server_loop=None, on_exit=None):
        self.root = root
        self.config = config
        self.server = server_instance
        self.server_loop = server_loop
        self.on_exit = on_exit
        self.root.title("TouchHelm - Remote Desktop Controller")
        self.root.geometry("880x700")
        self.root.minsize(820, 620)
        self.root.configure(bg=BG_DARK)

        self.event_queue = []
        self.ui_queue = queue.Queue()
        self._closing = False
        self._syncing_settings = False
        self._settings_snapshot = {}
        self._settings_display = {}
        self.clients_list = []
        self._device_rows = {}
        self._copy_feedback_after = None
        self.primary_ip = "127.0.0.1"
        self.port = self.config.get("port", 8765)
        self.tray_icon = None

        self._init_styles()
        self._build_ui()
        self._refresh_network_info()
        self._start_periodic_updates()
        self._init_tray_icon()
        self.root.protocol("WM_DELETE_WINDOW", self._exit_app)

    def _init_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG_DARK, borderwidth=0,
                        bordercolor=BG_CARD, lightcolor=BG_CARD, darkcolor=BG_CARD)
        style.configure("TNotebook.Tab", background=BG_CARD_ALT, foreground=TEXT_SECONDARY,
                        padding=(18, 10), font=("Segoe UI", 11), bordercolor=BORDER_COLOR,
                        lightcolor=BG_CARD, darkcolor=BG_CARD)
        style.map("TNotebook.Tab", background=[("selected", BG_CARD)],
                  foreground=[("selected", TEXT_PRIMARY)])
        style.configure("Pad.TButton", background=BG_CARD_ALT, foreground=TEXT_PRIMARY,
                        bordercolor=BORDER_COLOR, lightcolor=BG_CARD_ALT, darkcolor=BG_CARD_ALT,
                        padding=(12, 8), font=("Segoe UI", 10), focuscolor=ACCENT_BLUE)
        style.map("Pad.TButton", background=[("active", BORDER_COLOR)],
                  bordercolor=[("focus", ACCENT_BLUE)])
        style.configure("Primary.Pad.TButton", background=ACCENT_BLUE, foreground="#101b2d",
                        bordercolor=ACCENT_BLUE, lightcolor=ACCENT_BLUE, darkcolor=ACCENT_BLUE)
        style.map("Primary.Pad.TButton", background=[("active", "#a0c8ff")],
                  bordercolor=[("focus", TEXT_PRIMARY)])
        style.configure("Pad.Treeview", background=BG_CARD_ALT, fieldbackground=BG_CARD_ALT,
                        foreground=TEXT_PRIMARY, rowheight=38, font=("Segoe UI", 10),
                        borderwidth=0, bordercolor=BG_CARD_ALT,
                        lightcolor=BG_CARD_ALT, darkcolor=BG_CARD_ALT)
        style.configure("Pad.Treeview.Heading", background=BG_CARD, foreground=TEXT_SECONDARY,
                        relief="flat", padding=(8, 8), font=("Segoe UI", 10))
        style.map("Pad.Treeview", background=[("selected", "#29446b")],
                  foreground=[("selected", TEXT_PRIMARY)])
        style.configure("Vertical.TScrollbar", background=BORDER_COLOR, troughcolor=BG_CARD,
                        bordercolor=BG_CARD, lightcolor=BORDER_COLOR, darkcolor=BORDER_COLOR,
                        arrowcolor=TEXT_SECONDARY, borderwidth=0, arrowsize=14)
        style.map("Vertical.TScrollbar", background=[("active", TEXT_SECONDARY)])

    def _build_ui(self):
        header = tk.Frame(self.root, bg=BG_CARD, padx=24, pady=16)
        header.pack(fill="x")
        title = tk.Frame(header, bg=BG_CARD)
        title.pack(side="left")
        tk.Label(title, text="TouchHelm", font=("Segoe UI", 19, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w")
        tk.Label(title, text="Windows controller", font=("Segoe UI", 10),
                 fg=TEXT_SECONDARY, bg=BG_CARD).pack(anchor="w", pady=(2, 0))
        actions = tk.Frame(header, bg=BG_CARD)
        actions.pack(side="right")
        self.status_badge = tk.Label(actions, text="Server running", font=("Segoe UI", 10),
                                     fg=ACCENT_GREEN, bg=BG_CARD)
        self.status_badge.pack(side="left", padx=(0, 18))
        ttk.Button(actions, text="Minimize to tray", style="Pad.TButton",
                   command=self.minimize_to_tray).pack(side="left")

        content = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=20)
        content.pack(fill="both", expand=True)
        pairing = tk.Frame(content, bg=BG_CARD, width=300, padx=20, pady=16)
        pairing.pack(side="left", fill="y", padx=(0, 20))
        pairing.pack_propagate(False)
        tk.Label(pairing, text="Connect your phone", font=("Segoe UI", 14, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w")
        tk.Label(pairing, text="Use the same Wi-Fi as this PC, then scan the code with your phone camera.",
                 font=("Segoe UI", 10), fg=TEXT_SECONDARY, bg=BG_CARD,
                 wraplength=256, justify="left").pack(anchor="w", pady=(6, 12))
        self.qr_canvas = tk.Canvas(pairing, width=220, height=220, bg="#ffffff", highlightthickness=0)
        self.qr_canvas.pack()
        pairing.bind("<Configure>", self._resize_pairing)
        tk.Label(pairing, text="Or open this address on your phone", font=("Segoe UI", 10),
                 fg=TEXT_SECONDARY, bg=BG_CARD).pack(anchor="w", pady=(14, 8))
        self.url_value = tk.StringVar(value=f"http://{self.primary_ip}:{self.port}")
        self.lbl_url = tk.Entry(pairing, textvariable=self.url_value, state="readonly",
                                readonlybackground=BG_CARD_ALT, fg=TEXT_PRIMARY,
                                font=("Segoe UI", 10), relief="flat", bd=0,
                                highlightthickness=1, highlightbackground=BORDER_COLOR,
                                highlightcolor=ACCENT_BLUE, selectbackground="#29446b",
                                selectforeground=TEXT_PRIMARY)
        self.lbl_url.pack(fill="x", ipady=8)
        self.lbl_url.bind("<Control-a>", lambda event: (self.lbl_url.selection_range(0, "end"), "break")[-1])
        self.lbl_url.bind("<Control-A>", lambda event: (self.lbl_url.selection_range(0, "end"), "break")[-1])
        buttons = tk.Frame(pairing, bg=BG_CARD)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Copy URL", style="Primary.Pad.TButton",
                   command=self._copy_url).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(buttons, text="Open in browser", style="Pad.TButton",
                   command=self._open_browser).pack(side="left", fill="x", expand=True)
        self.lbl_copy_feedback = tk.Label(pairing, text="", font=("Segoe UI", 10),
                                          fg=ACCENT_GREEN, bg=BG_CARD, anchor="w")
        self.lbl_copy_feedback.pack(fill="x", pady=(2, 0))
        self.pin_info_frame = tk.Frame(pairing, bg=BG_CARD, pady=4)
        self.pin_info_frame.pack(fill="x")
        tk.Label(self.pin_info_frame, text="Connection security", font=("Segoe UI", 10, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w")
        self.lbl_pin_display = tk.Label(self.pin_info_frame, text="", font=("Segoe UI", 10),
                                        fg=TEXT_SECONDARY, bg=BG_CARD, justify="left", wraplength=256)
        self.lbl_pin_display.pack(anchor="w", pady=(5, 0))

        right = tk.Frame(content, bg=BG_DARK)
        right.pack(side="right", fill="both", expand=True)
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)
        self.tab_status = tk.Frame(self.notebook, bg=BG_CARD, padx=18, pady=18)
        self.notebook.add(self.tab_status, text="Connection")
        self._build_status_tab()
        self.tab_settings = tk.Frame(self.notebook, bg=BG_CARD, padx=18, pady=18)
        self.notebook.add(self.tab_settings, text="Settings")
        self._build_settings_tab()

    def _build_status_tab(self):
        heading = tk.Frame(self.tab_status, bg=BG_CARD)
        heading.pack(fill="x", pady=(0, 12))
        tk.Label(heading, text="Connected devices", font=("Segoe UI", 13, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")
        self.lbl_client_count = tk.Label(heading, text="0 devices", font=("Segoe UI", 10),
                                         fg=TEXT_SECONDARY, bg=BG_CARD)
        self.lbl_client_count.pack(side="right")
        self.devices_frame = tk.Frame(self.tab_status, bg=BG_CARD_ALT)
        self.devices_frame.pack(fill="x")
        self.devices_tree = ttk.Treeview(self.devices_frame, columns=("device", "address", "status", "ping"),
                                         show="headings", height=4, style="Pad.Treeview", selectmode="browse")
        for key, label, width, minimum in (("device", "Device", 140, 100), ("address", "Address", 116, 105),
                                           ("status", "Status", 95, 85), ("ping", "Link", 62, 50)):
            self.devices_tree.heading(key, text=label)
            self.devices_tree.column(key, width=width, minwidth=minimum, stretch=key == "device")
        self.devices_tree.tag_configure("ready", foreground=TEXT_PRIMARY)
        self.devices_tree.tag_configure("locked", foreground="#f0c778")
        scrollbar = ttk.Scrollbar(self.devices_frame, orient="vertical", command=self.devices_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.devices_tree.configure(yscrollcommand=scrollbar.set)
        self.devices_tree.pack(side="left", fill="both", expand=True)
        self.lbl_no_devices = tk.Label(self.tab_status, text="No phone connected. Scan the QR code to get started.",
                                       font=("Segoe UI", 10), fg=TEXT_SECONDARY, bg=BG_CARD,
                                       wraplength=430, justify="left", anchor="w")
        self.lbl_no_devices.pack(fill="x", pady=(10, 22))
        tk.Label(self.tab_status, text="Recent activity", font=("Segoe UI", 12, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w", pady=(0, 10))
        log_frame = tk.Frame(self.tab_status, bg=BG_CARD_ALT)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, bg=BG_CARD_ALT, fg=TEXT_SECONDARY, font=("Segoe UI", 10),
                                bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR,
                                highlightcolor=ACCENT_BLUE, state="disabled", wrap="word", padx=10, pady=10)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

    def _build_settings_tab(self):
        self.settings_canvas = tk.Canvas(self.tab_settings, bg=BG_CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_settings, orient="vertical", command=self.settings_canvas.yview)
        inner = tk.Frame(self.settings_canvas, bg=BG_CARD)
        inner.bind("<Configure>", lambda event: self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all")))
        self._settings_window = self.settings_canvas.create_window((0, 0), window=inner, anchor="nw")
        self.settings_canvas.bind("<Configure>", self._resize_settings)
        self.settings_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.settings_canvas.pack(side="left", fill="both", expand=True)

        def section(title, description):
            frame = tk.Frame(inner, bg=BG_CARD, pady=4)
            frame.pack(fill="x", pady=(0, 4))
            tk.Label(frame, text=title, font=("Segoe UI", 13, "bold"), fg=TEXT_PRIMARY,
                     bg=BG_CARD).pack(anchor="w")
            tk.Label(frame, text=description, font=("Segoe UI", 10), fg=TEXT_SECONDARY,
                     bg=BG_CARD, justify="left", wraplength=390).pack(anchor="w", pady=(4, 6))
            return frame

        def slider(parent, title, key, low, high, step, callback, digits):
            row = tk.Frame(parent, bg=BG_CARD)
            row.pack(fill="x", pady=(0, 4))
            label_row = tk.Frame(row, bg=BG_CARD)
            label_row.pack(fill="x")
            tk.Label(label_row, text=title, font=("Segoe UI", 10), fg=TEXT_PRIMARY,
                     bg=BG_CARD).pack(side="left")
            value = tk.Label(label_row, text=f"{self.config.get(key):.{digits}f}x", font=("Segoe UI", 10),
                             fg=ACCENT_BLUE, bg=BG_CARD)
            value.pack(side="right", padx=(12, 6))
            scale = tk.Scale(row, from_=low, to=high, resolution=step, orient="horizontal",
                              bg=BG_CARD, fg=TEXT_PRIMARY, troughcolor=BG_CARD_ALT,
                              activebackground=ACCENT_BLUE, highlightthickness=1,
                              highlightbackground=BG_CARD, highlightcolor=ACCENT_BLUE,
                              bd=0, showvalue=False, command=callback, takefocus=True,
                              sliderlength=24, width=16)
            scale.set(self.config.get(key))
            scale.pack(fill="x", pady=(6, 0))
            return scale, value

        pointer = section("Pointer", "Adjust cursor speed and how movement builds with faster swipes.")
        self.scale_sens, self.lbl_sens_val = slider(pointer, "Sensitivity", "mouse_sensitivity", .4, 3.5, .1,
                                                   self._on_sens_change, 1)
        self.scale_accel, self.lbl_accel_val = slider(pointer, "Acceleration", "mouse_acceleration", 1., 2.5, .05,
                                                     self._on_accel_change, 2)
        scrolling = section("Scrolling", "Control wheel speed and the direction of touch scrolling.")
        self.scale_scroll, self.lbl_scroll_val = slider(scrolling, "Scroll speed", "scroll_speed", .3, 2.5, .1,
                                                       self._on_scroll_change, 1)
        self.var_invert = tk.BooleanVar(value=self.config.get("invert_scroll", False))
        tk.Checkbutton(scrolling, text="Natural scrolling", variable=self.var_invert, font=("Segoe UI", 10),
                        fg=TEXT_PRIMARY, bg=BG_CARD, selectcolor=BG_CARD_ALT, activebackground=BG_CARD,
                        activeforeground=TEXT_PRIMARY, highlightcolor=ACCENT_BLUE,
                        command=self._on_invert_change).pack(anchor="w", pady=(0, 2))
        presentation = section("Presentation", "Choose the laser pointer color shown on this PC.")
        self.var_laser_color = tk.StringVar(value=self.config.get("laser_color", "red"))
        colors = tk.Frame(presentation, bg=BG_CARD)
        colors.pack(fill="x")
        colors.columnconfigure((0, 1), weight=1)
        for index, (label, color) in enumerate((("Red", "red"), ("Green", "green"), ("Blue", "blue"), ("Amber", "amber"))):
            tk.Radiobutton(colors, text=label, value=color, variable=self.var_laser_color, font=("Segoe UI", 10),
                           fg=TEXT_PRIMARY, bg=BG_CARD, selectcolor=BG_CARD_ALT, activebackground=BG_CARD,
                           activeforeground=TEXT_PRIMARY, highlightcolor=ACCENT_BLUE,
                           command=self._on_laser_color_change).grid(row=index // 2, column=index % 2,
                                                                   sticky="w", padx=(0, 12), pady=4)

    def _resize_settings(self, event):
        self.settings_canvas.itemconfigure(self._settings_window, width=event.width)

    def _resize_pairing(self, event):
        size = 220 if event.height >= 540 else 144
        if getattr(self, "_qr_size", 220) != size:
            self._qr_size = size
            self.qr_canvas.configure(width=size, height=size)
            self._render_qr_code(self._connection_url())

    def _connection_url(self):
        return f"http://{self.primary_ip}:{self.port}/?build={get_build_id()}"

    def _refresh_build_url(self):
        url = self._connection_url()
        if url != getattr(self, '_pairing_url', None):
            self._pairing_url = url
            self.url_value.set(url)
            self._render_qr_code(url)

    def _refresh_network_info(self):
        ips = get_local_ip_addresses()
        self.primary_ip = ips[0] if ips else "127.0.0.1"
        self.port = self.config.get("port", 8765)
        url = self._connection_url()
        self._pairing_url = url
        self.url_value.set(url)
        self._render_qr_code(url)

        if self.config.get("require_pin", False):
            self.lbl_pin_display.config(text=f"Security PIN: {self.config.get('pin_code', '')}")
        else:
            self.lbl_pin_display.config(text="PIN not required. Direct connection.")

    def _render_qr_code(self, url: str):
        self.qr_canvas.delete("all")
        qr = qrcode.QRCode(box_size=6, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        matrix = qr.get_matrix()

        n_rows = len(matrix)
        n_cols = len(matrix[0])
        size = getattr(self, "_qr_size", 220)
        cell_size = (size - 20) // max(n_rows, n_cols)
        offset_x = (size - (n_cols * cell_size)) // 2
        offset_y = (size - (n_rows * cell_size)) // 2

        self.qr_canvas.create_rectangle(0, 0, size, size, fill="#ffffff", outline="")

        for r, row in enumerate(matrix):
            for c, val in enumerate(row):
                if val:
                    x0 = offset_x + c * cell_size
                    y0 = offset_y + r * cell_size
                    x1 = x0 + cell_size
                    y1 = y0 + cell_size
                    self.qr_canvas.create_rectangle(x0, y0, x1, y1, fill="#0d1117", outline="")

    def _copy_url(self):
        url = self._connection_url()
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        if getattr(self, "_copy_feedback_after", None) is not None:
            self.root.after_cancel(self._copy_feedback_after)
        self.lbl_copy_feedback.config(text="Copied to clipboard.")
        self._copy_feedback_after = self.root.after(2500, lambda: self.lbl_copy_feedback.config(text=""))

    def _open_browser(self):
        webbrowser.open(self._connection_url())

    def _on_sens_change(self, val):
        if self._syncing_settings:
            return
        v = float(val)
        self._set_setting("mouse_sensitivity", v)
        self.lbl_sens_val.config(text=f"{self.config.get('mouse_sensitivity'):.1f}x")

    def _on_accel_change(self, val):
        if self._syncing_settings:
            return
        v = float(val)
        self._set_setting("mouse_acceleration", v)
        self.lbl_accel_val.config(text=f"{self.config.get('mouse_acceleration'):.2f}x")

    def _on_scroll_change(self, val):
        if self._syncing_settings:
            return
        v = float(val)
        self._set_setting("scroll_speed", v)
        self.lbl_scroll_val.config(text=f"{self.config.get('scroll_speed'):.1f}x")

    def _on_invert_change(self):
        self._set_setting("invert_scroll", self.var_invert.get())

    def _on_laser_color_change(self):
        self._set_setting("laser_color", self.var_laser_color.get())

    def _set_setting(self, key, value):
        if self._syncing_settings or self.config.get(key) == value:
            return
        # Scale callbacks can be deferred until idle. A rounded value produced
        # by refreshing a slider must not overwrite a more precise phone value.
        if self._settings_display.get(key, object()) == value:
            return
        self.config.set(key, value)
        self._settings_snapshot[key] = value
        self._settings_display[key] = value
        if self.server and self.server_loop and self.server_loop.is_running():
            coroutine = self.server.broadcast({"type": "config_sync", "config": self.config.public_data()})
            try:
                asyncio.run_coroutine_threadsafe(coroutine, self.server_loop)
            except RuntimeError:
                coroutine.close()

    def _refresh_settings(self):
        self._syncing_settings = True
        try:
            numeric = (
                ("mouse_sensitivity", self.scale_sens, self.lbl_sens_val, 1),
                ("mouse_acceleration", self.scale_accel, self.lbl_accel_val, 2),
                ("scroll_speed", self.scale_scroll, self.lbl_scroll_val, 1),
            )
            for key, control, label, digits in numeric:
                value = self.config.get(key)
                if self._settings_snapshot.get(key) != value:
                    control.set(value)
                    label.config(text=f"{value:.{digits}f}x")
                    self._settings_display[key] = float(control.get())
                    self._settings_snapshot[key] = value
            for key, variable in (("invert_scroll", self.var_invert), ("laser_color", self.var_laser_color)):
                value = self.config.get(key)
                if self._settings_snapshot.get(key) != value:
                    variable.set(value)
                    self._settings_display[key] = value
                    self._settings_snapshot[key] = value
            if self.config.get("require_pin", False):
                self.lbl_pin_display.config(text=f"Security PIN: {self.config.get('pin_code', '')}")
            else:
                self.lbl_pin_display.config(text="PIN not required. Direct connection.")
        finally:
            self._syncing_settings = False

    def log_event(self, event_str: str):
        self.event_queue.append(event_str)

    def update_clients(self, client_list: list):
        self.clients_list = client_list

    # --------------------------------------------------------------------------
    # SYSTEM TRAY INTEGRATION
    # --------------------------------------------------------------------------
    def _init_tray_icon(self):
        """Initializes and runs the system tray icon at boot in a background thread."""
        try:
            # pystray invokes actions on its own thread. Tk calls must wait
            # for the main thread's existing periodic update callback.
            def on_ui_thread(action):
                def callback(icon, item):
                    self.ui_queue.put(action)
                return callback

            menu = pystray.Menu(
                pystray.MenuItem("Show TouchHelm", on_ui_thread(self._do_restore), default=True),
                pystray.MenuItem("Minimize to Tray", on_ui_thread(self.minimize_to_tray)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Status: Active", None, enabled=False),
                pystray.MenuItem("Copy URL", on_ui_thread(self._copy_url)),
                pystray.MenuItem("Open in Browser", on_ui_thread(self._open_browser)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", on_ui_thread(self._exit_app))
            )
            self.tray_icon = pystray.Icon("TouchHelm", create_tray_image(), "TouchHelm - Remote Controller", menu=menu)
            icon = self.tray_icon

            def report_failure(error):
                self.ui_queue.put(lambda: self._handle_tray_failure(icon, error))

            def show_icon(ready_icon):
                try:
                    ready_icon.visible = True
                except Exception as error:
                    report_failure(error)

            def run_tray():
                try:
                    icon.run(setup=show_icon)
                except Exception as error:
                    report_failure(error)

            threading.Thread(target=run_tray, daemon=True).start()
        except Exception as e:
            sys.stderr.write(f"Failed to initialize tray icon: {e}\n")

    def _handle_tray_failure(self, icon, error):
        sys.stderr.write(f"System tray unavailable: {error}\n")
        if self.tray_icon is icon:
            try:
                icon.stop()
            except Exception:
                pass
            self.tray_icon = None
            if not self._closing and self.root.state() == "withdrawn":
                self._do_restore()

    def minimize_to_tray(self, event=None):
        """Hides window and keeps it running in system tray."""
        if self.tray_icon is None or not self.tray_icon.visible:
            self.root.iconify()
            return
        self.root.withdraw()
        # Hide console window if attached (prevents black terminal staying on screen/taskbar)
        try:
            import ctypes
            hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd_console:
                ctypes.windll.user32.ShowWindow(hwnd_console, 0)  # SW_HIDE
        except Exception:
            pass

        if self.tray_icon and not getattr(self, "_tray_notified", False):
            self._tray_notified = True
            try:
                self.tray_icon.notify("TouchHelm is minimized to system tray. Click or double-click to restore.", "TouchHelm")
            except Exception:
                pass

    def restore_from_tray(self, icon=None, item=None):
        """Restores window from system tray (scheduled on Tkinter main thread)."""
        self.ui_queue.put(self._do_restore)

    def _do_restore(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.attributes("-topmost", False)
        self.root.focus_force()
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _exit_app(self, icon=None, item=None):
        """Clean application shutdown."""
        if self._closing:
            return
        self._closing = True
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        if self.on_exit:
            self.on_exit()
        else:
            try:
                self.root.destroy()
            except Exception:
                pass

    def _refresh_devices(self):
        active = set()
        for client in self.clients_list:
            key = (client.get("ip", ""), client.get("device", "TouchHelm Client"), client.get("connected_at"))
            active.add(key)
            authorized = client.get("authenticated", False)
            ping = client.get("ping")
            latency = f"{ping} ms" if authorized and type(ping) in (int, float) and ping > 0 else "—"
            values = (client.get("device", "TouchHelm Client"), client.get("ip", ""),
                      "Ready" if authorized else "PIN required", latency)
            tags = ("ready" if authorized else "locked",)
            if key not in self._device_rows:
                self._device_rows[key] = self.devices_tree.insert("", "end", values=values, tags=tags)
            else:
                item = self._device_rows[key]
                if tuple(self.devices_tree.item(item)["values"]) != values:
                    self.devices_tree.item(item, values=values, tags=tags)
        for key in list(self._device_rows):
            if key not in active:
                self.devices_tree.delete(self._device_rows.pop(key))
        count = len(self.clients_list)
        self.lbl_client_count.config(text=f"{count} device{'s' if count != 1 else ''}")
        self.lbl_no_devices.config(text="" if count else "No phone connected. Scan the QR code to get started.")

    def _flush_activity(self):
        if not self.event_queue:
            return
        events = self.event_queue[:]
        del self.event_queue[:len(events)]
        at_bottom = self.log_text.yview()[1] >= 0.999
        self.log_text.configure(state="normal")
        self.log_text.insert("end", "\n".join(events) + "\n")
        excess = int(self.log_text.index("end-1c").split(".")[0]) - 1 - 1000
        if excess > 0:
            self.log_text.delete("1.0", f"{excess + 1}.0")
        if at_bottom:
            self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start_periodic_updates(self):
        def loop():
            if self._closing:
                return
            while True:
                try:
                    action = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                action()
                if self._closing:
                    return
            self._refresh_settings()
            self._refresh_build_url()
            self._flush_activity()
            self._refresh_devices()
            self.root.after(300, loop)

        self.root.after(300, loop)
