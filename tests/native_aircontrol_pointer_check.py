"""Opt-in native pointer check: owned blank window, no camera/clicks/typing."""
import asyncio
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.aircontrol.service import AirControlService
from server.aircontrol.engine import GestureEngine
from server.aircontrol.profiles import default_profile
from server.desktop_services import DesktopServices
from server.windows_input import WindowsInputController

SCRIPT=r'''
param([string]$ready)
Add-Type -AssemblyName System.Windows.Forms
$form=New-Object System.Windows.Forms.Form
$form.Text='TouchHelm pointer check - no clicks or typing'
$form.Width=440;$form.Height=260;$form.Left=80;$form.Top=80
$form.StartPosition='Manual';$form.TopMost=$true
$label=New-Object System.Windows.Forms.Label
$label.Text='Verifying pointer movement only. Cursor will be restored.'
$label.AutoSize=$true;$label.Left=20;$label.Top=20;$form.Controls.Add($label)
$form.Add_Shown({[System.IO.File]::WriteAllText($ready,$form.Handle.ToInt64().ToString())})
[System.Windows.Forms.Application]::Run($form)
$form.Dispose()
'''

async def run():
    native=WindowsInputController();providers=DesktopServices()
    before=native.get_physical_cursor_pos();service=None;process=None;handle=None
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    api.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    try:
        with tempfile.TemporaryDirectory(prefix='touchhelm-pointer-') as folder:
            directory=Path(folder);ready=directory/'ready';script=directory/'window.ps1'
            script.write_text(SCRIPT,encoding='utf-8-sig')
            process=subprocess.Popen(['powershell.exe','-NoProfile','-Sta','-ExecutionPolicy','Bypass','-File',str(script),str(ready)],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.monotonic()+12
            while not ready.exists() and time.monotonic()<deadline:await asyncio.sleep(.05)
            assert ready.exists(),'Scratch window did not open'
            handle=int(ready.read_text());rect=wintypes.RECT()
            assert api.GetWindowRect(handle,ctypes.byref(rect)),'Scratch geometry unavailable'
            displays=(await providers.displays())['displays']
            display=next(d for d in displays if d['rect']['x']<=rect.left<d['rect']['x']+d['rect']['width'])
            assert native.monitor_matches(display),'Physical monitor metadata does not match'
            setup=Mock();setup.snapshot.return_value={'ready':True,'state':'ready'}
            service=AirControlService(native,providers.displays,folder=directory/'air',setup=setup)
            profile=default_profile(mode='hand');profile.update(smoothing=0,auto_dictation=False)
            service.profile=profile;service.engine=GestureEngine(profile)
            service.display=display;service.state='active';service.owns_input=True
            r=display['rect'];points=[(rect.left+100,rect.top+110),(rect.left+230,rect.top+170)]
            for seq,(x,y) in enumerate(points):
                cx=.15+.7*(x-r['x'])/(r['width']-1);cy=.15+.7*(y-r['y'])/(r['height']-1)
                service.observe({'timestamp':time.monotonic(),'seq':seq,'hand':{
                    'tracked':True,'x':cx,'y':cy,'pose':'Pointing_Up','pinch_index':1,'pinch_middle':1}})
                assert service.state=='active',service.message
                actual=native.get_physical_cursor_pos()
                assert abs(actual[0]-x)<=1 and abs(actual[1]-y)<=1,'Windows cursor did not reach the scratch target'
                await asyncio.sleep(.04)
            service.observe({'timestamp':time.monotonic(),'seq':2})
            assert service.state=='tracking_lost','Tracking loss did not pause'
            print(json.dumps({'native_pointer':'passed','scratch_targets':2,'tracking_loss_pause':True,'camera_opened':False,'clicks_sent':0,'keys_sent':0}))
    finally:
        if service:await service.close()
        native.set_physical_cursor_pos(*before);native.close();await providers.close()
        if handle:api.PostMessageW(handle,0x10,0,0)
        if process:
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=3)

if __name__=='__main__':asyncio.run(run())
