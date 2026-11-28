#!/usr/bin/env python3
"""Fail closed on non-root image migration visibility; no DB, mounts or network."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PREFIX = 'services/api/'
PROBE = r"""import hashlib, json, os
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
root=Path('/app')
paths=[root/'alembic.ini',root/'alembic/env.py',*sorted((root/'alembic/versions').glob('*.py'))]
s=ScriptDirectory.from_config(Config('/app/alembic.ini'))
report={'uid':os.getuid(),'gid':os.getgid(),'heads':s.get_heads(),'revisions':sorted(r.revision for r in s.walk_revisions()),'files':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
print(json.dumps(report,sort_keys=True))
"""


def expected_files(repo):
    def git(*args):
        return subprocess.check_output(['git','-C',str(repo),*args],timeout=60)
    paths=git('ls-tree','-r','--name-only','HEAD','--',PREFIX+'alembic.ini',PREFIX+'alembic/env.py',PREFIX+'alembic/versions').decode().splitlines()
    paths=[p for p in paths if p.endswith(('.py','.ini'))]
    files={p[len(PREFIX):]:hashlib.sha256(git('show','HEAD:'+p)).hexdigest() for p in paths}
    if not {'alembic.ini','alembic/env.py'} <= files.keys() or not any(p.startswith('alembic/versions/') for p in files):
        raise ValueError('missing committed migration files')
    return files


def validate(report, files, uidgid):
    uid,gid=map(int,uidgid.split(':'))
    revs=report['revisions']; heads=report['heads']
    count=sum(p.startswith('alembic/versions/') and not p.endswith('/__init__.py') for p in files)
    if (uid<=0 or gid<=0 or (report['uid'],report['gid'])!=(uid,gid) or report['files']!=files
            or len(heads)!=1 or heads[0] not in revs or len(revs)!=count or len(set(revs))!=count
            or not {'0022','0023'} <= set(revs)):
        raise ValueError('non-root migration source or graph mismatch')
    return count


def check(repo,image,uidgid):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',image) or not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*',uidgid):
        raise ValueError('require immutable image ID and non-root numeric UID:GID')
    revision=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True,timeout=30).strip()
    label=subprocess.check_output(['docker','image','inspect','--format','{{index .Config.Labels "org.opencontainers.image.revision"}}',image],text=True,timeout=30).strip()
    if revision!=label: raise ValueError('image revision does not match committed source')
    files=expected_files(repo)
    raw=subprocess.check_output(['docker','run','--rm','--pull=never','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user',uidgid,'--env','SHUTONG_ENV=prod','--entrypoint','python',image,'-B','-c',PROBE],timeout=120,stderr=subprocess.PIPE)
    count=validate(json.loads(raw),files,uidgid)
    print('API_IMAGE_NONROOT_MIGRATION_GRAPH_OK uidgid='+uidgid+' revisions='+str(count),flush=True)


if __name__=='__main__':
    try:
        if len(sys.argv)!=4: raise ValueError('usage: check_api_image_migrations.py REPO IMAGE_ID UID:GID')
        check(Path(sys.argv[1]),sys.argv[2],sys.argv[3])
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as e:
        print('REFUSED: non-root API migration image check: '+type(e).__name__,file=sys.stderr)
        sys.exit(1)
