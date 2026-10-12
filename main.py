"""
TouchHelm - Windows Host Server & Remote Controller
Main Entry Point.
"""

import sys
import time
import argparse
import asyncio
import threading
import hashlib
import json
from pathlib import Path
from concurrent.futures import Future

from server.config import ConfigManager
from server.discovery import DiscoveryBeaconService, get_local_ip_addresses
from server.web_server import TouchHelmServer
from server.instance_control import InstanceController, source_build_id


def run_async_server(server_instance, loop, startup=None):
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server_instance.start())
        if startup is not None:
            startup.set_result(None)
        loop.run_forever()
    except Exception as error:
        if startup is not None and not startup.done():
            startup.set_exception(error)
        else:
            raise
    finally:
        try:
            loop.run_until_complete(server_instance.stop())
        finally:
            loop.close()
            asyncio.set_event_loop(None)


def print_banner(primary_ip, port, require_pin, pin_code):
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    url = f"http://{primary_ip}:{port}"
    print("\n" + "=" * 60)
    print("        TOUCHHELM - WINDOWS HOST CONTROLLER          ")
    print("=" * 60)
    print(f"  Local Web / Mobile URL : {url}")
    if require_pin:
        print(f"  Access Mode            : Security PIN ({pin_code})")
    else:
        print("  Access Mode            : Instant Connect (Direct Access)")
    print("  Auto-Discovery Beacon  : ACTIVE (UDP Port 53317)")
    print("-" * 60)
    print("  Scan the QR code below or visit the URL on your Android phone:")
    print("-" * 60)
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception:
        pass
    print("=" * 60)
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="TouchHelm Remote Control Host for Windows")
    parser.add_argument("--port", type=int, default=None, help="Server port (default: 8765)")
    parser.add_argument("--no-gui", "--headless", action="store_true", help="Run without Desktop GUI in terminal mode")
    parser.add_argument("--pin", type=str, default=None, help="Require 4-digit security PIN")
    parser.add_argument("--classic-ui", action="store_true", help="Use the classic Tk desktop instead of EdgeChromium")
    args = parser.parse_args()

    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.pin is not None and (len(args.pin) != 4 or not args.pin.isascii() or not args.pin.isdigit()):
        parser.error("--pin must contain exactly four ASCII digits")

    config = ConfigManager()
    if args.port is not None:
        config.set("port", args.port)
    if args.pin is not None:
        config.update({"require_pin": True, "pin_code": args.pin})

    port = int(config.get("port", 8765))
    ips = get_local_ip_addresses()
    primary_ip = ips[0] if ips else "127.0.0.1"

    source_root = Path(__file__).resolve().parent
    build = source_build_id(source_root)
    mode = 'headless' if args.no_gui else 'classic' if args.classic_ui else 'webview'
    # A saved CLI override must not merely restore a host using its old binding
    # or access policy. Only an opaque identity travels through protected IPC.
    startup_policy = {'port': port, 'require_pin': config.get('require_pin', False),
                      'pin_code': config.get('pin_code', '') if config.get('require_pin', False) else ''}
    policy_id = hashlib.sha256(json.dumps(startup_policy, sort_keys=True).encode()).hexdigest()[:12]
    instance = InstanceController(f'{build}-{mode}-{policy_id}', source_root=source_root)
    try:
        if not instance.acquire():
            handoff = instance.handoff(timeout=20)
            if handoff == 'restored':
                print('Restored the running TouchHelm host.')
                return 0
            if handoff != 'acquired':
                print('The running TouchHelm host could not be restored or stopped safely. Close it and try again.', file=sys.stderr)
                return 1
    except Exception as error:
        instance.close()
        print(f'Unable to initialize TouchHelm instance control: {error}', file=sys.stderr)
        return 1

    # Shared UI log handlers
    gui_app = None
    root = None
    server_loop = None
    server_thread = None
    beacon = None
    stopped = threading.Event()

    def restore_host():
        if gui_app:
            gui_app.restore_from_tray()

    def stop_host():
        stopped.set()
        if gui_app:
            if hasattr(gui_app, 'request_close'):
                gui_app.request_close()
            else:
                gui_app.ui_queue.put(gui_app._exit_app)

    def on_event_callback(msg):
        if gui_app:
            gui_app.log_event(msg)
        else:
            print(msg)

    def on_clients_callback(clients):
        if gui_app:
            gui_app.update_clients(clients)

    try:
        instance.start(restore_host, stop_host)
        if stopped.is_set(): return 0
        beacon = DiscoveryBeaconService(port=port,
            has_pin=lambda: config.get("require_pin", False), server_name=config.get("server_name"))
        server = TouchHelmServer(config=config, on_event=on_event_callback,
                                on_client_change=on_clients_callback)
        server_loop = asyncio.new_event_loop()
        startup = Future()
        server_thread = threading.Thread(target=run_async_server,
            args=(server, server_loop, startup), daemon=True, name='TouchHelm host')
        server_thread.start()
        try:
            startup.result(timeout=10.0)
        except Exception as error:
            print(f"Unable to start TouchHelm server: {error}", file=sys.stderr)
            return 1

        beacon.start()
        print_banner(
            primary_ip,
            port,
            config.get("require_pin", False),
            config.get("pin_code", "1234")
        )
        if stopped.is_set(): return 0
        if args.no_gui:
            while server_thread.is_alive() and not stopped.wait(.5):
                pass
        elif args.classic_ui:
            # Keep GUI dependencies optional for headless mode.
            import tkinter as tk
            from gui.app_window import TouchHelmDesktopApp

            root = tk.Tk()
            gui_app = TouchHelmDesktopApp(
                root,
                config=config,
                server_instance=server,
                server_loop=server_loop,
                on_exit=root.destroy
            )
            if stopped.is_set():
                root.destroy()
            else:
                root.mainloop()
        else:
            from gui.webview_window import WebViewDesktopApp
            gui_app = WebViewDesktopApp(config, server, server_loop,
                primary_ip=primary_ip, build_id=build, on_exit=stopped.set)
            if stopped.is_set(): gui_app.request_close()
            gui_app.run()
    except KeyboardInterrupt:
        print("\nShutting down TouchHelm server...")
    except Exception as error:
        print(f'Unable to open TouchHelm: {error}. Use run.bat --classic-ui for the classic desktop, or --headless for terminal mode.', file=sys.stderr)
        return 1
    finally:
        stopped.set()
        if gui_app:
            if hasattr(gui_app, 'close'):
                gui_app.close()
            elif gui_app.tray_icon:
                gui_app.tray_icon.stop()
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        if beacon: beacon.stop()
        if server_loop is not None and not server_loop.is_closed():
            try:
                server_loop.call_soon_threadsafe(server_loop.stop)
            except RuntimeError:
                pass
        if server_thread is not None:
            server_thread.join(timeout=15.0)
            if server_thread.is_alive():
                print('TouchHelm shutdown did not complete within 15 seconds.', file=sys.stderr)
        instance.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
