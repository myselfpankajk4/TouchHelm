"""Owned desktop onboarding for private HTTPS; no CA installation on a phone."""
import os
import shutil
import subprocess
import threading
import sys
from pathlib import Path
from .tailscale_pairing import find_tailscale
from .config import random_password

class TrustedPairingSetup:
    def __init__(self,app,*,find_cli=find_tailscale,find_winget=lambda:shutil.which('winget'),run=subprocess.run):
        self.app,self.find_cli,self.find_winget,self.run=app,find_cli,find_winget,run
        self.lock=threading.RLock();self.thread=None
        self.state={'state':'idle','message':'Recommended: private HTTPS without downloading a phone certificate. Tailscale sign-in is required on both devices.'}

    def snapshot(self):
        with self.lock:return dict(self.state)

    def _set(self,state,message):
        with self.lock:self.state={'state':state,'message':message}

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            self._set('checking','Checking trusted pairing requirements…')
            self.thread=threading.Thread(target=self._prepare,daemon=True,name='TouchHelm trusted pairing');self.thread.start()

    def _prepare(self):
        try:
            if not self.find_cli():
                winget=self.find_winget()
                if not winget:raise RuntimeError('Windows App Installer is unavailable. Use the official Windows download below, then choose Set up trusted pairing again.')
                self._set('installing','Installing Tailscale on this PC. Approve Windows administrator access if requested; this may take a few minutes.')
                result=self.run([winget,'install','--id','Tailscale.Tailscale','--exact','--source','winget','--accept-package-agreements','--accept-source-agreements','--disable-interactivity'],capture_output=True,text=True,timeout=600,creationflags=0x08000000 if os.name=='nt' else 0)
                if result.returncode or not self.find_cli():raise RuntimeError('Tailscale installation did not complete. Check Windows approval and internet access, or use the official Windows download below.')
            status=self.app.server.tailscale.inspect(force=True)
            if status['state']=='login_required':
                self._set('login_required','Tailscale is installed. Sign in from its Windows tray icon; install/sign in on your phone using the same account. Then choose Set up trusted pairing again.')
                return
            if status['state'] not in ('ready','setup_required'):raise RuntimeError(status['message'])
            from .remote_media import capabilities
            caps=capabilities()
            if not caps.get('video') or not caps.get('audio'):
                from .portable import bundle_root
                if bundle_root() is not None:
                    raise RuntimeError('The bundled screen/audio providers are unavailable. Download a fresh TouchHelm test EXE and retry.')
                self._set('installing','Installing the PC screen/audio providers. First-time setup may take a few minutes…')
                result=self.run([sys.executable,'-m','pip','install','-r',str(Path(__file__).resolve().parents[1]/'requirements-remote.txt')],capture_output=True,text=True,timeout=600,creationflags=0x08000000 if os.name=='nt' else 0)
                import importlib
                importlib.invalidate_caches()
                if result.returncode or not all(capabilities().get(k) for k in ('video','audio')):raise RuntimeError('Screen/audio providers could not be installed. Check internet access and the host Python installation, then retry.')
            self._set('configuring','Preparing your private HTTPS address and PIN…')
            with self.app._settings_lock:
                if not self.app.config.get('require_pin'):
                    self.app.config.update({'require_pin':True,'pin_code':random_password()})
                    self.app._submit(self.app.server.invalidate_auth_sessions())
            self.app._submit(self.app.server.enable_tailscale())
            status=self.app.server.tailscale.inspect(force=True)
            if not status.get('ready'):raise RuntimeError(status['message'])
            self.app.config.set('remote_enabled',True)
            self.app._submit(self.app.server.remote_settings_changed())
            self.app._save_preferences({**self.app._preferences(),'connection_mode':'tailscale'})
            self._set('ready','Private trusted HTTPS is ready. Connect Tailscale on the phone, scan the QR and enter the four-digit PIN. No certificate download is needed.')
        except Exception as error:self._set('unavailable',str(error)[:500])
