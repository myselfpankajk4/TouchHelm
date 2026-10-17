"""Windows speech requests; no audio capture, transcription or fabricated state."""
import asyncio
import os
from pathlib import Path
import subprocess
import threading
import time
from server.desktop_services import PersistentPowerShellBridge

class VoiceController:
    def __init__(self,input_controller,*,bridge=None,allowed=lambda:False):
        self.input=input_controller;self.allowed=allowed
        self.bridge=bridge or PersistentPowerShellBridge(timeout=2,script_path=Path(__file__).parents[1]/'text_bridge.ps1')
        self.message='Dictate uses Windows Win+H. Voice Access is a separate Windows feature.'
        self.last_target='';self.requested_field='';self.last_request=-10.;self.lock=asyncio.Lock()
    def snapshot(self):return {'message':self.message,'status':'requested' if self.message.startswith('Dictation requested') else 'idle'}
    async def _call(self,command,payload=None):
        cancelled=threading.Event()
        try:return await asyncio.wait_for(asyncio.to_thread(self.bridge.request,command,payload,cancelled=cancelled),22.2)
        except BaseException:
            cancelled.set();raise
    async def remember(self):
        try:
            target=await self._call('target')
            if target.get('available') and target.get('process_id')!=os.getpid():self.last_target=target['field_id']
        except Exception:pass
    async def dictate(self,*,explicit=False):
        async with self.lock:
            try:
                if not explicit and not self.allowed():return
                await asyncio.sleep(.15 if not explicit else 0)
                status=await self._call('speech_status')
                if status.get('voice_access'):
                    self.message='Voice Access is running. Use its text commands; automatic Win+H is suppressed.';return
                if status.get('toolbar_open'):
                    self.message='Windows voice typing is already open.';return
                if status.get('toolbar_unknown') or 'toolbar_open' not in status:
                    self.message='Windows speech toolbar state is unknown. Use Win+H manually to avoid toggling an open toolbar.';return
                target=await self._call('target')
                if not target.get('available') and explicit and self.last_target:
                    target=await self._call('restore_target',{'field_id':self.last_target})
                if not target.get('available') or target.get('process_id')==os.getpid():
                    self.message='Select a supported editable field outside TouchHelm, then use Dictate. Password and read-only fields are excluded.';return
                field=target['field_id'];self.last_target=field
                if not explicit and (field==self.requested_field or time.monotonic()-self.last_request<2):return
                verify=await self._call('target')
                if not verify.get('available') or verify.get('field_id')!=field:
                    self.message='The destination changed. Select the text field again.';return
                if not explicit and not self.allowed():return
                self.input.hotkey('win','h');self.requested_field=field;self.last_request=time.monotonic()
                self.message='Dictation requested. Windows manages microphone permission, internet requirements and listening state.'
            except asyncio.CancelledError:raise
            except Exception:self.message='Windows speech could not be checked. Select your text field and use Win+H, or retry.'
    async def open_voice_access(self):
        executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'/'VoiceAccess.exe'
        if not executable.is_file():raise ValueError('Voice Access requires a supported Windows 11 installation. Use Win+H voice typing instead.')
        await asyncio.to_thread(subprocess.Popen,[str(executable)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.message='Voice Access launch requested. Complete Windows language download and microphone setup; listening is not confirmed.'
    async def close(self):await asyncio.to_thread(self.bridge.close)
