"""Build a small EXE with automatic public first-run dependency preparation."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import build_portable as base

ROOT=base.ROOT
STAGE=ROOT/'build/compact-stage'
CACHE=ROOT/'build/portable-cache'
DIST=ROOT/'dist'


def prepare():
    base.STAGE=STAGE
    base.download({f'python-{base.PYTHON_VERSION}-embed-amd64.zip'})
    base.runtime('runtime',['requirements.txt','packaging/requirements-bootstrap.txt'])
    if sys.version_info[:3]!=(3,13,14):raise RuntimeError('Use CPython 3.13.14 x64 to build the matching Tk fallback.')
    origin=Path(sys.base_prefix)
    base.copytree(origin/'Lib/tkinter',STAGE/'runtime/Lib/tkinter')
    base.copytree(origin/'tcl',STAGE/'runtime/tcl')
    for name in ('_tkinter.pyd','tcl86t.dll','tk86t.dll','zlib1.dll'):
        shutil.copy2(origin/'DLLs'/name,STAGE/'runtime'/name)


def copy_app():
    app=STAGE/'app';app.mkdir(parents=True,exist_ok=True)
    for name in ('server','gui','web','assets'):
        shutil.copytree(ROOT/name,app/name,dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('__pycache__','*.pyc','review','*.task'))
    for name in ('main.py','portable_bootstrap.py','portable_setup.py','requirements.txt',
                 'requirements-remote.txt','requirements-aircontrol.txt'):
        shutil.copy2(ROOT/name,app/name)
    shutil.copy2(ROOT/'packaging/requirements-remote.lock',app/'requirements-remote-portable.txt')
    shutil.copy2(ROOT/'docs/COMPACT_TESTING.md',app/'COMPACT_TESTING.md')
    for name in ('LICENSE','LICENSE.md','LICENSE.txt','NOTICE'):
        if (ROOT/name).is_file():shutil.copy2(ROOT/name,app/name)
    with zipfile.ZipFile(CACHE/f'python-{base.PYTHON_VERSION}-embed-amd64.zip') as archive:
        seeds=[name for name in archive.namelist() if '/' not in name and not name.endswith('._pth')]
    manifest={'schema':1,'python':base.PYTHON_VERSION,'seed_files':seeds,
              'delivery':'automatic-first-run','webview':'system-evergreen'}
    (STAGE/'compact.json').write_text(json.dumps(manifest,indent=2))
    inventory_script='import importlib.metadata,json;print(json.dumps(sorted([(d.metadata["Name"],d.version) for d in importlib.metadata.distributions()])))'
    inventory=json.loads(subprocess.check_output([str(STAGE/'runtime/python.exe'),'-c',inventory_script],text=True))
    (STAGE/'dependencies.json').write_text(json.dumps({'core':inventory},indent=2))
    (STAGE/'redistributables.json').write_text(json.dumps({'python':{'version':base.PYTHON_VERSION,
        'url':base.SOURCES[f'python-{base.PYTHON_VERSION}-embed-amd64.zip'],
        'sha256':base.sha(CACHE/f'python-{base.PYTHON_VERSION}-embed-amd64.zip')}},indent=2))


def build():
    copy_app();DIST.mkdir(exist_ok=True)
    files=sorted(p for p in STAGE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and
        p.suffix!='.pyc' and p.name!='.dependencies-ready')
    forbidden={'config.json','.env','instance.json','desktop.log'}
    for path in files:
        if path.name in forbidden or path.suffix.lower() in ('.key','.pfx','.p12','.task'):
            raise RuntimeError('Unexpected private or large runtime file in compact stage: '+str(path.relative_to(STAGE)))
        if path.suffix=='.pem' and not path.as_posix().endswith('/certifi/cacert.pem'):
            raise RuntimeError('Unexpected PEM in compact stage')
    if any(p.relative_to(STAGE).parts[0] in ('camera','webview2') for p in files):
        raise RuntimeError('Compact stage contains offline feature runtimes')
    payload=CACHE/'compact-payload.zip'
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files:archive.write(path,path.relative_to(STAGE).as_posix())
    digest=base.sha(payload);length=payload.stat().st_size
    source=(ROOT/'packaging/PortableLauncher.cs').read_text().replace('@@PAYLOAD_HASH@@',digest).replace('@@PAYLOAD_LENGTH@@',str(length))
    generated=CACHE/'CompactLauncher.generated.cs';generated.write_text(source)
    exe=DIST/'TouchHelm-2.2.0-test2-compact-win-x64.exe'
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    base.run([compiler,'/nologo','/target:winexe','/platform:x64','/optimize+','/out:'+str(exe),
        '/win32icon:'+str(ROOT/'assets/touchhelm.ico'),'/win32manifest:'+str(ROOT/'packaging/portable.manifest'),
        '/r:System.IO.Compression.dll','/r:System.IO.Compression.FileSystem.dll',
        '/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll',generated])
    with exe.open('ab') as output,payload.open('rb') as stream:shutil.copyfileobj(stream,output,1024*1024)
    manifest={'file':exe.name,'bytes':exe.stat().st_size,'sha256':base.sha(exe),'payload_sha256':digest,
        'payload_bytes':length,'unpacked_bytes':sum(p.stat().st_size for p in files),'python':base.PYTHON_VERSION,
        'delivery':'automatic-first-run','signed':False,'target':'Windows 10/11 x64','core_dependencies':inventory()}
    (DIST/'compact-build-manifest.json').write_text(json.dumps(manifest,indent=2))
    (DIST/'SHA256SUMS-test2.txt').write_text(manifest['sha256']+'  '+exe.name+'\n')
    shutil.copy2(ROOT/'docs/COMPACT_TESTING.md',DIST/'COMPACT_TESTING.md')
    print(json.dumps({k:v for k,v in manifest.items() if k!='core_dependencies'},indent=2))


def inventory():
    return json.loads((STAGE/'dependencies.json').read_text())['core']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-runtime',action='store_true')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    if not args.reuse_runtime:prepare()
    if not args.prepare_only:build()
