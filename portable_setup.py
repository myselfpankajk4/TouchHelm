"""Automatic, cancellable preparation for the compact Windows distribution.

Only public, hash-locked wheels/models and Microsoft's signed WebView2 installer
are downloaded. No camera is opened and no input is injected by setup.
"""
import argparse
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import uuid


class SetupCancelled(Exception):
    pass


def component_directory(root, data):
    return ComponentSetup(root, data).component


class ComponentSetup:
    def __init__(self, root, data, *, progress_file=None, cancel_file=None, protector=None):
        self.root=Path(root).absolute(); self.data=Path(data).absolute()
        self.manifest=json.loads((self.root/'compact.json').read_text(encoding='utf-8'))
        if self.manifest.get('schema') != 1: raise ValueError('Unsupported compact setup manifest')
        self.remote_lock=self.root/'app/requirements-remote-portable.txt'
        self.camera_lock=self.root/'app/requirements-aircontrol.txt'
        self.model_manifest=self.root/'app/assets/aircontrol/manifest.json'
        signature=b'compact-v1:'+self.manifest.get('python','3.13.14').encode()
        for path in (self.remote_lock,self.camera_lock,self.model_manifest):signature+=path.read_bytes()
        self.identity=hashlib.sha256(signature).hexdigest()[:16]
        self.component=self.data/'components'/self.identity
        self.progress_file=Path(progress_file) if progress_file else None
        self.cancel_file=Path(cancel_file) if cancel_file else None
        self.protector=protector
        self.logfile=self.component/'setup.log'

    def check_cancel(self):
        if self.cancel_file and self.cancel_file.exists():raise SetupCancelled()

    def status(self,message,*,error=False):
        if self.progress_file:
            self.progress_file.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.progress_file.with_suffix('.tmp')
            temporary.write_text(json.dumps({'message':message,'error':error}),encoding='utf-8')
            temporary.replace(self.progress_file)

    @contextmanager
    def locked(self):
        import msvcrt
        self.component.mkdir(parents=True,exist_ok=True)
        if self.protector is None:
            from server.secure_pairing import protect_user_path
            protect_user_path(self.data/'components')
        else:self.protector(self.component)
        with (self.component/'setup.lock').open('a+b') as lock:
            lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
            deadline=time.monotonic()+900
            while True:
                self.check_cancel()
                try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('Another TouchHelm setup is still running. Close it and retry.')
                    self.status('Waiting for another TouchHelm setup…');time.sleep(.2)
            try:yield
            finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

    def command(self,args,timeout=900):
        self.check_cancel();self.component.mkdir(parents=True,exist_ok=True)
        with self.logfile.open('ab') as output:
            output.seek(0,2);started_at=output.tell()
            process=subprocess.Popen([str(arg) for arg in args],cwd=self.root/'app',
                stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
                env=dict(os.environ,PYTHONUTF8='1',PIP_DISABLE_PIP_VERSION_CHECK='1'))
            deadline=time.monotonic()+timeout
            try:
                while process.poll() is None:
                    self.check_cancel()
                    if time.monotonic()>deadline:raise RuntimeError('Preparation timed out. Check your internet connection and retry.')
                    time.sleep(.2)
                if process.returncode:
                    with self.logfile.open('rb') as log:
                        log.seek(max(started_at,log.seek(0,2)-3000));tail=log.read().decode('utf-8',errors='replace')
                    lines=[line.strip() for line in tail.splitlines() if line.strip()]
                    if any(word in tail.lower() for word in ('nameresolutionerror','failed to resolve','connection broken','connection timed out','read timed out')):
                        raise RuntimeError('Could not reach the component download server. Check your internet connection and reopen TouchHelm to retry.')
                    reason=re.sub(r'https?://\S+','[download source]',(lines or ['No diagnostic returned'])[-1])
                    raise RuntimeError(f'Preparation failed ({process.returncode}). {reason[:260]}')
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

    def download(self,url,target,digest=None,size=None,*,maximum=None):
        self.check_cancel()
        if not url.startswith('https://'):raise ValueError('Downloads must use HTTPS')
        target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+'.partial-'+uuid.uuid4().hex)
        limit=size if size is not None else maximum
        try:
            hasher=hashlib.sha256();received=0
            request=urllib.request.Request(url,headers={'User-Agent':'TouchHelm-Compact-Setup/1'})
            with urllib.request.urlopen(request,timeout=30) as response,temporary.open('xb') as output:
                while True:
                    self.check_cancel();chunk=response.read(256*1024)
                    if not chunk:break
                    received+=len(chunk)
                    if limit is not None and received>limit:raise RuntimeError('Downloaded file failed its integrity size limit')
                    hasher.update(chunk);output.write(chunk)
            if (size is not None and received!=size) or (digest and hasher.hexdigest()!=digest):
                raise RuntimeError('Downloaded file failed its integrity check')
            temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)

    def install_packages(self,target,requirements):
        self.command([self.root/'runtime/python.exe','-m','pip','--isolated','install',
            '--require-hashes','--only-binary=:all:','--no-input','--no-compile',
            '--disable-pip-version-check','--progress-bar','off','--retries','2','--timeout','30',
            '--resume-retries','0',
            '--cache-dir',self.data/'downloads/pip','--target',target,'-r',requirements])

    def seed_camera(self,target):
        target=Path(target);target.mkdir(parents=True,exist_ok=True)
        for name in self.manifest['seed_files']:
            if not isinstance(name,str) or name in ('','.','..') or Path(name).name!=name or '/' in name or '\\' in name or ':' in name:
                raise ValueError('Invalid camera seed file')
            shutil.copy2(self.root/'runtime'/name,target/name)
        self.camera_path(target)

    def camera_path(self,target):
        (Path(target)/'python313._pth').write_text('python313.zip\n.\nLib\nLib/site-packages\n'+str(self.root/'app')+'\nimport site\n',encoding='utf-8')

    def models_ready(self):
        models=json.loads(self.model_manifest.read_text())
        for name,item in models.items():
            if Path(name).name!=name or '/' in name or '\\' in name:return False
            path=self.component/'models'/name
            if not path.is_file() or path.stat().st_size!=item['bytes']:return False
            with path.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:return False
        return bool(models)

    def ensure_models(self):
        if self.models_ready():
            shutil.copy2(self.model_manifest,self.component/'models/manifest.json');return
        self.status('Preparing local camera models…')
        models=json.loads(self.model_manifest.read_text())
        for name,item in models.items():
            if Path(name).name!=name or '/' in name or '\\' in name:raise ValueError('Invalid camera model name')
            if urllib.parse.urlsplit(item['url']).hostname!='storage.googleapis.com':raise ValueError('Unexpected model download source')
            self.download(item['url'],self.component/'models'/name,item['sha256'],item['bytes'])
        shutil.copy2(self.model_manifest,self.component/'models/manifest.json')

    def feature_ready(self,name):
        folder=self.component/name; marker=folder/'ready'
        if not marker.is_file() or marker.read_text()!=self.identity:return False
        files={'remote':('site/aiortc/__init__.py','site/av/__init__.py','site/dxcam/__init__.py','site/cv2/__init__.py',
                         'site/pyaudiowpatch/__init__.py','site/numpy/__init__.py'),
               'camera':('python.exe','Lib/site-packages/mediapipe/__init__.py','Lib/site-packages/cv2/__init__.py')}
        if not all((folder/path).is_file() for path in files[name]):return False
        try:
            native=json.loads((folder/'.native-files.json').read_text())
            if not isinstance(native,dict) or not native:return False
            for relative,size in native.items():
                path=Path(relative)
                if path.is_absolute() or '..' in path.parts or ':' in relative or '\\' in relative:return False
                item=folder/path
                if type(size) is not int or not item.is_file() or item.stat().st_size!=size:return False
            return True
        except (OSError,ValueError,TypeError):return False

    def publish(self,staging,name):
        native={path.relative_to(staging).as_posix():path.stat().st_size for path in staging.rglob('*')
                if path.is_file() and path.suffix.lower() in ('.exe','.dll','.pyd','.zip')}
        if not native:raise RuntimeError('Prepared component contains no native runtime files')
        (staging/'.native-files.json').write_text(json.dumps(native))
        target=self.component/name
        if target.exists():target.rename(self.component/(name+'.previous-'+uuid.uuid4().hex))
        staging.rename(target)
        (target/'ready').write_text(self.identity)

    def ensure_remote(self):
        if self.feature_ready('remote'):return
        self.status('Preparing screen and audio controls…')
        staging=self.component/('.remote-'+uuid.uuid4().hex);staging.mkdir()
        try:
            self.install_packages(staging/'site',self.remote_lock)
            probe='import sys;sys.path.insert(0,sys.argv[1]);import aiortc,av,dxcam,pyaudiowpatch,cv2'
            self.command([self.root/'runtime/python.exe','-c',probe,staging/'site'],120)
            self.publish(staging,'remote')
        finally:self.remove_staging(staging)

    def ensure_camera(self):
        if self.feature_ready('camera'):
            self.camera_path(self.component/'camera');return
        self.status('Preparing hands-free camera controls…')
        staging=self.component/('.camera-'+uuid.uuid4().hex)
        try:
            self.seed_camera(staging)
            self.install_packages(staging/'Lib/site-packages',self.camera_lock)
            self.command([staging/'python.exe',self.root/'app/server/aircontrol/worker.py',
                          '--check','--models',self.component/'models'],120)
            self.publish(staging,'camera')
        finally:self.remove_staging(staging)

    def remove_staging(self,path):
        # Remove only our generated immediate child, after checking both logical
        # and resolved physical parents; never recursively remove a computed base.
        path=Path(path).absolute()
        if path.parent!=self.component or not re.fullmatch(r'\.(remote|camera)-[0-9a-f]{32}',path.name):
            raise ValueError('Unexpected setup staging path')
        if path.exists():
            if path.resolve().parent!=self.component.resolve():raise ValueError('Redirected setup staging path')
            shutil.rmtree(path)

    def webview_available(self):
        loader=self.root/'runtime/Lib/site-packages/webview/lib/runtimes/win-x64/native/WebView2Loader.dll'
        if os.name!='nt' or not loader.is_file():return False
        try:
            library=ctypes.WinDLL(str(loader));version=ctypes.c_void_p()
            query=library.GetAvailableCoreWebView2BrowserVersionString
            query.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_void_p)];query.restype=ctypes.c_long
            result=query(None,ctypes.byref(version))
            try:return result==0 and bool(version.value) and bool(ctypes.wstring_at(version))
            finally:
                if version.value:
                    free=ctypes.windll.ole32.CoTaskMemFree;free.argtypes=[ctypes.c_void_p];free(version)
        except OSError:return False

    def verify_microsoft(self,path):
        shell=Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        quoted=str(path).replace("'","''")
        script="Import-Module ($PSHOME+'\\Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1'); $ErrorActionPreference='Stop'; "+\
            "$s=Get-AuthenticodeSignature -LiteralPath '"+quoted+"'; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)'){exit 1}"
        try:self.command([shell,'-NoProfile','-NonInteractive','-Command',script],60)
        except SetupCancelled:raise
        except RuntimeError as error:
            raise RuntimeError('Microsoft browser setup signature could not be verified. Check Windows date/time and security updates, then retry.') from error

    def ensure_webview(self):
        if self.webview_available():return
        self.status('Preparing the desktop browser runtime…')
        installer=self.component/'MicrosoftEdgeWebview2Setup.exe'
        self.download('https://go.microsoft.com/fwlink/p/?LinkId=2124703',installer,maximum=8*1024*1024)
        self.verify_microsoft(installer)
        self.command([installer,'/silent','/install'],600)
        if not self.webview_available():raise RuntimeError('Windows could not finish browser setup. Check internet access and Windows security notifications, then retry.')

    def ensure(self):
        self.check_cancel()
        with self.locked():
            for path in self.component.iterdir():
                if re.fullmatch(r'\.(remote|camera)-[0-9a-f]{32}',path.name):self.remove_staging(path)
            self.ensure_webview();self.ensure_models();self.ensure_remote();self.ensure_camera()
            (self.component/'ready').write_text(self.identity)
            self.status('TouchHelm is ready.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--progress',required=True)
    parser.add_argument('--cancel',required=True)
    args=parser.parse_args()
    root=Path(__file__).absolute().parent.parent
    data=Path(os.environ['LOCALAPPDATA'])/'TouchHelm'
    os.environ.pop('WEBVIEW2_BROWSER_EXECUTABLE_FOLDER',None)
    setup=ComponentSetup(root,data,progress_file=args.progress,cancel_file=args.cancel)
    try:setup.ensure();return 0
    except SetupCancelled:setup.status('Setup cancelled. Open TouchHelm again to continue.');return 2
    except Exception as error:
        reason=re.sub(r'https?://\S+','[download source]',str(error))
        setup.status('TouchHelm could not finish preparation. '+reason[:320],error=True)
        return 1


if __name__=='__main__':raise SystemExit(main())
