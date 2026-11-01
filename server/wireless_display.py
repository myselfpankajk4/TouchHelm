"""Desktop-owned optional-feature setup. Never exposed as a phone HTTP action."""
import json
import os
import re
import subprocess
import threading
import time
import secrets
from pathlib import Path

SCRIPT=Path(__file__).with_name('wireless_display_setup.ps1')
BUSY={'checking','permission','installing'}

def progress_percent(output):
    matches=re.findall(r'(\d{1,3}(?:\.\d+)?)%',output)
    return min(99,int(float(matches[-1]))) if matches else None

def launch_installer(status_path):
    # Paths are application-generated, never supplied by a phone. Use literal PS
    # quoting then quoted Windows argv entries for the elevated helper.
    def quote(value):return "'"+str(value).replace("'","''")+"'"
    args=['-NoProfile','-ExecutionPolicy','Bypass','-File',f'"{SCRIPT}"','-StatusPath',f'"{status_path}"']
    command="Start-Process -FilePath powershell.exe -Verb RunAs -WindowStyle Hidden -PassThru -ArgumentList @("+','.join(quote(v) for v in args)+") | Out-Null"
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,creationflags=0x08000000,timeout=120)
    if result.returncode:raise PermissionError('Windows installation was not approved. Choose Install to retry the administrator prompt.')

class WirelessDisplaySetup:
    def __init__(self,folder,*,launcher=launch_installer):
        self.folder=Path(folder);self.launcher=launcher;self.lock=threading.RLock();self.thread=None
        self.state={'state':'unknown','progress':None,'message':'First-time Wireless Display setup may take a few minutes. Windows administrator approval is required.'}

    def snapshot(self):
        with self.lock:return dict(self.state)

    def _set(self,state,progress,message):
        with self.lock:self.state={'state':state,'progress':progress,'message':message}

    def check(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            self._set('checking',None,'Checking the Windows Wireless Display receiver…')
            self.thread=threading.Thread(target=self._check,daemon=True,name='TouchHelm Wireless Display check');self.thread.start()

    def _check(self):
        try:
            result=subprocess.run(['powershell.exe','-NoProfile','-Command',"$p=Get-AppxPackage -Name Microsoft.WirelessDisplay; if(!$p){$p=Get-AppxPackage -Name Microsoft.PPIProjection}; if($p){'installed'}else{'not_installed'}"],capture_output=True,text=True,creationflags=0x08000000,timeout=30)
            if result.returncode:raise RuntimeError('Windows receiver detection failed. Install checks the actual optional-feature state.')
            installed=result.stdout.strip()=='installed'
            self._set('installed' if installed else 'not_installed',100 if installed else None,'Wireless Display is installed. Open the receiver; your phone and Wi-Fi hardware must support Miracast.' if installed else 'Wireless Display is not registered for this user. Install it here; the first setup may take a few minutes.')
        except Exception as error:self._set('unavailable',None,str(error))

    def install(self):
        with self.lock:
            if self.state['state']=='installed' or self.thread and self.thread.is_alive():return
            self._set('permission',None,'Approve the Windows administrator prompt. First-time installation may take a few minutes.')
            self.thread=threading.Thread(target=self._install,daemon=True,name='TouchHelm Wireless Display setup');self.thread.start()

    def _install(self):
        try:
            self.folder.mkdir(parents=True,exist_ok=True)
            if self.launcher is launch_installer:
                from .private_storage import protect_user_path
                protect_user_path(self.folder)
            path=self.folder/('setup-'+secrets.token_hex(12)+'.json')
            self.launcher(path)
            deadline=time.monotonic()+1800
            while time.monotonic()<deadline:
                if path.exists():
                    try:state=json.loads(path.read_text(encoding='utf-8-sig'))
                    except (OSError,ValueError):state=None
                    if isinstance(state,dict) and state.get('state') in {'checking','installing','installed','restart_required','error'}:
                        self._set(state['state'],state.get('progress'),str(state.get('message',''))[:500])
                        if state['state'] in {'installed','restart_required','error'}:return
                time.sleep(.5)
            self._set('unavailable',None,'Windows setup is taking longer than expected. Check Windows Update and Projecting to this PC before retrying.')
        except PermissionError as error:self._set('permission_required',None,str(error))
        except Exception as error:self._set('error',None,'Wireless Display setup failed: '+str(error)[:300])
