import hashlib
import io
import os
import subprocess
from unittest.mock import patch
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import web_artifact_provenance as w


class ArtifactTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.p=Path(t.name)
        self.dist=self.p/'dist'; self.dist.mkdir(); (self.dist/'assets').mkdir()
        for n in ('index.html','admin.html','assets/a.js'): (self.dist/n).write_text('synthetic '+n)
        self.record=self.p/'record.json'; self.bundle=self.p/'bundle'; self.bundle.mkdir()
    def write_record(self):
        d,n=w.tree(self.dist); self.record.write_text(json.dumps(dict(format=1,source_git_sha='a'*40,tree_sha256=d,file_count=n,built_at_utc='2026-11-27T00:00:00Z')))
    def bundle_setup(self, recorded=True):
        if recorded: self.write_record()
        m=w.archive_tree(self.dist,self.record,self.bundle/'web-dist.tar.gz')
        m.update(timestamp_utc='2026-11-27T00:00:00Z',app_revision='api-aaaaaaa',migration_revision='0023',attachments_included='yes',attachment_count='1',artifact_format='2',api_git_sha='a'*40,api_image_id='sha256:'+'b'*64)
        (self.bundle/'postgres.dump').write_bytes(b'synthetic')
        with tarfile.open(self.bundle/'attachments.tar.gz','w:gz') as t:
            entry=tarfile.TarInfo('blob'); entry.size=3; t.addfile(entry,io.BytesIO(b'abc'))
        (self.bundle/'manifest.txt').write_text(''.join(f'{k}={v}\n' for k,v in m.items()))
        self.sums(); return m
    def sums(self):
        (self.bundle/'SHA256SUMS').write_text(''.join(f'{w.sha(self.bundle/n)}  {n}\n' for n in sorted(w.BASE_FILES|{'manifest.txt','web-dist.tar.gz'})))
    def test_roundtrip(self):
        m=self.bundle_setup(); self.assertEqual(w.validate_bundle(self.bundle),m)
        w.restore_web(self.bundle,self.p/'out'); self.assertEqual(w.tree(self.dist),w.tree(self.p/'out'))
    def test_legacy_source_unknown(self):
        self.assertEqual(self.bundle_setup(False)['web_source_git_sha'],w.UNKNOWN)
        self.assertEqual(w.restore_web(self.bundle,self.p/'out')['web_source_git_sha'],w.UNKNOWN)
    def test_tampered_record(self):
        self.write_record(); (self.dist/'index.html').write_text('tampered')
        with self.assertRaises(ValueError): w.archive_tree(self.dist,self.record,self.p/'archive')
    def test_root_link(self):
        p=self.p/'link'; p.symlink_to(self.dist)
        with self.assertRaises(ValueError): w.tree(p)
    def test_nested_link(self):
        (self.dist/'assets'/'link').symlink_to(self.dist/'index.html')
        with self.assertRaises(ValueError): w.tree(self.dist)
    def test_hardlink(self):
        (self.dist/'alias').hardlink_to(self.dist/'index.html')
        with self.assertRaises(ValueError): w.tree(self.dist)
    def test_nonempty(self):
        self.bundle_setup(); p=self.p/'out';p.mkdir();(p/'keep').write_text('keep')
        with self.assertRaises(ValueError): w.restore_web(self.bundle,p)
        self.assertEqual((p/'keep').read_text(),'keep')
    def test_destination_symlink(self):
        self.bundle_setup();p=self.p/'out';p.symlink_to(self.dist)
        with self.assertRaises(ValueError): w.restore_web(self.bundle,p)
    def test_manifest_hash(self):
        self.bundle_setup();p=self.bundle/'manifest.txt';p.write_text(p.read_text().replace('0023','0022'))
        with self.assertRaises(ValueError): w.validate_bundle(self.bundle)
    def test_attachment_invalid_archive(self):
        self.bundle_setup(); (self.bundle/'attachments.tar.gz').write_bytes(b'not a tar'); self.sums()
        with self.assertRaises((ValueError,tarfile.TarError)): w.validate_bundle(self.bundle)
    def test_attachment_unsafe_archive(self):
        self.bundle_setup()
        for names,kind in [(['../escape'],tarfile.REGTYPE),(['/absolute'],tarfile.REGTYPE),(['link'],tarfile.SYMTYPE),(['hard'],tarfile.LNKTYPE),(['pipe'],tarfile.FIFOTYPE),(['blob','./blob'],tarfile.REGTYPE)]:
            with self.subTest(names=names,kind=kind):
                with tarfile.open(self.bundle/'attachments.tar.gz','w:gz') as t:
                    for name in names:
                        m=tarfile.TarInfo(name); m.type=kind; t.addfile(m,io.BytesIO(b''))
                self.sums()
                with self.assertRaises(ValueError): w.validate_bundle(self.bundle)
    def test_attachment_count(self):
        self.bundle_setup(); p=self.bundle/'manifest.txt'; p.write_text(p.read_text().replace('attachment_count=1','attachment_count=2')); self.sums()
        with self.assertRaises(ValueError): w.validate_bundle(self.bundle)
    def test_mount_type_and_cardinality(self):
        mount={'Type':'bind','Source':str(self.p),'Destination':'/var/lib/shutong/attachments'}
        w.verify_mount(json.dumps([mount]),self.p)
        for mounts in ([],[mount,mount],[dict(mount,Type='volume')],[dict(mount,Source='/wrong')]):
            with self.assertRaises(ValueError): w.verify_mount(json.dumps(mounts),self.p)
    def test_manifest_tree(self):
        self.bundle_setup();p=self.bundle/'manifest.txt';p.write_text(p.read_text().replace('web_file_count=3','web_file_count=4'));self.sums()
        with self.assertRaises(ValueError): w.validate_bundle(self.bundle)
    def test_missing_web(self):
        self.bundle_setup();(self.bundle/'web-dist.tar.gz').unlink()
        with self.assertRaises(ValueError): w.validate_bundle(self.bundle)
    def test_unsafe_archive(self):
        for n,kind in [('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('hard',tarfile.LNKTYPE),('pipe',tarfile.FIFOTYPE),('a/../b',tarfile.REGTYPE)]:
            with self.subTest(n=n):
                p=self.p/'bad.tar.gz'
                with tarfile.open(p,'w:gz') as t:
                    m=tarfile.TarInfo(n);m.type=kind;t.addfile(m,io.BytesIO(b''))
                with self.assertRaises(ValueError): w.archive_digest(p)
    def test_duplicate_archive(self):
        p=self.p/'bad.tar.gz'
        with tarfile.open(p,'w:gz') as t:
            for _ in range(2): t.addfile(tarfile.TarInfo('index.html'),io.BytesIO(b''))
        with self.assertRaises(ValueError): w.archive_digest(p)
    def test_api_identity(self):
        tag='api-aaaaaaa';i='sha256:'+'b'*64
        self.assertEqual(w.api_identity(tag,tag,'shutong-api:'+tag,i,i,'a'*40)['api_git_sha'],'a'*40)
        self.assertEqual(w.api_identity(tag,tag,'shutong-api:'+tag,i,i,'<no value>')['api_git_sha'],w.UNKNOWN)
        for args in [(tag,'other','shutong-api:'+tag,i,i,'a'*40),(tag,tag,'shutong-api:'+tag,i,'sha256:'+'c'*64,'a'*40),(tag,tag,'shutong-api:'+tag,i,i,'c'*40)]:
            with self.assertRaises(ValueError): w.api_identity(*args)
    def test_build_from_commit(self):
        repo=self.p/'repo'; repo.mkdir(); state=repo/'.local';state.mkdir()
        web=repo/'apps/web';web.mkdir(parents=True)
        (repo/'.gitignore').write_text('.local/\napps/web/dist/\n')
        (web/'marker').write_text('committed source')
        def git(*args): return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
        git('init','-q');git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
        sha=git('rev-parse','HEAD'); bin=self.p/'bin';bin.mkdir(); npm=bin/'npm'
        npm.write_text('#!/bin/sh\nset -eu\nif [ "$1" = ci ]; then exit 0; fi\nmkdir -p dist/assets\ncp marker dist/index.html\ncp marker dist/admin.html\ncp marker dist/assets/app.js\n');npm.chmod(0o700)
        with patch.dict(os.environ,{'PATH':str(bin)+':'+os.defpath}):
            w.build_web(repo,state)
            record=json.loads((state/'web-provenance.json').read_text())
            self.assertEqual(record['source_git_sha'],sha)
            self.assertEqual((web/'dist/index.html').read_text(),'committed source')
            (web/'marker').write_text('dirty')
            with self.assertRaises(ValueError): w.build_web(repo,state)
            self.assertEqual(json.loads((state/'web-provenance.json').read_text()),record)
    def test_legacy_bundle(self):
        self.bundle_setup(); (self.bundle/'web-dist.tar.gz').unlink(); p=self.bundle/'manifest.txt';m=w.manifest(p);p.write_text(''.join(f'{k}={m[k]}\n' for k in sorted(w.BASE_KEYS)));(self.bundle/'SHA256SUMS').write_text(''.join(f'{w.sha(self.bundle/n)}  {n}\n' for n in sorted(w.BASE_FILES)))
        self.assertNotIn('artifact_format',w.validate_bundle(self.bundle))
        with self.assertRaises(ValueError): w.restore_web(self.bundle,self.p/'out')

    def test_export_private_umask_preserves_source_modes(self):
        repo=self.p/'source-repo'; repo.mkdir(); dest=self.p/'export'; dest.mkdir(mode=0o700)
        old=os.umask(0o077)
        try:
            d=repo/'services/api/alembic/versions'; d.mkdir(parents=True)
            f=d/'0022.py'; f.write_text('revision = "0022"\n')
            executable=repo/'run.sh'; executable.write_text('#!/bin/sh\n'); executable.chmod(0o700)
            w.git(repo,'init','-q'); w.git(repo,'add','.'); w.git(repo,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
            w.export_source(repo,w.git(repo,'rev-parse','HEAD'),dest)
            out=dest/'services/api/alembic/versions/0022.py'
            self.assertEqual(out.read_bytes(),f.read_bytes())
            self.assertEqual(out.stat().st_mode&0o777,0o644)
            self.assertEqual((dest/'run.sh').stat().st_mode&0o777,0o755)
            self.assertEqual(dest.stat().st_mode&0o777,0o700)
            for p in out.parents:
                if p==dest: break
                self.assertEqual(p.stat().st_mode&0o777,0o755)
        finally: os.umask(old)

    def test_export_refuses_unsafe_archive(self):
        for name,kind in [('../escape',tarfile.REGTYPE),('/abs',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('pipe',tarfile.FIFOTYPE)]:
            with self.subTest(name=name):
                dest=self.p/'unsafe'; dest.mkdir(mode=0o700,exist_ok=True)
                with io.BytesIO() as b:
                    with tarfile.open(fileobj=b,mode='w') as t:
                        m=tarfile.TarInfo(name); m.type=kind; t.addfile(m,io.BytesIO(b''))
                    b.seek(0)
                    with tarfile.open(fileobj=b) as t:
                        with self.assertRaises(ValueError): w.extract_committed_archive(t,dest)
                self.assertEqual(list(dest.iterdir()),[])
        (dest/'keep').write_text('keep')
        with self.assertRaises(ValueError): w.extract_committed_archive(None,dest)
        self.assertEqual((dest/'keep').read_text(),'keep')

    def test_image_graph_gate_rejects_bad_identity_graph_or_hash(self):
        import check_api_image_migrations as gate
        files={'alembic.ini':'a','alembic/env.py':'b','alembic/versions/0022.py':'c','alembic/versions/0023.py':'d'}
        good=dict(uid=1001,gid=1001,heads=['0023'],revisions=['0022','0023'],files=files)
        self.assertEqual(gate.validate(good,files,'1001:1001'),2)
        for bad in [dict(uid=0),dict(gid=0),dict(heads=[]),dict(heads=['0022','0023']),dict(revisions=['0023']),dict(files=dict(files,**{'alembic/versions/0022.py':'wrong'}))]:
            with self.subTest(bad=bad), self.assertRaises(ValueError): gate.validate(dict(good,**bad),files,'1001:1001')

if __name__=='__main__': unittest.main()
