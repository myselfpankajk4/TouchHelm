"""Local HTTP browser integration: generated files/media; native effects mocked."""
import asyncio
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import Mock,AsyncMock,patch
from server.config import ConfigManager
from server.web_server import TouchHelmServer
from server.file_store import FileStore
from server.discovery import get_local_ip_addresses
from tests.synthetic_media import GeneratedCapture,GeneratedAudio


async def main():
    with tempfile.TemporaryDirectory(dir='build',prefix='files-browser-') as work:
        root=Path(work).absolute();disk=root/'Downloads';disk.mkdir();(root/'Documents').mkdir()
        (root/'Pictures').mkdir();(root/'Videos').mkdir()
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',b'<< /Length 49 >>\nstream\nBT /F1 18 Tf 35 330 Td (Local PDF preview) Tj ET\nendstream',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
        pdf=b'%PDF-1.4\n';offsets=[]
        for index,body in enumerate(objects,1):offsets.append(len(pdf));pdf+=f'{index} 0 obj\n'.encode()+body+b'\nendobj\n'
        xref=len(pdf);pdf+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
        (disk/'Travel guide.pdf').write_bytes(pdf)
        import av
        from fractions import Fraction
        with av.open(str(disk/'Evening mix.mp3'),'w') as output:
            audio=output.add_stream('mp3',rate=48000)
            for i in range(90):
                frame=av.AudioFrame(format='s16p',layout='stereo',samples=1152);frame.sample_rate=48000;frame.pts=i*1152;frame.time_base=Fraction(1,48000)
                for plane in frame.planes:plane.update(bytes(plane.buffer_size))
                for packet in audio.encode(frame):output.mux(packet)
            for packet in audio.encode():output.mux(packet)
        with av.open(str(disk/'Voice memo.aac'),'w',format='adts') as output:
            audio=output.add_stream('aac',rate=48000)
            for i in range(120):
                frame=av.AudioFrame(format='fltp',layout='stereo',samples=1024);frame.sample_rate=48000;frame.pts=i*1024;frame.time_base=Fraction(1,48000)
                for plane in frame.planes:plane.update(bytes(plane.buffer_size))
                for packet in audio.encode(frame):output.mux(packet)
            for packet in audio.encode():output.mux(packet)
        for name,width,height in [('Weekend.mp4',320,180),('Portrait.mp4',360,640)]:
            with av.open(str(disk/name),'w') as output:
                video=output.add_stream('libx264',rate=10);video.width=width;video.height=height;video.pix_fmt='yuv420p'
                for i in range(40):
                    frame=av.VideoFrame(width,height,'yuv420p');frame.pts=i;frame.time_base=Fraction(1,10)
                    for index,plane in enumerate(frame.planes):plane.update(bytes([90+i if index==0 else 128])*plane.buffer_size)
                    for packet in video.encode(frame):output.mux(packet)
                for packet in video.encode():output.mux(packet)
        (disk/'Picture.png').write_bytes(__import__('base64').b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='))
        config=ConfigManager(str(root/'config.json'))
        with socket.socket() as probe:probe.bind(('0.0.0.0',0));port=probe.getsockname()[1]
        config.update({'server_name':'Test PC','port':port,'require_pin':True,'pin_code':'5678','files_enabled':True,'remote_enabled':True})
        with patch('server.web_server.WindowsInputController'),patch('server.web_server.LaserOverlayClient'),patch('server.web_server.DesktopServices'):
            server=TouchHelmServer(config)
        server.files.store=FileStore(roots=[{'path':disk,'name':'Downloads','kind':'downloads'},
            {'path':root/'Documents','name':'Documents','kind':'documents'},
            {'path':root/'Pictures','name':'Pictures','kind':'pictures'},
            {'path':root/'Videos','name':'Videos','kind':'videos'},
            {'path':root,'name':'Test drive','kind':'drive'}],temporary=root/'journal')
        server._log_event=lambda *args:None
        server.input_ctrl.get_volume.return_value=(50,False);server.input_ctrl.get_brightness.return_value=None
        server.input_ctrl.get_screen_size.return_value=(1920,1080)
        server.desktop_services.snapshot=AsyncMock(return_value={'media':{'available':False},'presentation':{'available':False}})
        server.desktop_services.list_apps=AsyncMock(return_value=[]);server.desktop_services.list_media=AsyncMock(return_value={'sessions':[],'items':[]})
        server.desktop_services.close=AsyncMock();server.desktop_services.displays=AsyncMock(return_value={'displays':[]})
        server.text_service.close=AsyncMock();server.text_service.request=AsyncMock(return_value={'available':False})
        from server.remote_media import MediaWorker
        capture=patch('server.remote_media.DesktopCapture',GeneratedCapture);capture.start()
        audio=patch('server.remote_media.AudioSource',GeneratedAudio);audio.start()
        media_trace=[]
        from server.remote_media import media_peer_matches as original_match
        def match(pc,peer):
            result=original_match(pc,peer)
            if not result:
                try:
                    hosts=[pair.remote_candidate.host for transceiver in pc.getTransceivers() for pair in transceiver.sender.transport.transport._connection._nominated.values()]
                    local=get_local_ip_addresses();media_trace.append({'expected_is_this_pc':peer in local,'selected_is_this_pc':all(host in local for host in hosts),'candidate_count':len(hosts)})
                except Exception as error:media_trace.append({'peer_check_error':type(error).__name__})
            return result
        matching=patch('server.remote_media.media_peer_matches',side_effect=match);matching.start()
        def worker(**options):
            callback=options['on_state']
            def event(state,message):
                if state!='cursor':media_trace.append({'state':state,'message':str(message)[:160]})
                callback(state,message)
            return MediaWorker(**dict(options,on_state=event))
        server.remote.worker_factory=worker
        server.remote.capabilities=lambda:{'video':True,'audio':True}
        server.remote.displays=AsyncMock(return_value={'displays':[{'id':'synthetic','name':'Generated display','rect':{'x':0,'y':0,'width':640,'height':360}}]})
        try:
            await server.start()
            url=f'http://{get_local_ip_addresses()[0]}:{port}/'
            process=await asyncio.create_subprocess_exec('node',str(Path('tests/offline_files_phone_check.cjs').absolute()),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            output,error=await asyncio.wait_for(process.communicate(json.dumps({'url':url}).encode()),180)
            if output:print(output.decode().strip())
            if error:print(error.decode().strip())
            if process.returncode:
                print(json.dumps({'generated_media_trace':media_trace[-8:]}))
                raise RuntimeError('Offline browser check failed')
            assert (disk/'phone file.bin').read_bytes()==bytes(range(256))*10000
            assert (disk/'phone file (1).bin').read_bytes()==bytes(range(256))*10000
            assert not (disk/'cancel me.bin').exists()
            assert not list(disk.glob('.touchhelm-*.part'))
            assert any(call.args==('synthetic local file control',) for call in server.input_ctrl.type_text.call_args_list)
        finally:
            await server.stop();capture.stop();audio.stop();matching.stop()


if __name__=='__main__':asyncio.run(main())
