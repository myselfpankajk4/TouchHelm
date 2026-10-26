"""Offline lifecycle/security checks. Never starts cloudflared or downloads it."""
import asyncio
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class FakeProcess:
    def __init__(self):
        self.stdout = asyncio.StreamReader()
        self.returncode = None
        self.done = asyncio.Event()
        self.terminated = 0
        self.killed = 0

    def line(self, value):
        self.stdout.feed_data((value + '\n').encode())

    def ready(self):
        self.line('Your quick Tunnel has been created!')
        self.line('| https://owned-test.trycloudflare.com |')
        self.line(json.dumps({'message': 'Registered tunnel connection', 'connIndex': 0}))

    def exit(self, code=0):
        self.returncode = code
        self.done.set()
        self.stdout.feed_eof()

    async def wait(self):
        await self.done.wait()
        return self.returncode

    def terminate(self):
        self.terminated += 1
        self.exit()

    def kill(self):
        self.killed += 1
        self.exit(-1)


class BrowserLinkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(importlib.util.find_spec('server.browser_link'), 'Browser link manager is missing')
        self.mod = importlib.import_module('server.browser_link')
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.helper = self.root/'cloudflared.exe'
        self.helper.write_bytes(b'owned helper')
        self.now = 100.
        self.process = FakeProcess()
        self.calls = []
        self.notifications = []
        self.hash_patch = patch.object(self.mod, 'HASH', hashlib.sha256(b'owned helper').hexdigest())
        self.hash_patch.start()

        async def factory(*args, **kwargs):
            self.calls.append((args, kwargs))
            return self.process

        async def stopped():
            self.notifications.append(True)

        self.manager = self.mod.BrowserLinkManager(stopped, executable=self.helper,
            clock=lambda: self.now, process_factory=factory, work_root=self.root/'runs',
            monitor_interval=.01, startup_timeout=.5)

    async def asyncTearDown(self):
        if hasattr(self, 'manager'):
            await self.manager.stop()
            self.hash_patch.stop()
            self.temp.cleanup()

    async def launch(self):
        task = asyncio.create_task(self.manager.start('http://127.0.0.1:43210'))
        for _ in range(100):
            if self.calls:
                break
            await asyncio.sleep(.001)
        self.process.ready()
        return await task

    async def test_ready_requires_assigned_url_and_registered_connection(self):
        task = asyncio.create_task(self.manager.start('http://127.0.0.1:43210'))
        while not self.calls:
            await asyncio.sleep(.001)
        self.process.line('https://api.trycloudflare.com/tunnel')
        self.process.line('Your quick Tunnel has been created!')
        self.process.line('| https://owned-test.trycloudflare.com |')
        await asyncio.sleep(.02)
        self.assertFalse(task.done())
        self.process.line('Registered tunnel connection connIndex=0')
        state = await task
        self.assertEqual(state['origin'], 'https://owned-test.trycloudflare.com')
        self.assertTrue(state['ready'])
        self.assertEqual(state['expires_in'], 1800)

    async def test_single_use_tickets_sessions_and_rotation(self):
        state = await self.launch()
        ticket = state['pairing_url'].split('=')[1]
        secret = self.manager.exchange(ticket)
        self.assertEqual(len(secret), 43)
        self.assertTrue(self.manager.valid_session(secret))
        self.assertIsNone(self.manager.exchange(ticket))
        next_ticket = self.manager.snapshot()['pairing_url'].split('=')[1]
        self.assertNotEqual(next_ticket, ticket)
        self.manager.rotate_ticket()
        self.assertIsNone(self.manager.exchange(next_ticket))

    async def test_ticket_expires_after_120_seconds_and_bogus_values_are_rejected(self):
        ticket = (await self.launch())['pairing_url'].split('=')[1]
        for value in (None, False, 1, [], {}, 'x'*10000, 'a'*42, '!'*43):
            self.assertIsNone(self.manager.exchange(value))
            self.assertFalse(self.manager.valid_session(value))
        self.now += 120
        self.assertIsNone(self.manager.exchange(ticket))
        fresh = self.manager.rotate_ticket()['pairing_url'].split('=')[1]
        self.assertTrue(self.manager.valid_session(self.manager.exchange(fresh)))

    async def test_sessions_are_capped_and_expire_with_total_link_lifetime(self):
        await self.launch()
        secrets = []
        for _ in range(8):
            token = self.manager.snapshot()['pairing_url'].split('=')[1]
            secrets.append(self.manager.exchange(token))
        self.assertEqual(len(set(secrets)), 8)
        self.assertIsNone(self.manager.exchange(self.manager.snapshot()['pairing_url'].split('=')[1]))
        self.now += 1800
        self.assertFalse(any(self.manager.valid_session(value) for value in secrets))
        await asyncio.sleep(.04)
        self.assertFalse(self.manager.snapshot()['ready'])
        self.assertEqual(self.notifications, [True])
        self.assertEqual(self.process.terminated, 1)

    async def test_stop_is_idempotent_and_revokes_everything(self):
        ticket = (await self.launch())['pairing_url'].split('=')[1]
        secret = self.manager.exchange(ticket)
        await self.manager.stop('Stopped by desktop')
        await self.manager.stop()
        self.assertFalse(self.manager.valid_session(secret))
        self.assertIsNone(self.manager.exchange(ticket))
        self.assertIsNone(self.manager.snapshot()['pairing_url'])
        self.assertEqual(self.notifications, [True])
        self.assertEqual(self.process.terminated, 1)

    async def test_helper_exit_revokes_sessions_without_deadlocking_monitor(self):
        ticket = (await self.launch())['pairing_url'].split('=')[1]
        secret = self.manager.exchange(ticket)
        self.process.exit(7)
        await asyncio.sleep(.04)
        self.assertEqual(self.manager.snapshot()['state'], 'error')
        self.assertFalse(self.manager.valid_session(secret))
        self.assertEqual(self.notifications, [True])

    async def test_stop_during_startup_does_not_publish_late_url(self):
        task = asyncio.create_task(self.manager.start('http://127.0.0.1:43210'))
        while not self.calls:
            await asyncio.sleep(.001)
        await self.manager.stop()
        with self.assertRaises(self.mod.BrowserLinkError):
            await task
        self.assertEqual(self.manager.snapshot()['state'], 'stopped')
        self.assertEqual(self.notifications, [True])

    async def test_invalid_backends_never_spawn(self):
        for url in ('https://127.0.0.1:12', 'http://example.com:12', 'http://192.168.0.1:12',
                    'http://user:password@127.0.0.1:12', 'http://127.0.0.1:12/path',
                    'http://127.0.0.1:12/?secret=x', 'http://127.0.0.1:12/#x', None):
            with self.subTest(url=url), self.assertRaises(self.mod.BrowserLinkError):
                await self.manager.start(url)
        self.assertEqual(self.calls, [])

    async def test_invalid_output_host_is_never_published(self):
        task = asyncio.create_task(self.manager.start('http://127.0.0.1:43210'))
        while not self.calls:
            await asyncio.sleep(.001)
        self.process.line('Your quick Tunnel has been created!')
        self.process.line('https://owned.trycloudflare.com.evil.example')
        self.process.line('Registered tunnel connection')
        with self.assertRaises(self.mod.BrowserLinkError):
            await task
        self.assertIsNone(self.manager.snapshot()['origin'])
        self.assertEqual(self.process.terminated, 1)

    async def test_private_config_home_and_environment_cannot_use_account_settings(self):
        inherited = {'TUNNEL_NAME': 'private-account', 'TUNNEL_ORIGIN_CERT': 'secret.pem',
            'TUNNEL_TOKEN': 'secret', 'CLOUDFLARED_CONFIG': 'user.yaml', 'NO_TLS_VERIFY': '1',
            'HTTP_PROXY': 'http://user:secret@proxy', 'CFDPATH': 'external', 'HOME': 'external',
            'USERPROFILE': 'external'}
        with patch.dict(os.environ, inherited):
            await self.launch()
        args, options = self.calls[0]
        config = Path(args[args.index('--config')+1])
        self.assertEqual(config.read_text(), '{}\n')
        env = options['env']
        for key in ('TUNNEL_NAME','TUNNEL_TOKEN','TUNNEL_ORIGIN_CERT','CLOUDFLARED_CONFIG','NO_TLS_VERIFY','HTTP_PROXY'):
            self.assertNotIn(key, env)
        self.assertEqual(env['HOME'], env['USERPROFILE'])
        self.assertEqual(env['HOME'], str(options['cwd']))
        self.assertEqual(args[args.index('--protocol')+1], 'http2')
        self.assertEqual(args[args.index('--output')+1], 'json')
        self.assertIn('--no-autoupdate', args)
        self.assertNotIn('--no-tls-verify', args)
        self.assertEqual(args[args.index('--metrics')+1], '127.0.0.1:0')
        await self.manager.stop()
        self.assertFalse(config.parent.exists())

    async def test_invalid_explicit_helper_never_runs(self):
        self.helper.write_bytes(b'changed')
        with self.assertRaises(self.mod.BrowserLinkError):
            await self.manager.start('http://127.0.0.1:43210')
        self.assertEqual(self.calls, [])
        self.assertNotIn(str(self.helper), str(self.manager.snapshot()))

    async def test_cached_helper_is_checked_and_failed_download_is_cleaned(self):
        cache = self.root/'cache'
        calls = []
        def download(url, target):
            calls.append(url)
            target.write_bytes(b'owned helper')
        with patch.object(self.mod, 'bundle_root', return_value=None):
            actual = self.mod.ensure_helper(cache_dir=cache, downloader=download, protector=lambda path: None)
            self.assertEqual(actual.read_bytes(), b'owned helper')
            self.mod.ensure_helper(cache_dir=cache, downloader=lambda *args: self.fail('Cached helper redownloaded'), protector=lambda path: None)
            actual.write_bytes(b'corrupted')
            with self.assertRaises(self.mod.BrowserLinkError):
                self.mod.ensure_helper(cache_dir=cache, downloader=lambda url, target: target.write_bytes(b'wrong'), protector=lambda path: None)
        self.assertEqual(calls, [self.mod.URL])
        self.assertEqual(list(cache.glob('.download-*')), [])

    async def test_valid_bundled_helper_avoids_download(self):
        bundle = self.root/'bundle'
        (bundle/'cloudflared').mkdir(parents=True)
        (bundle/'cloudflared/cloudflared.exe').write_bytes(b'owned helper')
        with patch.object(self.mod, 'bundle_root', return_value=bundle):
            self.assertEqual(self.mod.ensure_helper(downloader=lambda *args: self.fail('Download attempted')),
                bundle/'cloudflared/cloudflared.exe')

    async def test_termination_failure_still_kills_owned_process_and_notifies(self):
        await self.launch()
        with patch.object(self.process, 'terminate', side_effect=OSError('owned fixture')):
            await self.manager.stop()
        self.assertEqual(self.process.killed, 1)
        self.assertEqual(self.notifications, [True])

    async def test_callback_can_call_stop_without_deadlock(self):
        await self.launch()
        async def callback():
            self.notifications.append(True)
            await self.manager.stop()
        self.manager.on_stopped = callback
        await asyncio.wait_for(self.manager.stop(), 1)
        self.assertEqual(self.notifications, [True])

    async def test_late_spawn_after_stop_is_terminated(self):
        spawning, release = asyncio.Event(), asyncio.Event()
        async def factory(*args, **kwargs):
            spawning.set()
            await release.wait()
            return self.process
        self.manager._factory = factory
        task = asyncio.create_task(self.manager.start('http://127.0.0.1:43210'))
        await spawning.wait()
        await self.manager.stop()
        release.set()
        with self.assertRaises(self.mod.BrowserLinkError):
            await task
        self.assertEqual(self.process.terminated, 1)
        self.assertEqual(self.notifications, [True])

    async def test_default_download_has_a_size_limit_and_cleans_partial_data(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, count): return b'x'*16
        with patch.object(self.mod, 'bundle_root', return_value=None), \
             patch.object(self.mod, 'MAX_HELPER_BYTES', 8), \
             patch.object(self.mod.urllib.request, 'urlopen', return_value=Response()) as request:
            with self.assertRaises(self.mod.BrowserLinkError):
                self.mod.ensure_helper(cache_dir=self.root/'limited', protector=lambda path: None)
        self.assertEqual(request.call_args.kwargs['timeout'], 15)
        self.assertEqual(list((self.root/'limited').glob('.download-*')), [])
