"""Opt-in Head action check in an owned blank window. No camera or typing.

Real mouse events are guarded to this scratch window. Synthetic pose observations
verify native dispatch only, not physical gesture recognition or user comfort.
"""
import asyncio
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
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
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @'
using System;using System.Windows.Forms;using System.Drawing;
public class ScratchSurface:Panel {
 public ScratchSurface(){SetStyle(ControlStyles.StandardClick|ControlStyles.StandardDoubleClick,true);Dock=DockStyle.Fill;BackColor=Color.FromArgb(28,48,62);}
 protected override void OnMouseDown(MouseEventArgs e){Console.WriteLine("{\"kind\":\"down\",\"button\":\""+e.Button+"\",\"x\":"+e.X+",\"y\":"+e.Y+",\"clicks\":"+e.Clicks+"}");Console.Out.Flush();base.OnMouseDown(e);}
 protected override void OnMouseUp(MouseEventArgs e){Console.WriteLine("{\"kind\":\"up\",\"button\":\""+e.Button+"\",\"x\":"+e.X+",\"y\":"+e.Y+"}");Console.Out.Flush();base.OnMouseUp(e);}
 protected override void OnPaint(PaintEventArgs e){base.OnPaint(e);e.Graphics.DrawString("TouchHelm Head action check\nOwned scratch surface only. No camera or typing.",SystemFonts.MessageBoxFont,Brushes.White,20,20);}
}
'@
$form=New-Object System.Windows.Forms.Form
$form.Text='TouchHelm Head action check';$form.StartPosition='Manual'
$form.Left=80;$form.Top=80;$form.Width=520;$form.Height=360;$form.TopMost=$true
$surface=New-Object ScratchSurface;$form.Controls.Add($surface)
$form.Add_Shown({[IO.File]::WriteAllText($ready,$form.Handle.ToInt64().ToString())})
[Windows.Forms.Application]::Run($form);$form.Dispose()
'''


async def run():
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    api.WindowFromPoint.argtypes=[wintypes.POINT];api.WindowFromPoint.restype=wintypes.HWND
    api.WindowFromPhysicalPoint.argtypes=[wintypes.POINT];api.WindowFromPhysicalPoint.restype=wintypes.HWND
    api.IsWindowVisible.argtypes=[wintypes.HWND]
    api.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    api.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    api.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];api.GetAncestor.restype=wintypes.HWND
    api.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    native=WindowsInputController();providers=DesktopServices();before=native.get_physical_cursor_pos()
    service=None;process=None;handle=None;events=queue.Queue()
    try:
        with tempfile.TemporaryDirectory(prefix='touchhelm-head-input-') as folder:
            directory=Path(folder);script=directory/'scratch.ps1';ready=directory/'ready'
            script.write_text(SCRIPT,encoding='utf-8-sig')
            process=subprocess.Popen(['powershell.exe','-NoProfile','-Sta','-ExecutionPolicy','Bypass','-File',str(script),str(ready)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
            def read():
                for line in process.stdout:
                    try:events.put(json.loads(line))
                    except ValueError:pass
            threading.Thread(target=read,daemon=True).start()
            deadline=time.monotonic()+15
            while not ready.exists() and time.monotonic()<deadline:
                if process.poll() is not None:raise RuntimeError('Scratch failed: '+process.stderr.read()[-500:])
                await asyncio.sleep(.05)
            assert ready.exists(),'Scratch window did not open';handle=int(ready.read_text())
            api.SetWindowPos(handle,wintypes.HWND(-1),0,0,0,0,0x1|0x2|0x10|0x40)
            await asyncio.sleep(.2)
            rect=wintypes.RECT();assert api.GetWindowRect(handle,ctypes.byref(rect))
            display=next(d for d in (await providers.displays())['displays'] if d['rect']['x']<=rect.left<d['rect']['x']+d['rect']['width'])
            assert native.monitor_matches(display)
            if '--probe-only' in sys.argv:
                out=[]
                for x,y in [(rect.left+140,rect.top+150),(rect.left+330,rect.top+245)]:
                    root=api.GetAncestor(api.WindowFromPoint(wintypes.POINT(x,y)),2)
                    physical_root=api.GetAncestor(api.WindowFromPhysicalPoint(wintypes.POINT(x,y)),2)
                    name=ctypes.create_unicode_buffer(120);api.GetClassNameW(physical_root,name,120)
                    out.append({'target':[x,y],'root':root,'matches':root==handle,'physical_root':physical_root,'physical_matches':physical_root==handle,'covering_class':name.value})
                print(json.dumps({'scratch_handle':handle,'scratch_rect':[rect.left,rect.top,rect.right,rect.bottom],'visible':bool(api.IsWindowVisible(handle)),'process_running':process.poll() is None,'targets':out}),flush=True)
                return
            class ScratchInput:
                def __getattr__(self,name):return getattr(native,name)
                def guard(self):
                    x,y=native.get_physical_cursor_pos()
                    assert api.GetAncestor(api.WindowFromPhysicalPoint(wintypes.POINT(x,y)),2)==handle,'Input target left the owned scratch window'
                def mouse_down(self,button):self.guard();native.mouse_down(button)
                def click(self,button):self.guard();native.click(button)
                def double_click(self,button):self.guard();native.double_click(button)
            setup=Mock();setup.snapshot.return_value={'ready':True,'state':'ready'}
            service=AirControlService(ScratchInput(),providers.displays,folder=directory/'air',setup=setup)
            profile=default_profile(mode='head');profile.update(smoothing=0,head_stability=0,dwell_ms=400,auto_dictation=False)
            service.profile=profile;service.display=display;service.state='active';service.owns_input=True
            r=display['rect'];sequence=0
            async def point(x,y,seconds):
                nonlocal sequence
                deadline=time.monotonic()+seconds
                while time.monotonic()<deadline:
                    expected=service.last_point;actual=native.get_physical_cursor_pos()
                    service.observe({'timestamp':time.monotonic(),'seq':sequence,'face':{'tracked':True,'count':1,
                        'yaw':((x-r['x'])/(r['width']-1)-.5)*36,'pitch':((y-r['y'])/(r['height']-1)-.5)*36}})
                    sequence+=1
                    if service.state!='active':
                        print(json.dumps({'interrupted':service.message,'detail':service.last_error,'actual_before':actual,'last_commanded':expected}),flush=True)
                        raise AssertionError(service.message)
                    await asyncio.sleep(.04)
            a=(rect.left+140,rect.top+150);b=(rect.left+330,rect.top+245)
            recorded={}
            for action in ('left_click','right_click','double_click','drag'):
                service._release_buttons();service.engine=GestureEngine(profile);service.engine.select_dwell(action)
                await point(*a,.55)
                if action=='drag':
                    assert service.native_down,'First dwell did not hold'
                    await point(*b,1.05)
                    assert not service.native_down,'Second dwell did not drop'
                await asyncio.sleep(.1);batch=[]
                while not events.empty():batch.append(events.get_nowait())
                recorded[action]=batch
                print(json.dumps({'checked':action,'scratch_events':batch}),flush=True)
            assert any(e['kind']=='down' and e['button']=='Left' for e in recorded['left_click'])
            assert any(e['kind']=='down' and e['button']=='Right' for e in recorded['right_click'])
            assert any(e['kind']=='down' and e['clicks']==2 for e in recorded['double_click'])
            drag=recorded['drag'];down=next(e for e in drag if e['kind']=='down');up=next(e for e in drag if e['kind']=='up')
            assert abs(up['x']-down['x'])>150 and abs(up['y']-down['y'])>70,'Drag did not span both scratch targets'
            assert not service.native_down
            print(json.dumps({'head_native_actions':'passed','left_click':True,'right_click':True,'double_click':True,
                'dwell_drag_drop':True,'buttons_released':True,'camera_opened':False,'keys_sent':0}))
    finally:
        if service:await service.close()
        native.set_physical_cursor_pos(*before);native.close();await providers.close()
        if handle:api.PostMessageW(handle,0x10,0,0)
        if process:
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=3)


if __name__=='__main__':asyncio.run(run())
