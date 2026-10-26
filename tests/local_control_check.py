"""Actual Chrome + local aiortc, with every native PC boundary mocked."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from server.config import ConfigManager
from server.web_server import TouchHelmServer
from server.browser_gateway import BrowserLinkGateway


async def main(public=False):
    report={}
    with tempfile.TemporaryDirectory(prefix='local-check-',dir=Path('build')) as work:
        config=ConfigManager(str(Path(work)/'config.json'));config.update({'require_pin':True,'pin_code':'5678'})
        with patch('server.web_server.WindowsInputController'),patch('server.web_server.LaserOverlayClient'),patch('server.web_server.DesktopServices'):
            server=TouchHelmServer(config)
        server._log_event=lambda *args:None
        server.input_ctrl.get_volume.return_value=(50,False);server.input_ctrl.get_brightness.return_value=None
        server.input_ctrl.get_screen_size.return_value=(1920,1080)
        server.desktop_services.snapshot=AsyncMock(return_value={'media':{'available':False},'presentation':{'available':False}})
        server.desktop_services.list_apps=AsyncMock(return_value=[])
        server.desktop_services.list_media=AsyncMock(return_value={'sessions':[],'items':[]})
        server.desktop_services.displays=AsyncMock(return_value={'displays':[]})
        server.desktop_services.close=AsyncMock()
        server.desktop_services.assets.get.return_value=b'\x89PNG\r\n\x1a\n'+bytes(180000)
        server.text_service.close=AsyncMock();server.text_service.request=AsyncMock(return_value={'available':False,'message':'Synthetic field'})
        if public:
            server.browser_link.executable=Path('build/browser-link-helper/cloudflared.exe').absolute()
            server.browser_link._work_root=Path(work).absolute()/'helper'
        else:
            class Manager:
                active=True;origin=None
                def snapshot(self):return {'ready':self.active,'state':'ready' if self.active else 'stopped','origin':self.origin,'pairing_url':self.origin+'/#browser-link='+'s'*43 if self.active and self.origin else None,'message':'Synthetic','expires_in':120}
                def pairing_secret(self):return 's'*43 if self.active else None
                async def stop(self,*args):self.active=False;await server._browser_link_stopped()
            server.browser_link=manager=Manager()
        try:
            if public:
                await server.request_browser_link(True)
                task=server._browser_link_task
                if task:await asyncio.wait_for(asyncio.shield(task),150)
                snapshot=server.browser_link_status()
                if not snapshot['ready']:raise RuntimeError('Public bootstrap could not be verified')
                url=snapshot['pairing_url']
            else:
                await server.local_link.prepare()
                gateway=server.browser_gateway=BrowserLinkGateway(server,manager)
                manager.origin=await gateway.start()
                url=server.browser_link_status()['pairing_url']
            process=await asyncio.create_subprocess_exec('node',str(Path('tests/local_control_phone_check.cjs').absolute()),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            output,error=await asyncio.wait_for(process.communicate(json.dumps({'url':url}).encode()),100)
            report.update(json.loads(output))
            report['public_helper_stopped']=not server.browser_link.snapshot()['ready']
            report['public_gateway_closed']=server.browser_gateway is None
            report['native_mock_received_text']=any(call.args==('synthetic direct control',) for call in server.input_ctrl.type_text.call_args_list)
            report['no_real_native_services']=True
        except Exception as error:report['host_error_type']=type(error).__name__
        finally:
            await server.request_browser_link(False)
            for task in list(server._text_tasks.values())+list(server._service_tasks)+list(server._remote_tasks.values()):task.cancel()
            await server.remote.stop('Synthetic test ended.')
    print(json.dumps(report,sort_keys=True))
    return all(value is True for value in report.values()) and report.get('native_mock_received_text',False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--public',action='store_true');args=parser.parse_args()
    raise SystemExit(0 if asyncio.run(main(args.public)) else 1)
