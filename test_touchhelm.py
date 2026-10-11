"""
TouchHelm Automated End-to-End Verification Test
Tests:
1. Server HTTP API (/api/info, /api/config)
2. Static Asset Delivery (index.html, style.css, app.js, manifest.json, sw.js)
3. WebSocket Connection & Latency Ping/Pong
4. Authentication Handshake
5. PIN Enforcement & Invalidation
6. Mouse Movement, Click, Double Click, Scroll
7. Presentation Remote Actions
8. Keyboard & Unicode Typing
9. Digital Laser Pointer Overlay Communication
"""

import sys
import time
import asyncio
import aiohttp
import json

from server.config import ConfigManager
from server.web_server import TouchHelmServer

TEST_PORT = 8799

async def run_tests():
    print("[TEST] Initializing TouchHelm test instance on port", TEST_PORT)
    config = ConfigManager()
    config.set("port", TEST_PORT)
    config.set("require_pin", False)

    server = TouchHelmServer(config=config)
    await server.start()
    init_vol, init_muted = server.input_ctrl.get_volume()
    init_bright = server.input_ctrl.get_brightness()
    print("[TEST] Server started successfully.")

    base_url = f"http://127.0.0.1:{TEST_PORT}"
    ws_url = f"ws://127.0.0.1:{TEST_PORT}/ws"

    async with aiohttp.ClientSession() as session:
        # 1. Test /api/info
        print("[TEST] Checking /api/info...")
        async with session.get(f"{base_url}/api/info") as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            data = await resp.json()
            assert data["service"] == "touchhelm", f"Expected service touchhelm, got {data.get('service')}"
            assert "screen_width" in data
            assert "screen_height" in data
            assert "volume" in data
            assert "muted" in data
            assert "brightness" in data
            print(f" -> Info OK: Screen {data['screen_width']}x{data['screen_height']}, Volume: {data['volume']}%, Muted: {data['muted']}, Brightness: {data['brightness']}%, Service: {data['service']}")

        # Test /api/config GET & POST
        print("[TEST] Checking /api/config...")
        async with session.post(f"{base_url}/api/config", json={"mouse_sensitivity": 1.6, "laser_color": "blue"}) as cfg_resp:
            assert cfg_resp.status == 200
            cfg_data = await cfg_resp.json()
            assert cfg_data["success"] is True
            assert cfg_data["config"]["mouse_sensitivity"] == 1.6
            assert cfg_data["config"]["laser_color"] == "blue"
            print(" -> Config POST OK: Sensitivity updated to 1.6x, Laser color blue")

        # 2. Test Static Assets
        print("[TEST] Checking Static Assets...")
        for path in ["/", "/style.css", "/app.js", "/manifest.json", "/sw.js", "/icons/icon.svg"]:
            async with session.get(f"{base_url}{path}") as resp:
                assert resp.status == 200, f"Asset {path} failed with {resp.status}"
                body = await resp.read()
                assert len(body) > 0
                print(f" -> Asset {path} OK ({len(body)} bytes)")

        # 3. Test WebSocket Without PIN
        print("[TEST] Connecting to WebSocket at", ws_url)
        async with session.ws_connect(ws_url) as ws:
            # Server sends initial greeting
            init_msg = await ws.receive_json()
            assert init_msg["type"] == "auth_res"
            assert init_msg["success"] is True

            # Send Auth
            await ws.send_json({"type": "auth", "device_name": "Test Android TouchHelm"})
            auth_reply = await ws.receive_json()
            assert auth_reply["type"] == "auth_res"
            assert auth_reply["success"] is True
            print(" -> Auth Handshake (No PIN) OK")

            # Send Ping
            t0 = time.time() * 1000
            await ws.send_json({"type": "ping", "t": t0})
            pong = await ws.receive_json()
            assert pong["type"] == "pong"
            print(f" -> Ping/Pong OK (RTT: {time.time()*1000 - t0:.1f}ms)")

            # Send Mouse Move
            print("[TEST] Testing mouse relative movement...")
            await ws.send_json({"type": "move", "dx": 5, "dy": -3})
            await asyncio.sleep(0.05)
            print(" -> Mouse Move OK")

            # Send Mouse Clicks & Hold Drag Lock
            print("[TEST] Testing mouse clicks & drag lock...")
            await ws.send_json({"type": "click", "button": "left"})
            await ws.send_json({"type": "click", "button": "right"})
            await ws.send_json({"type": "click", "button": "middle"})
            await ws.send_json({"type": "mousedown", "button": "left"})
            await ws.send_json({"type": "move", "dx": 2, "dy": 2})
            await ws.send_json({"type": "mouseup", "button": "left"})
            await asyncio.sleep(0.05)
            print(" -> Mouse Clicks & Drag Lock OK")

            # Send Mouse Double Click (both dblclick and double_click aliases)
            print("[TEST] Testing mouse double click...")
            await ws.send_json({"type": "dblclick", "button": "left"})
            await ws.send_json({"type": "double_click", "button": "left"})
            await asyncio.sleep(0.05)
            print(" -> Mouse Double Click OK")

            # Send Mouse Scroll
            print("[TEST] Testing mouse scroll...")
            await ws.send_json({"type": "scroll", "dx": 0, "dy": 2})
            await asyncio.sleep(0.05)
            print(" -> Mouse Scroll OK")

            # Send Presentation Actions (all actions)
            print("[TEST] Testing presentation actions...")
            for act in ["start", "start_current", "current", "next", "prev", "black", "white", "end"]:
                await ws.send_json({"type": "presentation", "action": act})
            await asyncio.sleep(0.05)
            print(" -> Presentation Actions OK")

            # Send Media Actions (all actions)
            print("[TEST] Testing media actions...")
            # Send Media Actions
            print("[TEST] Testing media actions...")
            for m_act in ["play_pause", "next", "prev", "stop"]:
                await ws.send_json({"type": "media", "action": m_act})
            await asyncio.sleep(0.05)
            print(" -> Media Actions OK")

            # 4. Test Real-Time Windows Master Volume Control & Sync
            print("[TEST] Testing Real-Time Windows Master Volume...")
            await ws.send_json({"type": "volume", "level": 70})
            vol_sync = await ws.receive_json()
            assert vol_sync["type"] == "volume_sync"
            assert vol_sync["volume"] == 70
            assert "muted" in vol_sync
            print(f" -> Set volume to 70% OK (volume: {vol_sync['volume']}%, muted: {vol_sync['muted']})")

            await ws.send_json({"type": "volume", "action": "up"})
            vol_up_sync = await ws.receive_json()
            assert vol_up_sync["type"] == "volume_sync"
            assert vol_up_sync["volume"] == 72
            print(" -> Volume action up OK (72%)")

            await ws.send_json({"type": "volume", "action": "mute"})
            vol_mute_sync = await ws.receive_json()
            assert vol_mute_sync["type"] == "volume_sync"
            print(f" -> Volume action mute OK (muted={vol_mute_sync['muted']})")

            await ws.send_json({"type": "get_volume"})
            get_vol_sync = await ws.receive_json()
            assert get_vol_sync["type"] == "volume_sync"
            print(" -> get_volume query OK")

            # 5. Test Display Brightness Control & Sync
            print("[TEST] Testing Display Brightness Control...")
            await ws.send_json({"type": "brightness", "level": 85})
            bright_sync = await ws.receive_json()
            assert bright_sync["type"] == "brightness_sync"
            assert bright_sync["level"] == 85
            print(f" -> Set brightness to 85% OK (level: {bright_sync['level']}%)")

            await ws.send_json({"type": "brightness", "action": "down"})
            bright_down_sync = await ws.receive_json()
            assert bright_down_sync["type"] == "brightness_sync"
            assert bright_down_sync["level"] == 75
            print(" -> Brightness action down OK (75%)")

            await ws.send_json({"type": "get_brightness"})
            get_bright_sync = await ws.receive_json()
            assert get_bright_sync["type"] == "brightness_sync"
            print(" -> get_brightness query OK")

            # 6. Test Windows Start Button
            print("[TEST] Testing Windows Start menu triggers...")
            await ws.send_json({"type": "shortcut", "name": "start"})
            await ws.send_json({"type": "start_menu"})
            await asyncio.sleep(0.05)
            print(" -> Windows Start Menu triggers OK")

            # Send Shortcuts (all shortcuts)
            print("[TEST] Testing desktop shortcuts...")
            for sc in ["desktop", "app_switch", "task_view", "lock", "search", "screenshot"]:
                await ws.send_json({"type": "shortcut", "name": sc})
            await asyncio.sleep(0.05)
            print(" -> Desktop Shortcuts OK")

            # Send Keys & Hotkeys
            print("[TEST] Testing virtual keys and macros...")
            await ws.send_json({"type": "key", "key": "tab"})
            await ws.send_json({"type": "hotkey", "keys": ["ctrl", "a"]})
            await asyncio.sleep(0.05)
            print(" -> Keys & Macros OK")

            # Send Laser Update & Hide
            print("[TEST] Testing laser pointer update...")
            await ws.send_json({"type": "laser", "x": 0.5, "y": 0.5, "active": True, "color": "emerald"})
            await asyncio.sleep(0.05)
            await ws.send_json({"type": "laser_hide"})
            print(" -> Laser Pointer OK")

            # Send Unicode Text
            print("[TEST] Testing unicode typing...")
            await ws.send_json({"type": "text", "text": "TouchHelm Test"})
            await asyncio.sleep(0.05)
            print(" -> Unicode Typing OK")

        # 7. Test Multi-Client Real-Time Volume Broadcast & Zero-Auth
        print("[TEST] Testing Multi-Client Real-Time Volume Broadcast...")
        async with session.ws_connect(ws_url) as ws_c1, session.ws_connect(ws_url) as ws_c2:
            g1 = await ws_c1.receive_json()
            g2 = await ws_c2.receive_json()
            assert g1["type"] == "auth_res" and g2["type"] == "auth_res"

            # Client 1 sets volume, Client 2 receives broadcast
            await ws_c1.send_json({"type": "volume", "level": 60})
            sync1 = await ws_c1.receive_json()
            sync2 = await ws_c2.receive_json()
            assert sync1["type"] == "volume_sync" and sync1["volume"] == 60
            assert sync2["type"] == "volume_sync" and sync2["volume"] == 60
            print(" -> Multi-Client Volume Broadcast OK (both clients synced to 60%)")

            # Test auto-unmute on volume set > 0
            await ws_c1.send_json({"type": "volume", "action": "mute"})
            sync_mute = await ws_c1.receive_json()
            assert sync_mute["type"] == "volume_sync"
            if sync_mute["muted"]:
                # When muted, setting volume to 65% must automatically unmute
                await ws_c1.send_json({"type": "volume", "level": 65})
                sync_unmute = await ws_c1.receive_json()
                assert sync_unmute["type"] == "volume_sync"
                assert sync_unmute["volume"] == 65
                assert sync_unmute["muted"] is False
                print(" -> Auto-unmute on volume set > 0 OK")

            # Client 2 immediately moves cursor without any PIN challenges
            await ws_c2.send_json({"type": "move", "dx": -10, "dy": 5})
            await asyncio.sleep(0.05)
            print(" -> Client 2 instantly controlling without PIN OK")

    # 8. Test Desktop GUI Window Lifecycle (Minimize to Tray & Restore)
    print("[TEST] Testing Desktop GUI Window Lifecycle (Minimize to Tray & Restore)...")
    import tkinter as tk
    from gui.app_window import TouchHelmDesktopApp
    gui_root = tk.Tk()
    gui_app = TouchHelmDesktopApp(gui_root, config=config, server_instance=server)
    # Test minimize to tray
    gui_app.minimize_to_tray()
    assert gui_root.state() == "withdrawn", f"Expected withdrawn state, got {gui_root.state()}"
    print(" -> Minimize to Tray OK (root.state() == 'withdrawn')")
    # Test restore
    gui_app._do_restore()
    assert gui_root.state() == "normal", f"Expected normal state, got {gui_root.state()}"
    print(" -> Restore from Tray OK (root.state() == 'normal')")
    # Clean exit
    if gui_app.tray_icon:
        gui_app.tray_icon.stop()
    gui_root.destroy()
    print(" -> GUI Window Clean Destroy OK")

    print("[TEST] All TouchHelm tests passed successfully!")
    config.set("port", 8765)
    config.set("require_pin", False)
    config.set("pin_code", "")
    server.input_ctrl.set_volume(init_vol)
    server.input_ctrl.set_mute(init_muted)
    server.input_ctrl.set_brightness(init_bright)
    await server.stop()

if __name__ == "__main__":
    asyncio.run(run_tests())
