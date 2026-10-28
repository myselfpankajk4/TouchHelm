"""Bounded local filesystem operations; all entry IDs are server-issued."""
from collections import OrderedDict
from contextlib import contextmanager, suppress
import ctypes
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import threading
from .file_handles import DirectoryLease,check_local,check_stat,needs_recall,open_local,rename_open_file,delete_open_file

CHUNK=1024**2
MAX_FILE=16*1024**3
PAGE=200
SCAN=50000
MIMES={'.pdf':('application/pdf','pdf'),'.jpg':('image/jpeg','image'),'.jpeg':('image/jpeg','image'),'.png':('image/png','image'),'.gif':('image/gif','image'),'.webp':('image/webp','image'),'.avif':('image/avif','image'),'.mp3':('audio/mpeg','audio'),'.m4a':('audio/mp4','audio'),'.aac':('audio/aac','audio'),'.adts':('audio/aac','audio'),'.wav':('audio/wav','audio'),'.ogg':('audio/ogg','audio'),'.flac':('audio/flac','audio'),'.mp4':('video/mp4','video'),'.webm':('video/webm','video'),'.mov':('video/quicktime','video')}


class FileError(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status


def filename(name):
    if not isinstance(name,str) or not name or len(name.encode('utf-16-le'))>480 or name[-1] in ' .' or any(ord(c)<32 or c in '<>:"/\\|?*' for c in name) or name in ('.','..'):
        raise FileError('Use a filename without slashes, reserved characters or trailing spaces.')
    if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]',name.split('.')[0],re.I):
        raise FileError('Choose a filename that is not a Windows device name.')
    return name


def known_locations():
    result=[]
    if os.name=='nt':
        import uuid
        from ctypes import wintypes
        ids={'desktop':'B4BFCC3A-DB2C-424C-B029-7FE99A87C641','downloads':'374DE290-123F-4565-9164-39C4925E467B','documents':'FDD39AD0-238F-46AF-ADB4-6C85480369C7','pictures':'33E28130-4E1E-4676-835A-98395C3BC3BB','music':'4BD8D571-6D19-48D3-BE97-422220080E43','videos':'18989B1D-99B5-455B-841C-AB7C74E4DDFC'}
        shell=ctypes.WinDLL('shell32');ole=ctypes.WinDLL('ole32')
        shell.SHGetKnownFolderPath.argtypes=[ctypes.c_void_p,wintypes.DWORD,wintypes.HANDLE,ctypes.POINTER(ctypes.c_void_p)]
        ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
        for kind,guid in ids.items():
            data=ctypes.create_string_buffer(uuid.UUID(guid).bytes_le);value=ctypes.c_void_p()
            if shell.SHGetKnownFolderPath(data,0x4000,None,ctypes.byref(value))==0:
                try:result.append({'name':kind.title(),'kind':kind,'path':Path(ctypes.wstring_at(value))})
                finally:ole.CoTaskMemFree(value)
        mask=ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            root=Path(chr(65+i)+':/')
            if mask&(1<<i) and ctypes.windll.kernel32.GetDriveTypeW(str(root)) in (2,3,5,6):
                result.append({'name':f'Local drive ({chr(65+i)}:)','kind':'drive','path':root})
    else:result=[{'name':'Home','kind':'documents','path':Path.home()}]
    return result


class FileStore:
    def __init__(self,roots=None,temporary=None):
        self.roots=roots;self.entries=OrderedDict();self.keys={};self.uploads={};self.lock=threading.RLock();self.denied=OrderedDict()
        self.temporary=Path(temporary) if temporary else Path(os.environ.get('LOCALAPPDATA',Path.home()))/'TouchHelm'/'file-transfers'
        self.temporary.mkdir(parents=True,exist_ok=True);self._recover()

    def _recover(self):
        for record in list(self.temporary.glob('*.json'))[:100]:
            remove_record=False;path=None
            try:
                item=json.loads(record.read_text(encoding='utf-8'));path=Path(item['partial'])
                if not re.fullmatch(r'\.touchhelm-[0-9a-f]{48}\.part',path.name):remove_record=True;continue
                with DirectoryLease(path.parent),open_local(path,write=True) as stream:
                    delete_open_file(stream,path)
                remove_record=True
            except FileNotFoundError:
                # Missing parent may be a disconnected drive; retain its journal.
                if path is not None and path.parent.exists():remove_record=True
            except (ValueError,KeyError,TypeError):remove_record=True
            except OSError:pass
            finally:
                if remove_record:
                    with suppress(OSError):record.unlink()

    def _register(self,path,root=None,kind=None,name=None):
        path=check_local(path);info=path.lstat();check_stat(info)
        key=(str(path).casefold(),str(root or path).casefold(),info.st_dev,info.st_ino)
        if key in self.keys:
            identifier=self.keys[key];self.entries.move_to_end(identifier);return identifier
        while len(self.entries)>=8192:
            old,value=self.entries.popitem(last=False);self.keys.pop(value['key'],None)
        identifier=secrets.token_urlsafe(18)
        self.entries[identifier]={'path':path,'root':root or path,'identity':(info.st_dev,info.st_ino),'key':key,'kind':kind,'name':name}
        self.keys[key]=identifier;return identifier

    def _entry(self,identifier):
        if not isinstance(identifier,str) or identifier not in self.entries:raise FileError('This location expired. Open This PC and choose it again.',404)
        item=self.entries[identifier];self.entries.move_to_end(identifier)
        info=item['path'].lstat();check_stat(info)
        if (info.st_dev,info.st_ino)!=item['identity']:raise FileError('This file changed. Refresh the folder and choose it again.',409)
        return item

    def locations(self):
        with self.lock:
            result=[]
            for root in self.roots if self.roots is not None else known_locations():
                try:
                    with DirectoryLease(root['path']):
                        identifier=self._register(root['path'],kind=root['kind'],name=root['name'])
                    result.append({'id':identifier,'name':root['name'],'kind':root['kind'],'directory':True})
                except OSError:continue
            return {'locations':result,'max_file_size':MAX_FILE,'chunk_size':CHUNK}

    def _describe(self,path,root,info=None):
        enumerated=info is not None
        info=info or path.lstat()
        mime,preview=MIMES.get(path.suffix.lower(),('application/octet-stream','download'))
        if needs_recall(getattr(info,'st_file_attributes',0),enumerated=enumerated):
            return {'id':None,'name':path.name,'directory':stat.S_ISDIR(info.st_mode),'size':info.st_size,'modified':info.st_mtime,'mime':mime,'preview':preview,'unavailable':'Make this file or folder available offline on the PC first.'}
        check_stat(info,enumerated=enumerated)
        return {'id':self._register(path,root),'name':path.name,'directory':stat.S_ISDIR(info.st_mode),'size':info.st_size,'modified':info.st_mtime,'mime':mime,'preview':preview,'kind':'folder' if stat.S_ISDIR(info.st_mode) else preview}

    def listing(self,identifier,query='',sort='name',offset=0,limit=PAGE):
        if not isinstance(query,str) or len(query)>200 or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=PAGE or sort not in ('name','size','date','type'):
            raise FileError('Choose a valid folder search or sort.')
        with self.lock:
            item=self._entry(identifier);path=item['path'];rows=[];limited=False
            with DirectoryLease(path):
                with os.scandir(path) as source:
                    for index,entry in enumerate(source):
                        if index>=SCAN:limited=True;break
                        if entry.name.startswith('.touchhelm-') or query.casefold() not in entry.name.casefold():continue
                        try:
                            info=entry.stat(follow_symlinks=False)
                            if needs_recall(getattr(info,'st_file_attributes',0),enumerated=True):
                                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_reparse_tag',0)&0x20000000:continue
                            else:check_stat(info,enumerated=True)
                            rows.append((entry.name,info))
                        except OSError:continue
                def order(row):
                    name,info=row
                    value={'name':name.casefold(),'size':info.st_size,'date':-info.st_mtime,'type':Path(name).suffix.casefold()}[sort]
                    return (not stat.S_ISDIR(info.st_mode),value,name.casefold())
                rows.sort(key=order)
                entries=[]
                for name,info in rows[offset:offset+limit]:
                    try:entries.append(self._describe(path/name,item['root'],info))
                    except FileNotFoundError:continue
                    except OSError:
                        entries.append({'id':None,'name':name,'directory':stat.S_ISDIR(info.st_mode),'size':info.st_size,'modified':info.st_mtime,'unavailable':'Windows cannot access this item. Check its permissions and offline availability on the PC.'})
                chain=[];part=path
                while True:
                    chain.append({'id':self._register(part,item['root'],name=item['name'] if part==item['root'] else None),'name':item['name'] if part==item['root'] and item['name'] else part.name or str(part)})
                    if part==item['root'] or part==part.parent:break
                    part=part.parent
                return {'entries':entries,'breadcrumbs':list(reversed(chain)),'id':identifier,'name':item['name'] or path.name or str(path),'writable':os.access(path,os.W_OK),'has_more':offset+limit<len(rows),'next_offset':offset+limit,'limited':limited,'total':len(rows)}

    @contextmanager
    def open_read(self,identifier):
        with self.lock:item=dict(self._entry(identifier))
        with DirectoryLease(item['path'].parent),open_local(item['path']) as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or (info.st_dev,info.st_ino)!=item['identity']:raise FileError('File changed. Refresh and try again.',409)
            yield stream

    def describe(self,identifier):
        with self.lock:
            item=self._entry(identifier);return self._describe(item['path'],item['root'])

    def mkdir(self,parent,name,allowed=None):
        name=filename(name)
        with self.lock:
            item=self._entry(parent)
            with DirectoryLease(item['path']):
                if allowed and not allowed():raise FileError('File access ended. Reconnect before creating a folder.',401)
                try:(item['path']/name).mkdir()
                except FileExistsError:raise FileError('That folder already exists. Choose another name.',409)
                return self._describe(item['path']/name,item['root'])

    def begin(self,owner,parent,name,size,allowed=None):
        name=filename(name)
        if type(size) is not int or not 0<=size<=MAX_FILE:raise FileError('Files can be up to 16 GiB each.')
        with self.lock:
            if owner in self.denied:raise FileError('File access ended. Reconnect before sending.',401)
            if sum(upload['owner']==owner for upload in self.uploads.values())>=2 or len(self.uploads)>=8:raise FileError('Finish or cancel an active transfer first.',429)
            item=dict(self._entry(parent));lease=DirectoryLease(item['path']);stream=None
            token=secrets.token_hex(24);partial=item['path']/f'.touchhelm-{token}.part';record=self.temporary/f'{token}.json'
            try:
                if shutil.disk_usage(item['path']).free<size+1024**2:raise FileError('Not enough free space in this PC folder. Choose another drive.',507)
                if owner in self.denied or allowed and not allowed():raise FileError('File access ended. Reconnect before sending.',401)
                record.write_text(json.dumps({'partial':str(partial)}),encoding='utf-8')
                stream=open_local(partial,write=True,create=True)
                self.uploads[token]={'owner':owner,'item':item,'lease':lease,'stream':stream,'partial':partial,'record':record,'name':name,'size':size,'offset':0}
                return {'id':token,'offset':0,'chunk_size':CHUNK,'size':size}
            except BaseException:
                if stream:stream.close()
                lease.close()
                with suppress(OSError):record.unlink()
                raise

    def _upload(self,owner,identifier):
        if owner in self.denied:raise FileError('File access ended. Reconnect before sending.',401)
        upload=self.uploads.get(identifier)
        if not upload or upload['owner']!=owner:raise FileError('This transfer expired. Choose the file and send again.',404)
        return upload

    def append(self,owner,identifier,offset,data):
        with self.lock:
            upload=self._upload(owner,identifier)
            if type(offset) is not int or offset!=upload['offset'] or not isinstance(data,bytes) or len(data)>CHUNK or offset+len(data)>upload['size']:
                raise FileError('Transfer position changed. Cancel and send this file again.',409)
            written=upload['stream'].write(data)
            if written!=len(data):raise FileError('The PC could not save this chunk. Check free space.',507)
            upload['offset']+=written;return {'offset':upload['offset']}

    def finish(self,owner,identifier):
        with self.lock:
            upload=self._upload(owner,identifier)
            if upload['offset']!=upload['size']:raise FileError('The file is incomplete. Finish sending or cancel.',409)
            # The original native directory lease stays held throughout all chunks.
            if upload['lease'].identity!=upload['item']['identity']:raise FileError('Destination changed. Choose it again.',409)
            stream=upload['stream'];stream.flush();os.fsync(stream.fileno())
            if owner in self.denied:raise FileError('File access ended. Reconnect before sending.',401)
            name=upload['name'];stem=Path(name).stem;suffix=Path(name).suffix
            for number in range(10000):
                candidate=name if number==0 else f'{stem} ({number}){suffix}'
                destination=upload['item']['path']/candidate
                try:rename_open_file(stream,upload['partial'],destination);break
                except FileExistsError:continue
            else:raise FileError('Too many files with this name. Choose another filename.',409)
            stream.close();upload['lease'].close();self.uploads.pop(identifier)
            with suppress(OSError):upload['record'].unlink()
            return self._describe(destination,upload['item']['root'])

    def cancel(self,owner,identifier):
        with self.lock:
            upload=self.uploads.get(identifier)
            if not upload or upload['owner']!=owner:raise FileError('Transfer already ended.',404)
            deleted=False
            try:delete_open_file(upload['stream'],upload['partial']);deleted=True
            finally:
                upload['stream'].close();upload['lease'].close();self.uploads.pop(identifier,None)
                if deleted:
                    with suppress(OSError):upload['record'].unlink()
            return {'cancelled':True}

    def revoke(self,owner):
        self.deny(owner)
        with self.lock:
            for identifier,upload in list(self.uploads.items()):
                if upload['owner']==owner:
                    with suppress(OSError,FileError):self.cancel(owner,identifier)

    def deny(self,owner):
        # Set before queuing disk cleanup, so an already queued write cannot win.
        self.denied[owner]=True
        if len(self.denied)>256:
            active={item['owner'] for item in list(self.uploads.values())}
            for old in list(self.denied):
                if old not in active:self.denied.pop(old,None);break

    def close(self):
        with self.lock:
            for upload in list(self.uploads.values()):self.revoke(upload['owner'])
