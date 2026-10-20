"""Build a single offline Windows x64 test EXE. Run with CPython 3.13 x64.

Downloads are official redistributables; pip packages remain in separate runtimes.
The build cache/dist directories are ignored by Git. Never copies a dev venv.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'build/portable-cache'
STAGE = ROOT/'build/portable-stage'
DIST = ROOT/'dist'
PYTHON_VERSION = '3.13.14'
WEBVIEW_VERSION = '155.0.4283.62'
SOURCES = {
    f'python-{PYTHON_VERSION}-embed-amd64.zip': f'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip',
    f'webview2-{WEBVIEW_VERSION}-x64.cab': 'https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/232cf50b-3980-4531-afbb-779f446d7de1/Microsoft.WebView2.FixedVersionRuntime.155.0.4283.62.x64.cab',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def copytree(source, target):
    shutil.copytree(source, target, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store', 'review'))


def download():
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = CACHE/name
        if not target.is_file():
            partial = target.with_suffix('.download')
            print('Downloading', name, flush=True)
            urllib.request.urlretrieve(url, partial)
            partial.replace(target)


def runtime(name, requirements, *, hashes=False):
    folder = STAGE/name
    folder.mkdir(parents=True, exist_ok=True)
    signature = hashlib.sha256(b''.join((ROOT/r).read_bytes() for r in requirements)).hexdigest()
    marker = folder/'.dependencies-ready'
    if marker.is_file() and marker.read_text() == signature: return
    with zipfile.ZipFile(CACHE/f'python-{PYTHON_VERSION}-embed-amd64.zip') as archive:
        archive.extractall(folder)
    site = folder/'Lib/site-packages'
    args = [sys.executable, '-m', 'pip', 'install', '--upgrade', '--only-binary=:all:',
            '--no-compile', '--target', site]
    # proxy_tools is a tiny pure-Python dependency published only as an sdist.
    # Keep native packages wheel-only; this exception builds on the build host.
    if not hashes: args.append('--no-binary=proxy_tools')
    if hashes: args.append('--require-hashes')
    for req in requirements: args.extend(['-r', ROOT/req])
    run(args)
    (folder/'python313._pth').write_text('python313.zip\n.\nLib\nLib/site-packages\n../app\nimport site\n')
    marker.write_text(signature)


def prepare():
    download()
    runtime('runtime', ['requirements.txt', 'requirements-remote.txt'])
    runtime('camera', ['requirements-aircontrol.txt'], hashes=True)
    # The embeddable ZIP omits Tk. Redistribute the matching official CPython
    # installation's Tk modules and DLLs for the existing classic fallback.
    base = Path(sys.base_prefix)
    if sys.version_info[:3] != (3, 13, 14):
        raise RuntimeError('Build with official CPython 3.13.14 x64 to match Tk and the embedded ABI.')
    copytree(base/'Lib/tkinter', STAGE/'runtime/Lib/tkinter')
    copytree(base/'tcl', STAGE/'runtime/tcl')
    for name in ('_tkinter.pyd', 'tcl86t.dll', 'tk86t.dll', 'zlib1.dll'):
        shutil.copy2(base/'DLLs'/name, STAGE/'runtime'/name)
    webview = STAGE/'webview2'
    if not (webview/'msedgewebview2.exe').is_file():
        expanded = CACHE/'webview-expanded'; expanded.mkdir(exist_ok=True)
        run(['expand.exe', CACHE/f'webview2-{WEBVIEW_VERSION}-x64.cab', '-F:*', expanded])
        found = list(expanded.rglob('msedgewebview2.exe'))
        if len(found) != 1: raise RuntimeError('Unexpected Fixed Version WebView2 layout')
        copytree(found[0].parent, webview)
    # Record Authenticode status of the official native entrypoints.
    script = "Import-Module ($PSHOME+'\\Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1'); $ErrorActionPreference='Stop'; $paths = @(" + ','.join("'"+str(p).replace("'", "''")+"'" for p in (
        STAGE/'runtime/python.exe', STAGE/'webview2/msedgewebview2.exe')) + "); " + \
        "$paths | ForEach-Object { $s = Get-AuthenticodeSignature -LiteralPath $_; " + \
        "if ($s.Status -ne 'Valid') { throw ('Invalid vendor signature: ' + $_ + ' ' + $s.Status) }; " + \
        "[pscustomobject]@{File=[IO.Path]::GetFileName($_);Status=[string]$s.Status;Publisher=$s.SignerCertificate.Subject} } | ConvertTo-Json"
    result = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', script], text=True)
    (CACHE/'vendor-signatures.json').write_text(result)


def app_files():
    app = STAGE/'app'; app.mkdir(parents=True, exist_ok=True)
    # Explicit allowlist: no config, .env, histories, private keys, tests, tooling.
    for name in ('server', 'gui', 'web', 'assets'):
        copytree(ROOT/name, app/name)
    for name in ('main.py', 'portable_bootstrap.py', 'requirements.txt',
                 'requirements-remote.txt', 'requirements-aircontrol.txt'):
        shutil.copy2(ROOT/name, app/name)
    for name in ('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'NOTICE'):
        if (ROOT/name).is_file(): shutil.copy2(ROOT/name, app/name)
    shutil.copy2(ROOT/'docs/PORTABLE_TESTING.md', app/'PORTABLE_TESTING.md')
    # Machine-readable dependency inventories accompany all wheel license files.
    inventory = {}
    for name in ('runtime', 'camera'):
        script = 'import importlib.metadata,json;print(json.dumps(sorted([(d.metadata["Name"],d.version) for d in importlib.metadata.distributions()]),indent=2))'
        inventory[name] = json.loads(subprocess.check_output([str(STAGE/name/'python.exe'), '-c', script], text=True))
    (STAGE/'dependencies.json').write_text(json.dumps(inventory, indent=2))
    (STAGE/'vendor-signatures.json').write_bytes((CACHE/'vendor-signatures.json').read_bytes())
    inputs = {name: {'url': url, 'sha256': sha(CACHE/name)} for name, url in SOURCES.items()}
    (STAGE/'redistributables.json').write_text(json.dumps(inputs, indent=2))


def build():
    app_files()
    DIST.mkdir(exist_ok=True)
    payload = CACHE/'payload.zip'
    files = sorted(p for p in STAGE.rglob('*') if p.is_file() and
        '__pycache__' not in p.parts and p.suffix != '.pyc' and p.name != '.dependencies-ready')
    forbidden = {'config.json', '.env', 'instance.json', 'desktop.log'}
    public_ca = {STAGE/name/'Lib/site-packages/certifi/cacert.pem' for name in ('runtime', 'camera')}
    if any(p.name in forbidden or (p.suffix.lower() in ('.key', '.pem', '.pfx', '.p12') and p not in public_ca) for p in files):
        raise RuntimeError('Private/unexpected file in portable stage')
    print('Compressing', len(files), 'files;', sum(p.stat().st_size for p in files), 'unpacked bytes', flush=True)
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in files: archive.write(path, path.relative_to(STAGE).as_posix())
    digest, length = sha(payload), payload.stat().st_size
    source = (ROOT/'packaging/PortableLauncher.cs').read_text().replace('@@PAYLOAD_HASH@@', digest).replace('@@PAYLOAD_LENGTH@@', str(length))
    compiled = CACHE/'PortableLauncher.generated.cs'; compiled.write_text(source)
    exe = DIST/'TouchHelm-2.2.0-test-win-x64.exe'
    compiler = Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    run([compiler, '/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/out:'+str(exe),
        '/win32icon:'+str(ROOT/'assets/touchhelm.ico'), '/win32manifest:'+str(ROOT/'packaging/portable.manifest'),
        '/r:System.IO.Compression.dll', '/r:System.IO.Compression.FileSystem.dll',
        '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', compiled])
    with exe.open('ab') as output, payload.open('rb') as data: shutil.copyfileobj(data, output, 1024*1024)
    (DIST/'SHA256SUMS.txt').write_text(sha(exe)+'  '+exe.name+'\n')
    manifest = {'file': exe.name, 'bytes': exe.stat().st_size, 'sha256': sha(exe),
                'payload_sha256': digest, 'payload_bytes': length, 'unpacked_bytes': sum(p.stat().st_size for p in files),
                'python': PYTHON_VERSION, 'webview2': WEBVIEW_VERSION, 'signed': False,
                'target': 'Windows 10/11 x64', 'dependencies': json.loads((STAGE/'dependencies.json').read_text())}
    (DIST/'build-manifest.json').write_text(json.dumps(manifest, indent=2))
    shutil.copy2(ROOT/'docs/PORTABLE_TESTING.md', DIST/'PORTABLE_TESTING.md')
    print(json.dumps({k:v for k,v in manifest.items() if k!='dependencies'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--reuse-runtimes', action='store_true', help='Rebuild app/EXE using already verified runtime stage')
    args = parser.parse_args()
    if not args.reuse_runtimes: prepare()
    if not args.prepare_only: build()
