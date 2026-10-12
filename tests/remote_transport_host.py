"""Opt-in local transport probe: real capture/audio, mocked PC input, no recordings.
Run through remote_transport_check.cjs. Never included in test discovery.
"""
import asyncio
import datetime
import json
import secrets
import ssl
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from aiohttp import web
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes, serialization
from server.config import ConfigManager
from server.web_server import TouchHelmServer


async def main():
    import dxcam
    displays=[]
    for group in dxcam.__dict__['__factory'].outputs:
        for output in group:
            d=output.desc;r=d.DesktopCoordinates
            displays.append({'id':d.DeviceName,'name':d.DeviceName,'rect':{'x':r.left,'y':r.top,'width':r.right-r.left,'height':r.bottom-r.top}})
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder);config=ConfigManager(str(path/'config.json'))
        config.update({'require_pin':True,'pin_code':'5678','remote_enabled':True})
        with patch('server.web_server.WindowsInputController'),patch('server.web_server.LaserOverlayClient'),patch('server.web_server.DesktopServices'):
            server=TouchHelmServer(config)
        server.input_ctrl.get_volume.return_value=(50,False)
        server.input_ctrl.get_brightness.return_value=None
        server.input_ctrl.get_screen_size.return_value=(1920,1080)
        server.desktop_services.displays=AsyncMock(return_value={'displays':displays})
        server.remote.displays=server.desktop_services.displays
        original_notify=server.remote.notify
        def diagnostics(state):
            print('PROBE MEDIA '+json.dumps({k:state.get(k) for k in ('state','message','mode','audio')}),flush=True)
            original_notify(state)
        server.remote.notify=diagnostics
        server.desktop_services.close=AsyncMock()
        done=asyncio.Event();token=secrets.token_urlsafe(24)
        async def shutdown(request):
            if request.headers.get('X-Probe-Token')!=token:return web.Response(status=403)
            done.set();return web.json_response({'success':True})
        app=web.Application(middlewares=[server._private_transport])
        async def diagnostic_ws(request):
            try:return await server.handle_ws(request)
            except BaseException:
                import traceback
                traceback.print_exc();raise
        app.router.add_get('/ws',diagnostic_ws)
        app.router.add_get('/api/info',server.handle_info)
        app.router.add_get('/api/version',server.handle_version)
        app.router.add_get('/shutdown',shutdown)
        app.router.add_get('/',server.handle_index)
        app.router.add_static('/',Path(__file__).resolve().parents[1]/'web')
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),False).sign(key,hashes.SHA256())
        (path/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (path/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(path/'cert.pem',path/'key.pem')
        runner=web.AppRunner(app);await runner.setup()
        site=web.TCPSite(runner,'127.0.0.1',0,ssl_context=tls);await site.start()
        port=site._server.sockets[0].getsockname()[1]
        print(json.dumps({'probe_url':f'https://localhost:{port}','token':token}),flush=True)
        try:await asyncio.wait_for(done.wait(),120)
        finally:
            await server.remote.stop('Probe finished.')
            for task in server._remote_tasks.values():task.cancel()
            await asyncio.gather(*server._remote_tasks.values(),return_exceptions=True)
            await runner.cleanup()


if __name__=='__main__':asyncio.run(main())
