"""Safe desktop regressions: no windows, input injection, or real network sockets."""
import asyncio
import importlib.util
import io
import json
import pathlib
import queue
import sys
import threading
import tempfile
import types
import unittest
from unittest.mock import patch

from server import discovery
from server.config import ConfigManager

ROOT = pathlib.Path(__file__).resolve().parents[1]


class InMemoryLoop(asyncio.AbstractEventLoop):
    """Runs immediate test coroutines without asyncio's OS socketpair."""
    closed = False

    def run_until_complete(self, coroutine):
        try:
            coroutine.send(None)
        except StopIteration as result:
            return result.value
        raise AssertionError("test coroutine unexpectedly yielded")

    def run_forever(self):
        pass

    def close(self):
        self.closed = True

    def is_closed(self):
        return self.closed

    def call_soon_threadsafe(self, callback, *args):
        callback(*args)

    def stop(self):
        pass


def load_module(name, path, replacements=None):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, replacements or {}):
        spec.loader.exec_module(module)
    return module


class DesktopLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.main = load_module("desktop_entry_under_test", "main.py", {
            "server.web_server": types.SimpleNamespace(TouchHelmServer=object),
            "gui.app_window": types.SimpleNamespace(TouchHelmDesktopApp=object),
        })

    def test_start_failure_cleans_up_partial_server_and_closes_loop(self):
        class Server:
            stopped = False

            async def start(self):
                raise OSError("port already in use")

            async def stop(self):
                self.stopped = True

        server = Server()
        loop = InMemoryLoop()
        try:
            with self.assertRaisesRegex(OSError, "port already in use"):
                self.main.run_async_server(server, loop)
            self.assertTrue(server.stopped)
            self.assertTrue(loop.is_closed())
        finally:
            if not loop.is_closed():
                loop.close()

    def test_normal_shutdown_awaits_stop_once_and_closes_loop(self):
        loop = InMemoryLoop()

        class Server:
            stops = 0

            async def start(self):
                pass

            async def stop(self):
                self.stops += 1

        server = Server()
        try:
            self.main.run_async_server(server, loop)
            self.assertEqual(server.stops, 1)
            self.assertTrue(loop.is_closed())
        finally:
            if not loop.is_closed():
                loop.close()

    def test_failed_start_returns_error_without_announcing_or_advertising_server(self):
        class Server:
            async def start(self):
                raise OSError("port already in use")

            async def stop(self):
                pass

        class Beacon:
            started = False

            def start(self):
                self.started = True

            def stop(self):
                pass

        beacon = Beacon()
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["main.py", "--headless"]), patch.object(
            self.main, "TouchHelmServer", return_value=Server()
        ), patch.object(self.main, "DiscoveryBeaconService", return_value=beacon), patch.object(
            self.main, "get_local_ip_addresses", return_value=["192.168.1.10"]
        ), patch.object(self.main.asyncio, "new_event_loop", return_value=InMemoryLoop()), patch(
            "sys.stdout", output
        ), patch("sys.stderr", errors):
            result = self.main.main()
        self.assertEqual(result, 1)
        self.assertFalse(beacon.started)
        self.assertNotIn("ACTIVE", output.getvalue())
        self.assertIn("port already in use", errors.getvalue())

    def test_invalid_cli_pin_is_rejected_before_settings_are_written(self):
        with patch.object(sys, "argv", ["main.py", "--pin", "abc"]), patch.object(
            self.main, "ConfigManager", side_effect=AssertionError("settings accessed")
        ), patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                self.main.main()
        self.assertEqual(result.exception.code, 2)

    def test_cli_pin_enables_pin_when_saved_code_is_empty(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            config = ConfigManager(str(pathlib.Path(directory) / "config.json"))
            config.set("pin_code", "")
            with patch.object(sys, "argv", ["main.py", "--pin", "5678"]), patch.object(
                self.main, "ConfigManager", return_value=config
            ), patch.object(self.main, "get_local_ip_addresses", side_effect=RuntimeError("after settings")):
                with self.assertRaises(Exception) as result:
                    self.main.main()
            self.assertIs(type(result.exception), RuntimeError)
            self.assertEqual(str(result.exception), "after settings")
            self.assertTrue(config.get("require_pin"))
            self.assertEqual(config.get("pin_code"), "5678")


class DiscoveryTests(unittest.TestCase):
    def test_beacon_uses_current_pin_requirement(self):
        settings = {"require_pin": False}
        beacon = discovery.DiscoveryBeaconService(8765, has_pin=lambda: settings["require_pin"])
        settings["require_pin"] = True

        class Socket:
            payload = None

            def setsockopt(self, *args):
                pass

            def settimeout(self, timeout):
                pass

            def sendto(self, payload, address):
                self.payload = json.loads(payload)

            def close(self):
                pass

        sock = Socket()

        def ips():
            beacon.running = False
            return ["192.168.1.10"]

        beacon.running = True
        with patch.object(discovery.socket, "socket", return_value=sock), patch.object(
            discovery, "get_local_ip_addresses", side_effect=ips
        ):
            beacon._broadcast_loop()
        self.assertIsNotNone(sock.payload)
        self.assertIs(sock.payload["has_pin"], True)

    def test_ip_probe_closes_socket_when_connect_fails(self):
        class Socket:
            closed = False

            def connect(self, address):
                raise OSError("offline")

            def close(self):
                self.closed = True

        sock = Socket()
        with patch.object(discovery.socket, "socket", return_value=sock), patch.object(
            discovery.socket, "gethostbyname_ex", return_value=("pc", [], [])
        ):
            self.assertEqual(discovery.get_local_ip_addresses(), ["127.0.0.1"])
        self.assertTrue(sock.closed)

    def test_listener_closes_socket_when_bind_fails(self):
        class Socket:
            closed = False

            def setsockopt(self, *args):
                pass

            def bind(self, address):
                raise OSError("port already in use")

            def close(self):
                self.closed = True

        sock = Socket()
        with patch.object(discovery.socket, "socket", return_value=sock):
            discovery.DiscoveryBeaconService(8765)._listen_queries_loop()
        self.assertTrue(sock.closed)

    def test_stop_waits_for_threads_before_restart(self):
        beacon = discovery.DiscoveryBeaconService(8765)
        started = [threading.Event(), threading.Event()]
        release = threading.Event()

        def worker(index):
            started[index].set()
            release.wait(0.1)

        beacon._broadcast_loop = lambda: worker(0)
        beacon._listen_queries_loop = lambda: worker(1)
        try:
            beacon.start()
            self.assertTrue(all(event.wait(1) for event in started))
            beacon.stop()
            self.assertFalse(beacon.thread.is_alive())
            self.assertFalse(beacon.listener_thread.is_alive())
        finally:
            release.set()
            beacon.stop()
            beacon.thread.join(1)
            beacon.listener_thread.join(1)


class TrayTests(unittest.TestCase):
    def setUp(self):
        class Menu:
            SEPARATOR = object()

            def __init__(self, *items):
                self.items = items

        class MenuItem:
            def __init__(self, text, action, **kwargs):
                self.text, self.action = text, action

        class Icon:
            def __init__(self, *args, menu, **kwargs):
                self.menu = menu
                self.visible = False

            def run(self, setup=None):
                if setup:
                    setup(self)

        self.gui = load_module("desktop_gui_under_test", "gui/app_window.py", {
            "pystray": types.SimpleNamespace(Menu=Menu, MenuItem=MenuItem, Icon=Icon),
            "PIL": types.SimpleNamespace(Image=object, ImageDraw=object),
            "qrcode": types.SimpleNamespace(QRCode=object),
        })

    def bare_app(self):
        app = self.gui.TouchHelmDesktopApp.__new__(self.gui.TouchHelmDesktopApp)
        app.ui_queue = queue.Queue()
        app._closing = False
        app._syncing_settings = False
        app._settings_snapshot = {}
        app._settings_display = {}
        return app

    def test_desktop_settings_change_broadcasts_public_config_once(self):
        app = self.bare_app()
        messages = []
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            app.config = ConfigManager(str(pathlib.Path(directory) / "config.json"))
            app.lbl_sens_val = types.SimpleNamespace(config=lambda **kwargs: None)

            async def broadcast(message):
                messages.append(message)

            def submit(coroutine, loop):
                try:
                    coroutine.send(None)
                except StopIteration:
                    pass

            app.server = types.SimpleNamespace(broadcast=broadcast)
            app.server_loop = types.SimpleNamespace(is_running=lambda: True)
            with patch.object(asyncio, "run_coroutine_threadsafe", side_effect=submit):
                app._on_sens_change("2.0")
                app._on_sens_change("2.0")
            self.assertEqual(app.config.get("mouse_sensitivity"), 2.0)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "config_sync")
        self.assertEqual(messages[0]["config"]["mouse_sensitivity"], 2.0)
        self.assertNotIn("pin_code", messages[0]["config"])

    def test_phone_settings_refresh_controls_without_overwriting_rounded_values(self):
        app = self.bare_app()
        app._refresh_build_url = lambda: None  # Pairing refresh is covered independently.

        class Control:
            def __init__(self, *args, callback=None, **kwargs):
                self.value, self.text, self.callback = None, "", callback

            def set(self, value):
                self.value = round(value, 1) if type(value) is float else value
                if self.callback:
                    self.callback(str(self.value))

            def get(self):
                return self.value

            def config(self, **kwargs):
                self.text = kwargs.get("text", self.text)

            def pack(self, **kwargs):
                pass

        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            app.config = ConfigManager(str(pathlib.Path(directory) / "config.json"))
            app.config.update({"mouse_sensitivity": 2.35, "mouse_acceleration": 1.23,
                               "invert_scroll": True, "laser_color": "blue"})
            app.scale_sens = Control(callback=app._on_sens_change)
            app.scale_accel = Control(callback=app._on_accel_change)
            app.scale_scroll = Control(callback=app._on_scroll_change)
            app.lbl_sens_val, app.lbl_accel_val, app.lbl_scroll_val = Control(), Control(), Control()
            app.var_invert, app.var_laser_color, app.lbl_pin_display = Control(), Control(), Control()
            scheduled = []
            app.root = types.SimpleNamespace(after=lambda delay, callback: scheduled.append(callback))
            app.devices_frame = types.SimpleNamespace(winfo_children=lambda: [])
            app.event_queue, app.clients_list = [], []
            app._refresh_devices = lambda: None
            with patch.object(self.gui.tk, "Label", Control), patch.object(
                app.config, "set", side_effect=AssertionError("refresh persisted rounded settings")
            ):
                app._start_periodic_updates()
                scheduled.pop(0)()
                # Tk may invoke a Scale callback after the refresh has ended.
                app._on_accel_change(str(app.scale_accel.get()))
            self.assertEqual(app.lbl_sens_val.text, "2.4x")
            self.assertEqual(app.lbl_accel_val.text, "1.23x")
            self.assertTrue(app.var_invert.get())
            self.assertEqual(app.var_laser_color.get(), "blue")
            self.assertEqual(app.config.get("mouse_sensitivity"), 2.35)

    def test_copy_url_uses_inline_feedback_without_interrupting_user(self):
        app = self.bare_app()
        copied, notices = [], []
        app.primary_ip, app.port = "192.168.1.25", 8765
        app.root = types.SimpleNamespace(clipboard_clear=lambda: copied.clear(),
                                         clipboard_append=copied.append,
                                         after=lambda delay, callback: None)
        app.lbl_copy_feedback = types.SimpleNamespace(config=lambda **kwargs: notices.append(kwargs.get("text")))
        dialog = getattr(self.gui, "messagebox", types.SimpleNamespace(showinfo=lambda *args: None))
        with patch.object(dialog, "showinfo") as modal:
            app._copy_url()
        self.assertEqual(copied, [app._connection_url()])
        self.assertFalse(modal.called)
        self.assertIn("Copied to clipboard.", notices)

    def test_pairing_copy_browser_and_qr_use_the_same_current_build_address(self):
        app = self.bare_app()
        app.primary_ip, app.port = '192.168.1.25', 8765
        self.assertTrue(callable(getattr(app, '_connection_url', None)), 'Pairing URL must carry current build identity')
        url = app._connection_url()
        self.assertRegex(url, r'^http://192\.168\.1\.25:8765/\?build=[0-9a-f]{16}$')
        with patch.object(self.gui.webbrowser, 'open') as launch:
            app._open_browser()
        launch.assert_called_once_with(url)

    def test_settings_resize_fits_content_to_viewport(self):
        app = self.bare_app()
        widths = []
        app.settings_canvas = types.SimpleNamespace(itemconfigure=lambda item, **kwargs: widths.append(kwargs["width"]))
        app._settings_window = "content"
        getattr(app, "_resize_settings", lambda event: None)(types.SimpleNamespace(width=410))
        self.assertEqual(widths, [410])

    def test_device_refresh_exposes_pin_state_and_preserves_unchanged_rows(self):
        app = self.bare_app()

        class Tree:
            def __init__(self):
                self.rows, self.insertions = {}, 0

            def insert(self, parent, position, **kwargs):
                self.insertions += 1
                item = str(self.insertions)
                self.rows[item] = kwargs
                return item

            def item(self, item, **kwargs):
                if kwargs:
                    self.rows[item].update(kwargs)
                return self.rows[item]

            def delete(self, item):
                del self.rows[item]

        app.devices_tree = Tree()
        app._device_rows = {}
        app.lbl_client_count = types.SimpleNamespace(config=lambda **kwargs: None)
        app.lbl_no_devices = types.SimpleNamespace(config=lambda **kwargs: None)
        app.clients_list = [{"device": "Android Phone", "ip": "192.168.1.40", "connected_at": 1,
                             "authenticated": False, "ping": 12, "packets": 4}]
        refresh = getattr(app, "_refresh_devices", lambda: None)
        refresh()
        self.assertEqual(len(app.devices_tree.rows), 1)
        row = next(iter(app.devices_tree.rows.values()))
        self.assertIn("PIN required", row["values"])
        self.assertEqual(row["values"][-1], "—")
        refresh()
        self.assertEqual(app.devices_tree.insertions, 1)
        app.clients_list[0]["authenticated"] = True
        refresh()
        self.assertIn("Ready", next(iter(app.devices_tree.rows.values()))["values"])
        self.assertEqual(next(iter(app.devices_tree.rows.values()))["values"][-1], "12 ms")
        for ping in (None, 0, -1):
            app.clients_list[0]["ping"] = ping
            refresh()
            self.assertEqual(next(iter(app.devices_tree.rows.values()))["values"][-1], "—")

    def test_activity_log_is_bounded_without_forcing_reader_to_latest_line(self):
        app = self.bare_app()

        class Log:
            def __init__(self):
                self.lines, self.scrolled = [], False

            def yview(self):
                return (0.1, 0.4)

            def configure(self, **kwargs):
                pass

            def insert(self, position, text):
                self.lines.extend(text.splitlines())

            def index(self, position):
                return f"{len(self.lines) + 1}.0"

            def delete(self, start, end):
                del self.lines[:int(end.split(".")[0]) - 1]

            def see(self, position):
                self.scrolled = True

        app.log_text = Log()
        app.event_queue = [f"event {index}" for index in range(1005)]
        getattr(app, "_flush_activity", lambda: None)()
        self.assertEqual(len(app.log_text.lines), 1000)
        self.assertEqual(app.log_text.lines[0], "event 5")
        self.assertFalse(app.log_text.scrolled)
        self.assertEqual(app.event_queue, [])

    def test_tray_action_queues_work_without_accessing_tk_on_worker_thread(self):
        app = self.gui.TouchHelmDesktopApp.__new__(self.gui.TouchHelmDesktopApp)
        app.ui_queue = queue.Queue()
        actions = []
        app.minimize_to_tray = lambda *args: actions.append(threading.get_ident())
        with patch.object(self.gui, "create_tray_image", return_value=None):
            app._init_tray_icon()
        menu_item = next(item for item in app.tray_icon.menu.items
                         if getattr(item, "text", None) == "Minimize to Tray")
        worker = threading.Thread(target=lambda: menu_item.action(app.tray_icon, menu_item))
        worker.start()
        worker.join(1)
        self.assertEqual(actions, [])
        app.ui_queue.get_nowait()()
        self.assertEqual(actions, [threading.get_ident()])

    def test_exit_callback_runs_on_ui_thread_once(self):
        app = self.gui.TouchHelmDesktopApp.__new__(self.gui.TouchHelmDesktopApp)
        app.tray_icon = None
        app._closing = False
        threads = []
        app.on_exit = lambda: threads.append(threading.get_ident())
        app._exit_app()
        app._exit_app()
        self.assertEqual(threads, [threading.get_ident()])

    def test_minimize_remains_recoverable_when_tray_creation_failed(self):
        class Root:
            state = "normal"

            def withdraw(self):
                self.state = "hidden"

            def iconify(self):
                self.state = "minimized"

        app = self.gui.TouchHelmDesktopApp.__new__(self.gui.TouchHelmDesktopApp)
        app.root, app.tray_icon = Root(), None
        with patch.dict(sys.modules, {"ctypes": types.SimpleNamespace()}):
            app.minimize_to_tray()
        self.assertEqual(app.root.state, "minimized")

    def test_minimize_uses_taskbar_until_tray_is_visible(self):
        app = self.bare_app()
        states = []
        app.tray_icon = types.SimpleNamespace(visible=False)
        app.root = types.SimpleNamespace(withdraw=lambda: states.append("hidden"),
                                         iconify=lambda: states.append("minimized"))
        with patch.dict(sys.modules, {"ctypes": types.SimpleNamespace()}):
            app.minimize_to_tray()
        self.assertEqual(states, ["minimized"])

    def test_async_tray_failure_restores_window_on_ui_thread(self):
        app = self.bare_app()
        restored = []
        app.root = types.SimpleNamespace(state=lambda: "withdrawn")
        app._do_restore = lambda: restored.append(threading.get_ident())

        class FailedIcon:
            visible = True

            def run(self, setup=None):
                raise OSError("notification area unavailable")

        with patch.object(self.gui.pystray, "Icon", return_value=FailedIcon()), patch.object(
            self.gui, "create_tray_image", return_value=None
        ), patch("sys.stderr", io.StringIO()):
            app._init_tray_icon()
            # Existing code loses this error on the worker and never queues recovery.
            try:
                recovery = app.ui_queue.get(timeout=0.1)
            except queue.Empty:
                recovery = None
            self.assertIsNotNone(recovery)
            recovery()
        self.assertIsNone(app.tray_icon)
        self.assertEqual(restored, [threading.get_ident()])


if __name__ == "__main__":
    unittest.main()
