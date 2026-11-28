import hashlib, json, io, tarfile, tempfile, unittest, os
from pathlib import Path
import exam_bank_backup as b

class BackupTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.p=Path(t.name)
        self.root=self.p/b.NAME; self.root.mkdir(); self.archive=self.p/b.ARCHIVE
        self.entries=[]; self.rows=[]
        for i,(y,s) in enumerate(sorted(b.GROUPS)):
            key=f'{i:032x}'; sid=f'synthetic-source-{i}'; aid=f'synthetic-attachment-{i}'; raw=b'SYNTHETIC TEST DATA'; sha=hashlib.sha256(raw).hexdigest()
            a=dict(id=aid,source_document_id=sid,storage_key=key,sha256=sha,byte_size=len(raw)); base=f'{y}/{s}'
            structured=json.dumps(dict(source_documents=[dict(id=sid)],source_attachments=[a],questions=[dict(source_document_id=sid)])).encode()
            e=dict(attachment_id=aid,source_document_id=sid,storage_key=key,sha256=sha,bytes=len(raw),raw=f'{base}/raw/{key}.docx',processed=f'{base}/processed/questions.json',processed_sha256=hashlib.sha256(structured).hexdigest())
            for n,data in ((e['raw'],raw),(e['processed'],structured)):
                p=self.root/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
            (self.root/base/'validation').mkdir(); self.entries.append(e); self.rows.append([aid,sid,key,sha,len(raw),int(y),s,'confirmed',True,'北京市中考 SYNTHETIC'])
        self.m=dict(format_version=1,environment='production',entries=self.entries,source_count=32,attachment_count=32,attachment_bytes=sum(e['bytes'] for e in self.entries),question_count=32)
        self.repin()
    def repin(self):
        raw=json.dumps(self.m).encode(); (self.root/'manifest.json').write_bytes(raw); self.pin=hashlib.sha256(raw).hexdigest()
    def capture(self): b.capture(self.root,self.archive,self.pin,self.rows)
    def test_capture(self): self.capture(); self.assertEqual(b.validate_archive(self.archive,self.pin,self.rows),self.m)
    def test_wrong_pin(self):
        with self.assertRaises(ValueError): b.capture(self.root,self.archive,'0'*64,self.rows)
    def test_wrong_db(self):
        self.rows[0][0]='wrong'
        with self.assertRaises(ValueError): self.capture()
    def test_missing(self):
        (self.root/self.entries[0]['raw']).unlink()
        with self.assertRaises(ValueError): self.capture()
    def test_corrupt(self):
        (self.root/self.entries[0]['raw']).write_bytes(b'wrong')
        with self.assertRaises(ValueError): self.capture()
        self.assertFalse(self.archive.exists())
    def test_structured_corrupt(self):
        (self.root/self.entries[0]['processed']).write_bytes(b'{}')
        with self.assertRaises(ValueError): self.capture()
    def test_link(self):
        p=self.root/self.entries[0]['raw']; p.unlink(); p.symlink_to(self.root/self.entries[1]['raw'])
        with self.assertRaises(ValueError): self.capture()
    def test_duplicate(self):
        self.m['entries'][1]=self.m['entries'][0]; self.repin()
        with self.assertRaises(ValueError): self.capture()
    def test_wrong_env(self):
        self.m['environment']='development'; self.repin()
        with self.assertRaises(ValueError): self.capture()
    def test_mount(self):
        m=dict(Destination=b.DEST,Source=str(self.root),Type='bind',RW=False)
        b.mount_check(json.dumps([m]),self.root,'active'); b.mount_check('[]',self.root,'staged')
        for bad in ([dict(m,RW=True)],[],[m,dict(m,Destination=b.DEST+'/nested')]):
            with self.assertRaises(ValueError): b.mount_check(json.dumps(bad),self.root,'active')
    def test_tar_traversal(self):
        with tarfile.open(self.archive,'w:gz') as t:
            e=tarfile.TarInfo('../escape'); e.size=1; t.addfile(e,io.BytesIO(b'x'))
        with self.assertRaises(ValueError): b.validate_archive(self.archive,self.pin)
    def test_bundle_and_restore(self):
        import web_artifact_provenance as w
        self.capture(); bundle=self.p/'bundle'; bundle.mkdir(); self.archive.rename(bundle/b.ARCHIVE)
        dist=self.p/'dist'; dist.mkdir(); (dist/'assets').mkdir()
        for n in ('index.html','admin.html','assets/a.js'): (dist/n).write_text('synthetic')
        record=self.p/'record.json'; d,n=w.tree(dist); record.write_text(json.dumps(dict(format=1,source_git_sha='a'*40,tree_sha256=d,file_count=n,built_at_utc='2026-11-28T00:00:00Z')))
        m=w.archive_tree(dist,record,bundle/'web-dist.tar.gz'); m.update(timestamp_utc='2026-11-28T00:00:00Z',app_revision='api-aaaaaaa',migration_revision='0023',attachments_included='yes',attachment_count='1',artifact_format='3',api_git_sha='a'*40,api_image_id='sha256:'+'b'*64,exam_bank_manifest_sha256=self.pin)
        (bundle/'postgres.dump').write_bytes(b'synthetic')
        with tarfile.open(bundle/'attachments.tar.gz','w:gz') as t:
            e=tarfile.TarInfo('blob');e.size=3;t.addfile(e,io.BytesIO(b'abc'))
        (bundle/'manifest.txt').write_text(''.join(f'{k}={v}\n' for k,v in m.items()))
        def sums():
            (bundle/'SHA256SUMS').write_text(''.join(f'{w.sha(p)}  {p.name}\n' for p in sorted(bundle.iterdir()) if p.name!='SHA256SUMS'))
        sums(); self.assertEqual(w.validate_bundle(bundle),m)
        out=self.p/'restored'; b.restore(bundle,out); self.assertEqual((out/'manifest.json').read_bytes(),(self.root/'manifest.json').read_bytes())
        with self.assertRaises(ValueError): b.restore(bundle,out)
        w.restore_web(bundle,self.p/'web-restored')
        (bundle/b.ARCHIVE).write_bytes(b'bad'); sums()
        with self.assertRaises((ValueError,tarfile.TarError)): w.validate_bundle(bundle)

if __name__=='__main__': unittest.main()
