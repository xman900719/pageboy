#!/usr/bin/env python3
"""Pinned historical corpus archive; no production restore or database writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile
import tempfile

NAME = 'exam_bank_2018_2025'
ARCHIVE = 'exam-bank.tar.gz'
DEST = '/var/lib/shutong/' + NAME
GROUPS = {(str(y), s) for y in range(2018, 2026) for s in ('chinese','english','math','physics')}


def need(ok, msg):
    if not ok:
        raise ValueError('REFUSED: '+msg)


def safe(p):
    p = Path(p)
    need(p.is_absolute() and p.resolve() == p and not any(q.is_symlink() for q in (p,*p.parents)), 'unsafe corpus path')
    return p


def digest(f):
    h=hashlib.sha256(); size=0
    for chunk in iter(lambda:f.read(1024*1024), b''):
        h.update(chunk); size+=len(chunk)
    return size,h.hexdigest()


def regular(p):
    p=safe(p)
    need(p.is_file() and p.stat().st_nlink==1, 'not a single-link corpus file')
    return p


def hexval(x,n):
    return isinstance(x,str) and re.fullmatch('[0-9a-f]{'+str(n)+'}',x) is not None


def parse(raw,pin):
    need(hexval(pin,64) and hashlib.sha256(raw).hexdigest()==pin,'corpus manifest pin mismatch')
    m=json.loads(raw)
    need(m.get('format_version')==1 and m.get('environment')=='production','wrong corpus manifest identity')
    entries=m['entries']; need(isinstance(entries,list) and len(entries)==32,'expected 32 historical corpus originals')
    expected={}; groups=set(); ids=set(); sources=set(); keys=set(); total=0
    for e in entries:
        key=e['storage_key']; aid=e['attachment_id']; sid=e['source_document_id']
        need(hexval(key,32) and isinstance(aid,str) and bool(aid) and isinstance(sid,str) and bool(sid),'invalid corpus identity')
        need(key not in keys and aid not in ids and sid not in sources,'duplicate corpus identity')
        keys.add(key); ids.add(aid); sources.add(sid)
        parts=PurePosixPath(e['raw']).parts; need(len(parts)==4 and tuple(parts[:2]) in GROUPS,'invalid corpus group')
        group=tuple(parts[:2]); need(group not in groups,'duplicate corpus group'); groups.add(group)
        base='/'.join(group)
        need(e['raw']==base+'/raw/'+key+'.docx' and e['processed']==base+'/processed/questions.json','invalid corpus member path')
        need(type(e['bytes']) is int and 0<e['bytes']<=35*1024*1024 and hexval(e['sha256'],64) and hexval(e['processed_sha256'],64),'invalid corpus file metadata')
        expected[e['raw']]=(e['bytes'],e['sha256']); expected[e['processed']]=(None,e['processed_sha256']); total+=e['bytes']
    need(groups==GROUPS and m['source_count']==32 and m['attachment_count']==32 and m['attachment_bytes']==total,'corpus coverage/size mismatch')
    need(type(m['question_count']) is int and m['question_count']>0,'invalid question count')
    return m,expected


def check_rows(m,rows):
    """Exact DB identities for all selected official sources; other references handled by legacy verifier."""
    need(isinstance(rows,list) and len(rows)==32,'database corpus coverage mismatch')
    expected={(e['attachment_id'],e['source_document_id'],e['storage_key'],e['sha256'],e['bytes'],*e['raw'].split('/')[:2]) for e in m['entries']}
    got=set()
    for r in rows:
        need(isinstance(r,list) and len(r)==10 and r[7]=='confirmed' and r[8] is True and '北京市' in r[9] and '中考' in r[9],'database corpus identity/review mismatch')
        got.add(tuple(r[:5])+(str(r[5]),r[6]))
    need(got==expected,'database corpus attachment mismatch')


def validate_archive(archive,pin,rows=None):
    archive=regular(archive); actual={}; dirs=set(); document=None; payloads={}
    with tarfile.open(archive,'r:gz') as t:
        for member in t:
            n=member.name; p=PurePosixPath(n)
            need(n==str(p) and not p.is_absolute() and '..' not in p.parts and '\\' not in n and n not in actual and n not in dirs,'unsafe or duplicate corpus archive member')
            need(member.isfile() or member.isdir(),'corpus archive link/special entry')
            if member.isdir():
                dirs.add(n); continue
            need(0<=member.size<=70*1024*1024 and len(actual)<65,'corpus archive size/count limit')
            with t.extractfile(member) as f:
                if n=='manifest.json':
                    need(member.size<=1024*1024,'oversized corpus manifest'); document=f.read(); actual[n]=(len(document),hashlib.sha256(document).hexdigest())
                elif n.endswith('/processed/questions.json'):
                    raw=f.read(); actual[n]=(len(raw),hashlib.sha256(raw).hexdigest()); payloads[n]=json.loads(raw)
                else: actual[n]=digest(f)
    need(document is not None,'missing corpus manifest'); m,expected=parse(document,pin)
    need(set(actual)==set(expected)|{'manifest.json'},'unexpected or missing corpus archive files')
    permitted={str(p) for n in expected for p in PurePosixPath(n).parents if str(p)!='.'}
    permitted|={y+'/'+s+'/validation' for y,s in GROUPS}
    need(dirs<=permitted,'unexpected corpus archive directory')
    questions=0
    for e in m['entries']:
        for n in (e['raw'],e['processed']):
            size,sha=expected[n]; need(actual[n][1]==sha and (size is None or size==actual[n][0]),'corpus archive member mismatch')
        data=payloads[e['processed']]; src=data['source_documents']; att=data['source_attachments']
        need(len(src)==1 and src[0]['id']==e['source_document_id'] and len(att)==1 and all(att[0][k]==v for k,v in {'id':e['attachment_id'],'source_document_id':e['source_document_id'],'storage_key':e['storage_key'],'sha256':e['sha256'],'byte_size':e['bytes']}.items()),'structured snapshot identity mismatch')
        q=data['questions']; need(isinstance(q,list) and all(x['source_document_id']==e['source_document_id'] for x in q),'structured snapshot source mismatch'); questions+=len(q)
    need(questions==m['question_count'],'structured snapshot question count mismatch')
    if rows is not None: check_rows(m,rows)
    return m


def capture(root,archive,pin,rows):
    root=safe(root); archive=safe(archive)
    need(root.is_dir() and root.name==NAME and not archive.exists(),'invalid corpus capture destination/source')
    raw=regular(root/'manifest.json').read_bytes(); m,expected=parse(raw,pin); check_rows(m,rows)
    allowed=set(expected)|{'manifest.json'}; paths={}; dirs=[]
    for p in root.rglob('*'):
        safe(p); n=p.relative_to(root).as_posix()
        if p.is_dir(): dirs.append((n,p))
        else: paths[n]=regular(p)
    need(set(paths)==allowed,'unexpected or missing corpus tree files')
    try:
        with tarfile.open(archive,'x:gz') as t:
            for n,p in sorted(dirs): t.add(p,arcname=n,recursive=False)
            for n,p in sorted(paths.items()): t.add(p,arcname=n,recursive=False)
        validate_archive(archive,pin,rows)
        need(regular(root/'manifest.json').read_bytes()==raw,'corpus manifest changed during capture')
        for n,p in paths.items():
            with regular(p).open('rb') as f: actual=digest(f)
            size,sha=expected.get(n,(len(raw),pin)); need(actual[1]==sha and (size is None or size==actual[0]),'corpus source changed during capture')
    except BaseException:
        archive.unlink(missing_ok=True); raise


def mount_check(raw,root,mode):
    root=safe(root); need(root.is_dir() and root.name==NAME,'missing corpus directory')
    mounts=json.loads(raw); need(isinstance(mounts,list),'invalid mount data')
    selected=[m for m in mounts if m.get('Destination')==DEST]
    need(not any(str(m.get('Destination','')).startswith(DEST+'/') for m in mounts),'nested corpus mount')
    if mode=='staged': need(not selected,'unexpected inactive corpus mount'); return
    need(mode=='active' and len(selected)==1 and selected[0].get('Type')=='bind' and selected[0].get('RW') is False and selected[0].get('Source')==str(root),'corpus bind mount mismatch')


def restore(bundle,dest):
    # Deliberately independent file-only restore; does not restore PostgreSQL or touch runtime paths.
    import web_artifact_provenance as w
    bundle=safe(bundle); dest=safe(dest); parent=dest.parent
    need(not dest.exists() and parent.is_dir() and parent.stat().st_uid==os.getuid() and stat.S_IMODE(parent.stat().st_mode)==0o700,'private empty restore destination required')
    need(not {'production','development','pageboy-home','apps','repo'}.intersection(dest.parts) and not dest.is_relative_to(bundle),'non-isolated restore destination')
    m=w.validate_bundle(bundle); need(m.get('artifact_format')=='3','snapshot has no historical corpus archive')
    pin=m['exam_bank_manifest_sha256']; stage=Path(tempfile.mkdtemp(prefix='.exam-bank-restore-',dir=parent))
    try:
        with tarfile.open(bundle/ARCHIVE,'r:gz') as t:
            for member in t:
                n=member.name; rel=PurePosixPath(n)
                need(n==str(rel) and not rel.is_absolute() and ".." not in rel.parts and "\\" not in n and (member.isfile() or member.isdir()), "unsafe restore member")
                target=stage/n
                if member.isdir(): target.mkdir(mode=0o700,parents=True,exist_ok=True)
                else:
                    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                    with t.extractfile(member) as src, target.open('xb') as dst: shutil.copyfileobj(src,dst)
                    target.chmod(0o600)
        manifest,expected=parse((stage/'manifest.json').read_bytes(),pin)
        for name,(size,sha) in expected.items():
            with regular(stage/name).open('rb') as f: n,h=digest(f)
            need(h==sha and (size is None or n==size),'restored corpus content mismatch')
        need(w.validate_bundle(bundle)==m,'bundle changed during restore')
        need(not dest.exists(),'restore destination appeared'); stage.rename(dest)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    print('EXAM_BANK_RESTORE_OK='+pin)


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    for cmd,args in [('capture',('root','archive','pin')),('verify',('archive','pin')),('mount',('raw','root','mode')),('restore',('bundle','dest'))]:
        s=sub.add_parser(cmd)
        for a in args:s.add_argument(a)
    a=p.parse_args()
    try:
        if a.cmd=='capture': capture(Path(a.root),Path(a.archive),a.pin,json.load(sys.stdin))
        elif a.cmd=='verify': validate_archive(Path(a.archive),a.pin,json.load(sys.stdin)); print('EXAM_BANK_REFS_OK')
        elif a.cmd=='mount': mount_check(a.raw,Path(a.root),a.mode)
        else: restore(Path(a.bundle),Path(a.dest))
    except (ValueError,OSError,KeyError,TypeError,AttributeError,tarfile.TarError) as e:
        print('EXAM_BANK_BLOCKED: '+str(e),file=sys.stderr); return 2
    return 0

if __name__=='__main__': sys.exit(main())
