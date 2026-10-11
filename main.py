"""
TouchHelm - Windows Host Server & Remote Controller
Main Entry Point.
"""

import sys
import time
import argparse
import asyncio
import threading
from concurrent.futures import Future

from server.config import ConfigManager
from server.discovery import DiscoveryBeaconService, get_local_ip_addresses
from server.web_server import TouchHelmServer


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

    # Start UDP Discovery Beacon
    beacon = DiscoveryBeaconService(
        port=port,
        has_pin=lambda: config.get("require_pin", False),
        server_name=config.get("server_name")
    )

    # Shared UI log handlers
    gui_app = None

    def on_event_callback(msg):
        if gui_app:
            gui_app.log_event(msg)
        else:
            print(msg)

    def on_clients_callback(clients):
        if gui_app:
            gui_app.update_clients(clients)

    # Initialize Web & WebSocket Server
    server = TouchHelmServer(
        config=config,
        on_event=on_event_callback,
        on_client_change=on_clients_callback
    )

    # Start Async Server loop in background thread
    server_loop = asyncio.new_event_loop()
    startup = Future()
    server_thread = threading.Thread(
        target=run_async_server,
        args=(server, server_loop, startup),
        daemon=True
    )
    server_thread.start()

    root = None
    try:
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
        if args.no_gui:
            while server_thread.is_alive():
                time.sleep(0.5)
        else:
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
            root.mainloop()
    except KeyboardInterrupt:
        print("\nShutting down TouchHelm server...")
    finally:
        if gui_app and gui_app.tray_icon:
            gui_app.tray_icon.stop()
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        beacon.stop()
        if not server_loop.is_closed():
            try:
                server_loop.call_soon_threadsafe(server_loop.stop)
            except RuntimeError:
                pass
        server_thread.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
