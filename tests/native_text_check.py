"""Opt-in real UIA check against an owned scratch window; no user text output.

Run manually: python tests/native_text_check.py
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.desktop_services import PersistentPowerShellBridge
from server.text_sync import FocusedTextService

SCRIPT = r'''
param([string]$directory)
Add-Type -AssemblyName System.Windows.Forms
$form=New-Object System.Windows.Forms.Form
$form.Text='TouchHelm isolated text test';$form.Width=450;$form.Height=180;$form.TopMost=$true
$edit=New-Object System.Windows.Forms.TextBox
$edit.Multiline=$true;$edit.Width=400;$edit.Height=70;$edit.Text='Scratch PC text'
$password=New-Object System.Windows.Forms.TextBox
$password.UseSystemPasswordChar=$true;$password.Text='scratch-only';$password.Top=80
$form.Controls.Add($edit);$form.Controls.Add($password)
$timer=New-Object System.Windows.Forms.Timer;$timer.Interval=100
$timer.Add_Tick({
    $file=Join-Path $directory 'command'
    if(Test-Path $file){
        $command=Get-Content $file -Raw;Remove-Item $file
        switch($command){
            'edit' {$edit.Text='PC changed outside phone';$edit.Focus()|Out-Null}
            'password' {$password.Focus()|Out-Null}
            'readonly' {$edit.ReadOnly=$true;$edit.Focus()|Out-Null}
            'normal' {$edit.ReadOnly=$false;$form.Activate();$form.ActiveControl=$edit;$edit.Select();$edit.Focus()|Out-Null}
            'complete-g' {$edit.Text='google.com';$edit.Select(1,9);$edit.Focus()|Out-Null}
            'complete-gi' {$edit.Text='github.com';$edit.Select(2,8);$edit.Focus()|Out-Null}
            'accept-completion' {$edit.Select($edit.Text.Length,0);$edit.Focus()|Out-Null}
            'stop' {$form.Close()}
        }
        [System.IO.File]::WriteAllText((Join-Path $directory 'done'),$command)
    }
})
$form.Add_Shown({$form.Activate();$edit.Focus()|Out-Null;[System.IO.File]::WriteAllText((Join-Path $directory 'ready'),'ready');$timer.Start()})
[System.Windows.Forms.Application]::Run($form)
$timer.Dispose();$form.Dispose()
'''

def run():
    with tempfile.TemporaryDirectory(prefix='touchhelm-text-check-') as tmp:
        directory=Path(tmp);script=directory/'scratch.ps1';script.write_text(SCRIPT,encoding='utf-8-sig')
        process=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),tmp],
            creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        bridge=PersistentPowerShellBridge(script_path=Path('server/text_bridge.ps1').resolve())
        def wait(path):
            deadline=time.monotonic()+12
            while not path.exists():
                if process.poll() is not None:raise AssertionError('Owned scratch window exited')
                if time.monotonic()>deadline:raise AssertionError('Owned scratch window timed out')
                time.sleep(.1)
        def command(value):
            (directory/'done').unlink(missing_ok=True)
            (directory/'command').write_text(value,encoding='ascii');wait(directory/'done');time.sleep(.1)
        try:
            wait(directory/'ready');time.sleep(.2);command('normal')
            first=bridge.request('read')
            if first.get('text')!='Scratch PC text':
                diagnostic=subprocess.run(['powershell.exe','-NoProfile','-Command',
                    'Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes; $e=[System.Windows.Automation.AutomationElement]::FocusedElement; '+
                    'if($e.Current.ProcessId -eq '+str(process.pid)+') { @{type=$e.Current.ControlType.ProgrammaticName;focus=$e.Current.HasKeyboardFocus;patterns=@($e.GetSupportedPatterns()|ForEach-Object {$_.ProgrammaticName})}|ConvertTo-Json -Compress } else { "Scratch window does not own focus" }'],capture_output=True,text=True)
                print(diagnostic.stdout.strip())
            assert first.get('text')=='Scratch PC text','Scratch field not detected'
            target=bridge.request('target')
            assert target.get('available') and target.get('process_id')==process.pid,'Editable metadata target not detected'
            assert 'text' not in target,'Dictation metadata exposed text'
            next_value='Phone edit\nSecond line 🙂'
            result=bridge.request('write',{'field_id':first['field_id'],'revision':first['revision'],'text':next_value})
            assert result.get('text')==next_value,'Phone edit not applied to scratch field'
            command('edit')
            stale=bridge.request('write',{'field_id':first['field_id'],'revision':first['revision'],'text':'stale'})
            assert not stale.get('available'),'Stale revision was accepted'
            assert bridge.request('read').get('text')=='PC changed outside phone','PC edit not observed'
            service=FocusedTextService(bridge=bridge)
            async def sync(action, **payload):
                return await service.request({'action': action, **payload})
            state=asyncio.run(sync('read'))
            state=asyncio.run(sync('write',field_id=state['field_id'],revision=state['revision'],text='g'))
            command('complete-g')
            raw=bridge.request('read')
            assert raw.get('selection_start')==1 and raw.get('selection_end')==10,'Native selected suffix not reported'
            state=asyncio.run(sync('read'))
            assert state.get('text')=='g','Inline completion replaced phone prefix'
            assert state['revision']==raw['revision'],'Completion lost the raw revision'
            state=asyncio.run(sync('write',field_id=state['field_id'],revision=state['revision'],text='gi'))
            assert state.get('text')=='gi','Typing after completion failed'
            command('complete-gi')
            state=asyncio.run(sync('read'))
            assert state.get('text')=='gi','Repeated completion replaced phone prefix'
            command('accept-completion')
            assert asyncio.run(sync('read')).get('text')=='github.com','Accepted completion did not sync'
            command('password');assert not bridge.request('read').get('available'),'Password field exposed'
            assert not bridge.request('target').get('available'),'Password accepted as a dictation target'
            command('readonly');assert not bridge.request('read').get('available'),'Read-only field exposed'
            assert not bridge.request('target').get('available'),'Read-only dictation target accepted'
            print(json.dumps({'native_scratch_test':'passed','two_way':True,'stale_write_rejected':True,'inline_completion':True,'accepted_completion':True,'password_excluded':True,'readonly_excluded':True}))
        finally:
            bridge.close()
            if process.poll() is None:
                try:command('stop');process.wait(timeout=3)
                except Exception:process.terminate();process.wait(timeout=3)

if __name__=='__main__':run()
