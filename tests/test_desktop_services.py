"""Desktop providers tested without launching apps, playing files, or sending input."""
import asyncio
import json
import os
import subprocess
import queue
import threading
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from server.desktop_services import DesktopServices, PersistentPowerShellBridge

ROOT = Path(__file__).resolve().parents[1]


class Bridge:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.fail = False

    def request(self, command, payload=None, *, cancelled=None):
        self.calls.append((command, payload or {}))
        if self.fail:
            raise TimeoutError('Windows provider timed out')
        if command == 'apps':
            return {'apps': [
                {'id': 'registered:alpha', 'name': 'Alpha', 'running': False},
                {'id': 'registered:zeta', 'name': 'Zeta', 'running': True},
                {'id': 'registered:beta', 'name': 'Beta', 'running': False},
            ]}
        if command == 'snapshot':
            return {'presentation': {'available': False, 'message': 'No presenter'},
                    'media': {'available': False, 'message': 'No active media session'}}
        if command == 'media_library':
            return {'sessions': [], 'items': [], 'playlist_supported': False,
                    'playlist_message': 'Player does not expose a queue'}
        return {'success': True, 'message': 'Requested', 'handled': True}

    def close(self):
        self.closed = True


class DesktopServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.bridge = Bridge()
        self.usage = Path(self.folder.name) / 'usage.json'
        self.service = DesktopServices(bridge=self.bridge, usage_file=self.usage,
                                       media_dirs=[Path(self.folder.name)])

    async def asyncTearDown(self):
        await self.service.close()
        self.folder.cleanup()

    async def test_forged_app_id_never_reaches_launch_boundary(self):
        result = await self.service.launch_app('powershell.exe -Command bad')
        self.assertFalse(result['success'])
        self.assertNotIn('launch_app', [call[0] for call in self.bridge.calls])

    async def test_app_ranking_uses_running_state_and_persisted_successful_touchhelm_launches(self):
        await self.service.list_apps()
        self.assertTrue((await self.service.launch_app('registered:beta'))['success'])
        self.assertTrue((await self.service.launch_app('registered:beta'))['success'])
        apps = await self.service.list_apps()
        self.assertEqual([app['name'] for app in apps], ['Zeta', 'Beta', 'Alpha'])
        self.assertEqual(apps[1]['launches'], 2)
        self.assertEqual(json.loads(self.usage.read_text())['registered:beta'], 2)
        other = DesktopServices(bridge=Bridge(), usage_file=self.usage, media_dirs=[])
        try:
            self.assertEqual((await other.list_apps())[1]['launches'], 2)
        finally:
            await other.close()

    async def test_failed_launch_does_not_inflate_usage(self):
        await self.service.list_apps()
        self.bridge.fail = True
        self.assertFalse((await self.service.launch_app('registered:alpha'))['success'])
        self.assertFalse(self.usage.exists())

    async def test_provider_failure_returns_explicit_null_context_without_raising(self):
        self.bridge.fail = True
        state = await self.service.snapshot()
        self.assertFalse(state['presentation']['available'])
        self.assertIsNone(state['presentation']['slide'])
        self.assertIsNone(state['presentation']['total'])
        self.assertFalse(state['media']['available'])
        self.assertIsNone(state['media']['position'])
        self.assertIsNone(state['media']['duration'])
        self.assertIn('timed out', state['media']['message'])

    async def test_snapshot_includes_all_players_without_changing_current_player(self):
        sessions = [{'id': 'one', 'session_id': 'one', 'title': 'First song', 'position': 8, 'duration': 90},
                    {'id': 'two', 'session_id': 'two', 'title': 'Second song', 'position': 12, 'duration': 180}]
        def request(command, payload=None, **kwargs):
            return {'presentation': {'available': False},
                    'media': {'available': True, 'session_id': 'one', 'title': 'First song', 'sessions': sessions}}
        self.bridge.request = request
        state = await self.service.snapshot()
        self.assertEqual(state['media']['session_id'], 'one')
        self.assertEqual(state['media'].get('sessions'), sessions)

    async def test_local_media_is_bounded_and_only_catalog_ids_can_play(self):
        folder = Path(self.folder.name)
        (folder / 'Song.mp3').write_bytes(b'media fixture')
        (folder / 'Ignore.txt').write_text('not media')
        library = await self.service.list_media()
        self.assertFalse(library['playlist_supported'])
        self.assertEqual(len(library['items']), 1)
        song = library['items'][0]
        self.assertEqual(song['title'], 'Song')
        self.assertEqual(song['kind'], 'local')
        self.assertNotIn('path', song)
        forged = await self.service.media_command('play', item_id='../../windows/system32/cmd.exe')
        self.assertFalse(forged['success'])
        self.assertNotIn('media_play', [call[0] for call in self.bridge.calls])
        result = await self.service.media_command('play', item_id=song['id'])
        self.assertTrue(result['success'])
        self.assertEqual(self.bridge.calls[-1][0], 'media_play')
        self.assertEqual(self.bridge.calls[-1][1]['path'], str(folder / 'Song.mp3'))

    async def test_media_catalog_bounds_and_exposed_queue_and_session_items(self):
        from server import desktop_services
        base_request = self.bridge.request
        def request(command, payload=None, **kwargs):
            if command == 'media_library':
                return {'sessions': [{'id': 'session-player', 'title': 'Current song', 'app': 'Real player'}],
                        'items': [{'id': 'queue-real', 'title': 'Queued track', 'subtitle': 'Artist', 'kind': 'queue'}],
                        'playlist_supported': True, 'playlist_message': 'Actual exposed queue'}
            return base_request(command, payload)
        self.bridge.request = request
        folder = Path(self.folder.name)
        for index in range(8):
            (folder / f'{index}.mp3').write_bytes(b'fixture')
        with patch.object(desktop_services, 'MAX_MEDIA_ITEMS', 3):
            library = await self.service.list_media()
        self.assertEqual(len(library['items']), 3)
        self.assertTrue(library['playlist_supported'])
        self.assertEqual(library['items'][0]['title'], 'Queued track')
        self.assertEqual(library['items'][1]['kind'], 'session')
        self.assertTrue((await self.service.media_command('play', item_id='queue-real'))['success'])
        self.assertEqual(self.bridge.calls[-1][1], {'kind': 'queue', 'item_id': 'queue-real'})
        self.assertTrue((await self.service.media_command('play', item_id='session:session-player'))['success'])
        self.assertEqual(self.bridge.calls[-1][1]['session_id'], 'session-player')

    async def test_stale_and_forged_player_ids_do_not_fall_back_to_another_player(self):
        result = await self.service.media_command('next', session_id='missing-player')
        self.assertFalse(result['success'])
        self.assertTrue(result['handled'])
        self.assertNotIn('media_command', [call[0] for call in self.bridge.calls])

    async def test_unsupported_commands_do_not_call_provider(self):
        for action in ('invoke-expression', ['play'], None):
            result = await self.service.media_command(action)
            self.assertFalse(result['handled'])
        result = await self.service.presentation_command('delete_slide')
        self.assertFalse(result['handled'])
        self.assertEqual(self.bridge.calls, [])

    async def test_slow_provider_keeps_event_loop_responsive_and_deadline_is_bounded(self):
        import time
        self.bridge.request = lambda *args, **kwargs: time.sleep(.2)
        self.service = DesktopServices(bridge=self.bridge, usage_file=self.usage,
                                       media_dirs=[], timeout=.04)
        query = asyncio.create_task(self.service.snapshot())
        await asyncio.sleep(.005)
        self.assertFalse(query.done())
        result = await asyncio.wait_for(query, .15)
        self.assertFalse(result['media']['available'])
        self.assertIn('timed out', result['media']['message'].lower())

    async def test_close_owns_bridge_and_prevents_further_queries(self):
        await self.service.close()
        self.assertTrue(self.bridge.closed)
        self.bridge.calls.clear()
        self.assertFalse((await self.service.snapshot())['media']['available'])
        self.assertEqual(self.bridge.calls, [])

    async def test_cancelled_queued_launch_never_writes_to_the_native_bridge(self):
        bridge = PersistentPowerShellBridge(timeout=1)
        process = Mock()
        process.poll.return_value = None
        bridge._proc = process
        responses = bridge._responses = queue.Queue()
        sent_first = threading.Event()
        writes = []

        def write(line):
            request = json.loads(line)
            writes.append(request['command'])
            if request['command'] == 'snapshot':
                sent_first.set()
            else:
                responses.put({'id': request['id'], 'result': {'success': True}})
        process.stdin.write.side_effect = write
        first = asyncio.create_task(asyncio.to_thread(bridge.request, 'snapshot'))
        self.assertTrue(await asyncio.to_thread(sent_first.wait, .5))
        service = DesktopServices(bridge=bridge, usage_file=self.usage, media_dirs=[], timeout=1)
        service._apps = {'catalog-id': {'id': 'catalog-id', 'name': 'Catalog app'}}
        service._apps_at = time.monotonic()
        attempted = asyncio.create_task(service.launch_app('catalog-id'))
        await asyncio.sleep(.03)
        attempted.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await attempted
        responses.put({'id': 1, 'result': {}})
        await first
        # Drain the cancelled worker's queue after the active query releases it.
        await asyncio.to_thread(lambda: (bridge._lock.acquire(), bridge._lock.release()))
        self.assertEqual(writes, ['snapshot'])
        process.kill.assert_not_called()
        await service.close()


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell provider projection')
class PowerShellIdentityTests(unittest.TestCase):
    def run_provider_fixture(self, script):
        prefix = ". '" + str(ROOT / 'server' / 'desktop_bridge.ps1').replace("'", "''") + "'\n"
        process = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                                  '-Command', prefix + script], stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, encoding='utf-8',
                                 timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_snapshot_session_metadata_does_not_contain_recursive_session_lists(self):
        result = self.run_provider_fixture(r'''
function Read-Presentation { return @{available=$false} }
function Read-MediaLibrary {
    $current = @{id='active'; session_id='active'; title='Playing song'}
    return @{current=$current; sessions=@($current, @{id='other'; title='Other song'})}
}
$snapshot = Dispatch-Request @{command='snapshot'; payload=@{}}
@{currentTitle=$snapshot.media.title; count=$snapshot.media.sessions.Count;
  nested=$snapshot.media.sessions[0].ContainsKey('sessions')} | ConvertTo-Json -Compress
''')
        self.assertEqual(result['currentTitle'], 'Playing song')
        self.assertEqual(result['count'], 2)
        self.assertFalse(result['nested'])

    def test_session_ids_survive_reorder_and_current_player_matches_identity(self):
        result = self.run_provider_fixture(r'''
function Initialize-Media { return $true }
function Get-ActiveMediaPlayer { return $null }
function Read-MediaSession($session, $identifier) { return @{id=$identifier; session_id=$identifier; title=$session.Label} }
function Await-WinRT($operation, $resultType) { return $operation }
$first = [pscustomobject]@{SourceAppUserModelId='same-app'; Label='first'}
$second = [pscustomobject]@{SourceAppUserModelId='same-app'; Label='second'}
foreach ($session in @($first, $second)) { $session | Add-Member ScriptMethod TryPlayAsync { return $true } }
$script:sessionOrder = @($first, $second)
$script:chosenSession = $first
$script:mediaManager = [pscustomobject]@{}
$script:mediaManager | Add-Member ScriptMethod GetSessions { return ,$script:sessionOrder }
$script:mediaManager | Add-Member ScriptMethod GetCurrentSession { return $script:chosenSession }
$before = Read-MediaLibrary
$script:sessionOrder = @($second, $first)
$after = Read-MediaLibrary
$removedId = @($after.sessions | Where-Object {$_.title -eq 'second'})[0].id
$script:sessionOrder = @($first)
[void](Read-MediaLibrary)
$stale = Media-Command 'play' $removedId
@{before=$before.sessions; after=$after.sessions; current=$before.current; stale=$stale} | ConvertTo-Json -Depth 10 -Compress
''')
        before = {row['title']: row['id'] for row in result['before']}
        after = {row['title']: row['id'] for row in result['after']}
        self.assertEqual(before, after)
        self.assertNotEqual(before['first'], before['second'])
        self.assertEqual(result['current']['title'], 'first')
        self.assertFalse(result['stale']['success'])
        self.assertTrue(result['stale']['handled'])

    def test_queue_reorder_never_rebinds_an_old_id_to_a_different_track(self):
        result = self.run_provider_fixture(r'''
function Initialize-Media { return $false }
function Get-ActiveMediaPlayer { return $script:fakePlayer }
$first = [pscustomobject]@{sourceURL='D:\fixture\first.mp3'; name='First'}
$second = [pscustomobject]@{sourceURL='D:\fixture\second.mp3'; name='Second'}
foreach ($track in @($first, $second)) { $track | Add-Member ScriptMethod getItemInfo { return 'Artist' } }
$script:queueOrder = @($first, $second)
$playlist = [pscustomobject]@{count=2}
$playlist | Add-Member ScriptMethod Item { param($index) return $script:queueOrder[$index] }
$script:played = @()
$controls = [pscustomobject]@{}
$controls | Add-Member ScriptMethod playItem { param($track) $script:played += $track.sourceURL }
$script:fakePlayer = [pscustomobject]@{currentPlaylist=$playlist; controls=$controls}
$before = Read-MediaLibrary
$oldId = $before.items[0].id
$script:queueOrder = @($second, $first)
$after = Read-MediaLibrary
$playResult = Dispatch-Request @{command='media_play'; payload=@{kind='queue'; item_id=$oldId}}
$script:queueOrder = @($second); $playlist.count = 1
[void](Read-MediaLibrary)
$stale = Dispatch-Request @{command='media_play'; payload=@{kind='queue'; item_id=$oldId}}
@{before=$before.items; after=$after.items; played=$script:played; success=$playResult.success; stale=$stale} | ConvertTo-Json -Depth 10 -Compress
''')
        before = {row['title']: row['id'] for row in result['before']}
        after = {row['title']: row['id'] for row in result['after']}
        self.assertEqual(before, after)
        self.assertTrue(result['success'])
        self.assertEqual(result['played'], ['D:\\fixture\\first.mp3'])
        self.assertFalse(result['stale']['success'])

if __name__ == '__main__':
    unittest.main()
