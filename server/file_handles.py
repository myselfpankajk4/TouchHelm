"""Local Windows file leases. No elevation, network paths or cloud recall."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import stat


def check_local(path):
    path=Path(path)
    if not path.is_absolute() or str(path).startswith(('\\\\','//')):
        raise PermissionError('Choose a local PC folder.')
    if os.name=='nt':
        drive=ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor))
        if drive not in (2,3,5,6):raise PermissionError('Network drives are not available in local Files.')
    return path


def check_stat(info):
    if stat.S_ISLNK(info.st_mode) or getattr(info,'st_reparse_tag',0)&0x20000000:
        raise PermissionError('Linked folders and files are not shared. Open their original local location.')
    if getattr(info,'st_file_attributes',0)&(0x1000|0x40000|0x400000):
        raise PermissionError('Make this file or folder available offline on the PC first.')
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        raise PermissionError('Only ordinary local files and folders are available.')


if os.name=='nt':
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    api.CreateFileW.restype=wintypes.HANDLE
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    api.GetFileInformationByHandleEx.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    api.SetFileInformationByHandle.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]


def _native_open(path,access,creation=3):
    # Never follow the final reparse point; ancestors are individually leased.
    handle=api.CreateFileW('\\\\?\\'+str(path),access,1,None,creation,0x02000000|0x00200000|0x00100000,None)
    if handle==wintypes.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        tags=(wintypes.DWORD*2)()
        if not api.GetFileInformationByHandleEx(handle,9,ctypes.byref(tags),ctypes.sizeof(tags)):
            raise ctypes.WinError(ctypes.get_last_error())
        if tags[0]&(0x1000|0x40000|0x400000) or tags[1]&0x20000000:
            raise PermissionError('This location is linked or needs an online download. Choose its offline original.')
        return handle
    except BaseException:
        api.CloseHandle(handle);raise


class DirectoryLease:
    """Hold every directory component without delete/write sharing until close."""
    def __init__(self,path):
        self.path=check_local(path);self.handles=[]
        try:
            for item in [*reversed(self.path.parents),self.path]:
                if os.name=='nt':self.handles.append(_native_open(item,0x80))
                info=item.lstat();check_stat(info)
                if not stat.S_ISDIR(info.st_mode):raise NotADirectoryError()
            self.identity=(info.st_dev,info.st_ino)
        except BaseException:self.close();raise

    def close(self):
        for handle in reversed(self.handles):api.CloseHandle(handle)
        self.handles=[]

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def open_local(path,*,write=False,create=False):
    """Caller holds a DirectoryLease on parent; returned handle owns its identity."""
    path=check_local(path)
    if os.name=='nt':
        import msvcrt
        handle=_native_open(path,0x80000000|(0x40000000|0x10000 if write else 0),1 if create else 3)
        try:fd=msvcrt.open_osfhandle(handle,os.O_BINARY|(os.O_RDWR if write else os.O_RDONLY))
        except BaseException:api.CloseHandle(handle);raise
    else:
        fd=os.open(path,(os.O_RDWR if write else os.O_RDONLY)|getattr(os,'O_NOFOLLOW',0)|(os.O_CREAT|os.O_EXCL if create else 0),0o600)
    try:
        check_stat(os.fstat(fd))
        return os.fdopen(fd,'r+b' if write else 'rb',buffering=0)
    except BaseException:os.close(fd);raise


def rename_open_file(stream,source,destination):
    if os.name!='nt':
        os.link(source,destination,follow_symlinks=False);os.unlink(source);return
    import msvcrt
    class Rename(ctypes.Structure):
        _fields_=[('flags',wintypes.DWORD),('root',wintypes.HANDLE),('length',wintypes.DWORD),('name',wintypes.WCHAR*1)]
    name=str(destination).encode('utf-16-le')
    buffer=ctypes.create_string_buffer(Rename.name.offset+len(name)+2)
    header=Rename.from_buffer(buffer);header.flags=0;header.root=None;header.length=len(name)
    ctypes.memmove(ctypes.addressof(buffer)+Rename.name.offset,name,len(name))
    if not api.SetFileInformationByHandle(msvcrt.get_osfhandle(stream.fileno()),3,buffer,len(buffer)):
        error=ctypes.get_last_error()
        if error in (80,183):raise FileExistsError()
        raise ctypes.WinError(error)


def delete_open_file(stream,path):
    if os.name=='nt':
        import msvcrt
        flag=wintypes.BOOL(True)
        if not api.SetFileInformationByHandle(msvcrt.get_osfhandle(stream.fileno()),4,ctypes.byref(flag),ctypes.sizeof(flag)):
            raise ctypes.WinError(ctypes.get_last_error())
    else:os.unlink(path)
