"""Opt-in browser/WS/UIA probe against an owned scratch form only.

Started by native_text_browser_check.cjs; pointer/media providers are mocked.
"""
import asyncio
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from server.config import ConfigManager
from server.web_server import TouchHelmServer
from tests.native_text_check import SCRIPT


async def main():
    with tempfile.TemporaryDirectory(prefix='touchhelm-browser-text-') as folder:
        directory = Path(folder)
        script = directory/'scratch.ps1'
        focus_helper = r'''
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ProbeFocus {
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
  [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a,uint b,bool attach);
  [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
  public static bool IsForeground(IntPtr owned) { return GetForegroundWindow()==owned; }
  public static void Activate(IntPtr owned) {
    uint current=GetCurrentThreadId(), foreground=GetWindowThreadProcessId(GetForegroundWindow(),IntPtr.Zero);
    bool attached=current!=foreground && AttachThreadInput(current,foreground,true);
    try { SetForegroundWindow(owned); }
    finally { if(attached) AttachThreadInput(current,foreground,false); }
  }
}
'@
'''
        scratch = SCRIPT.replace('Add-Type -AssemblyName System.Windows.Forms',
            'Add-Type -AssemblyName System.Windows.Forms\n'+focus_helper)
        scratch = scratch.replace('$form.Activate();', '$form.Activate();[ProbeFocus]::Activate($form.Handle);')
        scratch = scratch.replace("[System.IO.File]::WriteAllText((Join-Path $directory 'done'),$command)",
            "[System.IO.File]::WriteAllText((Join-Path $directory 'focus.json'),(@{edit=$edit.Focused;password=$password.Focused;foreground=[ProbeFocus]::IsForeground($form.Handle)}|ConvertTo-Json -Compress));"
            "[System.IO.File]::WriteAllText((Join-Path $directory 'done'),$command)")
        script.write_text(scratch, encoding='utf-8-sig')
        process = subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(script), folder], creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        async def wait_for(path):
            async with asyncio.timeout(12):
                while not path.exists():
                    if process.poll() is not None:
                        raise RuntimeError('Owned scratch form exited')
                    await asyncio.sleep(.05)

        async def command(value):
            (directory/'done').unlink(missing_ok=True)
            (directory/'command').write_text(value, encoding='ascii')
            await wait_for(directory/'done')

        server = runner = None
        try:
            await wait_for(directory/'ready')
            await command('password')
            config = ConfigManager(str(directory/'config.json'))
            config.update({'require_pin':True, 'pin_code':'5678'})
            with patch('server.web_server.WindowsInputController'), \
                    patch('server.web_server.LaserOverlayClient'), \
                    patch('server.web_server.DesktopServices'):
                server = TouchHelmServer(config, on_event=lambda *_:None)
            server._log_event = lambda *_:None
            server.input_ctrl.get_volume.return_value = (None,None)
            server.input_ctrl.get_brightness.return_value = None
            server.input_ctrl.get_screen_size.return_value = (1920,1080)
            for name, value in {'snapshot':{}, 'list_apps':[], 'list_media':{},
                                'displays':{'displays':[]}}.items():
                setattr(server.desktop_services,name,AsyncMock(return_value=value))
            done = asyncio.Event()

            async def probe(request):
                value = request.match_info['command']
                if value == 'diagnostics':
                    code = ('Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes; '
                        '$e=[System.Windows.Automation.AutomationElement]::FocusedElement; '
                        'if($e.Current.ProcessId -eq '+str(process.pid)+') { '
                        '@{owned=$true;type=$e.Current.ControlType.ProgrammaticName;focus=$e.Current.HasKeyboardFocus;'
                        'offscreen=$e.Current.IsOffscreen;password=$e.Current.IsPassword;'
                        'patterns=@($e.GetSupportedPatterns()|ForEach-Object {$_.ProgrammaticName})}|ConvertTo-Json -Compress '
                        '} else { @{owned=$false}|ConvertTo-Json -Compress }')
                    result = await asyncio.to_thread(subprocess.run,
                        ['powershell.exe','-NoProfile','-Command',code],capture_output=True,text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                    return web.json_response({'focus':result.stdout.strip(),'diagnostic_failed':bool(result.returncode),
                        'form':json.loads((directory/'focus.json').read_text())})
                if value == 'shutdown':
                    done.set()
                elif value in ('normal','edit','password','readonly'):
                    await command(value)
                else:
                    return web.Response(status=400)
                return web.json_response({'ok':True,'focus_owned':
                    json.loads((directory/'focus.json').read_text()).get('foreground',False)})

            app = web.Application()
            app.router.add_post('/probe/{command}',probe)
            app.router.add_get('/ws',server.handle_ws)
            app.router.add_get('/api/info',server.handle_info)
            app.router.add_get('/api/version',server.handle_version)
            app.router.add_route('*','/api/config',server.handle_config)
            app.router.add_get('/',server.handle_index)
            app.router.add_static('/',Path(__file__).resolve().parents[1]/'web')
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner,'127.0.0.1',0)
            await site.start()
            print(json.dumps({'origin':'http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])}),flush=True)
            await asyncio.wait_for(done.wait(),100)
        finally:
            if runner:
                await runner.cleanup()
            if server:
                for task in server._text_tasks.values():
                    task.cancel()
                await asyncio.gather(*server._text_tasks.values(),return_exceptions=True)
                await server.text_service.close()
            if process.poll() is None:
                with contextlib.suppress(Exception):
                    await command('stop')
                    await asyncio.to_thread(process.wait,3)
                if process.poll() is None:
                    process.terminate()
                    await asyncio.to_thread(process.wait,3)


if __name__ == '__main__':
    asyncio.run(main())
