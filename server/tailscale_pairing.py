"""Private Serve endpoint ownership. No installer, login, Funnel or reset commands."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

BACKEND = 'http://127.0.0.1:8767'
HTTPS_PORT = 8443
HELP_URLS = {'windows':'https://tailscale.com/download/windows',
             'android':'https://tailscale.com/download/android',
             'login':'https://tailscale.com/docs/how-to/quickstart'}


def find_tailscale():
    installed = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))/'Tailscale'/'tailscale.exe'
    return str(installed) if installed.is_file() else shutil.which('tailscale')


class TailscalePairingManager:
    def __init__(self, config, *, run=subprocess.run, find_cli=find_tailscale):
        self.config, self.run, self.find_cli = config, run, find_cli
        self._lock = threading.RLock()
        self._cached, self._checked = None, 0

    def _call(self, *args):
        executable = self.find_cli()
        if not executable: raise FileNotFoundError('Install Tailscale on this PC first.')
        result = self.run([executable,*args], capture_output=True, text=True, timeout=4,
                          creationflags=0x08000000 if os.name == 'nt' else 0)
        if result.returncode:
            detail = (result.stderr or result.stdout or 'Tailscale command failed.').strip()[:500]
            if any(word in detail.lower() for word in ('denied','permission','access')): raise PermissionError(detail)
            raise RuntimeError(detail)
        return result.stdout

    def _read(self):
        status = json.loads(self._call('status','--json'))
        if status.get('BackendState') != 'Running':
            return {'state':'login_required','ready':False,'url':None,'message':'Open Tailscale on this PC and sign in. Connect your phone to the same tailnet.'}, None
        host = status.get('Self',{}).get('DNSName','').rstrip('.').lower()
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.ts\.net',host):
            raise RuntimeError('A Tailscale DNS name is unavailable. Check MagicDNS and HTTPS in your tailnet settings.')
        serve = json.loads(self._call('serve','status','--json')) or {}
        if not isinstance(serve,dict): raise ValueError('Invalid Serve configuration')
        endpoint = f'{host}:{HTTPS_PORT}'
        web = serve.get('Web',{}) or {}; tcp = serve.get('TCP',{}) or {}
        funnel = (serve.get('AllowFunnel',{}) or {}).get(endpoint,False)
        handlers = (web.get(endpoint,{}) or {}).get('Handlers',{})
        exact = (handlers == {'/':{'Proxy':BACKEND}} and tcp.get(str(HTTPS_PORT)) == {'HTTPS':True}
                 and not any(key.endswith(f':{HTTPS_PORT}') and key != endpoint for key in web))
        occupied = str(HTTPS_PORT) in tcp or any(key.endswith(f':{HTTPS_PORT}') for key in web)
        owned = self.config.get('tailscale_owned_host','') == host
        state = 'conflict' if funnel or (occupied and not (exact and owned)) else 'ready' if exact and owned else 'setup_required'
        message = {'conflict':'Port 8443 is used by an unrelated or public service. Resolve it in Tailscale before enabling TouchHelm.',
                   'ready':'Private HTTPS is ready. Connect the phone to the same tailnet, scan, and enter the host PIN.',
                   'setup_required':'Tailscale is connected. Enable private HTTPS to create this PC’s phone address.'}[state]
        return {'state':state,'ready':state=='ready','url':f'https://{endpoint}/' if state=='ready' else None,
                'host':host,'message':message}, serve

    def inspect(self, force=False):
        with self._lock:
            if not force and self._cached is not None and time.monotonic()-self._checked < 10: return dict(self._cached)
            try: result,_ = self._read()
            except FileNotFoundError: result = {'state':'not_installed','ready':False,'url':None,'message':'Install Tailscale on Windows and Android, then sign in to the same tailnet.'}
            except Exception as error:
                result = {'state':'permission_required' if isinstance(error,PermissionError) else 'unavailable',
                          'ready':False,'url':None,'message':str(error)[:500] or 'Tailscale is unavailable. Reconnect and refresh.'}
            self._cached, self._checked = result, time.monotonic()
            return dict(result)

    def enable(self):
        with self._lock:
            if not self.config.get('require_pin') or not self.config._valid_pin(self.config.get('pin_code')):
                raise RuntimeError('Enable a four-digit host PIN before private HTTPS.')
            status = self.inspect(force=True)
            if status['state'] not in ('ready','setup_required'): raise RuntimeError(status['message'])
            if status['state'] != 'ready':
                # Persist ownership before creating a background endpoint. A
                # later CLI/save failure then remains recoverable from this UI.
                self.config.update({'tailscale_owned_host':status['host'],'tailscale_enabled':False})
                self._call('serve','--bg','--https=8443',BACKEND)
                self.config.set('tailscale_enabled',True)
            else: self.config.set('tailscale_enabled',True)
            result = self.inspect(force=True)
            if not result['ready']: raise RuntimeError(result['message'])
            return result

    def disable(self):
        with self._lock:
            status = self.inspect(force=True)
            if status['state'] == 'ready': self._call('serve','--bg','--https=8443',BACKEND,'off')
            elif status['state'] != 'setup_required': raise RuntimeError(status['message'])
            self.config.update({'tailscale_enabled':False,'tailscale_owned_host':''})
            return self.inspect(force=True)
