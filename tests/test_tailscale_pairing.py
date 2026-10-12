"""CLI is simulated: these tests never install, authenticate or change Serve."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from server.config import ConfigManager


class TailscalePairingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('server.tailscale_pairing'), 'Private Serve manager must exist')
        from server.tailscale_pairing import TailscalePairingManager
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.config = ConfigManager(str(Path(self.folder.name)/'config.json'))
        self.serve = {}
        self.calls = []
        self.status = {'BackendState':'Running','Self':{'DNSName':'pc.example.ts.net.'}}
        def cli(args, **kwargs):
            self.calls.append(args[1:])
            if args[1:] == ['status','--json']: value = self.status
            elif args[1:] == ['serve','status','--json']: value = self.serve
            else:
                self.serve = {} if args[-1] == 'off' else {'TCP':{'8443':{'HTTPS':True}},'Web':{'pc.example.ts.net:8443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:8767'}}}}}
                value = {}
            return subprocess.CompletedProcess(args,0,json.dumps(value),'')
        self.run = Mock(side_effect=cli)
        self.manager = TailscalePairingManager(self.config, run=self.run, find_cli=lambda:'tailscale.exe')

    def test_failed_ownership_save_does_not_create_an_unmanaged_endpoint(self):
        self.config.update({'require_pin':True,'pin_code':'9876'})
        with patch.object(self.config,'update',side_effect=OSError('disk write failed')):
            with self.assertRaises(OSError):self.manager.enable()
        self.assertFalse(any('--https=8443' in call for call in self.calls))

    def test_missing_cli_is_honest_and_never_installs(self):
        self.manager.find_cli = lambda: None
        self.assertEqual(self.manager.inspect()['state'],'not_installed')
        self.run.assert_not_called()

    def test_enable_requires_pin_and_owns_only_private_exact_endpoint(self):
        with self.assertRaisesRegex(RuntimeError,'PIN'): self.manager.enable()
        self.config.update({'require_pin':True,'pin_code':'9876'})
        result = self.manager.enable()
        self.assertTrue(result['ready']); self.assertEqual(result['url'],'https://pc.example.ts.net:8443/')
        self.assertIn(['serve','--bg','--https=8443','http://127.0.0.1:8767'],self.calls)
        self.manager.disable()
        self.assertIn(['serve','--bg','--https=8443','http://127.0.0.1:8767','off'],self.calls)
        self.assertFalse(any('reset' in c or 'funnel' in c or 'up' in c for c in self.calls))

    def test_conflict_or_funnel_never_overwrites_existing_service(self):
        self.config.update({'require_pin':True,'pin_code':'9876'})
        for existing in ({'TCP':{'8443':{'HTTPS':True}}}, {'AllowFunnel':{'pc.example.ts.net:8443':True}}):
            self.serve = existing
            with self.assertRaises(RuntimeError): self.manager.enable()
        self.assertTrue(all(c in (['status','--json'],['serve','status','--json']) for c in self.calls))

    def test_changed_owned_endpoint_cannot_be_disabled(self):
        self.config.update({'require_pin':True,'pin_code':'9876'}); self.manager.enable()
        self.serve['Web']['pc.example.ts.net:8443']['Handlers']['/']['Proxy']='http://127.0.0.1:9999'
        with self.assertRaises(RuntimeError): self.manager.disable()
        self.assertFalse(any(c[-1]=='off' for c in self.calls))

    def test_cli_error_timeout_and_invalid_json_are_bounded_unavailable(self):
        for failure in (PermissionError('denied'),subprocess.TimeoutExpired('tailscale',4),ValueError('invalid')):
            self.run.side_effect = failure
            self.assertIn(self.manager.inspect(force=True)['state'],('permission_required','unavailable'))

    def test_status_cache_and_login_state(self):
        self.status['BackendState']='NeedsLogin'
        self.assertEqual(self.manager.inspect()['state'],'login_required')
        self.manager.inspect(); self.assertEqual(self.run.call_count,1)

if __name__ == '__main__': unittest.main()
