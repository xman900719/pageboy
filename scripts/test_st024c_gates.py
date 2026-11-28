"""Pure tests: no server, network, credentials or production paths used."""
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import st024c_local as c


class BundleGate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)
        (self.p/'postgres.dump').write_bytes(b'synthetic fixture')
        self.archive('blob.mp3')
        (self.p/'manifest.txt').write_text('timestamp_utc=2026-11-27T00:00:00Z\napp_revision='+c.APP+'\nmigration_revision=0023\nattachments_included=yes\nattachment_count=1\n')
        self.sums()
    def archive(self,name,kind=None):
        with tarfile.open(self.p/'attachments.tar.gz','w:gz') as t:
            m=tarfile.TarInfo(name)
            if kind: m.type=kind;m.linkname='elsewhere';t.addfile(m)
            else: m.size=3;t.addfile(m,io.BytesIO(b'abc'))
    def sums(self):
        (self.p/'SHA256SUMS').write_text(''.join(f'{c.sha(self.p/f)}  {f}\n' for f in c.FILES))
    def rejects(self):
        with self.assertRaises((RuntimeError,ValueError)): c.validate_bundle(self.p)
    def test_valid(self):
        self.assertEqual(c.validate_bundle(self.p)['migration_revision'],'0023')
    def test_missing_attachment(self):
        (self.p/'attachments.tar.gz').unlink();self.rejects()
    def test_bad_hash(self):
        (self.p/'postgres.dump').write_bytes(b'tampered');self.rejects()
    def test_manifest_count(self):
        p=self.p/'manifest.txt';p.write_text(p.read_text().replace('count=1','count=2'));self.rejects()
    def test_manifest_missing(self):
        (self.p/'manifest.txt').unlink();self.rejects()
    def test_checksum_path(self):
        p=self.p/'SHA256SUMS';p.write_text(p.read_text().replace('postgres.dump','../postgres.dump'));self.rejects()
    def test_duplicate_checksum(self):
        p=self.p/'SHA256SUMS';p.write_text(p.read_text()*2);self.rejects()
    def test_tar_escape(self):
        for name in ('../escape','/absolute','a/../../escape'):
            with self.subTest(name=name): self.archive(name);self.sums();self.rejects()
    def test_tar_link(self):
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.FIFOTYPE):
            with self.subTest(kind=kind): self.archive('x',kind);self.sums();self.rejects()
    def test_nonlocal_manifest(self):
        p=self.p/'manifest.txt';p.write_text(p.read_text().replace(c.APP,'api-real'));self.rejects()


class IsolationGate(unittest.TestCase):
    def test_wrong_root(self):
        for p in ('/tmp','/tmp/other','/not-a-drill','relative'):
            with self.subTest(path=p),self.assertRaises(RuntimeError):c.root_guard(p)
    def test_symlink_and_existing_target(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'keep').mkdir();(p/'link').symlink_to(p/'keep')
            for name in ('link','keep','../escape'):
                with self.subTest(name=name),self.assertRaises(RuntimeError):c.child(p,name,exists=False)
    def test_mismatched_server_id(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);m=p/'identity';m.write_text('{"id":"111"}')
            t=object.__new__(c.Target);t.root=p;t.mark=m
            with patch.object(t,'live_identity',return_value={'id':'222'}),self.assertRaises(RuntimeError):t.verify()
    def test_cleanup_must_verify(self):
        t=object.__new__(c.Target);t.started=True
        with patch.object(t,'verify',side_effect=RuntimeError('identity mismatch')),patch.object(c,'run') as run:
            with self.assertRaises(RuntimeError):t.stop()
            run.assert_not_called()
    def test_no_ambient_credentials(self):
        with patch.dict(os.environ,{'PGHOST':'sentinel','DATABASE_URL':'sentinel','RESTIC_REPOSITORY':'sentinel','AWS_ACCESS_KEY_ID':'sentinel','SHUTONG_ADMIN_TOKEN':'sentinel'}):
            e=c.clean_env(Path('/tmp/synthetic'))
            self.assertFalse(any(k in e for k in ('PGHOST','DATABASE_URL','RESTIC_REPOSITORY','AWS_ACCESS_KEY_ID','SHUTONG_ADMIN_TOKEN')))

if __name__=='__main__':unittest.main()
