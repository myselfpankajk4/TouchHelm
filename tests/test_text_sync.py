"""Focused-field synchronization stays separate from pointer processing."""
import unittest
from unittest.mock import Mock

from server.text_sync import FocusedTextService


class TextSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_inline_completion_does_not_replace_phone_prefix_or_raw_revision(self):
        bridge = Mock(startup_timeout=0)
        service = FocusedTextService(bridge=bridge)
        bridge.request.return_value = {'available': True, 'field_id': 'address',
            'revision': 'raw-google', 'text': 'google.com',
            'selection_start': 1, 'selection_end': 10}
        state = await service.request({'action': 'write', 'field_id': 'address',
            'revision': 'empty', 'text': 'g'})
        self.assertEqual(state['text'], 'g')
        self.assertEqual(state['revision'], 'raw-google')
        # Polling must not pull the highlighted suffix into the phone later.
        self.assertEqual((await service.request({'action': 'read'}))['text'], 'g')
        # A later mobile edit still compares against the actual PC revision.
        bridge.request.return_value = {'available': True, 'field_id': 'address',
            'revision': 'raw-github', 'text': 'github.com',
            'selection_start': 2, 'selection_end': 10}
        state = await service.request({'action': 'write', 'field_id': 'address',
            'revision': state['revision'], 'text': 'gi'})
        self.assertEqual(state['text'], 'gi')
        self.assertEqual(bridge.request.call_args.args[1]['revision'], 'raw-google')

    async def test_delayed_completion_is_filtered_but_accepting_it_syncs_the_full_value(self):
        bridge = Mock(startup_timeout=0)
        service = FocusedTextService(bridge=bridge)
        bridge.request.return_value = {'available': True, 'field_id': 'address',
            'revision': 'g', 'text': 'g'}
        await service.request({'action': 'write', 'field_id': 'address',
            'revision': 'empty', 'text': 'g'})
        completion = {'available': True, 'field_id': 'address',
            'revision': 'google', 'text': 'google.com',
            'selection_start': 1, 'selection_end': 10}
        bridge.request.return_value = completion
        self.assertEqual((await service.request({'action': 'read'}))['text'], 'g')
        bridge.request.return_value = {**completion, 'selection_start': 10}
        self.assertEqual((await service.request({'action': 'read'}))['text'], 'google.com')
        # Selecting a suffix after the value was accepted is an ordinary PC selection.
        bridge.request.return_value = completion
        self.assertEqual((await service.request({'action': 'read'}))['text'], 'google.com')

    async def test_pc_selections_and_other_fields_are_not_treated_as_phone_completion(self):
        bridge = Mock(startup_timeout=0)
        service = FocusedTextService(bridge=bridge)
        first = {'available': True, 'field_id': 'address', 'revision': 'r1',
            'text': 'google.com', 'selection_start': 1, 'selection_end': 10}
        bridge.request.return_value = first
        self.assertEqual((await service.request({'action': 'read'}))['text'], 'google.com')
        await service.request({'action': 'write', 'field_id': 'address',
            'revision': 'r1', 'text': 'g'})
        for state in ({**first, 'selection_start': 0},
                      {**first, 'selection_end': 9},
                      {**first, 'selection_start': 2},
                      {**first, 'field_id': 'another'}):
            with self.subTest(state=state):
                bridge.request.return_value = first
                await service.request({'action': 'write', 'field_id': 'address',
                    'revision': 'r1', 'text': 'g'})
                bridge.request.return_value = state
                self.assertEqual((await service.request({'action': 'read'}))['text'], 'google.com')

    async def test_completion_offsets_are_utf16_and_invalid_ranges_never_trim_text(self):
        bridge = Mock(startup_timeout=0)
        service = FocusedTextService(bridge=bridge)
        snapshot = {'available': True, 'field_id': 'field', 'revision': 'raw',
            'text': '🙂.example', 'selection_start': 2, 'selection_end': 10}
        bridge.request.return_value = snapshot
        state = await service.request({'action': 'write', 'field_id': 'field',
            'revision': 'old', 'text': '🙂'})
        self.assertEqual(state['text'], '🙂')
        for start, end in ((True, 10), (1, 10), (-1, 10), (2, 99), (2, None)):
            with self.subTest(start=start, end=end):
                bridge.request.return_value = snapshot
                await service.request({'action': 'write', 'field_id': 'field',
                    'revision': 'old', 'text': '🙂'})
                bridge.request.return_value = {**snapshot, 'selection_start': start, 'selection_end': end}
                self.assertEqual((await service.request({'action': 'read'}))['text'], '🙂.example')

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
