"""Opt-in read-only camera enumeration and owned HUD smoke check. No capture/input."""
import asyncio
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.aircontrol.devices import cameras
from server.aircontrol.overlay import AirOverlay

def run():
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.GetForegroundWindow.restype=wintypes.HWND
    api.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    api.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    api.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    api.IsWindowVisible.argtypes=[wintypes.HWND]
    enum_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def owned(pid):
        result=[]
        @enum_type
        def visit(handle,param):
            owner=wintypes.DWORD();api.GetWindowThreadProcessId(handle,ctypes.byref(owner))
            if owner.value==pid and api.IsWindowVisible(handle):result.append(handle)
            return True
        api.EnumWindows(visit,0);return result
    events=[];hud=AirOverlay(events.append);before=api.GetForegroundWindow()
    state={'owns_input':True,'state':'active','gesture_label':'Smoke check · no camera',
        'progress':.5,'point':[.5,.5],'display':{'rect':{'x':0,'y':0,'width':api.GetSystemMetrics(0),'height':api.GetSystemMetrics(1)}}}
    try:
        hud.update(state);deadline=time.monotonic()+18
        while time.monotonic()<deadline:
            windows=owned(hud.process.pid)
            if windows:break
            time.sleep(.1)
        assert windows,'Owned HUD did not become visible'
        time.sleep(.25)
        assert before==api.GetForegroundWindow(),'HUD stole foreground focus'
        # Only send a button message to this test's own HUD process.
        @enum_type
        def click_pause(handle,param):
            title=ctypes.create_unicode_buffer(80);api.GetWindowTextW(handle,title,80)
            if title.value=='Pause':api.SendMessageW(handle,0x00F5,0,0)
            return True
        api.EnumChildWindows(windows[0],click_pause,0)
        deadline=time.monotonic()+2
        while 'pause' not in events and time.monotonic()<deadline:time.sleep(.05)
        assert 'pause' in events,'HUD Pause callback did not arrive'
        hud.update(dict(state,state='paused'));time.sleep(.3)
        assert len(owned(hud.process.pid))==2,'Paused virtual cursor did not appear'
        assert before==api.GetForegroundWindow(),'Paused HUD/virtual cursor stole focus'
        devices=asyncio.run(cameras());assert devices['available'],devices['message']
        print(json.dumps({'native_hud':'passed','no_activation':True,'pause_callback':True,
            'paused_virtual_cursor':True,'camera_enumeration':len(devices['cameras']),
            'camera_opened':False,'hotkey':hud.hotkey_status}))
    finally:hud.close()

if __name__=='__main__':run()
