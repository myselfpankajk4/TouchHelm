"""Explicit, cancellable installation into a private runtime; never opens cameras."""
import hashlib
import json
import os
import platform
import re
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
REQUIREMENTS=ROOT/'requirements-aircontrol.txt'
MODELS=ROOT/'assets'/'aircontrol'

def checked_model(path,digest):
    try:return hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    except OSError:return False

class AirControlSetup:
    def __init__(self,folder):
        self.folder=Path(folder);self._resolve_paths()
        self.lock=threading.RLock();self.thread=None;self.process=None
        self.cancelled=threading.Event()
        ready=self._ready()
        self.state={'state':'ready' if ready else 'setup_required','ready':ready,'progress':100 if ready else None,
            'message':'AirControl is ready. Select a camera and start practice.' if ready else 'Set up the isolated camera runtime. First-time setup may take a few minutes; phone controls keep working.'}

    def _resolve_paths(self):
        # Store Python redirects LocalAppData. Its venv launcher is a native
        # executable, so it must receive the real directory, not the virtual alias.
        self.folder=self.folder.resolve()
        self.python=self.folder/'runtime'/'Scripts'/'python.exe'
        self.models=self.folder/'models'

    def _signature(self):
        try:return hashlib.sha256(REQUIREMENTS.read_bytes()+(MODELS/'manifest.json').read_bytes()).hexdigest()
        except OSError:return ''

    def _ready(self):
        try:
            if not self.python.is_file() or (self.folder/'ready').read_text()!=self._signature():return False
            return all(checked_model(self.models/name,item['sha256']) for name,item in json.loads((MODELS/'manifest.json').read_text()).items())
        except (OSError,ValueError):return False

    def snapshot(self):
        with self.lock:return dict(self.state)

    def _set(self,state,message,progress=None):
        with self.lock:self.state={'state':state,'ready':state=='ready','message':message,'progress':progress}

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            self.cancelled.clear();self._set('installing','Preparing an isolated camera runtime…')
            self.thread=threading.Thread(target=self._install,daemon=True,name='TouchHelm AirControl setup');self.thread.start()
        return self.snapshot()

    def cancel(self):
        with self.lock:
            if self.state['ready']:return
        self.cancelled.set()
        process=self.process
        if process and process.poll() is None:
            try:process.terminate()
            except OSError:pass
        self._set('cancelled','Setup cancelled. Choose Set up AirControl to retry.')

    def _run(self,args,timeout,*,stage='AirControl setup'):
        if self.cancelled.is_set():raise InterruptedError()
        self.process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),cwd=str(ROOT),
            env=dict(os.environ,PYTHONUTF8='1',PIP_DISABLE_PIP_VERSION_CHECK='1'))
        process=self.process
        started=time.monotonic()
        # Drain bounded chunks concurrently so pip cannot block on a full pipe.
        output=bytearray()
        def drain():
            for chunk in iter(lambda:process.stdout.read(1024),b''):
                output.extend(chunk)
                if len(output)>8192:del output[:-8192]
        reader=threading.Thread(target=drain,daemon=True);reader.start()
        try:
            while process.poll() is None:
                if self.cancelled.wait(.1) or time.monotonic()-started>timeout:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                    raise InterruptedError() if self.cancelled.is_set() else TimeoutError(stage+' timed out. Check internet access and retry.')
            reader.join(timeout=1)
            if self.cancelled.is_set():raise InterruptedError()
            if process.returncode:
                diagnostic=output.decode('utf-8',errors='replace')
                diagnostic=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',diagnostic)
                diagnostic=re.sub(r'https?://\S+','[package source]',diagnostic)
                lines=[line.strip() for line in diagnostic.splitlines() if line.strip()]
                errors=[line for line in lines if any(word in line.lower() for word in ('error','failed','exception','no module','permission','space','pyvenv.cfg'))]
                reason=(errors or lines or ['No installer details were returned. Check internet access and retry.'])[-1]
                raise RuntimeError(f'{stage} failed (exit {process.returncode}). {reason[:240]}')
        finally:
            reader.join(timeout=1)
            if not reader.is_alive():process.stdout.close()
            if self.process is process:self.process=None

    def _install(self):
        try:
            if os.name!='nt' or sys.version_info[:2]!=(3,13) or platform.machine().lower() not in ('amd64','x86_64'):
                raise RuntimeError('AirControl currently requires Windows x64 and Python 3.13. Phone controls remain available in the existing environment.')
            from server.secure_pairing import protect_user_path
            self.folder.mkdir(parents=True,exist_ok=True)
            # Resolve again after creation: a fresh Store-Python directory may
            # only acquire its physical LocalCache location once it exists.
            self._resolve_paths();protect_user_path(self.folder)
            (self.folder/'ready').unlink(missing_ok=True)
            self._run([sys.executable,'-m','venv',str(self.folder/'runtime')],180,stage='Creating the camera runtime')
            self._set('installing','Installing checksum-locked camera packages. Download progress is indeterminate…')
            self._run([str(self.python),'-m','pip','install','--only-binary=:all:','--require-hashes','-r',str(REQUIREMENTS)],900,stage='Installing camera packages')
            self._set('installing','Verifying bundled hand and face models…')
            self.models.mkdir(exist_ok=True)
            manifest=json.loads((MODELS/'manifest.json').read_text(encoding='utf-8'))
            for name,item in manifest.items():
                if self.cancelled.is_set():raise InterruptedError()
                if Path(name).name!=name or not checked_model(MODELS/name,item['sha256']):raise RuntimeError('A bundled model failed its integrity check. Restore the official application files and retry.')
                shutil.copyfile(MODELS/name,self.models/name)
                if not checked_model(self.models/name,item['sha256']):raise RuntimeError('Model verification failed')
            self._set('installing','Checking the installed camera runtime without opening a camera…')
            self._run([str(self.python),str(Path(__file__).with_name('worker.py')),'--check','--models',str(self.models)],60,stage='Checking camera models')
            if self.cancelled.is_set():raise InterruptedError()
            (self.folder/'ready').write_text(self._signature())
            self._set('ready','AirControl is ready. Choose Start camera for calibration and practice.',100)
        except InterruptedError:self._set('cancelled','Setup cancelled. Retry when ready.')
        except Exception as error:self._set('unavailable',str(error)[:350])
        finally:self.process=None
