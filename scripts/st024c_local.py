#!/usr/bin/env python3
"""ST-024-C1/C2: local synthetic-only backup/restore; no Docker, TCP DB, R2 or prod env."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote
import web_artifact_provenance as web

REPO = Path(__file__).resolve().parents[1]
API = REPO / 'services/api'
DB = 'pageboy_drill'
PORT = '5432'  # Unix socket filename only; no TCP listener.
TARGETS = ('source', 'restored')
FILES = ('postgres.dump', 'attachments.tar.gz')
APP = 'st024c-local-synthetic'


def require(ok, msg):
    if not ok:
        raise RuntimeError('REFUSED: ' + msg)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def clean_env(root):
    # Deliberately not inherited: PG*, DATABASE_URL, SHUTONG*, AWS*, RESTIC*, proxies.
    return {'PATH': os.defpath, 'HOME': str(root), 'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8', 'TMPDIR': str(root), 'PYTHONNOUSERSITE': '1',
            'PYTHONDONTWRITEBYTECODE': '1'}


def run(args, root, *, env=None, input=None, stdout=subprocess.PIPE, timeout=120):
    p = subprocess.run([str(a) for a in args], env=clean_env(root) | (env or {}),
                       input=input, stdout=stdout, stderr=subprocess.PIPE, timeout=timeout, cwd=root)
    if p.returncode:
        # No DSNs, environment values or private data printed.
        raise RuntimeError(f'{Path(str(args[0])).name} failed rc={p.returncode}: {p.stderr.decode(errors="replace")[-800:]}')
    return p.stdout


def root_guard(root):
    p = Path(root)
    require(p.is_absolute() and p.parent == Path('/tmp') and re.fullmatch(r'pageboy-c-[a-z0-9_]{8}', p.name), 'not a dedicated /tmp/pageboy-c-* run directory')
    require(p.is_dir() and not p.is_symlink() and p.resolve() == p, 'run directory identity invalid')
    st = p.stat()
    require(st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o700, 'run directory owner/mode invalid')
    marker = p / '.st024c-run'
    require(marker.is_file() and not marker.is_symlink() and marker.read_text() == p.name, 'run marker invalid')
    require(os.getuid() != 0, 'root execution prohibited')
    return p


def child(root, name, *, exists=True, directory=True):
    require(re.fullmatch(r'[a-zA-Z0-9_.-]+', name) and name not in ('.', '..'), 'invalid child name')
    p = root / name
    require(not p.is_symlink() and p.resolve() == p, 'symlink/path escape')
    if exists:
        require(p.is_dir() if directory else p.is_file(), 'missing expected child')
        require(p.stat().st_uid == os.getuid(), 'foreign child owner')
    else:
        require(not p.exists(), 'target already exists')
    return p


def pg_bin(root):
    # Native PG16 server + clients, not the system service. Never use an ambient PGHOST.
    candidates = [REPO / '.cache/st024c-tools/pg16/bin', REPO.parent / 'pageboy-st024-c/.cache/st024c-tools/pg16/bin', Path('/usr/lib/postgresql/16/bin'), Path('/usr/local/pgsql/bin')]
    config = shutil.which('pg_config', path=os.defpath)
    if config:
        candidates.append(Path(run([config, '--bindir'], root).decode().strip()))
    names = ('postgres','initdb','pg_ctl','psql','pg_dump','pg_restore','createdb')
    for b in candidates:
        if all((b / n).is_file() and os.access(b / n, os.X_OK) for n in names):
            version = run([b/'postgres','--version'], root).decode()
            if re.search(r'PostgreSQL\) 16(?:\.|\s|$)', version):
                return b
    raise RuntimeError('BLOCKED: native PostgreSQL 16 server/client binaries not found; do not use production Docker or sudo')


class Target:
    def __init__(self, root, name):
        self.root = root_guard(root)
        require(name in TARGETS, 'unrecognized target')
        self.name = name
        self.bin = pg_bin(root)
        self.data = root / f'{name}-data'
        self.sock = root / f'{name}-sock'
        self.mark = root / f'{name}-identity.json'
        import pwd
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.started = False

    def args(self, db=DB):
        return ['-h', str(self.sock), '-p', PORT, '-U', self.user, '-d', db]

    def sql(self, sql, db=DB):
        return run([self.bin/'psql','-X','-w','-v','ON_ERROR_STOP=1','-At',*self.args(db),'-c',sql], self.root).decode().strip()

    def live_identity(self):
        root_guard(self.root)
        child(self.root, self.data.name)
        child(self.root, self.sock.name)
        require(stat.S_IMODE(self.sock.stat().st_mode) == 0o700, 'socket directory not private')
        row = json.loads(self.sql("SELECT json_build_object('data',current_setting('data_directory'),'listen',current_setting('listen_addresses'),'socket',current_setting('unix_socket_directories'),'user',current_user,'id',(pg_control_system()).system_identifier::text)", 'postgres'))
        require(row['data'] == str(self.data) and row['socket'] == str(self.sock) and row['listen'] == '' and row['user'] == self.user and re.fullmatch(r'[0-9]+', row['id']), 'server identity mismatch')
        return row

    def verify(self):
        marker = child(self.root, self.mark.name, directory=False)
        require(self.live_identity() == json.loads(marker.read_text()), 'server system identifier mismatch')

    def start(self):
        for p in (self.data, self.sock, self.mark):
            child(self.root, p.name, exists=False)
        self.sock.mkdir(mode=0o700)
        run([self.bin/'initdb','-D',self.data,'--username',self.user,'--auth-local=peer','--auth-host=reject','--encoding=UTF8','--no-locale'], self.root, timeout=120)
        opts = shlex.join(['-c','listen_addresses=','-c',f'unix_socket_directories={self.sock}','-c','unix_socket_permissions=0700','-p',PORT,'-c','max_connections=12','-c','shared_buffers=32MB'])
        run([self.bin/'pg_ctl','-D',self.data,'-l',self.root/f'{self.name}.log','-o',opts,'-w','-t','30','start'], self.root, timeout=45)
        self.started = True
        self.mark.write_text(json.dumps(self.live_identity()))
        self.verify()
        run([self.bin/'createdb','-w','-h',self.sock,'-p',PORT,'-U',self.user,DB], self.root)
        print(f'ISOLATED_TARGET_OK {self.name}: private Unix socket, no TCP, unique system identifier', flush=True)

    def stop(self):
        if self.started:
            self.verify()  # never stop a process solely by name/pid/port
            run([self.bin/'pg_ctl','-D',self.data,'-m','fast','-w','-t','30','stop'], self.root, timeout=45)
            require(not (self.data/'postmaster.pid').exists(), 'target did not stop')
            self.started = False
            print(f'ISOLATED_TARGET_STOPPED {self.name}', flush=True)

    def revision(self):
        self.verify()
        rev = self.sql('SELECT version_num FROM alembic_version')
        require(re.fullmatch(r'[0-9]{4}', rev), 'unknown/multiple migration revisions')
        return rev

    def url(self):
        self.verify()
        return f'postgresql+psycopg://{quote(self.user,safe="")}@/{DB}?host={quote(str(self.sock),safe="")}&port={PORT}'

    def fingerprint(self):
        self.verify()
        names = self.sql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
        require(bool(names), 'no public tables')
        out = {}
        for name in names:
            require(re.fullmatch(r'[a-z_][a-z0-9_]*',name), 'unexpected table name')
            n = self.sql(f'SELECT count(*) FROM public."{name}"')
            # canonical JSONB row values sorted bytewise, not just row counts.
            rows = run([self.bin/'psql','-X','-w','-v','ON_ERROR_STOP=1','-At',*self.args(),'-c',f'SELECT to_jsonb(t)::text FROM public."{name}" t ORDER BY to_jsonb(t)::text COLLATE "C"'],self.root)
            out[name] = (int(n),hashlib.sha256(rows).hexdigest())
        return out


def regular_tree(path):
    files = []
    for p in path.rglob('*'):
        require(not p.is_symlink() and (p.is_dir() or p.is_file()), 'attachment is not regular file/directory')
        if p.is_file(): files.append(p)
    return sorted(files)


def backup(root, name):
    t = Target(root,name)
    require(name == 'source', 'local backup source must be source target')
    attach = child(t.root,'source-attachments')
    output = child(t.root,'backup',exists=False)
    files = regular_tree(attach)
    require(len(files)==1, 'synthetic drill requires exactly one attachment')
    rev = t.revision()
    output.mkdir(mode=0o700)
    with (output/FILES[0]).open('xb') as f:
        run([t.bin/'pg_dump','-w',*t.args(),'-Fc'], t.root, stdout=f)
    require((output/FILES[0]).stat().st_size > 0, 'empty dump')
    with tarfile.open(output/FILES[1], 'x:gz') as archive:
        for p in files: archive.add(p, arcname=p.relative_to(attach).as_posix(),recursive=False)
    require(t.revision() == rev, 'revision changed during backup')
    (output/'SHA256SUMS').write_text(''.join(f'{sha(output/f)}  {f}\n' for f in FILES))
    (output/'manifest.txt').write_text(f'timestamp_utc={datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}\napp_revision={APP}\nmigration_revision={rev}\nattachments_included=yes\nattachment_count={len(files)}\n')
    webdir = t.root/'source-web'
    if webdir.exists():
        meta = web.archive_tree(webdir, t.root/'absent-web-record.json', output/'web-dist.tar.gz')
        with (output/'manifest.txt').open('a') as f:
            f.write('artifact_format=2\napi_git_sha=UNVERIFIED\napi_image_id=UNVERIFIED\n')
            f.write(''.join(f'{k}={v}\n' for k,v in meta.items()))
        (output/'SHA256SUMS').write_text(''.join(f'{sha(output/f)}  {f}\n' for f in (*FILES,'web-dist.tar.gz','manifest.txt')))
    validate_bundle(output)
    print('LOCAL_BACKUP_OK (synthetic only; no R2)',flush=True)


def validate_bundle(path):
    require(path.is_dir() and not path.is_symlink(),'backup directory missing or invalid')
    for name in (*FILES,'SHA256SUMS','manifest.txt'):
        p = path/name
        require(p.is_file() and not p.is_symlink() and p.stat().st_size > 0,'missing/invalid '+name)
    manifest = web.validate_bundle(path)
    require(manifest['app_revision']==APP and manifest['attachments_included']=='yes' and re.fullmatch(r'[0-9]{4}',manifest['migration_revision']) and re.fullmatch(r'[1-9][0-9]*',manifest['attachment_count']),'manifest invalid/not synthetic local drill')
    datetime.strptime(manifest['timestamp_utc'],'%Y-%m-%dT%H:%M:%SZ')
    with tarfile.open(path/FILES[1],'r:gz') as archive:
        seen=set(); files=set(); count=0
        for member in archive:
            p=PurePosixPath(member.name)
            require(not p.is_absolute() and p.parts and '..' not in p.parts and (member.isfile() or member.isdir()),'unsafe tar member')
            require(str(p) not in seen,'duplicate tar member'); seen.add(str(p))
            if member.isfile(): count+=1; files.add(str(p))
        require(all(not any(str(parent) in files for parent in PurePosixPath(name).parents) for name in seen),'tar file used as directory')
        require(count==int(manifest['attachment_count']),'attachment count mismatch')
    return manifest


def restore(root,name):
    t=Target(root,name)
    require(name=='restored','restore must target newly created restored instance')
    t.verify()
    attach=child(t.root,'restored-attachments',exists=False)
    bundle=child(t.root,'backup')
    manifest=validate_bundle(bundle)
    require(t.sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'")=='0','target database is not empty')
    # Validate archive first, before any writes. No arbitrary URL or output path accepted.
    if manifest.get('artifact_format') == '2':
        web.restore_web(bundle, child(t.root,'restored-web',exists=False))
    attach.mkdir(mode=0o700)
    with tarfile.open(bundle/FILES[1],'r:gz') as archive:
        archive.extractall(attach,filter='data')
    t.verify()
    with (bundle/FILES[0]).open('rb') as f:
        p=subprocess.run([str(t.bin/'pg_restore'),'-w',*t.args(),'--no-owner','--no-privileges','--exit-on-error','--single-transaction'],stdin=f,env=clean_env(t.root),capture_output=True,timeout=120,cwd=t.root)
    require(p.returncode==0,'pg_restore failed; disposable target must be discarded')
    require(t.revision()==manifest['migration_revision'],'restored DB revision differs from manifest')
    print('LOCAL_RESTORE_OK',flush=True)


def api_env(t, attach):
    return {'DATABASE_URL':t.url(),'SHUTONG_ENV':'test','PAGEBOY_HOME':str(t.root/'home'),
            'SHUTONG_PRIVATE_DIR':str(attach),'SHUTONG_APP_REVISION':APP,
            'SHUTONG_ADMIN_TOKEN':secrets.token_hex(24),'SHUTONG_STUDENT_TOKEN':secrets.token_hex(24),
            'PYTHONPATH':str(API)}


def api_probe(t, phase):
    attach=child(t.root,f'{t.name}-attachments')
    env=api_env(t,attach)
    output=run([sys.executable,Path(__file__).resolve(),'api-probe',phase],t.root,env=env)
    return json.loads(output)


def probe(phase):
    # Only launched by parent with isolated socket DSN and temporary Home; validate again before importing app.
    root=root_guard(Path(os.environ['PAGEBOY_HOME']).parent)
    target=Target(root,'source' if phase=='seed' else 'restored')
    require(os.environ['DATABASE_URL']==target.url() and os.environ['SHUTONG_PRIVATE_DIR']==str(root/f'{target.name}-attachments') and os.environ['SHUTONG_ENV']=='test','probe identity mismatch')
    child(root,f'{target.name}-attachments')
    e={k:os.environ[k] for k in ('DATABASE_URL','SHUTONG_ENV','PAGEBOY_HOME','SHUTONG_PRIVATE_DIR','SHUTONG_APP_REVISION','SHUTONG_ADMIN_TOKEN','SHUTONG_STUDENT_TOKEN','PYTHONPATH')}
    require(e['SHUTONG_APP_REVISION']==APP and e['PAGEBOY_HOME']==str(root/'home') and e['PYTHONPATH']==str(API) and e['SHUTONG_ADMIN_TOKEN']!=e['SHUTONG_STUDENT_TOKEN'],'probe config invalid')
    os.environ.clear();os.environ.update(clean_env(root)|e)
    from fastapi.testclient import TestClient
    from shutong.main import app
    from shutong.database import engine
    from shutong.models import SourceAttachment
    from sqlalchemy import select
    admin=os.environ['SHUTONG_ADMIN_TOKEN']; student=os.environ['SHUTONG_STUDENT_TOKEN']
    with TestClient(app) as c:
        def call(path,method='GET',body=None,token=admin,**kwargs):
            r=c.request(method,path,json=body,headers={'Authorization':f'Bearer {token}'}|kwargs.pop('headers',{}),**kwargs)
            require(200<=r.status_code<300,f'{method} {path.split("?")[0]} HTTP {r.status_code}: {r.text[:160]}')
            return r
        require(call('/health/live').json()['app_revision']==APP,'wrong app revision')
        require(call('/health/ready').json()['status']=='ready','not ready')
        if phase=='seed':
            review={'exam_year':2026,'source_url':'https://example.org/synthetic-st024c.pdf','acquired_at':'2026-11-27','rights_status':'licensed','rights_basis':'虚构测试数据：合成题','applicable':True,'applicability_note':'虚构测试数据：隔离演练','reviewed_by_human':True}
            def source(title):
                sid=call('/api/admin/sources','POST',{'title':title,'subject':'math','rights_status':'licensed','verified':True}).json()['id']
                call(f'/api/admin/sources/{sid}/review','POST',review)
                return sid
            def publish(qid):
                call(f'/api/admin/questions/{qid}/review','POST');call(f'/api/admin/questions/{qid}/publish','POST')
            sid=source('虚构测试数据：ST-024-C 题源 A')
            q=call('/api/admin/questions','POST',{'source_document_id':sid,'stem':'虚构测试数据：1+1=?','kind':'single_choice','options':['A. 2','B. 1'],'correct_answer':'A','knowledge_ids':['math.drill'],'max_points':2}).json();publish(q['id'])
            sid=source('虚构测试数据：ST-024-C 题源 B')
            mp3=b'ID3\x03\x00\x00\x00'+bytes(500)
            aid=call(f'/api/admin/sources/{sid}/attachments?filename='+quote('虚构测试数据.mp3'),'POST',content=mp3,headers={'Content-Type':'audio/mpeg'}).json()['id']
            call(f'/api/admin/attachments/{aid}/parse','POST')
            v=call(f'/api/admin/attachments/{aid}/confirm','POST',{'confirmed_by_human':True,'questions':[{'source_document_id':sid,'stem':'虚构测试数据：听力题','kind':'single_choice','options':['A. 甲','B. 乙'],'correct_answer':'A','knowledge_ids':['math.listen'],'max_points':2,'media_attachment_id':aid}]}).json()['question_version_ids'][0]
            call(f'/api/admin/sources/{sid}/review','POST',review);publish(v)
            # Preserve the existing student-facing security boundary; test rejection first.
            denied=c.get('/api/practice/next?subject=math&knowledge_id=math.drill&purpose=training',headers={'Authorization':f'Bearer {student}'})
            require(denied.status_code==400 and 'KNOWLEDGE_FILTER_FORBIDDEN' in denied.json().get('detail',''),'student knowledge filter must be refused')
            nxt=call('/api/practice/next?subject=math&purpose=training',token=student).json()
            require(nxt['question_version_id'] in (q['id'],v) and nxt['kind']=='single_choice','unexpected synthetic question')
            attempt=call('/api/practice/attempts','POST',{'client_attempt_id':'st024c-synthetic-1','exposure_id':nxt['exposure_id'],'answer':'A','hints_used':False},token=student).json()
            require(attempt['status']=='recorded' and attempt['earned_points']==attempt['max_points']==2 and attempt['scoring_origin']=='reviewed_answer_key','synthetic scoring mismatch')
        attempts=call('/api/practice/attempts?subject=math',token=student).json()
        require(len(attempts)==1,'synthetic attempt count mismatch')
        records=[]
        with engine.connect() as conn:
            for row in conn.execute(select(SourceAttachment.id,SourceAttachment.storage_key,SourceAttachment.sha256,SourceAttachment.byte_size)):
                p=Path(os.environ['SHUTONG_PRIVATE_DIR'])/row.storage_key
                require(p.is_file() and p.resolve().is_relative_to(Path(os.environ['SHUTONG_PRIVATE_DIR'])) and not p.is_symlink(),'attachment path invalid')
                require(sha(p)==row.sha256 and p.stat().st_size==row.byte_size,'attachment DB/file mismatch')
                data=call(f'/api/admin/attachments/{row.id}/download').content
                require(hashlib.sha256(data).hexdigest()==row.sha256,'attachment download mismatch')
                records.append([row.id,row.sha256,row.byte_size])
        require(len(records)==1,'synthetic attachment count mismatch')
        print(json.dumps({'attempts':attempts,'attachments':records},default=str))
    engine.dispose()


def drill():
    require(os.getuid()!=0,'run as non-root development user')
    os.umask(0o077)
    root=Path(tempfile.mkdtemp(prefix='pageboy-c-',dir='/tmp'))
    (root/'.st024c-run').write_text(root.name)
    targets=[]; success=False
    try:
        source=Target(root,'source');targets.append(source);source.start()
        attach=child(root,'source-attachments',exists=False);attach.mkdir()
        run([sys.executable,'-m','alembic','-c',API/'alembic.ini','upgrade','head'],root,env=api_env(source,attach)|{'PYTHONPATH':str(API)},timeout=180)
        require(source.revision()=='0023','unexpected head; review baseline')
        original=api_probe(source,'seed'); before=source.fingerprint()
        require(all(before.get(n,(0,))[0]>0 for n in ('source_documents','questions','question_versions','exposures','answer_attempts','source_attachments')),'fixture incomplete')
        webdir=child(root,'source-web',exists=False); webdir.mkdir(); (webdir/'assets').mkdir()
        for n in ('index.html','admin.html','assets/app.js'):
            (webdir/n).write_text('synthetic Web '+n)
        web_before=web.tree(webdir)
        run(['bash',REPO/'infra/backup.sh','--local-drill',root,'source'],root)
        print('LOCAL_BACKUP_OK',flush=True)
        source.stop()
        shutil.rmtree(child(root,'source-data'));shutil.rmtree(child(root,'source-attachments'))
        shutil.rmtree(webdir)
        require(not source.data.exists() and not webdir.exists(),'source still exists')
        restored=Target(root,'restored');targets.append(restored);restored.start()
        require(json.loads(source.mark.read_text())['id']!=json.loads(restored.mark.read_text())['id'],'same cluster identity')
        run(['bash',REPO/'infra/restore.sh','--local-drill',root,'restored'],root)
        print('LOCAL_RESTORE_OK',flush=True)
        require(web.tree(child(root,'restored-web'))==web_before,'restored Web differs')
        print('LOCAL_WEB_ROUNDTRIP_OK',flush=True)
        after=restored.fingerprint();require(before==after,'full public-table row fingerprints differ')
        require(original==api_probe(restored,'verify'),'API evidence differs')
        require(after==restored.fingerprint(),'verify probe unexpectedly modified database')
        print(f'ALL_PUBLIC_TABLES_EQUAL={len(before)}; ATTACHMENT_DB_FILE_API_SHA_OK; MIGRATION_REVISION=0023',flush=True)
        # Negative case: same target cannot be restored again.
        try: restore(root,'restored')
        except RuntimeError as e: require('REFUSED:' in str(e),'unexpected negative failure')
        else: raise RuntimeError('repeat restore was not refused')
        print('NONEMPTY_RESTORE_REFUSED',flush=True)
        success=True
    finally:
        cleanup_ok=True
        for t in reversed(targets):
            try:
                t.stop()
                if (t.data/'postmaster.pid').exists(): cleanup_ok=False
            except Exception as exc:
                cleanup_ok=False;print(f'CLEANUP_BLOCKED {t.name}: {exc}',file=sys.stderr)
        if cleanup_ok:
            root_guard(root);shutil.rmtree(root)
            print('ISOLATED_CLEANUP_OK',flush=True)
        else:
            print(f'BLOCKED: retained isolated run directory {root}; do not force-stop unknown processes',file=sys.stderr)
        require(cleanup_ok,'cleanup identity not proven')
    if success: print('ST024C12_LOCAL_DRILL_OK',flush=True)


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('drill')
    for op in ('backup','restore'):
        q=sub.add_parser(op);q.add_argument('root');q.add_argument('target')
    q=sub.add_parser('api-probe');q.add_argument('phase',choices=('seed','verify'))
    a=p.parse_args();os.umask(0o077)
    if a.cmd=='drill': drill()
    elif a.cmd=='api-probe': probe(a.phase)
    else: globals()[a.cmd](Path(a.root),a.target)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'STOP: {e}',file=sys.stderr);sys.exit(1)
