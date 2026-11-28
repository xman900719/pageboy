#!/usr/bin/env python3
"""ST-024-C5: build-bound Web provenance, verified bundle, isolated extraction."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone

UNKNOWN = 'UNVERIFIED'
BASE_FILES = {'postgres.dump', 'attachments.tar.gz'}
WEB_KEYS = {'web_source_git_sha', 'web_tree_sha256', 'web_file_count'}
API_KEYS = {'api_git_sha', 'api_image_id'}
BASE_KEYS = {'timestamp_utc', 'app_revision', 'migration_revision', 'attachments_included', 'attachment_count'}


def need(ok, msg):
    if not ok:
        raise ValueError('REFUSED: ' + msg)


def safe(path):
    p = Path(os.path.abspath(path))
    need('..' not in Path(path).parts, 'parent traversal')
    for q in (p, *p.parents):
        need(not q.is_symlink(), 'symlink path')
    return p


def regular(path):
    p = safe(path)
    need(p.is_file() and p.stat().st_nlink == 1, 'not a single-link regular file')
    return p


def sha(path):
    with regular(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def name_ok(name):
    p = PurePosixPath(name)
    need(bool(p.parts) and not p.is_absolute() and '..' not in p.parts and str(p) == name
         and '\\' not in name and not any(ord(c) < 32 or ord(c) == 127 for c in name), 'unsafe archive path')
    return name


def files(root):
    root = safe(root)
    need(root.is_dir(), 'missing Web directory')
    result = []
    for base, dirs, names in os.walk(root, followlinks=False):
        for n in dirs:
            p = Path(base)/n
            need(not p.is_symlink() and p.is_dir(), 'unsafe directory')
        for n in names:
            p = regular(Path(base)/n)
            result.append((name_ok(p.relative_to(root).as_posix()), p))
    return sorted(result)


def tree(root):
    rows = files(root)
    names = {n for n, _ in rows}
    need({'index.html', 'admin.html'} <= names and any(n.startswith('assets/') for n in names), 'incomplete Web build')
    h = hashlib.sha256()
    for n, p in rows:
        h.update(n.encode() + b'\0' + sha(p).encode() + b'\n')
    return h.hexdigest(), len(rows)


def git(repo, *args):
    return subprocess.check_output(['git','-C',str(repo),*args], text=True).strip()


def source_sha(repo):
    need(not git(repo, 'status', '--porcelain', '--untracked-files=all'), 'dirty source tree')
    revision = git(repo, 'rev-parse', 'HEAD')
    need(re.fullmatch('[0-9a-f]{40}', revision), 'invalid Git SHA')
    return revision


def extract_committed_archive(archive, dest):
    """Extract trusted Git source into an empty private build root, independent of umask."""
    dest = safe(dest)
    need(dest.is_dir() and not any(dest.iterdir()), 'nonempty source destination')
    need(stat.S_IMODE(dest.stat().st_mode) & 0o077 == 0, 'source destination must be private')
    members = archive.getmembers()
    names = set()
    for m in members:
        name = name_ok(m.name)
        need(name not in names and (m.isfile() or m.isdir()), 'source contains duplicate/link/special entry')
        names.add(name)
    archive.extractall(dest, members=members, filter='data')
    # data filter intentionally discards directory modes; normalize only exported descendants.
    for base, dirs, files_ in os.walk(dest):
        for n in dirs:
            p = Path(base)/n
            need(not p.is_symlink() and p.is_dir(), 'unsafe source directory')
            p.chmod(0o755)
    for m in members:
        if m.isfile():
            regular(dest/m.name).chmod(0o755 if m.mode & 0o111 else 0o644)


def export_source(repo, revision, dest):
    need(source_sha(repo) == revision, 'source SHA mismatch')
    # git archive exports only committed files; no ignored .env, node_modules or dist.
    with tempfile.TemporaryFile() as f:
        subprocess.run(['git','-C',str(repo),'archive','--format=tar',revision], stdout=f, check=True)
        f.seek(0)
        with tarfile.open(fileobj=f, mode='r:') as t:
            extract_committed_archive(t, dest)


def build_web(repo, state):
    repo, state = safe(repo), safe(state)
    revision = source_sha(repo)
    dist = safe(repo/'apps/web/dist')
    record = safe(state/'web-provenance.json')
    need(state.is_dir(), 'missing state directory')
    need(not dist.exists() or dist.is_dir(), 'invalid live Web dir')
    # Existing build is left untouched until the new clean build is complete.
    with tempfile.TemporaryDirectory(prefix='.c5-web-', dir=state) as d:
        work = Path(d); src = work/'source'; src.mkdir(mode=0o700)
        export_source(repo, revision, src)
        home = work/'home'; home.mkdir()
        env = {'PATH':os.environ.get('PATH',os.defpath),'HOME':str(home),'LANG':'C.UTF-8',
               'NPM_CONFIG_USERCONFIG':str(home/'user.npmrc'),'NPM_CONFIG_GLOBALCONFIG':str(home/'global.npmrc')}
        for n in ('user.npmrc','global.npmrc'): (home/n).touch()
        web = src/'apps/web'
        subprocess.run(['npm','ci','--no-audit','--no-fund'],cwd=web,env=env,check=True)
        subprocess.run(['npm','run','build'],cwd=web,env=env,check=True)
        built = web/'dist'; digest,count = tree(built)
        need(source_sha(repo) == revision, 'source changed during build')
        value = {'format':1,'source_git_sha':revision,'tree_sha256':digest,'file_count':count,
                 'built_at_utc':datetime.now(timezone.utc).isoformat()}
        with tempfile.NamedTemporaryFile(mode='w',dir=state,delete=False) as f:
            json.dump(value,f,sort_keys=True); f.write('\n'); tmp = Path(f.name)
        previous = work/'previous'
        try:
            if dist.exists(): dist.rename(previous)
            try:
                built.rename(dist)
                need(tree(dist)==(digest,count), 'published Web mismatch')
                os.replace(tmp,record)
            except BaseException:
                if dist.exists(): dist.rename(work/'failed')
                if previous.exists(): previous.rename(dist)
                raise
        finally:
            tmp.unlink(missing_ok=True)
    print('WEB_BUILD_PROVENANCE_OK')


def archive_tree(dist, record, archive):
    dist, record, archive = safe(dist), safe(record), safe(archive)
    need(not archive.exists(), 'archive exists')
    digest,count = tree(dist)
    revision = UNKNOWN
    if record.exists():
        r = json.loads(regular(record).read_text())
        need(set(r)=={'format','source_git_sha','tree_sha256','file_count','built_at_utc'} and r['format']==1,
             'invalid Web record')
        need(re.fullmatch('[0-9a-f]{40}',r['source_git_sha']) and (r['tree_sha256'],r['file_count'])==(digest,count), 'Web record mismatch')
        revision = r['source_git_sha']
    with tarfile.open(archive,'x:gz') as t:
        for n,p in files(dist):
            info = tarfile.TarInfo(n); info.size = p.stat().st_size; info.mode = 0o644
            with p.open('rb') as f: t.addfile(info,f)
    need(tree(dist)==(digest,count) and archive_digest(archive)==(digest,count), 'Web changed during capture')
    return {'web_source_git_sha':revision,'web_tree_sha256':digest,'web_file_count':str(count)}


def archive_digest(archive, destination=None):
    entries = {}; dirs = set()
    with tarfile.open(regular(archive),'r:gz') as t:
        for m in t:
            n = name_ok(m.name)
            need(n not in entries and n not in dirs and (m.isfile() or m.isdir()), 'duplicate/link/special archive entry')
            if m.isdir(): dirs.add(n); continue
            need(m.size >= 0, 'invalid size')
            h = hashlib.sha256()
            if destination is not None:
                out = destination/n; out.parent.mkdir(parents=True,exist_ok=True)
                f = out.open('xb')
            else: f = None
            try:
                with t.extractfile(m) as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):
                        h.update(chunk)
                        if f: f.write(chunk)
            finally:
                if f: f.close()
            entries[n] = h.hexdigest()
    for n in entries.keys() | dirs:
        need(not any(str(p) in entries for p in PurePosixPath(n).parents), 'file as parent')
    need({'index.html','admin.html'} <= entries.keys() and any(n.startswith('assets/') for n in entries), 'incomplete Web archive')
    h=hashlib.sha256()
    for n,d in sorted(entries.items()): h.update(n.encode()+b'\0'+d.encode()+b'\n')
    return h.hexdigest(),len(entries)


def api_identity(tag, deployed, config_image, running_id, tagged_id, label):
    need(re.fullmatch(r'[A-Za-z0-9_.-]+',tag) and tag not in ('dev','unknown'), 'invalid API tag')
    need(deployed==tag and config_image=='shutong-api:'+tag and running_id==tagged_id and re.fullmatch('sha256:[0-9a-f]{64}',running_id), 'API tag/image mismatch')
    if label in ('','<no value>',UNKNOWN): revision=UNKNOWN
    else:
        need(re.fullmatch('[0-9a-f]{40}',label) and re.fullmatch('api-[0-9a-f]{7,40}',tag) and label.startswith(tag[4:]), 'API source label mismatch')
        revision=label
    return {'api_git_sha':revision,'api_image_id':running_id}


def validate_attachments(archive, expected_count):
    """Accept GNU tar -C DIR . and canonical relative names; never extract."""
    entries = {}
    with tarfile.open(regular(archive), 'r:gz') as t:
        for m in t:
            name = m.name
            if name == '.':
                need(m.isdir() and '' not in entries, 'invalid attachment root')
                entries[''] = False
                continue
            if name.startswith('./'):
                name = name[2:]
            name_ok(name)
            need(name not in entries and (m.isfile() or m.isdir()), 'duplicate/link/special attachment entry')
            entries[name] = m.isfile()
    for name in entries:
        need(not any(entries.get(str(p), False) for p in PurePosixPath(name).parents), 'attachment file as parent')
    need(sum(entries.values()) == expected_count, 'attachment count mismatch')


def verify_attachment_refs(archive, refs):
    """Verify each DB file reference against bytes in the captured tar, without extraction."""
    need(isinstance(refs, list), 'invalid attachment references')
    expected = {}
    for row in refs:
        need(isinstance(row, list) and len(row) == 4, 'invalid attachment reference')
        key, digest, size, rel = row
        need(isinstance(key, str) and re.fullmatch('[0-9a-f]{32}', key)
             and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest)
             and type(size) is int and size >= 0 and (rel is None or isinstance(rel, str)), 'invalid attachment metadata')
        if rel and rel.strip():
            name = 'school-exams/' + name_ok(rel.strip())
        else:
            name = key
        need(name not in expected or expected[name] == (digest, size), 'conflicting attachment references')
        expected[name] = (digest, size)
    found = set()
    with tarfile.open(regular(archive), 'r:gz') as t:
        for m in t:
            name = m.name[2:] if m.name.startswith('./') else m.name
            if name not in expected:
                continue
            need(m.isfile() and name not in found, 'invalid referenced attachment entry')
            h = hashlib.sha256()
            with t.extractfile(m) as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(chunk)
            need((h.hexdigest(), m.size) == expected[name], 'referenced attachment content mismatch')
            found.add(name)
    need(found == set(expected), 'referenced attachment missing from archive')
    return len(refs)


def verify_mount(raw, directory):
    mounts = json.loads(raw)
    need(isinstance(mounts, list), 'invalid container mounts')
    matches = [m for m in mounts if m.get('Destination') == '/var/lib/shutong/attachments']
    need(len(matches) == 1 and matches[0].get('Type') == 'bind', 'attachment bind mount missing or ambiguous')
    need(not any(str(m.get('Destination', '')).startswith('/var/lib/shutong/attachments/') for m in mounts), 'nested attachment mount escapes backup root')
    source = matches[0].get('Source', '')
    need(isinstance(source, str) and os.path.isabs(source) and os.path.realpath(source) == os.path.realpath(directory), 'attachment mount differs from backup root')


def manifest(path):
    result={}
    for line in regular(path).read_text().splitlines():
        k,sep,v=line.partition('='); need(sep and k not in result and v, 'bad manifest'); result[k]=v
    return result


def validate_bundle(root):
    root=safe(root); need(root.is_dir(),'missing backup directory')
    m=manifest(root/'manifest.txt')
    need(BASE_KEYS <= m.keys() and m['attachments_included']=='yes' and re.fullmatch('[0-9]+',m['attachment_count']), 'invalid base manifest')
    modern = 'artifact_format' in m
    if modern:
        v3 = m['artifact_format']=='3'
        extra = {'exam_bank_manifest_sha256'} if v3 else set()
        need(m['artifact_format'] in ('2','3') and set(m)==BASE_KEYS|WEB_KEYS|API_KEYS|{'artifact_format'}|extra, 'invalid modern manifest')
        need(m['web_source_git_sha']==UNKNOWN or re.fullmatch('[0-9a-f]{40}',m['web_source_git_sha']), 'invalid Web source')
        need(m['api_git_sha']==UNKNOWN or re.fullmatch('[0-9a-f]{40}',m['api_git_sha']), 'invalid API source')
        need(m['api_image_id']==UNKNOWN or re.fullmatch('sha256:[0-9a-f]{64}',m['api_image_id']), 'invalid image ID')
        if m['api_git_sha']!=UNKNOWN:
            need(m['api_image_id']!=UNKNOWN and re.fullmatch('api-[0-9a-f]{7,40}',m['app_revision']) and m['api_git_sha'].startswith(m['app_revision'][4:]), 'inconsistent API identity')
        expected=BASE_FILES|{'manifest.txt','web-dist.tar.gz'}
        if v3: expected=expected|{'exam-bank.tar.gz'}
    else:
        need(set(m)==BASE_KEYS and not (root/'web-dist.tar.gz').exists(), 'partial legacy manifest')
        expected=BASE_FILES
    sums={}
    for line in regular(root/'SHA256SUMS').read_text().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  ([a-zA-Z0-9_.-]+)',line)
        need(match and match[2] not in sums,'invalid checksum line'); sums[match[2]]=match[1]
    need(set(sums)==expected,'incomplete checksum list')
    need({p.name for p in root.iterdir()} == expected|{'manifest.txt','SHA256SUMS'},'unexpected bundle entries')
    for n,d in sums.items(): need(sha(root/n)==d,'checksum mismatch: '+n)
    validate_attachments(root/'attachments.tar.gz', int(m['attachment_count']))
    if modern:
        need(re.fullmatch('[0-9a-f]{64}',m['web_tree_sha256']) and re.fullmatch('[1-9][0-9]*',m['web_file_count']), 'invalid Web tree metadata')
        need(archive_digest(root/'web-dist.tar.gz')==(m['web_tree_sha256'],int(m['web_file_count'])),'archive tree mismatch')
    if modern and v3:
        from exam_bank_backup import validate_archive
        validate_archive(root/'exam-bank.tar.gz',m['exam_bank_manifest_sha256'])
    return m


def restore_web(root,dest):
    m=validate_bundle(root)
    need(m.get('artifact_format') in ('2','3'),'legacy snapshot has no Web artifact (UNVERIFIED)')
    dest=safe(dest); need(not dest.exists() or (dest.is_dir() and not any(dest.iterdir())), 'restore destination must be empty')
    # Only private, current-user-owned parent, never the live dist or production path.
    parent=dest.parent; need(parent.is_dir() and parent.stat().st_uid==os.getuid() and stat.S_IMODE(parent.stat().st_mode)==0o700,'private 0700 parent required')
    need('production' not in dest.parts and 'apps' not in dest.parts and dest!=safe(root) and not dest.is_relative_to(safe(root)), 'non-isolated Web destination')
    staging=Path(tempfile.mkdtemp(prefix='.web-restore-',dir=parent))
    try:
        expected=(m['web_tree_sha256'],int(m['web_file_count']))
        need(archive_digest(Path(root)/'web-dist.tar.gz',staging)==expected and tree(staging)==expected,'restored tree mismatch')
        if dest.exists(): dest.rmdir()
        staging.rename(dest)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    print('WEB_RESTORE_OK; SOURCE='+m['web_source_git_sha'])
    return m


def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
    for cmd,args in [('build',('repo','state')),('export',('repo','revision','dest')),('archive',('dist','record','archive')),('restore',('root','dest')),('verify',('root',)),('refs',('archive',)),('api',('tag','deployed','config_image','running_id','tagged_id','label')),('mount',('raw','directory'))]:
        sub=s.add_parser(cmd)
        for arg in args: sub.add_argument(arg)
    a=p.parse_args(); d=vars(a); cmd=d.pop('cmd')
    try:
        if cmd=='build': build_web(Path(a.repo),Path(a.state)); return
        if cmd=='export': export_source(Path(a.repo),a.revision,Path(a.dest)); return
        if cmd=='archive': result=archive_tree(Path(a.dist),Path(a.record),Path(a.archive))
        elif cmd=='restore': restore_web(Path(a.root),Path(a.dest)); return
        elif cmd=='verify': validate_bundle(Path(a.root)); print('BUNDLE_CHECK_OK'); return
        elif cmd=='refs':
            import sys
            print('ATTACHMENT_REFS_OK='+str(verify_attachment_refs(Path(a.archive),json.load(sys.stdin)))); return
        elif cmd=='mount': verify_mount(a.raw,a.directory); return
        else: result=api_identity(**d)
        for k,v in result.items(): print(f'{k}={v}')
    except (OSError,ValueError,TypeError,tarfile.TarError,subprocess.SubprocessError) as e:
        raise SystemExit(str(e))

if __name__=='__main__': main()
