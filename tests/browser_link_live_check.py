"""Opt-in real HTTPS/WSS smoke test. Synthetic host only; no native PC services.

Run with an already hash-verified --helper. Never prints the assigned hostname,
QR token or cookie. Does not change certificate stores or start TouchHelm.
"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from aiohttp import ClientSession, web
from server.browser_link import BrowserLinkManager
from server.browser_gateway import BrowserLinkGateway


async def check(helper,phone=False):
    report={}
    with tempfile.TemporaryDirectory(prefix='browser-probe-',dir=Path('build')) as work:
        manager=BrowserLinkManager(executable=helper,work_root=Path(work).absolute(),startup_timeout=55)
        async def index(request):
            source=Path('web/index.html').read_text(encoding='utf-8').replace('__TOUCHHELM_BUILD__','synthetic-probe')
            return web.Response(text=source,content_type='text/html')
        async def info(request):return web.json_response({'synthetic':True})
        async def socket(request):
            ws=web.WebSocketResponse();await ws.prepare(request)
            await ws.send_json({'type':'auth_required'})
            async for message in ws:
                if message.type==web.WSMsgType.TEXT and message.json().get('type')=='auth' and message.json().get('pin')=='5678':
                    await ws.send_json({'type':'auth_res','success':True,'synthetic':True})
            return ws
        async def version(request):return web.json_response({'build':'synthetic-probe'})
        owner=SimpleNamespace(handle_index=index,handle_info=info,handle_ws=socket,handle_version=version)
        gateway=BrowserLinkGateway(owner,manager)
        try:
            backend=await gateway.start()
            snapshot=await manager.start(backend)
            report['helper_ready']=snapshot['ready']
            origin=snapshot['origin']
            async with ClientSession() as client:
                # Wait for the new hostname to propagate without weakening TLS.
                last='not attempted'
                for attempt in range(15):
                    try:
                        async with client.get(origin+'/',timeout=12) as response:
                            last=str(response.status)
                            if response.status==200:
                                report['trusted_https']=True
                                report['gate_present']='touchhelm-browser-link' in await response.text()
                                break
                    except Exception as error:last=type(error).__name__
                    await asyncio.sleep(2)
                if not report.get('trusted_https'):
                    report['https_failure']=last
                    raise RuntimeError('HTTPS propagation or connection failed')
                async with client.get(origin+'/api/info') as response:report['pin_alone_blocked']=response.status==401
                ticket=snapshot['pairing_url'].split('browser-link=')[1]
                async with client.post(origin+'/api/browser-link/pair',headers={'Origin':origin},json={'token':ticket}) as response:
                    report['one_use_pairing']=response.status==200
                    cookie=response.cookies.get('th_browser_link')
                    report['secure_cookie']=bool(cookie and cookie['secure'] and cookie['httponly'] and cookie['samesite']=='Strict')
                async with client.get(origin+'/api/info') as response:report['cookie_authorized']=response.status==200 and (await response.json()).get('synthetic') is True
                async with client.ws_connect(origin+'/ws',origin=origin) as ws:
                    report['pin_required']=(await ws.receive_json(timeout=10))['type']=='auth_required'
                    await ws.send_json({'type':'auth','pin':'5678'})
                    report['trusted_wss_roundtrip']=(await ws.receive_json(timeout=10)).get('success') is True
                async with client.post(origin+'/api/browser-link/pair',headers={'Origin':origin},json={'token':ticket}) as response:report['replay_blocked']=response.status==401
                for route in ('/sw.js','/api/pairing/certificate','/preview/desktop/'):
                    async with client.get(origin+route) as response:report['blocked_'+route]=response.status==404
                if phone:
                    fresh=manager.rotate_ticket()['pairing_url']
                    process=await asyncio.create_subprocess_exec('node',str(Path('tests/browser_link_phone_check.cjs').absolute()),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                    output,_=await asyncio.wait_for(process.communicate(json.dumps({'url':fresh}).encode()),90)
                    result=json.loads(output)
                    report.update({'phone_'+key:value for key,value in result.items()})
        except Exception as error:
            report['error_type']=type(error).__name__
        finally:
            await manager.stop()
            await gateway.close()
            report['owned_helper_stopped']=manager._process is None
    print(json.dumps(report,sort_keys=True))
    return all(value is True for value in report.values()) and report.get('trusted_wss_roundtrip',False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--helper',type=Path,required=True);parser.add_argument('--phone',action='store_true')
    args=parser.parse_args()
    raise SystemExit(0 if asyncio.run(check(args.helper.absolute(),args.phone)) else 1)
