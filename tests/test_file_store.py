"""File operations use temporary fixtures, never personal PC files."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


class FileStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('server.file_store'), 'Files engine has not been implemented')
        from server.file_store import FileStore, FileError
        self.Error=FileError
        self.work=tempfile.TemporaryDirectory(dir='build');self.addCleanup(self.work.cleanup)
        self.root=Path(self.work.name).absolute();self.disk=self.root/'disk';self.disk.mkdir()
        self.store=FileStore(roots=[{'name':'Downloads','path':self.disk,'kind':'downloads'}],temporary=self.root/'journal')
        self.addCleanup(self.store.close)
        self.location=self.store.locations()['locations'][0]['id']

    def test_list_search_sort_and_bounded_page_with_unicode(self):
        (self.disk/'Folder').mkdir()
        for name in ['भारत.pdf','music.mp3','z.txt']:(self.disk/name).write_bytes(b'abc')
        result=self.store.listing(self.location,offset=0,limit=2)
        self.assertEqual(len(result['entries']),2);self.assertTrue(result['has_more'])
        self.assertTrue(result['entries'][0]['directory'])
        result=self.store.listing(self.location,query='भारत')
        self.assertEqual(result['entries'][0]['name'],'भारत.pdf')
        self.assertEqual(result['entries'][0]['preview'],'pdf')

    def test_empty_unicode_upload_and_atomic_duplicate_names(self):
        for content in (b'',b'hello'*10000):
            upload=self.store.begin('phone',self.location,'नमस्ते.txt',len(content))
            self.store.append('phone',upload['id'],0,content)
            result=self.store.finish('phone',upload['id'])
            self.assertEqual((self.disk/result['name']).read_bytes(),content)
        self.assertEqual(len(list(self.disk.glob('*.txt'))),2)

    def test_extended_attributes_do_not_make_local_files_cloud_only(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        target=self.disk/'downloaded.pdf';target.write_bytes(b'local fixture')
        original=Path.lstat
        def lstat(path,*args,**kwargs):
            info=original(path,*args,**kwargs)
            if path!=target:return info
            fields={key:getattr(info,key,0) for key in ('st_mode','st_dev','st_ino','st_size','st_mtime','st_reparse_tag')}
            return SimpleNamespace(**fields,st_file_attributes=0x40020)
        with patch.object(Path,'lstat',lstat):
            entries=self.store.listing(self.location)['entries']
            self.assertEqual(entries[0]['name'],'downloaded.pdf')
            self.assertIsNotNone(entries[0]['id'])
            with self.store.open_read(entries[0]['id']) as source:self.assertEqual(source.read(),b'local fixture')

    def test_one_entry_losing_access_does_not_block_the_whole_folder(self):
        from unittest.mock import patch
        (self.disk/'available.txt').write_bytes(b'local')
        (self.disk/'changed.txt').write_bytes(b'local')
        original=self.store._register
        def register(path,*args,**kwargs):
            if path.name=='changed.txt':raise PermissionError('Entry no longer accessible')
            return original(path,*args,**kwargs)
        with patch.object(self.store,'_register',side_effect=register):
            entries=self.store.listing(self.location)['entries']
        self.assertIn('available.txt',[entry['name'] for entry in entries])
        changed=next(entry for entry in entries if entry['name']=='changed.txt')
        self.assertIsNone(changed['id']);self.assertTrue(changed['unavailable'])

    def test_recall_on_open_enumeration_is_still_disabled(self):
        from types import SimpleNamespace
        import stat
        info=SimpleNamespace(st_file_attributes=0x40000,st_reparse_tag=0,st_mode=stat.S_IFREG,st_size=100,st_mtime=0)
        entry=self.store._describe(self.disk/'virtual.pdf',self.disk,info)
        self.assertIsNone(entry['id']);self.assertIn('offline',entry['unavailable'])

    def test_upload_owner_offset_size_and_cancel(self):
        upload=self.store.begin('phone',self.location,'file.bin',4)
        for owner,offset,body in [('other',0,b'x'),('phone',1,b'x'),('phone',0,b'12345')]:
            with self.assertRaises(self.Error):self.store.append(owner,upload['id'],offset,body)
        with self.assertRaises(self.Error):self.store.finish('phone',upload['id'])
        self.store.append('phone',upload['id'],0,b'1234')
        self.store.cancel('phone',upload['id'])
        self.assertEqual(list(self.disk.iterdir()),[])

    def test_revocation_removes_partials_and_new_folder_is_non_destructive(self):
        self.store.begin('phone',self.location,'file.bin',8)
        self.store.revoke('phone')
        self.assertEqual(list(self.disk.iterdir()),[])
        folder=self.store.mkdir(self.location,'New folder')
        self.assertEqual(folder['name'],'New folder')
        with self.assertRaises(self.Error):self.store.mkdir(self.location,'New folder')

    def test_no_path_traversal_reserved_devices_or_large_allocations(self):
        for name in ['../x','a/b','a\\b','C:foo','CON','nul.txt','COM1.log','a.','a ','a\x00b']:
            with self.subTest(name=name),self.assertRaises(self.Error):self.store.begin('phone',self.location,name,1)
        for size in (-1,True,16*1024**3+1):
            with self.assertRaises(self.Error):self.store.begin('phone',self.location,'big.bin',size)
        with self.assertRaises(self.Error):self.store.listing('../')

    def test_read_identity_and_active_content_disposition(self):
        (self.disk/'bad.svg').write_text('<svg><script>alert(1)</script></svg>')
        entry=self.store.listing(self.location)['entries'][0]
        self.assertEqual(entry['preview'],'download')
        with self.store.open_read(entry['id']) as source:self.assertIn(b'<svg',source.read())
        (self.disk/'bad.svg').unlink();(self.disk/'bad.svg').write_bytes(b'replacement')
        with self.assertRaises(self.Error):
            with self.store.open_read(entry['id']):pass

    def test_aac_files_are_recognized_for_browser_audio_preview(self):
        (self.disk/'memo.aac').write_bytes(b'fixture')
        entry=self.store.listing(self.location)['entries'][0]
        self.assertEqual(entry['preview'],'audio');self.assertEqual(entry['mime'],'audio/aac')

    @unittest.skipUnless(os.name=='nt','Windows sharing semantics')
    def test_destination_cannot_be_renamed_while_upload_lease_is_open(self):
        target=self.store.mkdir(self.location,'target')
        upload=self.store.begin('phone',target['id'],'file.txt',1)
        with self.assertRaises(OSError):(self.disk/'target').rename(self.disk/'redirected')
        self.store.cancel('phone',upload['id'])

    def test_chunk_limit_and_concurrency_are_explicit(self):
        uploads=[self.store.begin('phone',self.location,f'{i}.bin',1024**2+1) for i in range(2)]
        with self.assertRaises(self.Error):self.store.begin('phone',self.location,'third',1)
        with self.assertRaises(self.Error):self.store.append('phone',uploads[0]['id'],0,bytes(1024**2+1))

    def test_recovery_keeps_journal_when_drive_is_temporarily_unavailable(self):
        from unittest.mock import patch
        upload=self.store.begin('phone',self.location,'abandoned.bin',1)
        record=self.store.uploads[upload['id']]['record']
        self.assertTrue(record.exists())
        with patch('server.file_store.DirectoryLease',side_effect=PermissionError('Drive unavailable')):self.store._recover()
        self.assertTrue(record.exists(),'Keep cleanup intent until the offline drive returns')

    def test_directory_name_collision_receives_a_numbered_filename(self):
        (self.disk/'name.txt').mkdir()
        upload=self.store.begin('phone',self.location,'name.txt',0)
        result=self.store.finish('phone',upload['id'])
        self.assertEqual(result['name'],'name (1).txt')

    def test_cloud_only_entry_is_visible_but_never_opened_or_hydrated(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import stat
        info=SimpleNamespace(st_file_attributes=0x400000,st_reparse_tag=0,st_mode=stat.S_IFREG,st_size=100,st_mtime=0)
        entry=SimpleNamespace(name='Cloud-only.pdf',stat=lambda **kw:info)
        class Scan:
            def __enter__(self):return iter([entry])
            def __exit__(self,*args):pass
        with patch('server.file_store.os.scandir',return_value=Scan()),patch('server.file_store.open_local') as opening:
            result=self.store.listing(self.location)
        self.assertEqual(result['entries'][0]['name'],'Cloud-only.pdf')
        self.assertIn('offline',result['entries'][0]['unavailable'])
        self.assertIsNone(result['entries'][0]['id']);opening.assert_not_called()

    def test_disk_full_start_leaves_no_partial_file(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        with patch('server.file_store.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaises(self.Error) as failure:self.store.begin('phone',self.location,'file.bin',100)
        self.assertEqual(failure.exception.status,507);self.assertEqual(list(self.disk.iterdir()),[])

    def test_startup_recovers_an_abandoned_upload(self):
        from server.file_store import FileStore
        upload=self.store.begin('phone',self.location,'abandoned.bin',100)
        item=self.store.uploads.pop(upload['id']);item['stream'].close();item['lease'].close()
        recovered=FileStore(roots=[],temporary=self.root/'journal');recovered.close()
        self.assertEqual(list(self.disk.iterdir()),[])
        self.assertEqual(list((self.root/'journal').glob('*.json')),[])

    @unittest.skipUnless(os.name=='nt','Windows NTFS junction boundary')
    def test_a_replaced_parent_junction_is_rejected_even_with_the_same_file_identity(self):
        import subprocess
        target=self.disk/'target';target.mkdir();(target/'safe.txt').write_bytes(b'fixture')
        folder=self.store.listing(self.location)['entries'][0]
        entry=self.store.listing(folder['id'])['entries'][0]
        parked=self.disk/'parked';target.rename(parked)
        outside=self.root/'outside';outside.mkdir();os.link(parked/'safe.txt',outside/'safe.txt')
        self.assertTrue(target.is_relative_to(self.root) and outside.is_relative_to(self.root))
        result=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(target),str(outside)],capture_output=True)
        if result.returncode:self.skipTest('Junction creation is unavailable on this test filesystem')
        try:
            with self.assertRaises((self.Error,PermissionError)):
                with self.store.open_read(entry['id']):pass
        finally:
            self.assertTrue(target.is_junction());target.rmdir()
