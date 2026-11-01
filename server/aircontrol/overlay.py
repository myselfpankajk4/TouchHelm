"""Non-activating native status/control HUD, isolated from the desktop renderer."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from .hud import HEAD_ACTIONS,HEAD_SCROLL_ACTIONS,layout,regions

class AirOverlay:
    def __init__(self,callback):
        self.callback=callback;self.process=None;self.pending=queue.Queue(maxsize=1)
        self.last=0.;self.hotkey=None;self.hotkey_thread=None;self.hotkey_status='Available after enabling control'
    def _start(self):
        self.process=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Sta','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_suffix('.ps1'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        process=self.process
        def read():
            for line in process.stdout:
                try:value=json.loads(line)
                except ValueError:continue
                if value.get('action') in ('pause','resume','stop','recenter',*HEAD_ACTIONS,*HEAD_SCROLL_ACTIONS):self.callback(value['action'])
        def write():
            while self.process is process and process.poll() is None:
                try:value=self.pending.get(timeout=.2)
                except queue.Empty:continue
                try:process.stdin.write(json.dumps(value)+'\n');process.stdin.flush()
                except (OSError,ValueError):break
        threading.Thread(target=read,daemon=True,name='AirControl HUD events').start()
        threading.Thread(target=write,daemon=True,name='AirControl HUD state').start()
        self._hotkey()
    def _hotkey(self):
        if self.hotkey:self.hotkey.set()
        if self.hotkey_thread:self.hotkey_thread.join(timeout=.15)
        self.hotkey=threading.Event();stop=self.hotkey
        def run():
            import ctypes
            from ctypes import wintypes
            api=ctypes.windll.user32
            registered=api.RegisterHotKey(None,0x5448,0x4000|0x2|0x1,0x20)
            self.hotkey_status='Ctrl+Alt+Space' if registered else 'Ctrl+Alt+Space is used by another app. Use HUD or tray Pause.'
            if not registered:return
            try:
                message=wintypes.MSG()
                while not stop.wait(.025):
                    while api.PeekMessageW(ctypes.byref(message),None,0,0,1):
                        if message.message==0x0312:self.callback('toggle')
            finally:api.UnregisterHotKey(None,0x5448)
        self.hotkey_thread=threading.Thread(target=run,daemon=True,name='AirControl pause hotkey');self.hotkey_thread.start()
    def update(self,state):
        if not state.get('owns_input'):return
        if time.monotonic()-self.last<.08:return
        self.last=time.monotonic()
        if self.process is None or self.process.poll() is not None:
            try:self._start()
            except OSError:self.hotkey_status='HUD unavailable. Use the desktop or tray to stop.';return
        value={k:state.get(k) for k in ('state','message','gesture_label','progress','point','display')}
        value.update(mode=state.get('profile',{}).get('mode'),dwell_action=state.get('dwell_action'),dragging=state.get('dragging',False),head_scroll=state.get('head_scroll',False))
        if state.get('display'):value['layout']=layout(state['display'],active=state.get('state')=='active',head=value['mode']=='head',dragging=value['dragging'],scrolling=value['head_scroll'])
        try:self.pending.put_nowait(value)
        except queue.Full:
            try:self.pending.get_nowait()
            except queue.Empty:pass
            try:self.pending.put_nowait(value)
            except queue.Full:pass
    def dwell(self,x,y,display):
        if not display:return
        for target in regions(display):
            left,top,right,bottom=target['rect']
            if left<=x<=right and top<=y<=bottom:self.callback(target['action']);return
    def hide(self):self.close()
    def close(self):
        if self.hotkey:self.hotkey.set();self.hotkey=None
        if self.hotkey_thread:self.hotkey_thread.join(timeout=.15);self.hotkey_thread=None
        process,self.process=self.process,None
        if process:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=.3)
            except subprocess.TimeoutExpired:process.kill()
            for stream in (process.stdin,process.stdout):
                if stream:
                    try:stream.close()
                    except OSError:pass
