"""ST-024-D4 production storage contract; synthetic files only, no Docker/R2."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import web_artifact_provenance as w

ROOT = Path(__file__).resolve().parents[1]
KEY = 'a'*32
DATA = '虚构测试数据'.encode()
SHA = hashlib.sha256(DATA).hexdigest()
REL = '2026-11_虚构测试数据/exam-paper/test.pdf'

class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.p = Path(self.temp.name); self.archive = self.p/'a.tar.gz'
    def tar(self, entries):
        with tarfile.open(self.archive,'w:gz') as t:
            for name,data in entries:
                m=tarfile.TarInfo(name); m.size=len(data); t.addfile(m,io.BytesIO(data))
    def test_old_and_new_references(self):
        self.tar([('./'+KEY,DATA),('./school-exams/'+REL,DATA)])
        self.assertEqual(w.verify_attachment_refs(self.archive, [[KEY,SHA,len(DATA),None],['b'*32,SHA,len(DATA),REL]]),2)
        dest=self.p/'restored';dest.mkdir()
        with tarfile.open(self.archive) as t: t.extractall(dest,filter='data')
        self.assertEqual((dest/KEY).read_bytes(), DATA)
        self.assertEqual((dest/'school-exams'/REL).read_bytes(), DATA)
    def test_missing_relative_path_even_when_blob_exists(self):
        self.tar([(KEY,DATA)])
        with self.assertRaises(ValueError): w.verify_attachment_refs(self.archive,[[KEY,SHA,len(DATA),REL]])
    def test_corrupt_and_unsafe_reference(self):
        self.tar([('school-exams/'+REL,b'wrong')])
        for rel in (REL,'../escape','/absolute','a/../b'):
            with self.subTest(rel=rel),self.assertRaises(ValueError): w.verify_attachment_refs(self.archive,[[KEY,SHA,len(DATA),rel]])
    def test_shadow_mount_refused(self):
        mount={'Type':'bind','Source':str(self.p),'Destination':'/var/lib/shutong/attachments'}
        w.verify_mount(json.dumps([mount]),self.p)
        with self.assertRaises(ValueError): w.verify_mount(json.dumps([mount,dict(mount,Destination=mount['Destination']+'/school-exams')]),self.p)
    def test_actual_school_file_writes_and_reload(self):
        root=self.p/'home';attach=self.p/'attachments';attach.mkdir()
        env={'PATH':os.defpath,'HOME':str(self.p),'TMPDIR':str(self.p),'PYTHONPATH':str(ROOT/'services/api'), 'PYTHONDONTWRITEBYTECODE':'1','SHUTONG_ENV':'test','PAGEBOY_HOME':str(root),'SHUTONG_PRIVATE_DIR':str(attach),'SHUTONG_SCHOOL_EXAMS_DIR':str(attach/'school-exams')}
        code="""from pathlib import Path
import os
from types import SimpleNamespace
from hashlib import sha256
from shutong import private_files as f
from shutong.home import default_school_exams_dir
from shutong.school_exam_pipeline import school_exam_storage_root
root=Path(os.environ['SHUTONG_PRIVATE_DIR']); school=root/'school-exams'
assert default_school_exams_dir()==default_school_exams_dir('development')==school_exam_storage_root('test')==school
assert default_school_exams_dir('production') != school
assert default_school_exams_dir('development', root/'other') != school
payload='虚构测试数据'.encode(); old=f.write_blob(payload)
key,rel=f.write_school_exam_file('fixture','exam-paper','sample.pdf',payload)
key2,rel2=f.write_school_exam_scoped_blob('reports','report.pdf',payload)
for k,r in [(old,None),(key,rel),(key2,rel2)]:
    a=SimpleNamespace(storage_key=k,relative_path=r,byte_size=len(payload),sha256=sha256(payload).hexdigest())
    assert f.load_blob(a)==payload
assert (root/old).is_file() and (school/rel).is_file() and (school/rel2).is_file()
"""
        subprocess.run([sys.executable,'-B','-c',code],env=env,cwd=self.p,check=True)
        # Simulate a fresh process + archive/extract + independent path resolution.
        with tarfile.open(self.archive,'w:gz') as t:t.add(attach,arcname='.')
        restored=self.p/'restored';restored.mkdir()
        with tarfile.open(self.archive) as t:t.extractall(restored,filter='data')
        env.update(SHUTONG_PRIVATE_DIR=str(restored),SHUTONG_SCHOOL_EXAMS_DIR=str(restored/'school-exams'))
        code2="""from pathlib import Path
import os
from shutong import private_files as f
from shutong.school_exam_pipeline import school_exam_storage_root
root=Path(os.environ['SHUTONG_PRIVATE_DIR']);assert school_exam_storage_root('test')==root/'school-exams'
files=[p for p in root.rglob('*') if p.is_file()]; assert len(files)==3 and all(p.read_bytes()=='虚构测试数据'.encode() for p in files)
"""
        subprocess.run([sys.executable,'-B','-c',code2],env=env,cwd=self.p,check=True)

if __name__=='__main__':unittest.main()
