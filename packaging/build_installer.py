"""Build a per-user Windows installer with all Python/features included.

Prepare the verified offline runtime with build_portable.py --prepare-only first.
Only system WebView2 may need Microsoft's automatic bootstrapper on the target.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import build_portable as base
from windows_redist import ensure_openmp

ROOT = base.ROOT
DIST = ROOT/'dist'
VERSION = '2.2.0-test.3'
OUTPUT = 'TouchHelm-2.2.0-test3-setup-win-x64'


def validate_files(stage):
    models = json.loads((stage/'app/assets/aircontrol/manifest.json').read_text())
    for name, item in models.items():
        path = stage/'app/assets/aircontrol'/name
        if Path(name).name != name or not path.is_file() or base.sha(path) != item['sha256']:
            raise RuntimeError('Missing or invalid bundled camera model')
    files = sorted(p for p in stage.rglob('*') if p.is_file())
    for path in files:
        if path.is_symlink() or path.name in ('config.json', '.env', 'instance.json', 'desktop.log'):
            raise RuntimeError('Unexpected private file in installer stage')
        if path.suffix.lower() in ('.key', '.pfx', '.p12'):
            raise RuntimeError('Unexpected key in installer stage')
        if path.suffix.lower() == '.pem' and not path.as_posix().endswith('/certifi/cacert.pem'):
            raise RuntimeError('Unexpected certificate in installer stage')
        if path.suffix.lower() == '.task' and path.parent != stage/'app/assets/aircontrol':
            raise RuntimeError('Unexpected model in installer stage')
    if (stage/'webview2').exists() or (stage/'compact.json').exists():
        raise RuntimeError('Installer must use bundled features with system WebView2')
    if not (stage/'runtime/vcomp140.dll').is_file():
        raise RuntimeError('Screen capture requires the bundled Microsoft OpenMP runtime')
    return files


def stage_runtime(source):
    stage = ROOT/'build'/('installer-stage-'+uuid.uuid4().hex[:8])
    stage.mkdir(parents=True)
    for name in ('runtime', 'camera'):
        if not (source/name/'python.exe').is_file():
            raise RuntimeError('Prepare offline runtime first: packaging/build_portable.py --prepare-only')
        shutil.copytree(source/name, stage/name,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.dependencies-ready'))
    openmp, vendor = ensure_openmp(ROOT/'build/portable-cache')
    shutil.copy2(openmp, stage/'runtime/vcomp140.dll')
    (stage/'redistributables.json').write_text(json.dumps({'openmp': vendor}, indent=2))
    app = stage/'app'
    app.mkdir()
    for name in ('server', 'gui', 'web', 'assets'):
        base.copytree(ROOT/name, app/name)
    for name in ('main.py', 'portable_bootstrap.py', 'portable_setup.py', 'requirements.txt',
                 'requirements-remote.txt', 'requirements-aircontrol.txt'):
        shutil.copy2(ROOT/name, app/name)
    shutil.copy2(ROOT/'packaging/requirements-remote.lock', app/'requirements-remote-portable.txt')
    shutil.copy2(ROOT/'docs/WINDOWS_INSTALLER.md', app/'WINDOWS_INSTALLER.md')
    (app/'MICROSOFT_RUNTIME_NOTICE.txt').write_text(
        'Microsoft Visual C++ v14 OpenMP runtime, x64, 14.51.36247.0\n'
        'Copyright Microsoft Corporation. All rights reserved.\n'
        'Original Microsoft-signed binary, distributed app-locally for DXcam.\n'
        'Microsoft license terms: https://aka.ms/VCRedistLicense\n'
        'Source and SHA-256: ../redistributables.json\n')
    for name in ('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'NOTICE'):
        if (ROOT/name).is_file():
            shutil.copy2(ROOT/name, app/name)
    (stage/'installed.json').write_text(json.dumps({'schema': 1, 'python': base.PYTHON_VERSION,
        'version': VERSION, 'delivery': 'installed-bundled-features', 'webview': 'system-evergreen'}, indent=2))
    inventory = {}
    for name in ('runtime', 'camera'):
        script = 'import importlib.metadata,json;print(json.dumps(sorted((d.metadata["Name"],d.version) for d in importlib.metadata.distributions())))'
        inventory[name] = json.loads(subprocess.check_output([str(stage/name/'python.exe'), '-c', script], text=True))
        if any(package.lower() == 'pip' for package, _ in inventory[name]):
            raise RuntimeError('Installed builds must not ship a package installer')
    (stage/'dependencies.json').write_text(json.dumps(inventory, indent=2))
    return stage


def build(compiler, source):
    stage = stage_runtime(source)
    generated = stage/'Launcher.generated.cs'
    generated.write_text((ROOT/'packaging/PortableLauncher.cs').read_text()
        .replace('@@PAYLOAD_HASH@@', '').replace('@@PAYLOAD_LENGTH@@', '0'))
    csc = Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    base.run([csc, '/nologo', '/define:INSTALLED', '/target:winexe', '/platform:x64', '/optimize+',
        '/out:'+str(stage/'TouchHelm.exe'), '/win32icon:'+str(ROOT/'assets/touchhelm.ico'),
        '/win32manifest:'+str(ROOT/'packaging/portable.manifest'),
        '/r:System.IO.Compression.dll', '/r:System.IO.Compression.FileSystem.dll',
        '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', '/r:System.Web.Extensions.dll', generated])
    generated.unlink()
    files = validate_files(stage)
    DIST.mkdir(exist_ok=True)
    base.run([compiler, '/Qp', '/DStageDir='+str(stage), '/DOutputDir='+str(DIST),
        '/DOutputName='+OUTPUT, ROOT/'packaging/TouchHelm.iss'])
    exe = DIST/(OUTPUT+'.exe')
    manifest = {'file': exe.name, 'bytes': exe.stat().st_size, 'sha256': base.sha(exe),
        'unpacked_bytes': sum(p.stat().st_size for p in files), 'file_count': len(files),
        'python': base.PYTHON_VERSION, 'version': VERSION, 'signed': False,
        'features_bundled': True, 'requires_system_python': False, 'changes_path': False,
        'webview': 'system-evergreen-auto-bootstrap-if-missing', 'target': 'Windows 10/11 x64',
        'stage': str(stage.relative_to(ROOT)), 'dependencies': json.loads((stage/'dependencies.json').read_text())}
    (DIST/'installer-build-manifest.json').write_text(json.dumps(manifest, indent=2))
    (DIST/'SHA256SUMS-test3.txt').write_text(manifest['sha256']+'  '+exe.name+'\n')
    shutil.copy2(ROOT/'docs/WINDOWS_INSTALLER.md', DIST/'WINDOWS_INSTALLER.md')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'dependencies'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iscc', type=Path, default=ROOT/'build/tools/InnoSetup/ISCC.exe')
    parser.add_argument('--runtime-source', type=Path, default=ROOT/'build/portable-stage')
    args = parser.parse_args()
    if not args.iscc.is_file():
        parser.error('Install the official Inno Setup 6 compiler and pass --iscc path/to/ISCC.exe')
    build(args.iscc.absolute(), args.runtime_source.absolute())
