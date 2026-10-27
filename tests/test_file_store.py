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
