import unittest
from unittest.mock import Mock
from server.aircontrol.voice import VoiceController

class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.input=Mock();self.bridge=Mock(startup_timeout=0)
        self.bridge.request.side_effect=lambda command,payload=None,**k: {'available':True,'field_id':'field','process_id':123} if command in ('target','restore_target') else {'voice_access':False,'toolbar_open':False,'toolbar_unknown':False}
        self.voice=VoiceController(self.input,bridge=self.bridge,allowed=lambda:True)
    async def asyncTearDown(self):await self.voice.close()
    async def test_auto_dictation_requests_once_per_field(self):
        await self.voice.dictate(explicit=False);await self.voice.dictate(explicit=False)
        self.input.hotkey.assert_called_once_with('win','h')
    async def test_already_open_toolbar_is_not_toggled(self):
        self.bridge.request.side_effect=lambda command,payload=None,**k: {'available':True,'field_id':'field','process_id':123} if command=='target' else {'voice_access':False,'toolbar_open':True}
        await self.voice.dictate(explicit=False);self.input.hotkey.assert_not_called()
    async def test_password_or_unsupported_field_never_requests_dictation(self):
        self.bridge.request.return_value={'available':False};self.bridge.request.side_effect=None
        await self.voice.dictate(explicit=False);self.input.hotkey.assert_not_called()
    async def test_voice_access_prevents_competing_dictation(self):
        self.bridge.request.side_effect=lambda command,payload=None,**k: {'voice_access':True}
        await self.voice.dictate(explicit=True);self.input.hotkey.assert_not_called()
    async def test_paused_control_cannot_complete_queued_auto_dictation(self):
        self.voice.allowed=lambda:False
        await self.voice.dictate(explicit=False);self.input.hotkey.assert_not_called()
