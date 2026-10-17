"""Read-only DirectShow enumeration in the same order OpenCV uses; no capture."""
import asyncio
import json
from pathlib import Path
import subprocess

async def cameras():
    path=str(Path(__file__).with_suffix('.cs')).replace("'","''")
    script="Add-Type -Path '"+path+"'; ConvertTo-Json -InputObject @([TouchHelmCameras]::List()) -Compress"
    try:
        result=await asyncio.to_thread(subprocess.run,['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
            capture_output=True,text=True,encoding='utf-8',timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise RuntimeError()
        value=json.loads(result.stdout)
        return {'available':True,'cameras':value,'message':'Choose your PC camera.' if value else 'No camera detected. Connect a webcam, allow Windows camera access, then refresh.'}
    except Exception:return {'available':False,'cameras':[],'message':'Camera discovery is unavailable. Check Windows camera privacy settings and reconnect your webcam.'}
