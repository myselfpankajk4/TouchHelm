"""TouchHelm v2 provider contracts; all mutation/COM effects are fixtures."""
import asyncio
import base64
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from server.desktop_services import DesktopServices


def picture(format='PNG', size=(12, 8)):
    output = io.BytesIO()
    Image.new('RGB', size, 'blue').save(output, format=format)
    return output.getvalue()


class FixtureBridge:
    def __init__(self):
        self.calls = []
        self.session = dict(id='player', session_id='player', title='Song', available=True,
                            position=30, duration=120, min_seek=10, max_seek=100,
                            capabilities={key: True for key in
                                          ('play', 'pause', 'next', 'prev', 'stop', 'seek', 'shuffle', 'repeat', 'rate')})
        self.apps = [dict(id='registered', name='Editor', running=True,
                         windows=[dict(id='win-known', title='Document')],
                         icon_data=base64.b64encode(picture()).decode())]

    def request(self, command, payload=None, **kwargs):
        self.calls.append((command, payload or {}))
        if command == 'media_library':
            return dict(sessions=[self.session], items=[], playlist_supported=False,
                        playlist_message='Queue unavailable')
        if command == 'snapshot':
            return dict(media=dict(self.session, sessions=[self.session],
                                   artwork_data=base64.b64encode(picture('JPEG')).decode()),
                        presentation=dict(available=True, capabilities={'goto': True}))
        if command == 'apps':
            return dict(apps=self.apps)
        if command == 'presentation_details':
            return dict(available=True, current=dict(slide=1, preview_data=base64.b64encode(picture()).decode()),
                        next=None, notes='Actual notes', slides=[dict(slide=1, title='Title')],
                        capabilities={'goto': True})
        if command == 'displays':
            return dict(displays=[dict(id='screen', name='Primary', primary=True,
                                       rect={'x': -1920, 'y': 0, 'width': 1920, 'height': 1080})], selected_id='screen')
        return dict(success=True, handled=True, message='Requested')

    def close(self):
        pass


class AssetTests(unittest.TestCase):
    def test_normalized_png_opaque_id_and_invalid_input(self):
        from server.asset_store import AssetStore
        store = AssetStore(max_items=2, max_bytes=4096, max_dimension=16)
        identifier = store.put(picture('JPEG', (40, 20)))
        self.assertRegex(identifier, r'^[a-f0-9]{32}$')
        payload = store.get(identifier)
        self.assertTrue(payload.startswith(b'\x89PNG'))
        with Image.open(io.BytesIO(payload)) as decoded:
            self.assertEqual(decoded.size, (16, 8))
        self.assertIsNone(store.get('../../config.json'))
        self.assertIsNone(store.put(b'not an image'))
        self.assertIsNone(store.put(b'x' * (4 * 1024 * 1024 + 1)))

    def test_cache_bounded_and_deduplicates(self):
        from server.asset_store import AssetStore
        store = AssetStore(max_items=1)
        first = store.put(picture())
        self.assertEqual(store.put(picture()), first)
        second = store.put(picture(size=(8, 8)))
        self.assertIsNone(store.get(first))
        self.assertIsNotNone(store.get(second))


class ProviderV2Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.usage = Path(self.folder.name) / 'usage.json'
        self.bridge = FixtureBridge()
        self.service = DesktopServices(bridge=self.bridge, usage_file=self.usage,
                                       media_dirs=[Path(self.folder.name)])

    async def asyncTearDown(self):
        await self.service.close()
        self.folder.cleanup()

    async def test_only_genuine_queues_no_file_or_current_session_fake_items(self):
        (Path(self.folder.name) / 'Song.mp3').write_bytes(b'fixture')
        catalog = await self.service.list_media()
        self.assertEqual(catalog['items'], [])
        self.assertEqual(catalog['playlist_message'], 'Queue unavailable')

    async def test_media_actions_validate_capability_and_relative_seek_bounds(self):
        await self.service.list_media()
        for invalid in (None, True, float('nan'), -1, 101):
            response = await self.service.media_command('seek', session_id='player', value=invalid)
            self.assertFalse(response['success'])
        self.assertNotIn('media_command', [call[0] for call in self.bridge.calls])
        response = await self.service.media_command('seek', session_id='player', value=45.5)
        self.assertTrue(response['success'])
        self.assertEqual(self.bridge.calls[-1], ('media_command', {'action':'seek', 'session_id':'player', 'value':45.5}))
        self.bridge.session['capabilities']['seek'] = False
        self.assertFalse((await self.service.media_command('seek', session_id='player', value=50))['success'])

    async def test_shuffle_repeat_rate_reject_wrong_types_and_out_of_range(self):
        for action, value in [('shuffle', 1), ('repeat','bogus'), ('rate', math.inf), ('rate', 0), ('rate', True)]:
            self.assertFalse((await self.service.media_command(action, session_id='player', value=value))['success'])
        self.assertNotIn('media_command', [call[0] for call in self.bridge.calls])
        for action, value in [('shuffle',True), ('repeat','track'), ('rate',1.5)]:
            self.assertTrue((await self.service.media_command(action, session_id='player', value=value))['success'])

    async def test_assets_are_png_references_not_embedded_payloads(self):
        state = await self.service.snapshot()
        self.assertNotIn('artwork_data', state['media'])
        self.assertIsNotNone(self.service.assets.get(state['media']['artwork_id']))
        self.assertTrue(state['media']['capabilities']['seek'])
        self.assertIsNotNone(state['media']['updated_at'])
        apps = await self.service.list_apps()
        self.assertIsNotNone(self.service.assets.get(apps[0]['icon_id']))
        self.assertNotIn('icon_data', apps[0])
        raw = {'artwork_data':base64.b64encode(picture()).decode(),'artwork_id':None}
        fixed = self.service._normalize_assets(raw)
        self.assertIsNotNone(self.service.assets.get(fixed['artwork_id']))

    async def test_pin_migrates_counts_and_persists_without_launching(self):
        self.usage.write_text(json.dumps({'registered': 4}))
        await self.service.list_apps()
        self.assertTrue((await self.service.app_action('registered','pin'))['success'])
        self.assertTrue((await self.service.list_apps())[0]['pinned'])
        saved = json.loads(self.usage.read_text())
        self.assertEqual(saved['launches']['registered'],4)
        self.assertEqual(saved['pinned'],['registered'])
        self.assertNotIn('launch_app',[call[0] for call in self.bridge.calls])

    async def test_malformed_pin_history_is_ignored_without_losing_launch_counts(self):
        self.usage.write_text(json.dumps({'launches':{'registered':4},'pinned':None}))
        self.service._load_usage()
        apps=await self.service.list_apps()
        self.assertEqual(apps[0]['launches'],4)
        self.assertFalse(apps[0]['pinned'])

    async def test_bounded_progressive_icons_complete_without_discarding_catalog(self):
        previous = self.bridge.request
        count = 0
        def request(command, payload=None, **kwargs):
            nonlocal count
            response = previous(command, payload, **kwargs)
            if command == 'apps':
                count += 1
                response['icons_pending'] = count == 1
            return response
        self.bridge.request = request
        apps = await self.service.list_apps()
        self.assertEqual(count, 2)
        self.assertIsNotNone(apps[0]['icon_id'])

    async def test_forged_windows_and_actions_do_not_reach_native_boundary(self):
        await self.service.list_apps()
        for app, action, window in [('registered','focus','forged'),('unknown','pin',''),('registered','close','')]:
            self.assertFalse((await self.service.app_action(app,action,window))['success'])
        self.assertNotIn('app_action',[call[0] for call in self.bridge.calls])
        self.assertTrue((await self.service.app_action('registered','focus','win-known'))['success'])

    async def test_presentation_details_on_demand_and_goto_validation(self):
        self.assertNotIn('presentation_details',[call[0] for call in self.bridge.calls])
        detail = await self.service.presentation_details()
        self.assertEqual(detail['notes'],'Actual notes')
        self.assertIsNotNone(self.service.assets.get(detail['current']['artwork_id']))
        for index in (None, True, 0, -1, 10001):
            self.assertFalse((await self.service.presentation_command('goto',slide=index))['success'])
        self.assertNotIn('presentation_command',[call[0] for call in self.bridge.calls])
        self.assertTrue((await self.service.presentation_command('goto',slide=1))['success'])

    async def test_display_coordinates_and_selected_id_are_preserved(self):
        state = await self.service.displays()
        self.assertEqual(state['selected_id'],'screen')
        self.assertEqual(state['displays'][0]['rect']['x'],-1920)


from tests import test_desktop_services as existing_tests


@unittest.skipUnless(__import__('os').name == 'nt', 'Windows bridge fixtures')
class BridgeV2Tests(unittest.TestCase):
    run_provider_fixture = existing_tests.PowerShellIdentityTests.run_provider_fixture

    def test_seek_uses_start_offset_ticks_and_rejects_unsupported_controls(self):
        result = self.run_provider_fixture(r'''
function Initialize-Media { return $true }
function Await-WinRT($operation, $resultType) { return $operation }
$script:requested = @()
$controls = [pscustomobject]@{IsPlaybackPositionEnabled=$true; IsPlayEnabled=$true}
$timeline = [pscustomobject]@{StartTime=[TimeSpan]::FromSeconds(100); MinSeekTime=[TimeSpan]::FromSeconds(110); MaxSeekTime=[TimeSpan]::FromSeconds(200); EndTime=[TimeSpan]::FromSeconds(220)}
$session = [pscustomobject]@{}
$session | Add-Member ScriptMethod GetPlaybackInfo { return [pscustomobject]@{Controls=$controls} }
$session | Add-Member ScriptMethod GetTimelineProperties { return $timeline }
$session | Add-Member ScriptMethod TryChangePlaybackPositionAsync { param($ticks) $script:requested += $ticks; return $true }
$script:sessions['player'] = $session
$good = Media-Command 'seek' 'player' 45.5
$bad = Media-Command 'seek' 'player' 101
$controls.IsPlaybackPositionEnabled = $false
$unsupported = Media-Command 'seek' 'player' 50
@{good=$good;bad=$bad;unsupported=$unsupported;ticks=$script:requested} | ConvertTo-Json -Depth 8 -Compress
''')
        self.assertTrue(result['good']['success'])
        self.assertFalse(result['bad']['success'])
        self.assertFalse(result['unsupported']['success'])
        self.assertEqual(result['ticks'], [1455000000])

    def test_arbitrary_browser_and_changed_foreground_are_not_presentation_fallback(self):
        result = self.run_provider_fixture(r'''
function Get-PowerPoint { return $null }
function Read-Window { return @{app='chrome'; title='Mail inbox'; handle=42} }
$context = Read-Presentation
$command = Presentation-Command 'next'
@{context=$context; command=$command} | ConvertTo-Json -Depth 8 -Compress
''')
        self.assertFalse(result['context']['available'])
        self.assertTrue(result['command']['handled'])
        self.assertFalse(result['command']['success'])

    def test_exact_app_identity_no_generic_title_running_match(self):
        result = self.run_provider_fixture(r'''
function Get-RegisteredApps { return @(@{id='a';name='Editor';exe='C:\App\editor.exe'},@{id='b';name='Other';exe='C:\Other\other.exe'}) }
function Get-DesktopWindows { return @(@{handle=10;pid=4;identity='4:10';title='Editor help';exe='C:\Other\other.exe';aumid=''}) }
function Read-AppIcon($identifier) { return $null }
$result = Read-Apps
$result | ConvertTo-Json -Depth 8 -Compress
''')
        self.assertFalse(result['apps'][0]['running'])
        self.assertTrue(result['apps'][1]['running'])
        self.assertEqual(result['apps'][1]['windows'][0]['title'], 'Editor help')

    def test_presentation_details_real_notes_indices_and_only_requested_previews(self):
        result = self.run_provider_fixture(r'''
function Read-SlidePreview($slide) { return 'fixture:' + $slide.SlideIndex }
$first = [pscustomobject]@{SlideIndex=1; Shapes=[pscustomobject]@{HasTitle=$true;Title=[pscustomobject]@{TextFrame=[pscustomobject]@{TextRange=[pscustomobject]@{Text='Opening'}}}}}
$second = [pscustomobject]@{SlideIndex=2; Shapes=[pscustomobject]@{HasTitle=$false}}
$notes = [pscustomobject]@{HasTextFrame=$true;PlaceholderFormat=[pscustomobject]@{Type=2};TextFrame=[pscustomobject]@{TextRange=[pscustomobject]@{Text='Actual speaker notes'}}}
$unrelated = [pscustomobject]@{HasTextFrame=$true}
$unrelated | Add-Member ScriptProperty PlaceholderFormat { throw 'not a notes placeholder' }
$first | Add-Member NoteProperty NotesPage ([pscustomobject]@{Shapes=@($unrelated,$notes)})
$second | Add-Member NoteProperty NotesPage ([pscustomobject]@{Shapes=@()})
$script:slides = @($first,$second)
$collection = [pscustomobject]@{Count=2}
$collection | Add-Member ScriptMethod Item { param($index) return $script:slides[$index-1] }
$script:fakePowerPoint = [pscustomobject]@{ActivePresentation=[pscustomobject]@{Slides=$collection};SlideShowWindows=[pscustomobject]@{Count=0};ActiveWindow=[pscustomobject]@{View=[pscustomobject]@{Slide=$first}}}
function Get-PowerPoint { return $script:fakePowerPoint }
Read-PresentationDetails | ConvertTo-Json -Depth 10 -Compress
''')
        self.assertTrue(result['available'])
        self.assertEqual(result['notes'],'Actual speaker notes')
        self.assertEqual(result['current']['index'],1)
        self.assertEqual(result['current']['artwork_data'],'fixture:1')
        self.assertEqual(result['next']['index'],2)
        self.assertEqual(result['slides'],[{'index':1,'title':'Opening'},{'index':2,'title':''}])

    def test_focused_pdf_fallback_cannot_follow_new_document_or_changed_window(self):
        result = self.run_provider_fixture(r'''
function Get-PowerPoint { return $null }
function Display-ForWindow($handle) { return $null }
$script:window = @{app='SumatraPDF'; title='Slides.pdf'; handle=10; identity='one'}
function Read-Window { return $script:window }
[void](Read-Presentation)
$ready = Presentation-Command 'next'
$script:window = @{app='SumatraPDF'; title='Other.pdf'; handle=11; identity='two'}
$wrong = Presentation-Command 'next'
@{ready=$ready;wrong=$wrong} | ConvertTo-Json -Compress
''')
        self.assertFalse(result['ready']['handled'])
        self.assertTrue(result['wrong']['handled'])
        self.assertFalse(result['wrong']['success'])

    def test_browser_deck_caption_has_guarded_fallback_without_fake_slide_details(self):
        result = self.run_provider_fixture(r'''
function Get-PowerPoint { return $null }
function Display-ForWindow($handle) { return $null }
function Read-Window { return @{app='chrome';title='Deck - Google Slides - Google Chrome';handle=10;identity='browser-window'} }
$context = Read-Presentation
$command = Presentation-Command 'next'
@{context=$context;command=$command} | ConvertTo-Json -Depth 8 -Compress
''')
        self.assertTrue(result['context']['capabilities']['native_fallback'])
        self.assertIsNone(result['context']['slide'])
        self.assertIsNone(result['context']['total'])
        self.assertIn('caption',result['context']['message'].lower())
        self.assertFalse(result['command']['handled'])

    def test_full_session_metadata_relative_timeline_and_capabilities(self):
        result = self.run_provider_fixture(r'''
function Get-SessionProperties($session) { return [pscustomobject]@{Title='Song';Artist='Artist';AlbumTitle='Album';Genres=@('Jazz');TrackNumber=3;AlbumTrackCount=12;Thumbnail=$null} }
function Read-Thumbnail($thumbnail) { return $null }
$controls=[pscustomobject]@{IsPlayEnabled=$true;IsPauseEnabled=$true;IsPlaybackPositionEnabled=$true;IsShuffleEnabled=$false;IsRepeatEnabled=$true;IsPlaybackRateEnabled=$true}
$timeline=[pscustomobject]@{StartTime=[TimeSpan]::FromSeconds(100);Position=[TimeSpan]::FromSeconds(145);EndTime=[TimeSpan]::FromSeconds(200);MinSeekTime=[TimeSpan]::FromSeconds(110);MaxSeekTime=[TimeSpan]::FromSeconds(190);LastUpdatedTime=[DateTimeOffset]::FromUnixTimeSeconds(1000)}
$session=[pscustomobject]@{SourceAppUserModelId='app'}
$session | Add-Member ScriptMethod GetPlaybackInfo { return [pscustomobject]@{Controls=$controls;PlaybackStatus='Playing';PlaybackRate=1.5;IsShuffleActive=$false;AutoRepeatMode='Track'} }
$session | Add-Member ScriptMethod GetTimelineProperties { return $timeline }
Read-MediaSession $session 'id' | ConvertTo-Json -Depth 8 -Compress
''')
        self.assertEqual(result['position'],45)
        self.assertEqual(result['duration'],100)
        self.assertEqual(result['min_seek'],10)
        self.assertEqual(result['max_seek'],90)
        self.assertEqual(result['updated_at'],1000)
        self.assertEqual(result['genre'],['Jazz'])
        self.assertEqual(result['track'],3)
        self.assertEqual(result['playback_rate'],1.5)
        self.assertEqual(result['repeat'],'track')
        self.assertTrue(result['capabilities']['seek'])
        self.assertFalse(result['capabilities']['shuffle'])

    def test_stale_window_focus_revalidates_actual_identity_before_native_focus(self):
        result = self.run_provider_fixture(r'''
$script:focusCalls=0
function Focus-DesktopWindow($handle) { $script:focusCalls++; return $true }
$script:knownApps['a']=@{id='a';exe='C:\App\editor.exe'}
$script:appWindows['window']=@{app_id='a';window=@{identity='old';handle=4}}
function Get-DesktopWindows { return @(@{identity='different';handle=4;exe='C:\App\editor.exe';aumid=''}) }
$result = App-Action 'a' 'focus' 'window'
@{result=$result;calls=$script:focusCalls} | ConvertTo-Json -Depth 8 -Compress
''')
        self.assertFalse(result['result']['success'])
        self.assertEqual(result['calls'],0)

    def test_preview_export_preserves_deck_aspect_and_cleans_owned_file(self):
        result = self.run_provider_fixture(r'''
$script:exportDimensions=@();$script:exportPath=''
$slide=[pscustomobject]@{}
$slide | Add-Member ScriptMethod Export {
 param($path,$format,$width,$height)
 $script:exportDimensions=@($width,$height);$script:exportPath=$path
 [IO.File]::WriteAllBytes($path,[byte[]]@(1,2,3))
}
$deck=[pscustomobject]@{PageSetup=[pscustomobject]@{SlideWidth=720;SlideHeight=540}}
$data=Read-SlidePreview $slide $deck
@{dimensions=$script:exportDimensions;data=$data;remains=(Test-Path -LiteralPath $script:exportPath)} | ConvertTo-Json -Depth 8 -Compress
''')
        self.assertEqual(result['dimensions'],[960,720])
        self.assertEqual(result['data'],'AQID')
        self.assertFalse(result['remains'])
