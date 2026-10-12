"""Runs only the thumbnail functions with fake PowerPoint objects, no COM/input."""
import json
from pathlib import Path
import subprocess
import unittest

class PreviewCacheTests(unittest.TestCase):
    def test_repeated_slide_reuses_export_until_expiry_or_identity_changes(self):
        source=(Path(__file__).resolve().parents[1]/'server/desktop_bridge.ps1').read_text(encoding='utf-8')
        functions=source[source.index('function Read-SlideTitle'):source.index('function Read-PresentationDetails')]
        fixture=r'''
        $script:exports=0
        $slide=[PSCustomObject]@{SlideID=12;Shapes=[PSCustomObject]@{Count=2;HasTitle=$false}}
        $slide | Add-Member ScriptMethod Export {param($path,$format,$width,$height) $script:exports++;[IO.File]::WriteAllBytes($path,[byte[]](1,2,3))}
        $deck=[PSCustomObject]@{FullName='fixture';Name='fixture';Saved=$true;PageSetup=[PSCustomObject]@{SlideWidth=960;SlideHeight=540}}
        $first=Read-SlidePreview $slide $deck
        $again=Read-SlidePreview $slide $deck
        $cached=$script:exports
        foreach($item in $script:slidePreviewCache.Values){$item.created=[DateTime]::UtcNow.AddSeconds(-11)}
        $fresh=Read-SlidePreview $slide $deck
        $expired=$script:exports
        $slide.SlideID=13
        $changed=Read-SlidePreview $slide $deck
        @{cached=$cached;expired=$expired;changed=$script:exports;same=($first -eq $again)} | ConvertTo-Json -Compress
        '''
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',functions+fixture],capture_output=True,text=True,timeout=5,creationflags=0x08000000)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'cached':1,'expired':2,'changed':3,'same':True})
