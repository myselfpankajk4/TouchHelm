"""Focused-field synchronization stays separate from pointer processing."""
import unittest
from unittest.mock import Mock

from server.text_sync import FocusedTextService


class TextSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_and_compare_revision_write_use_isolated_provider(self):
        bridge = Mock(startup_timeout=0)
        bridge.request.return_value = {'available': True, 'field_id': 'opaque',
            'revision': 'one', 'text': 'PC edit', 'editable': True}
        service = FocusedTextService(bridge=bridge)
        state = await service.request({'action': 'read'})
        self.assertEqual(state['text'], 'PC edit')
        await service.request({'action': 'write', 'field_id': 'opaque',
            'revision': 'one', 'text': 'Phone edit'})
        self.assertEqual(bridge.request.call_args.args[0], 'write')
        self.assertEqual(bridge.request.call_args.args[1]['revision'], 'one')
        await service.close()
        bridge.close.assert_called_once()

    async def test_failures_do_not_echo_native_field_contents(self):
        bridge = Mock(startup_timeout=0)
        bridge.request.side_effect = RuntimeError('secret provider details')
        service = FocusedTextService(bridge=bridge)
        state = await service.request({'action': 'read'})
        self.assertFalse(state['available'])
        self.assertNotIn('secret', str(state))
        await service.close()

    async def test_invalid_actions_and_oversized_text_are_rejected_before_native_work(self):
        bridge = Mock(startup_timeout=0)
        service = FocusedTextService(bridge=bridge)
        for packet in ({'action': 'anything'}, {'action':'write', 'text':'x'*10001}):
            with self.assertRaises(ValueError): await service.request(packet)
        bridge.request.assert_not_called()
        await service.close()
